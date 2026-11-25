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

__version__ = "1.0.0"
__all__ = ["__version__"]
