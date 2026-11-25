"""Custom exception untuk aplikasi SensorMon.

Semua exception buatan sendiri mewarisi ``SensorMonError`` sehingga lapisan
CLI cukup menangkap satu kelas induk, tetapi tetap dapat membedakan jenis
kesalahan bila diperlukan.
"""


class SensorMonError(Exception):
    """Kelas induk untuk semua kesalahan yang dapat diprediksi di aplikasi."""


class DataFileError(SensorMonError):
    """File input/output tidak dapat diakses (tidak ada, izin ditolak, dll)."""


class InvalidFormatError(SensorMonError):
    """Isi file tidak sesuai format (JSON rusak, kolom wajib hilang, dll)."""


class InvalidRecordError(SensorMonError):
    """Satu baris data sensor tidak valid. Baris ini dilewati, bukan fatal."""


class InvalidInputError(SensorMonError):
    """Input pengguna (argumen CLI / menu interaktif) tidak sesuai aturan."""
