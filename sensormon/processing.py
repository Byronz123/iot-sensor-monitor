"""Lapisan logika bisnis (service): validasi, deduplikasi, klasifikasi,
filtering, pengelompokan, dan rekapitulasi data sensor.

Seluruh fungsi di module ini *pure* sejauh memungkinkan: menerima data lewat
parameter, mengembalikan data baru lewat ``return``, tidak mengubah data asli,
tidak membaca/menulis file, dan tidak memanggil ``print()``. Satu-satunya side
effect yang disengaja adalah pencatatan ``logging``.
"""

from __future__ import annotations

import logging
from datetime import datetime

from .config import (
    DEFAULT_CRITICAL_TEMP,
    DEFAULT_WARNING_TEMP,
    LINE_KEY,
    SAFE_HUMIDITY_RANGE,
    STATUS_CRITICAL,
    STATUS_NORMAL,
    STATUS_WARNING,
    STATUSES,
    TEMPERATURE_RANGE,
)
from .exceptions import InvalidInputError, InvalidRecordError
from .models import parse_reading, parse_timestamp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Validasi & pembersihan
# ---------------------------------------------------------------------------
def describe_raw(raw: dict) -> str:
    """Ringkas raw record menjadi satu baris teks untuk laporan penolakan.

    Args:
        raw: Raw record (boleh berisi kunci internal).

    Returns:
        Teks ``kunci=nilai`` dipisahkan ``; `` tanpa kunci internal.
    """
    return "; ".join(
        f"{key}={value}" for key, value in raw.items() if not str(key).startswith("_")
    ) or str(raw)


