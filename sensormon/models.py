"""Lapisan data (model): parsing dan validasi satu baris data sensor.

Module ini hanya bertanggung jawab mengubah *raw record* (dict berisi string
dari CSV/JSON) menjadi *record bersih* dengan tipe data yang benar. Module ini
tidak membaca file dan tidak mencetak apa pun (tanpa side effect).
"""

from __future__ import annotations

import math
from datetime import datetime

from .config import (
    HUMIDITY_RANGE,
    NON_OBJECT_KEY,
    REQUIRED_FIELDS,
    TEMPERATURE_RANGE,
    TIMESTAMP_FORMAT,
)
from .exceptions import InvalidRecordError


def is_blank(value: object) -> bool:
    """Cek apakah sebuah nilai dianggap kosong.

    Sengaja TIDAK memakai ``not value`` karena angka ``0``/``0.0`` adalah
    data sah (misalnya suhu 0 °C) tetapi bernilai *falsy* di Python.

    Args:
        value: Nilai apa pun dari raw record.

    Returns:
        True jika nilai ``None`` atau string kosong/berisi spasi saja.
    """
    return value is None or str(value).strip() == ""


def parse_timestamp(text: object) -> datetime:
    """Ubah teks timestamp menjadi objek ``datetime``.

    Args:
        text: Timestamp dengan format ``YYYY-MM-DD HH:MM:SS``.

    Returns:
        Objek ``datetime`` hasil parsing.

    Raises:
        InvalidRecordError: Jika format timestamp tidak sesuai.
    """
    try:
        return datetime.strptime(str(text).strip(), TIMESTAMP_FORMAT)
    except ValueError as error:
        raise InvalidRecordError(
            f"timestamp '{text}' tidak sesuai format {TIMESTAMP_FORMAT}"
        ) from error


def parse_number(text: object, field: str) -> float:
    """Ubah teks menjadi bilangan float yang terhingga (finite).

    Mendukung desimal koma (``27,5``) yang umum pada file hasil ekspor
    spreadsheet berlocale Indonesia.

    Args:
        text: Nilai mentah (string atau angka).
        field: Nama kolom, dipakai pada pesan error.

    Returns:
        Nilai float.

    Raises:
        InvalidRecordError: Jika bukan angka atau bernilai NaN/inf.
    """
    cleaned = str(text).strip().replace(",", ".")
    try:
        number = float(cleaned)
    except ValueError as error:
        raise InvalidRecordError(f"{field} '{text}' bukan angka") from error
    if not math.isfinite(number):
        raise InvalidRecordError(f"{field} '{text}' bukan angka terhingga")
    return number


def check_range(value: float, bounds: tuple[float, float], field: str) -> float:
    """Pastikan nilai berada di dalam rentang fisik sensor.

    Args:
        value: Nilai yang diperiksa.
        bounds: Tuple ``(minimum, maksimum)`` inklusif.
        field: Nama kolom untuk pesan error.

    Returns:
        Nilai yang sama jika valid.

    Raises:
        InvalidRecordError: Jika nilai di luar rentang.
    """
    low, high = bounds
    if not low <= value <= high:
        raise InvalidRecordError(
            f"{field} {value} di luar rentang sensor ({low} s.d. {high})"
        )
    return value


def parse_reading(raw: dict) -> dict:
    """Validasi dan normalisasi satu raw record menjadi record bersih.

    Normalisasi yang dilakukan:
    * ``sensor_id`` di-strip dan dijadikan huruf besar (`` s01 `` -> ``S01``).
    * ``location`` di-strip dan spasi berlebih dirapikan.
    * ``timestamp`` diseragamkan ke format standar.
    * ``temperature`` dan ``humidity`` dikonversi ke float (1 desimal).

    Args:
        raw: Dictionary dari ``csv.DictReader`` atau elemen list JSON.

    Returns:
        Dictionary baru dengan kunci sesuai ``REQUIRED_FIELDS``.

    Raises:
        InvalidRecordError: Jika ada kolom kosong atau nilai tidak valid.
    """
    if not isinstance(raw, dict) or NON_OBJECT_KEY in raw:
        raise InvalidRecordError("record bukan objek key-value")

    missing = [field for field in REQUIRED_FIELDS if is_blank(raw.get(field))]
    if missing:
        raise InvalidRecordError(f"kolom kosong/hilang: {', '.join(missing)}")

    timestamp = parse_timestamp(raw["timestamp"])
    temperature = check_range(
        parse_number(raw["temperature"], "temperature"),
        TEMPERATURE_RANGE,
        "temperature",
    )
    humidity = check_range(
        parse_number(raw["humidity"], "humidity"), HUMIDITY_RANGE, "humidity"
    )

    return {
        "timestamp": timestamp.strftime(TIMESTAMP_FORMAT),
        "sensor_id": str(raw["sensor_id"]).strip().upper(),
        "location": " ".join(str(raw["location"]).split()),
        "temperature": round(temperature, 1),
        "humidity": round(humidity, 1),
    }
