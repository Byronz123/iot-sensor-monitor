"""Lapisan file I/O: membaca dan menulis file CSV / JSON.

Module ini adalah satu-satunya tempat yang menyentuh file system. Semua
kesalahan level sistem operasi (``FileNotFoundError``, ``PermissionError``,
``UnicodeDecodeError``, ``json.JSONDecodeError``) diterjemahkan menjadi
custom exception agar lapisan di atasnya cukup menangani satu jenis error.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from .config import LINE_KEY, NON_OBJECT_KEY, REQUIRED_FIELDS
from .exceptions import DataFileError, InvalidFormatError

logger = logging.getLogger(__name__)


def read_csv_file(path: Path) -> list[dict]:
    """Baca file CSV menjadi list of dict.

    Encoding ``utf-8-sig`` dipakai agar BOM dari file ekspor Excel ikut
    dibuang (lihat skenario debugging di ``docs/debugging``).

    Args:
        path: Lokasi file CSV.

    Returns:
        List raw record; setiap record memiliki kunci ``_line``.

    Raises:
        InvalidFormatError: Jika header kosong atau kolom wajib tidak ada.
    """
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise InvalidFormatError(f"file CSV '{path}' kosong (tidak ada header)")

        headers = {name.strip() for name in reader.fieldnames if name}
        missing = [field for field in REQUIRED_FIELDS if field not in headers]
        if missing:
            raise InvalidFormatError(
                f"kolom wajib tidak ditemukan di '{path}': {', '.join(missing)}"
            )

        rows = []
        for row in reader:
            # Kunci None muncul bila sebuah baris punya kolom berlebih.
            record = {key.strip(): value for key, value in row.items() if key}
            record[LINE_KEY] = reader.line_num
            rows.append(record)
    return rows


def read_json_file(path: Path) -> list[dict]:
    """Baca file JSON berisi list record atau objek ``{"readings": [...]}``.

    Args:
        path: Lokasi file JSON.

    Returns:
        List raw record; setiap record dict diberi kunci ``_line``
        berisi nomor urut record (mulai 1).

    Raises:
        InvalidFormatError: Jika JSON rusak atau strukturnya tidak sesuai.
    """
    with open(path, "r", encoding="utf-8-sig") as file:
        try:
            data = json.load(file)
        except json.JSONDecodeError as error:
            raise InvalidFormatError(
                f"JSON tidak valid di '{path}' baris {error.lineno} "
                f"kolom {error.colno}: {error.msg}"
            ) from error

    if isinstance(data, dict):
        data = data.get("readings")
    if not isinstance(data, list):
        raise InvalidFormatError(
            f"struktur JSON '{path}' harus list atau objek dengan kunci 'readings'"
        )

    records = []
    for index, item in enumerate(data, start=1):
        record = dict(item) if isinstance(item, dict) else {NON_OBJECT_KEY: item}
        record[LINE_KEY] = index
        records.append(record)
    return records


# Data-driven logic: pemetaan ekstensi file -> fungsi pembaca.
READERS = {".csv": read_csv_file, ".json": read_json_file}


def load_readings(path: str | Path) -> list[dict]:
    """Muat raw record dari file CSV atau JSON berdasarkan ekstensinya.

    Args:
        path: Lokasi file input (``.csv`` atau ``.json``).

    Returns:
        List raw record (belum divalidasi).

    Raises:
        InvalidFormatError: Ekstensi tidak didukung / isi file rusak.
        DataFileError: File tidak ditemukan atau tidak dapat dibaca.
    """
    file_path = Path(path)
    reader = READERS.get(file_path.suffix.lower())
    if reader is None:
        supported = ", ".join(READERS)
        raise InvalidFormatError(
            f"ekstensi '{file_path.suffix or '(tanpa ekstensi)'}' tidak didukung; "
            f"gunakan {supported}"
        )

    try:
        records = reader(file_path)
    except FileNotFoundError as error:
        raise DataFileError(f"file tidak ditemukan: '{file_path}'") from error
    except IsADirectoryError as error:
        raise DataFileError(f"'{file_path}' adalah folder, bukan file") from error
    except PermissionError as error:
        raise DataFileError(f"tidak ada izin membaca '{file_path}'") from error
    except UnicodeDecodeError as error:
        raise InvalidFormatError(
            f"'{file_path}' bukan file teks UTF-8 yang valid"
        ) from error

    logger.info("Memuat %d record dari %s", len(records), file_path)
    return records


def write_csv_file(path: str | Path, rows: list[dict], fieldnames: tuple) -> Path:
    """Tulis list of dict ke file CSV (folder tujuan dibuat otomatis).

    Args:
        path: Lokasi file keluaran.
        rows: Data yang akan ditulis.
        fieldnames: Urutan kolom; kunci lain pada ``rows`` diabaikan.

    Returns:
        Path file yang berhasil ditulis.

    Raises:
        DataFileError: Jika file tidak dapat ditulis.
    """
    file_path = Path(path)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    except OSError as error:
        raise DataFileError(f"gagal menulis '{file_path}': {error}") from error

    logger.info("Menulis %d baris ke %s", len(rows), file_path)
    return file_path


def write_json_file(path: str | Path, data: object) -> Path:
    """Serialisasi objek Python ke file JSON yang rapi (indent 4).

    Args:
        path: Lokasi file keluaran.
        data: Objek yang dapat diserialisasi JSON (dict/list/str/angka).

    Returns:
        Path file yang berhasil ditulis.

    Raises:
        DataFileError: Jika file tidak dapat ditulis.
    """
    file_path = Path(path)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
            file.write("\n")
    except OSError as error:
        raise DataFileError(f"gagal menulis '{file_path}': {error}") from error

    logger.info("Menulis JSON ke %s", file_path)
    return file_path
