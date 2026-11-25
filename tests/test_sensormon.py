"""Unit test SensorMon (hanya standard library: unittest).

Jalankan dari folder project:
    python -m unittest discover -s tests -v
"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from sensormon.cli import EXIT_DATA_ERROR, EXIT_INPUT_ERROR, EXIT_OK, main
from sensormon.exceptions import (
    DataFileError,
    InvalidFormatError,
    InvalidInputError,
    InvalidRecordError,
)
from sensormon.io_handler import load_readings, write_csv_file, write_json_file
from sensormon.models import is_blank, parse_reading
from sensormon.processing import (
    calculate_stats,
    classify_readings,
    count_by_status,
    determine_status,
    filter_readings,
    find_first_by_status,
    group_by,
    remove_duplicates,
    run_pipeline,
    validate_thresholds,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def make_raw(**overrides):
    """Buat raw record valid; kolom tertentu dapat ditimpa."""
    raw = {
        "timestamp": "2026-11-18 10:00:00",
        "sensor_id": "S01",
        "location": "Ruang Server Utama",
        "temperature": "24.5",
        "humidity": "45.0",
    }
    raw.update(overrides)
    return raw


class TestModels(unittest.TestCase):
    """Validasi dan normalisasi satu record."""

    def test_valid_record_is_normalized(self):
        record = parse_reading(make_raw(sensor_id="  s01 ", location=" Ruang   Server "))
        self.assertEqual(record["sensor_id"], "S01")
        self.assertEqual(record["location"], "Ruang Server")
        self.assertEqual(record["temperature"], 24.5)

    def test_decimal_comma_is_accepted(self):
        self.assertEqual(parse_reading(make_raw(temperature="25,1"))["temperature"], 25.1)

    def test_zero_is_not_blank(self):
        # 0 bernilai falsy, tetapi tetap data sah (bukan kolom kosong).
        self.assertFalse(is_blank(0))
        self.assertEqual(parse_reading(make_raw(temperature=0))["temperature"], 0.0)

    def test_invalid_values_raise(self):
        invalid_cases = {
            "kosong": make_raw(humidity=""),
            "bukan angka": make_raw(temperature="ERR"),
            "nan": make_raw(temperature="nan"),
            "di luar rentang": make_raw(temperature="125"),
            "timestamp salah": make_raw(timestamp="2026-11-18 25:00:00"),
            "kolom hilang": {"timestamp": "2026-11-18 10:00:00"},
        }
        for label, raw in invalid_cases.items():
            with self.subTest(kasus=label), self.assertRaises(InvalidRecordError):
                parse_reading(raw)


class TestProcessing(unittest.TestCase):
    """Logika bisnis: dedup, status, filter, rekap."""

    def setUp(self):
        self.records = [
            parse_reading(make_raw(timestamp="2026-11-18 10:00:00", temperature="24")),
            parse_reading(make_raw(timestamp="2026-11-18 11:00:00", temperature="33")),
            parse_reading(make_raw(timestamp="2026-11-18 11:00:00", sensor_id="s01")),
            parse_reading(make_raw(sensor_id="S02", location="Lab Jaringan", temperature="27.5")),
        ]

    def test_remove_duplicates_keeps_first_and_order(self):
        unique, duplicates = remove_duplicates(self.records)
        self.assertEqual(len(unique), 3)
        self.assertEqual(len(duplicates), 1)
        self.assertEqual(unique[1]["temperature"], 33.0)

    def test_status_boundaries(self):
        cases = [
            (26.9, 50, "NORMAL"), (27.0, 50, "WASPADA"), (31.9, 50, "WASPADA"),
            (32.0, 50, "KRITIS"), (25, 20.0, "NORMAL"), (25, 80.0, "NORMAL"),
            (25, 19.9, "WASPADA"), (25, 80.1, "WASPADA"),
        ]
        for temperature, humidity, expected in cases:
            with self.subTest(suhu=temperature, rh=humidity):
                self.assertEqual(determine_status(temperature, humidity), expected)

    def test_classify_does_not_mutate_input(self):
        classified = classify_readings(self.records)
        self.assertNotIn("status", self.records[0])
        self.assertEqual(classified[1]["status"], "KRITIS")

    def test_filter_and_search(self):
        classified = classify_readings(remove_duplicates(self.records)[0])
        self.assertEqual(len(filter_readings(classified, sensor_id=" s02 ")), 1)
        self.assertEqual(len(filter_readings(classified, location="server", status="kritis")), 1)
        self.assertEqual(filter_readings(classified, sensor_id="S99"), [])

    def test_group_and_count(self):
        classified = classify_readings(remove_duplicates(self.records)[0])
        self.assertEqual(list(group_by(classified, "sensor_id")), ["S01", "S02"])
        self.assertEqual(count_by_status(classified), {"NORMAL": 1, "WASPADA": 1, "KRITIS": 1})
        self.assertEqual(count_by_status([]), {"NORMAL": 0, "WASPADA": 0, "KRITIS": 0})

    def test_stats_empty_returns_none(self):
        self.assertIsNone(calculate_stats([]))
        self.assertEqual(calculate_stats([20, 30])["avg"], 25.0)

    def test_find_first_by_status(self):
        classified = classify_readings(self.records)
        self.assertEqual(find_first_by_status(classified, "KRITIS")["timestamp"],
                         "2026-11-18 11:00:00")
        self.assertIsNone(find_first_by_status(classified[:1], "KRITIS"))

    def test_invalid_thresholds(self):
        with self.assertRaises(InvalidInputError):
            validate_thresholds(35, 30)
        with self.assertRaises(InvalidInputError):
            validate_thresholds(27, 500)

    def test_pipeline_on_empty_input(self):
        result = run_pipeline([])
        self.assertEqual(result["clean"], [])
        self.assertIsNone(result["summary"]["overall"]["temperature"])


class TestFileHandling(unittest.TestCase):
    """Baca/tulis CSV & JSON beserta kondisi error file."""

    def test_sample_csv_numbers_are_correct(self):
        result = run_pipeline(load_readings(DATA_DIR / "sensor_readings.csv"))
        quality = result["summary"]["data_quality"]
        self.assertEqual(
            (quality["raw_records"], quality["rejected_records"],
             quality["duplicates_removed"], quality["clean_records"]),
            (106, 7, 3, 96),
        )
        self.assertEqual(result["summary"]["overall"]["status_count"],
                         {"NORMAL": 84, "WASPADA": 10, "KRITIS": 2})

    def test_sample_json_is_supported(self):
        result = run_pipeline(load_readings(DATA_DIR / "sensor_readings.json"))
        self.assertEqual(len(result["clean"]), 24)
        self.assertEqual(len(result["rejected"]), 2)

    def test_excel_bom_csv_is_read(self):
        self.assertEqual(len(load_readings(DATA_DIR / "edge_bom_excel.csv")), 8)

    def test_file_errors(self):
        cases = {
            "tidak ada": (DATA_DIR / "tidak_ada.csv", DataFileError),
            "kolom hilang": (DATA_DIR / "edge_missing_column.csv", InvalidFormatError),
            "json rusak": (DATA_DIR / "edge_broken.json", InvalidFormatError),
            "ekstensi": (DATA_DIR / "catatan.txt", InvalidFormatError),
        }
        for label, (path, error) in cases.items():
            with self.subTest(kasus=label), self.assertRaises(error):
                load_readings(path)

    def test_write_then_read_roundtrip(self):
        rows = [parse_reading(make_raw())]
        with tempfile.TemporaryDirectory() as folder:
            csv_path = write_csv_file(Path(folder) / "a" / "out.csv", rows, tuple(rows[0]))
            json_path = write_json_file(Path(folder) / "out.json", rows)
            self.assertEqual(parse_reading(load_readings(csv_path)[0]), rows[0])
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8")), rows)


class TestCommandLine(unittest.TestCase):
    """Exit code dan file keluaran dari antarmuka CLI."""

    def run_cli(self, *argv):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_report_writes_all_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            code, out, _ = self.run_cli("report", "-i", str(DATA_DIR / "sensor_readings.csv"),
                                        "-o", folder)
            self.assertEqual(code, EXIT_OK)
            self.assertIn("Record bersih     : 96", out)
            for name in ("clean_readings.csv", "alerts.csv", "rejected_rows.csv",
                         "summary.json", "sensormon.log"):
                self.assertTrue((Path(folder) / name).is_file(), name)

    def test_error_exit_codes(self):
        with tempfile.TemporaryDirectory() as folder:
            code, _, err = self.run_cli("report", "-i", "tidak_ada.csv", "-o", folder)
            self.assertEqual(code, EXIT_DATA_ERROR)
            self.assertIn("file tidak ditemukan", err)

            code, _, err = self.run_cli("report", "--warning", "35", "--critical", "30",
                                        "-o", folder)
            self.assertEqual(code, EXIT_INPUT_ERROR)

            code, _, err = self.run_cli("search", "--start", "2026-13-01", "-o", folder)
            self.assertEqual(code, EXIT_INPUT_ERROR)


if __name__ == "__main__":
    unittest.main()
