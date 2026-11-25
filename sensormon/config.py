"""Konstanta konfigurasi aplikasi SensorMon.

Semua nilai tetap (konstanta) dikumpulkan di satu module agar mudah diubah
tanpa menyentuh logika program (prinsip *single source of truth*).
Penamaan mengikuti PEP 8: konstanta ditulis UPPER_CASE.
"""

# --- Struktur data input ---------------------------------------------------
REQUIRED_FIELDS = ("timestamp", "sensor_id", "location", "temperature", "humidity")
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
DATE_FORMAT = "%Y-%m-%d"

# --- Batas fisik sensor DHT22 (di luar rentang ini = data rusak) -----------
TEMPERATURE_RANGE = (-40.0, 80.0)
HUMIDITY_RANGE = (0.0, 100.0)

# --- Ambang batas status ruang server / laboratorium ------------------------
# Rekomendasi umum ruang server: suhu 18-27 °C dan kelembapan 20-80 %RH.
DEFAULT_WARNING_TEMP = 27.0
DEFAULT_CRITICAL_TEMP = 32.0
SAFE_HUMIDITY_RANGE = (20.0, 80.0)

# --- Label status ------------------------------------------------------------
STATUS_NORMAL = "NORMAL"
STATUS_WARNING = "WASPADA"
STATUS_CRITICAL = "KRITIS"
STATUSES = (STATUS_NORMAL, STATUS_WARNING, STATUS_CRITICAL)

# --- Kolom file keluaran -----------------------------------------------------
CLEAN_FIELDS = REQUIRED_FIELDS + ("status",)
REJECTED_FIELDS = ("line", "reason", "raw")

# --- Kunci internal yang ditambahkan saat file dibaca -------------------------
LINE_KEY = "_line"  # nomor baris CSV / nomor urut record JSON
NON_OBJECT_KEY = "_non_object"  # penanda elemen JSON yang bukan objek

# --- Lokasi default ------------------------------------------------------------
DEFAULT_OUTPUT_DIR = "output"
LOG_FILENAME = "sensormon.log"
