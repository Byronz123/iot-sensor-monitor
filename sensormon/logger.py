"""Konfigurasi logging aplikasi.

Log lengkap (level DEBUG ke atas) selalu ditulis ke file. Terminal tidak
menerima log secara default agar output laporan tetap bersih (pesan error
yang ramah sudah dicetak oleh ``cli.py``). Opsi ``--verbose`` menampilkan
log level INFO ke atas di terminal (stderr).
"""

from __future__ import annotations

import logging
from pathlib import Path

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_path: str | Path, *, verbose: bool = False) -> Path | None:
    """Siapkan logging ke file dan ke terminal (stderr).

    Jika file log tidak dapat dibuat (misalnya izin ditolak), aplikasi tetap
    berjalan dengan logging ke terminal saja (defensive programming).

    Args:
        log_path: Lokasi file log.
        verbose: True agar pesan INFO juga tampil di terminal.

    Returns:
        Path file log yang aktif, atau ``None`` jika gagal membuat file log.
    """
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    handlers: list[logging.Handler] = [console] if verbose else []
    failure: OSError | None = None

    file_path: Path | None = Path(log_path)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        handlers.append(file_handler)
    except OSError as error:
        file_path = None
        failure = error
        if not verbose:
            console.setLevel(logging.WARNING)
            handlers.append(console)

    logging.basicConfig(
        level=logging.DEBUG,
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        handlers=handlers,
        force=True,
    )
    if file_path is None:
        logging.getLogger(__name__).warning(
            "File log tidak dapat dibuat (%s); log hanya tampil di terminal", failure
        )
    return file_path


def close_logging() -> None:
    """Tutup dan lepas semua handler logging milik root logger.

    Dipanggil di akhir ``cli.main``. Di Windows, file yang masih dibuka oleh
    ``FileHandler`` tidak dapat dihapus atau dipindah (``PermissionError``
    WinError 32), sehingga handler harus ditutup setelah program selesai.
    """
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
