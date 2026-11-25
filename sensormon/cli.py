"""Lapisan antarmuka pengguna (command line interface).

Module ini menerima input pengguna (argumen CLI atau menu interaktif),
memvalidasinya, memanggil fungsi dari ``io_handler`` dan ``processing``,
lalu menampilkan hasil dengan bantuan ``report``. Semua exception yang dapat
diprediksi ditangkap di fungsi ``main`` dan diubah menjadi pesan yang ramah
serta *exit code* yang konsisten.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .config import (
    CLEAN_FIELDS,
    DATE_FORMAT,
    DEFAULT_CRITICAL_TEMP,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_WARNING_TEMP,
    LOG_FILENAME,
    REJECTED_FIELDS,
    STATUSES,
    TIMESTAMP_FORMAT,
)
from .exceptions import DataFileError, InvalidFormatError, InvalidInputError
from .io_handler import load_readings, write_csv_file, write_json_file
from .logger import close_logging, setup_logging
from .processing import filter_readings, run_pipeline, validate_thresholds
from .report import format_rejected, format_summary, format_table

logger = logging.getLogger(__name__)

DEFAULT_INPUT = "data/sensor_readings.csv"

EXIT_OK = 0
EXIT_DATA_ERROR = 1
EXIT_INPUT_ERROR = 2
EXIT_UNEXPECTED = 3
EXIT_INTERRUPTED = 130


# ---------------------------------------------------------------------------
# Validasi input pengguna
# ---------------------------------------------------------------------------
def positive_int(text: str) -> int:
    """Tipe argparse: bilangan bulat > 0.

    Args:
        text: Teks dari command line.

    Returns:
        Bilangan bulat positif.

    Raises:
        argparse.ArgumentTypeError: Jika bukan bilangan bulat positif.
    """
    try:
        number = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"'{text}' bukan bilangan bulat") from error
    if number <= 0:
        raise argparse.ArgumentTypeError("nilai harus lebih besar dari 0")
    return number


def parse_user_datetime(text: str | None, *, end_of_day: bool = False) -> datetime | None:
    """Ubah input tanggal pengguna menjadi ``datetime``.

    Menerima ``YYYY-MM-DD`` atau ``YYYY-MM-DD HH:MM:SS``. Jika hanya tanggal
    dan ``end_of_day`` True, jam diisi 23:59:59 agar seluruh hari ikut.

    Args:
        text: Teks tanggal, atau ``None``/kosong bila tidak dipakai.
        end_of_day: Pakai akhir hari untuk input tanpa jam.

    Returns:
        Objek ``datetime`` atau ``None``.

    Raises:
        InvalidInputError: Jika format tanggal salah.
    """
    if text is None or not text.strip():
        return None

    cleaned = text.strip()
    for pattern in (TIMESTAMP_FORMAT, DATE_FORMAT):
        try:
            moment = datetime.strptime(cleaned, pattern)
        except ValueError:
            continue
        if pattern == DATE_FORMAT and end_of_day:
            moment = moment.replace(hour=23, minute=59, second=59)
        return moment

    raise InvalidInputError(
        f"tanggal '{text}' tidak valid; gunakan YYYY-MM-DD atau 'YYYY-MM-DD HH:MM:SS'"
    )


def build_criteria(args: argparse.Namespace) -> dict:
    """Bentuk dict kriteria filter dari argumen ``search``.

    Args:
        args: Hasil ``parse_args``.

    Returns:
        Dict kriteria untuk ``processing.filter_readings``.

    Raises:
        InvalidInputError: Jika rentang tanggal terbalik.
    """
    start = parse_user_datetime(args.start)
    end = parse_user_datetime(args.end, end_of_day=True)
    if start and end and start > end:
        raise InvalidInputError("tanggal --start tidak boleh setelah --end")
    return {
        "sensor_id": args.sensor.strip().upper() if args.sensor else None,
        "location": args.location.strip() if args.location else None,
        "status": args.status,
        "start": start,
        "end": end,
    }


# ---------------------------------------------------------------------------
# Penyimpanan hasil
# ---------------------------------------------------------------------------
def save_outputs(result: dict, output_dir: str | Path) -> list[Path]:
    """Simpan seluruh hasil pipeline ke folder keluaran.

    Args:
        result: Hasil ``processing.run_pipeline``.
        output_dir: Folder tujuan.

    Returns:
        Daftar path file yang ditulis.
    """
    folder = Path(output_dir)
    return [
        write_csv_file(folder / "clean_readings.csv", result["clean"], CLEAN_FIELDS),
        write_csv_file(folder / "alerts.csv", result["alerts"], CLEAN_FIELDS),
        write_csv_file(folder / "rejected_rows.csv", result["rejected"], REJECTED_FIELDS),
        write_json_file(folder / "summary.json", result["summary"]),
    ]


EXPORT_SUFFIXES = (".csv", ".json")


def validate_export_path(path: str | None) -> None:
    """Pastikan file ``--export`` (bila diisi) berakhiran .csv atau .json.

    Args:
        path: Nilai argumen ``--export`` atau ``None``.

    Raises:
        InvalidInputError: Jika ekstensi tidak didukung.
    """
    if path is not None and Path(path).suffix.lower() not in EXPORT_SUFFIXES:
        raise InvalidInputError("file --export harus berakhiran .csv atau .json")


def export_rows(rows: list[dict], path: str) -> Path:
    """Ekspor hasil pencarian ke CSV atau JSON sesuai ekstensi file.

    Args:
        rows: Record hasil filter.
        path: File tujuan berakhiran ``.csv`` atau ``.json``.

    Returns:
        Path file yang ditulis.

    Raises:
        InvalidInputError: Jika ekstensi tidak didukung.
    """
    validate_export_path(path)
    if Path(path).suffix.lower() == ".csv":
        return write_csv_file(path, rows, CLEAN_FIELDS)
    return write_json_file(path, rows)


def load_and_process(args: argparse.Namespace) -> dict:
    """Muat file input lalu jalankan pipeline (dipakai semua perintah).

    Args:
        args: Hasil ``parse_args`` (butuh ``input``, ``warning``, ``critical``).

    Returns:
        Hasil ``processing.run_pipeline``.
    """
    validate_thresholds(args.warning, args.critical)  # cek input dulu (fail fast)
    raw_records = load_readings(args.input)
    return run_pipeline(raw_records, warning_temp=args.warning, critical_temp=args.critical)


# ---------------------------------------------------------------------------
# Perintah: report, search, menu
# ---------------------------------------------------------------------------
def command_report(args: argparse.Namespace) -> int:
    """Perintah ``report``: proses file dan simpan seluruh keluaran.

    Args:
        args: Argumen CLI.

    Returns:
        Exit code.
    """
    result = load_and_process(args)
    if not result["clean"]:
        print("[!] PERINGATAN: tidak ada data bersih yang dapat dianalisis.")
    print(format_summary(result["summary"]))
    print(format_rejected(result["rejected"]))
    print("\nFile keluaran:")
    for path in save_outputs(result, args.output_dir):
        print(f"  - {path.as_posix()}")
    return EXIT_OK


def command_search(args: argparse.Namespace) -> int:
    """Perintah ``search``: tampilkan data yang sesuai kriteria.

    Args:
        args: Argumen CLI.

    Returns:
        Exit code.
    """
    criteria = build_criteria(args)
    validate_export_path(args.export)  # validasi input dulu (fail fast)
    result = load_and_process(args)
    matches = sorted(
        filter_readings(result["clean"], **criteria), key=lambda item: item["timestamp"]
    )
    shown = matches[: args.limit] if args.limit else matches

    active = [
        f"{key}={value.strftime(TIMESTAMP_FORMAT) if isinstance(value, datetime) else value}"
        for key, value in criteria.items()
        if value is not None
    ]
    print(f"Kriteria : {', '.join(active) or 'semua data'}")
    note = f" (ditampilkan {len(shown)})" if args.limit else ""
    print(f"Ditemukan: {len(matches)} data{note}")
    print(format_table(shown))

    if args.export:
        path = export_rows(matches, args.export)
        print(f"\nHasil pencarian disimpan ke {path.as_posix()}")
    return EXIT_OK


def ask(prompt: str) -> str:
    """Baca input pengguna; Ctrl+D / akhir input dianggap keluar.

    Args:
        prompt: Teks pertanyaan.

    Returns:
        Jawaban yang sudah di-strip, atau ``"0"`` bila input berakhir.
    """
    try:
        return input(prompt).strip()
    except EOFError:
        print()
        return "0"


def menu_summary(result: dict, args: argparse.Namespace) -> None:
    """Menu 1: tampilkan ringkasan."""
    print(format_summary(result["summary"]))


def menu_by_sensor(result: dict, args: argparse.Namespace) -> None:
    """Menu 2: cari data berdasarkan ID sensor (input divalidasi)."""
    sensors = sorted({record["sensor_id"] for record in result["clean"]})
    if not sensors:
        print("Belum ada data sensor.")
        return
    sensor_id = ask(f"ID sensor {sensors}: ").upper()
    if sensor_id not in sensors:
        print(f"[!] Sensor '{sensor_id}' tidak dikenal. Pilih salah satu dari {sensors}.")
        return
    print(format_table(filter_readings(result["clean"], sensor_id=sensor_id)))


def menu_by_status(result: dict, args: argparse.Namespace) -> None:
    """Menu 3: filter berdasarkan status (input divalidasi)."""
    status = ask(f"Status {list(STATUSES)}: ").upper()
    if status not in STATUSES:
        print(f"[!] Status '{status}' tidak valid.")
        return
    print(format_table(filter_readings(result["clean"], status=status)))


def menu_alerts(result: dict, args: argparse.Namespace) -> None:
    """Menu 4: tampilkan 10 peringatan paling parah."""
    print(format_table(result["alerts"][:10]))


def menu_save(result: dict, args: argparse.Namespace) -> None:
    """Menu 5: simpan seluruh keluaran ke folder output."""
    for path in save_outputs(result, args.output_dir):
        print(f"  - tersimpan: {path.as_posix()}")


# Data-driven logic: nomor menu -> (label, fungsi).
MENU_ACTIONS = {
    "1": ("Tampilkan ringkasan", menu_summary),
    "2": ("Cari data per sensor", menu_by_sensor),
    "3": ("Filter berdasarkan status", menu_by_status),
    "4": ("Tampilkan 10 peringatan teratas", menu_alerts),
    "5": ("Simpan laporan ke folder output", menu_save),
}


def command_menu(args: argparse.Namespace) -> int:
    """Perintah ``menu``: mode interaktif berbasis pilihan angka.

    Args:
        args: Argumen CLI.

    Returns:
        Exit code.
    """
    result = load_and_process(args)
    print(f"Data dimuat: {len(result['clean'])} record bersih dari {args.input}")
    while True:
        print("\n=== MENU SensorMon ===")
        for key, (label, _) in MENU_ACTIONS.items():
            print(f"{key}. {label}")
        print("0. Keluar")

        choice = ask("Pilih menu: ")
        if choice == "0":
            print("Terima kasih.")
            break
        if choice not in MENU_ACTIONS:
            print(f"[!] Pilihan '{choice}' tidak tersedia. Masukkan angka 0-{len(MENU_ACTIONS)}.")
            logger.warning("Pilihan menu tidak valid: %r", choice)
            continue

        label, action = MENU_ACTIONS[choice]
        logger.info("Menu dipilih: %s", label)
        action(result, args)
    return EXIT_OK


COMMANDS = {
    "report": command_report,
    "search": command_search,
    "menu": command_menu,
}


# ---------------------------------------------------------------------------
# Parser & entry point
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    """Bangun parser argumen command line.

    Returns:
        Objek ``ArgumentParser`` dengan sub-perintah report/search/menu.
    """
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-i", "--input", default=DEFAULT_INPUT,
                        help=f"file data sensor .csv/.json (default: {DEFAULT_INPUT})")
    common.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR,
                        help=f"folder keluaran (default: {DEFAULT_OUTPUT_DIR})")
    common.add_argument("--warning", type=float, default=DEFAULT_WARNING_TEMP,
                        help=f"ambang suhu WASPADA °C (default: {DEFAULT_WARNING_TEMP})")
    common.add_argument("--critical", type=float, default=DEFAULT_CRITICAL_TEMP,
                        help=f"ambang suhu KRITIS °C (default: {DEFAULT_CRITICAL_TEMP})")
    common.add_argument("--log-file", default=None,
                        help="lokasi file log (default: <output-dir>/sensormon.log)")
    common.add_argument("-v", "--verbose", action="store_true",
                        help="tampilkan log INFO di terminal")

    parser = argparse.ArgumentParser(
        prog="sensormon",
        description="SensorMon - pengolah data sensor suhu & kelembapan "
                    "ruang server/laboratorium berbasis command line.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="PERINTAH")

    subparsers.add_parser("report", parents=[common],
                          help="validasi, rekap, dan simpan laporan ke folder output")

    search = subparsers.add_parser("search", parents=[common],
                                   help="cari/filter data sensor")
    search.add_argument("--sensor", help="ID sensor, mis. S01")
    search.add_argument("--location", help="potongan nama lokasi, mis. server")
    search.add_argument("--status", type=str.upper, choices=STATUSES,
                        help="NORMAL, WASPADA, atau KRITIS")
    search.add_argument("--start", help="mulai tanggal YYYY-MM-DD [HH:MM:SS]")
    search.add_argument("--end", help="sampai tanggal YYYY-MM-DD [HH:MM:SS]")
    search.add_argument("--limit", type=positive_int,
                        help="jumlah baris maksimum yang ditampilkan")
    search.add_argument("--export", help="simpan hasil ke file .csv atau .json")

    subparsers.add_parser("menu", parents=[common], help="mode menu interaktif")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point aplikasi.

    Args:
        argv: Daftar argumen (``None`` = ambil dari ``sys.argv``).

    Returns:
        Exit code: 0 sukses, 1 error file/data, 2 input salah,
        3 error tak terduga, 130 dibatalkan pengguna.
    """
    args = build_parser().parse_args(argv)
    log_file = args.log_file or Path(args.output_dir) / LOG_FILENAME
    setup_logging(log_file, verbose=args.verbose)
    logger.info("Mulai perintah '%s' dengan input '%s'", args.command, args.input)

    try:
        return COMMANDS[args.command](args)
    except InvalidInputError as error:
        logger.error("Input tidak valid: %s", error)
        print(f"[INPUT TIDAK VALID] {error}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    except (DataFileError, InvalidFormatError) as error:
        logger.error("Gagal memproses file: %s", error)
        print(f"[ERROR DATA] {error}", file=sys.stderr)
        return EXIT_DATA_ERROR
    except BrokenPipeError:
        # Output dipotong program lain (mis. `| head`): bukan kesalahan aplikasi.
        # Arahkan stdout ke devnull agar flush saat interpreter berhenti tidak error lagi.
        logger.warning("Output terminal ditutup lebih awal oleh program penerima (broken pipe)")
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return EXIT_OK
    except KeyboardInterrupt:
        logger.warning("Dibatalkan oleh pengguna (Ctrl+C)")
        print("\nDibatalkan oleh pengguna.", file=sys.stderr)
        return EXIT_INTERRUPTED
    except Exception:  # batas terluar aplikasi: catat detail lengkap ke log
        logger.critical("Kesalahan tak terduga", exc_info=True)
        print(f"[ERROR] Kesalahan tak terduga. Detail tercatat di {log_file}", file=sys.stderr)
        return EXIT_UNEXPECTED
    finally:
        logger.info("Perintah '%s' selesai", args.command)
        close_logging()  # lepas file log agar bisa dihapus/dipindah (Windows)
