"""SensorMon: package pengolah data sensor suhu & kelembapan berbasis CLI.

Struktur module (dari lapisan terbawah ke teratas)::

    config       -> konstanta (ambang batas, nama kolom, format waktu)
    exceptions   -> custom exception
    models       -> parsing & validasi satu record      (data layer)
    io_handler   -> baca/tulis file CSV & JSON           (file layer)
    processing   -> dedup, klasifikasi, filter, rekap    (service layer)
    report       -> format tabel/laporan teks            (presentation helper)
    logger       -> konfigurasi logging
    cli          -> argparse + menu interaktif           (user interface)
"""

import logging

# Praktik standar library/package: tambahkan NullHandler agar pesan log tidak
# tercetak ke layar ketika aplikasi belum mengatur logging (mis. saat fungsi
# dipanggil langsung dari unit test). Konfigurasi sebenarnya ada di logger.py.
logging.getLogger(__name__).addHandler(logging.NullHandler())

__version__ = "1.0.0"
__all__ = ["__version__"]