def validate_records(raw_records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Pisahkan raw record menjadi record valid dan record yang ditolak.

    Baris tidak valid TIDAK menghentikan program; baris tersebut dicatat
    beserta alasannya (defensive programming).

    Args:
        raw_records: Hasil ``io_handler.load_readings``.

    Returns:
        Tuple ``(valid, rejected)``. ``rejected`` berisi dict dengan kunci
        ``line``, ``reason``, dan ``raw``.
    """
    valid, rejected = [], []
    for raw in raw_records:
        line = raw.get(LINE_KEY, "?") if isinstance(raw, dict) else "?"
        try:
            valid.append(parse_reading(raw))
        except InvalidRecordError as error:
            rejected.append({"line": line, "reason": str(error), "raw": describe_raw(raw)})
            logger.warning("Baris %s dilewati: %s", line, error)
    return valid, rejected


def remove_duplicates(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Hapus data duplikat berdasarkan pasangan ``(sensor_id, timestamp)``.

    Sebuah sensor tidak mungkin mengirim dua pembacaan berbeda pada detik
    yang sama, sehingga pasangan tersebut dijadikan kunci unik. Kemunculan
    pertama dipertahankan dan urutan data asli tidak berubah.

    Args:
        records: Record yang sudah tervalidasi.

    Returns:
        Tuple ``(unique, duplicates)``.
    """
    seen: set[tuple[str, str]] = set()
    unique, duplicates = [], []
    for record in records:
        key = (record["sensor_id"], record["timestamp"])
        if key in seen:
            duplicates.append(record)
            continue
        seen.add(key)
        unique.append(record)

    if duplicates:
        logger.info("Menghapus %d data duplikat", len(duplicates))
    return unique, duplicates


# ---------------------------------------------------------------------------
# 2. Klasifikasi status
# ---------------------------------------------------------------------------
def validate_thresholds(warning_temp: float, critical_temp: float) -> None:
    """Pastikan ambang batas suhu masuk akal.

    Args:
        warning_temp: Suhu mulai status WASPADA.
        critical_temp: Suhu mulai status KRITIS.

    Raises:
        InvalidInputError: Jika di luar rentang sensor atau warning >= critical.
    """
    low, high = TEMPERATURE_RANGE
    if not (low <= warning_temp <= high and low <= critical_temp <= high):
        raise InvalidInputError(f"ambang suhu harus di antara {low} dan {high} °C")
    if warning_temp >= critical_temp:
        raise InvalidInputError(
            f"ambang WASPADA ({warning_temp}) harus lebih kecil dari "
            f"ambang KRITIS ({critical_temp})"
        )


def determine_status(
    temperature: float,
    humidity: float,
    *,
    warning_temp: float = DEFAULT_WARNING_TEMP,
    critical_temp: float = DEFAULT_CRITICAL_TEMP,
) -> str:
    """Tentukan status kondisi ruangan dari satu pembacaan sensor.

    Aturan (dievaluasi berurutan dengan guard clause / early return):
    1. suhu >= ``critical_temp``                      -> KRITIS
    2. suhu >= ``warning_temp`` ATAU kelembapan di luar
       ``SAFE_HUMIDITY_RANGE``                         -> WASPADA
    3. selain itu                                      -> NORMAL

    Args:
        temperature: Suhu dalam °C.
        humidity: Kelembapan relatif dalam %.
        warning_temp: Ambang WASPADA (keyword-only).
        critical_temp: Ambang KRITIS (keyword-only).

    Returns:
        Salah satu dari ``STATUSES``.
    """
    if temperature >= critical_temp:
        return STATUS_CRITICAL

    humidity_low, humidity_high = SAFE_HUMIDITY_RANGE
    humidity_unsafe = not humidity_low <= humidity <= humidity_high
    if temperature >= warning_temp or humidity_unsafe:
        return STATUS_WARNING

    return STATUS_NORMAL


def classify_readings(
    records: list[dict],
    *,
    warning_temp: float = DEFAULT_WARNING_TEMP,
    critical_temp: float = DEFAULT_CRITICAL_TEMP,
) -> list[dict]:
    """Tambahkan kolom ``status`` ke setiap record tanpa mengubah data asli.

    Args:
        records: Record bersih.
        warning_temp: Ambang WASPADA.
        critical_temp: Ambang KRITIS.

    Returns:
        List baru berisi salinan record + kunci ``status``.
    """
    return [
        {
            **record,
            "status": determine_status(
                record["temperature"],
                record["humidity"],
                warning_temp=warning_temp,
                critical_temp=critical_temp,
            ),
        }
        for record in records
    ]


# ---------------------------------------------------------------------------
# 3. Pencarian & filtering
# ---------------------------------------------------------------------------
def matches_criteria(
    record: dict,
    *,
    sensor_id: str | None = None,
    location: str | None = None,
    status: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> bool:
    """Cek apakah satu record memenuhi SEMUA kriteria yang diberikan.

    Kriteria bernilai ``None`` dianggap tidak dipakai. Pencocokan lokasi
    bersifat *substring* dan tidak peka huruf besar/kecil.

    Args:
        record: Record bersih (sudah berstatus bila memfilter status).
        sensor_id: ID sensor persis, mis. ``S01``.
        location: Potongan nama lokasi, mis. ``server``.
        status: Salah satu dari ``STATUSES``.
        start: Batas awal waktu (inklusif).
        end: Batas akhir waktu (inklusif).

    Returns:
        True jika semua kriteria terpenuhi.
    """
    timestamp = parse_timestamp(record["timestamp"])
    checks = (
        sensor_id is None or record["sensor_id"] == sensor_id.strip().upper(),
        location is None or location.strip().lower() in record["location"].lower(),
        status is None or record.get("status") == status.strip().upper(),
        start is None or timestamp >= start,
        end is None or timestamp <= end,
    )
    return all(checks)


def filter_readings(records: list[dict], **criteria) -> list[dict]:
    """Ambil record yang memenuhi kriteria (lihat ``matches_criteria``).

    Args:
        records: Record yang akan difilter.
        **criteria: ``sensor_id``, ``location``, ``status``, ``start``, ``end``.

    Returns:
        List baru berisi record yang cocok (urutan asli dipertahankan).
    """
    return [record for record in records if matches_criteria(record, **criteria)]


def find_first_by_status(records: list[dict], status: str) -> dict | None:
    """Cari kejadian PERTAMA (berdasarkan waktu) dengan status tertentu.

    Menggunakan pola ``for ... break ... else`` untuk pencarian linear.

    Args:
        records: Record berstatus.
        status: Status yang dicari.

    Returns:
        Record pertama yang cocok, atau ``None`` jika tidak ada.
    """
    for record in sorted(records, key=lambda item: item["timestamp"]):
        if record.get("status") == status:
            found = record
            break
    else:
        found = None
    return found


def sort_by_severity(records: list[dict]) -> list[dict]:
    """Urutkan record: KRITIS dulu, lalu WASPADA, lalu suhu tertinggi.

    Args:
        records: Record berstatus.

    Returns:
        List baru yang sudah terurut.
    """
    severity = {status: rank for rank, status in enumerate(reversed(STATUSES))}
    return sorted(
        records,
        key=lambda item: (severity[item["status"]], -item["temperature"], item["timestamp"]),
    )


# ---------------------------------------------------------------------------
# 4. Pengelompokan & rekapitulasi
# ---------------------------------------------------------------------------
def group_by(records: list[dict], field: str) -> dict[str, list[dict]]:
    """Kelompokkan record berdasarkan nilai sebuah kolom.

    Args:
        records: Record yang akan dikelompokkan.
        field: Nama kolom, mis. ``sensor_id`` atau ``location``.

    Returns:
        Dictionary ``{nilai_kolom: [record, ...]}`` dengan kunci terurut.
    """
    groups: dict[str, list[dict]] = {}
    for record in records:
        groups.setdefault(record[field], []).append(record)
    return dict(sorted(groups.items()))


def calculate_stats(values: list[float]) -> dict | None:
    """Hitung statistik deskriptif sederhana.

    Args:
        values: Daftar angka.

    Returns:
        Dict ``count``, ``min``, ``max``, ``avg`` (2 desimal), atau ``None``
        jika ``values`` kosong (bukan 0, agar tidak menyesatkan).
    """
    if not values:
        return None
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "avg": round(sum(values) / len(values), 2),
    }


def count_by_status(records: list[dict]) -> dict[str, int]:
    """Hitung jumlah record untuk setiap status.

    Args:
        records: Record berstatus.

    Returns:
        Dictionary ``{status: jumlah}`` untuk semua status (termasuk 0).
    """
    return {
        status: sum(1 for record in records if record["status"] == status)
        for status in STATUSES
    }


def summarize_group(records: list[dict]) -> dict:
    """Buat rekap untuk satu kelompok record.

    Args:
        records: Record berstatus dalam satu kelompok.

    Returns:
        Dict berisi statistik suhu, kelembapan, jumlah per status, dan
        daftar lokasi/sensor unik di kelompok tersebut.
    """
    return {
        "readings": len(records),
        "temperature": calculate_stats([record["temperature"] for record in records]),
        "humidity": calculate_stats([record["humidity"] for record in records]),
        "status_count": count_by_status(records),
        "locations": sorted({record["location"] for record in records}),
        "sensors": sorted({record["sensor_id"] for record in records}),
    }


def build_summary(
    *,
    raw_count: int,
    classified: list[dict],
    rejected: list[dict],
    duplicates: list[dict],
    warning_temp: float,
    critical_temp: float,
) -> dict:
    """Susun laporan rekapitulasi lengkap yang siap diserialisasi ke JSON.

    Args:
        raw_count: Jumlah record mentah yang dibaca dari file.
        classified: Record bersih, unik, dan berstatus.
        rejected: Record yang ditolak validasi.
        duplicates: Record duplikat yang dibuang.
        warning_temp: Ambang WASPADA yang dipakai.
        critical_temp: Ambang KRITIS yang dipakai.

    Returns:
        Dictionary laporan (hanya berisi tipe yang didukung JSON).
    """
    first_critical = find_first_by_status(classified, STATUS_CRITICAL)
    timestamps = [record["timestamp"] for record in classified]
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "thresholds": {
            "warning_temp": warning_temp,
            "critical_temp": critical_temp,
            "safe_humidity": list(SAFE_HUMIDITY_RANGE),
        },
        "data_quality": {
            "raw_records": raw_count,
            "valid_records": len(classified) + len(duplicates),
            "rejected_records": len(rejected),
            "duplicates_removed": len(duplicates),
            "clean_records": len(classified),
        },
        "period": {
            "start": min(timestamps) if timestamps else None,
            "end": max(timestamps) if timestamps else None,
        },
        "overall": summarize_group(classified),
        "by_sensor": {
            sensor: summarize_group(rows)
            for sensor, rows in group_by(classified, "sensor_id").items()
        },
        "by_location": {
            location: summarize_group(rows)
            for location, rows in group_by(classified, "location").items()
        },
        "first_critical_event": first_critical,
    }


# ---------------------------------------------------------------------------
# 5. Pipeline lengkap
# ---------------------------------------------------------------------------
def run_pipeline(
    raw_records: list[dict],
    *,
    warning_temp: float = DEFAULT_WARNING_TEMP,
    critical_temp: float = DEFAULT_CRITICAL_TEMP,
) -> dict:
    """Jalankan seluruh tahap: validasi -> dedup -> klasifikasi -> rekap.

    Args:
        raw_records: Raw record dari file.
        warning_temp: Ambang WASPADA.
        critical_temp: Ambang KRITIS.

    Returns:
        Dict dengan kunci ``clean``, ``alerts``, ``rejected``,
        ``duplicates``, dan ``summary``.

    Raises:
        InvalidInputError: Jika ambang batas tidak valid.
    """
    validate_thresholds(warning_temp, critical_temp)
    if not raw_records:
        logger.warning("File input tidak berisi record data")

    valid, rejected = validate_records(raw_records)
    unique, duplicates = remove_duplicates(valid)
    classified = classify_readings(
        unique, warning_temp=warning_temp, critical_temp=critical_temp
    )
    alerts = sort_by_severity(
        [record for record in classified if record["status"] != STATUS_NORMAL]
    )
    summary = build_summary(
        raw_count=len(raw_records),
        classified=classified,
        rejected=rejected,
        duplicates=duplicates,
        warning_temp=warning_temp,
        critical_temp=critical_temp,
    )
    logger.info(
        "Pipeline selesai: %d bersih, %d ditolak, %d duplikat, %d peringatan",
        len(classified), len(rejected), len(duplicates), len(alerts),
    )
    return {
        "clean": classified,
        "alerts": alerts,
        "rejected": rejected,
        "duplicates": duplicates,
        "summary": summary,
    }
