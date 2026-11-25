# SensorMon — Pengolah Data Sensor Suhu & Kelembapan Ruang Server

Aplikasi **command line** berbasis Python (hanya *standard library*) untuk
membersihkan, menganalisis, dan merekap data sensor IoT suhu & kelembapan
(DHT22 + ESP32) di ruang server dan laboratorium.

> UTS Pemrograman Dasar (TK091) — S1 Teknik Komputer, Universitas Amikom Yogyakarta
> Nama: Muhammad Adiyaat Alfathi · NIM: 25.83.1198 · Repository: 

---

## 1. Latar belakang masalah

Ruang server dan laboratorium dipantau oleh beberapa node sensor yang
mengirim data per jam ke gateway, lalu disimpan sebagai file CSV/JSON.
Masalah yang terjadi di lapangan:

* data berisi **baris rusak** (sensor mengirim `ERR`, nilai `nan`, kolom kosong,
  timestamp salah, nilai di luar batas fisik sensor);
* gateway kadang **mengirim ulang** data sehingga muncul **duplikat**;
* format penulisan **tidak seragam** (`s02` vs `S02`, spasi berlebih,
  desimal koma `25,1` dari Excel, file CSV dengan BOM);
* petugas harus memeriksa ratusan baris secara manual untuk tahu kapan suhu
  ruang server melewati batas aman (rekomendasi umum 18–27 °C, RH 20–80 %).

**Tujuan aplikasi:** mengubah data mentah tersebut menjadi data bersih,
peringatan (alert) yang terurut menurut tingkat bahaya, dan rekap statistik
per sensor/lokasi secara otomatis serta dapat diulang.

**Target pengguna:** laboran, teknisi jaringan, dan admin ruang server
kampus/kantor yang sudah terbiasa memakai terminal.

## 2. Fitur utama

| No | Fitur | Perintah |
|----|-------|----------|
| 1 | Validasi & pembersihan data (tolak baris invalid + alasannya, normalisasi format) | `report` |
| 2 | Penghapusan data duplikat berdasarkan `(sensor_id, timestamp)` | `report` |
| 3 | Klasifikasi status `NORMAL` / `WASPADA` / `KRITIS` dengan ambang yang dapat diatur | `report`, `--warning`, `--critical` |
| 4 | Rekapitulasi statistik (min/maks/rata-rata, jumlah status) per sensor & per lokasi | `report` |
| 5 | Pencarian & filter berdasarkan sensor, lokasi, status, rentang waktu + ekspor | `search` |
| 6 | Menu interaktif dengan validasi input pengguna | `menu` |

## 3. Struktur project

```text
iot-sensor-monitor/
├── main.py                  # entry point: python main.py <perintah>
├── sensormon/               # package buatan sendiri
│   ├── __init__.py          # penanda package + versi
│   ├── __main__.py          # agar bisa dijalankan: python -m sensormon
│   ├── config.py            # konstanta: kolom wajib, ambang batas, label status
│   ├── exceptions.py        # custom exception (SensorMonError dan turunannya)
│   ├── models.py            # data layer: parsing & validasi 1 record
│   ├── io_handler.py        # file layer: baca/tulis CSV & JSON
│   ├── processing.py        # service layer: dedup, status, filter, grup, rekap
│   ├── report.py            # presentation helper: format tabel & laporan teks
│   ├── logger.py            # konfigurasi logging (file + terminal)
│   └── cli.py               # user interface: argparse + menu interaktif
├── data/                    # contoh file input (normal + edge case)
├── output/                  # contoh hasil keluaran + transkrip konsol
├── tests/test_sensormon.py  # 20 unit test (unittest)
├── docs/debugging.md        # laporan 2 skenario debugging
├── requirements.txt         # daftar dependency (kosong: hanya standard library)
└── README.md
```

## 4. Alur dependensi & pemanggilan antar-module

Dependensi hanya mengarah **ke bawah** (low coupling), tidak ada import
melingkar, dan hanya `cli.py` yang menyentuh terminal:

```text
main.py
  └─► sensormon.cli ──────────────┬─► sensormon.logger
                                  ├─► sensormon.io_handler ──► config, exceptions
                                  ├─► sensormon.processing ──► models ──► config, exceptions
                                  │                        └─► config, exceptions
                                  ├─► sensormon.report ─────► config
                                  └─► config, exceptions
```

Alur pemanggilan perintah `report`:

```text
cli.main()
 ├─ build_parser().parse_args()          # baca argumen
 ├─ logger.setup_logging()               # siapkan log file
 └─ command_report(args)
     ├─ load_and_process(args)
     │   ├─ processing.validate_thresholds()   # validasi input dulu
     │   ├─ io_handler.load_readings()          # CSV/JSON -> list of dict mentah
     │   └─ processing.run_pipeline()
     │       ├─ validate_records()   -> models.parse_reading()   (valid / ditolak)
     │       ├─ remove_duplicates()                              (set kunci unik)
     │       ├─ classify_readings()  -> determine_status()       (tambah status)
     │       ├─ sort_by_severity()                               (daftar alert)
     │       └─ build_summary()      -> group_by(), summarize_group(), calculate_stats()
     ├─ report.format_summary() / format_rejected()  -> print ke terminal
     └─ save_outputs() -> io_handler.write_csv_file() / write_json_file()
```

## 5. Persyaratan, package & dependency

* Python **3.9 atau lebih baru** (diuji pada 3.9, 3.11, 3.12, 3.13).
* **Tidak ada library pihak ketiga.** Module standard library yang dipakai:
  `argparse`, `csv`, `json`, `logging`, `pathlib`, `datetime`, `math`, `os`,
  `sys`, dan untuk pengujian `unittest`, `tempfile`, `io`, `contextlib`.
* Package buatan sendiri: `sensormon` (lihat struktur di atas).

## 6. Instalasi

```bash
git clone <URL repository> iot-sensor-monitor
cd iot-sensor-monitor

# (disarankan) buat virtual environment
python -m venv .venv
source .venv/bin/activate          # Linux/macOS
.venv\Scripts\activate             # Windows

pip install -r requirements.txt    # tidak meng-install apa pun (tanpa dependency)
```

> Semua perintah dijalankan dari **folder project** (folder yang berisi `main.py`).
> Di Windows gunakan `python`, di Linux/macOS bisa `python3`.

## 7. Cara menjalankan

### 7.1 Laporan lengkap (`report`)

```bash
python main.py report                                   # pakai data/sensor_readings.csv
python main.py report -i data/sensor_readings.json -o output/json_input
python main.py report --warning 26 --critical 30        # ubah ambang suhu
```

Menghasilkan di folder `-o` (default `output/`):

| File | Isi |
|------|-----|
| `clean_readings.csv` | data bersih, unik, berstatus |
| `alerts.csv` | data WASPADA/KRITIS, terurut dari yang paling parah |
| `rejected_rows.csv` | baris yang ditolak + nomor baris + alasan |
| `summary.json` | rekap lengkap (kualitas data, statistik, per sensor, per lokasi) |
| `sensormon.log` | log proses (INFO/WARNING/ERROR) |

### 7.2 Pencarian & filter (`search`)

```bash
python main.py search --sensor S01 --start "2026-11-18 12:00:00" --end "2026-11-18 18:00:00"
python main.py search --location lab --status WASPADA --export output/search_lab_waspada.csv
python main.py search --status KRITIS --limit 5
```

### 7.3 Menu interaktif (`menu`)

```bash
python main.py menu
```

### 7.4 Opsi umum

| Opsi | Keterangan | Default |
|------|-----------|---------|
| `-i, --input` | file `.csv` atau `.json` | `data/sensor_readings.csv` |
| `-o, --output-dir` | folder keluaran | `output` |
| `--warning` | ambang suhu WASPADA (°C) | `27.0` |
| `--critical` | ambang suhu KRITIS (°C) | `32.0` |
| `--log-file` | lokasi file log | `<output-dir>/sensormon.log` |
| `-v, --verbose` | tampilkan log INFO di terminal | mati |

Bantuan lengkap: `python main.py --help` atau `python main.py search --help`.
Alternatif: `python -m sensormon report`.

## 8. Format input & output

**CSV** (header wajib, urutan bebas, kolom tambahan diabaikan):

```csv
timestamp,sensor_id,location,temperature,humidity
2026-11-18 00:00:00,S01,Ruang Server Utama,22.8,49.7
```

**JSON** — list objek, atau objek dengan kunci `readings`:

```json
{
    "device_gateway": "GW-LAB-01",
    "readings": [
        {"timestamp": "2026-11-19 00:00:00", "sensor_id": "S01",
         "location": "Ruang Server Utama", "temperature": 23.9, "humidity": 44.1}
    ]
}
```

Aturan validasi: `timestamp` format `YYYY-MM-DD HH:MM:SS`; suhu −40…80 °C
dan kelembapan 0…100 % (batas fisik DHT22); semua kolom wajib terisi; angka
boleh memakai desimal koma.

**Aturan status** (diperiksa berurutan):

1. suhu ≥ `--critical` → `KRITIS`
2. suhu ≥ `--warning` **atau** kelembapan di luar 20–80 % → `WASPADA`
3. selain itu → `NORMAL`

## 9. Penanganan error & exit code

| Kondisi | Contoh | Perilaku | Exit code |
|---------|--------|----------|-----------|
| File tidak ditemukan / folder / tanpa izin | `-i data/tidak_ada.csv` | pesan `[ERROR DATA]`, dicatat di log | 1 |
| Format file salah | JSON rusak, kolom wajib hilang, ekstensi `.txt` | pesan `[ERROR DATA]` + lokasi kesalahan | 1 |
| Baris data tidak valid | `ERR`, `nan`, `125.0`, jam `25:00` | baris dilewati, alasan di `rejected_rows.csv` | 0 |
| Input pengguna salah | `--warning 35 --critical 30`, tanggal `2026-13-01`, `--export x.xlsx` | pesan `[INPUT TIDAK VALID]` | 2 |
| Tipe argumen salah | `--warning abc`, `--status PANAS`, `--limit 0` | ditolak argparse | 2 |
| Pilihan menu salah | `9`, `abc`, sensor `S05` | pesan `[!]`, menu diulang | 0 |
| Output dipotong (`| head`) | — | dicatat WARNING, keluar normal | 0 |
| Ctrl+C | — | "Dibatalkan oleh pengguna." | 130 |
| Error tak terduga | — | pesan singkat, traceback lengkap di log | 3 |

## 10. Edge case yang disiapkan

| File | Kasus | Hasil yang diharapkan |
|------|-------|----------------------|
| `data/edge_empty.csv` | hanya header, 0 data | laporan "belum ada data", tidak crash, exit 0 |
| `data/edge_all_invalid.csv` | semua baris rusak | 4 baris ditolak dengan alasan masing-masing |
| `data/edge_boundary.csv` | nilai tepat di ambang (27.0, 32.0, RH 20/80, 19.9/80.1) | 27.0→WASPADA, 32.0→KRITIS, RH 20 & 80→NORMAL |
| `data/edge_bom_excel.csv` | CSV ekspor Excel (BOM) | terbaca normal (lihat `docs/debugging.md`) |
| `data/edge_missing_column.csv` | kolom `humidity` tidak ada | error format, exit 1 |
| `data/edge_broken.json` | JSON kurang koma | error dengan nomor baris & kolom, exit 1 |

Transkrip seluruh skenario ada di `output/console/`.

## 11. Pengujian

```bash
python -m unittest discover -s tests -v
```

Hasil: 20 test, semua `OK` (lihat `output/console/07_unit_test.txt`).

## 12. Debugging

Dua skenario error nyata (CSV ber-BOM dari Excel dan `BrokenPipeError`)
didokumentasikan langkah demi langkah di [`docs/debugging.md`](docs/debugging.md),
termasuk sesi `pdb` dengan breakpoint.

## 13. Gaya kode

PEP 8 (snake_case, UPPER_CASE untuk konstanta, PascalCase untuk class),
docstring Google-style di setiap function, panjang baris maks. 99 karakter
(batas yang diizinkan PEP 8 untuk tim). Diperiksa dengan `pycodestyle` dan
`pyflakes` tanpa peringatan.

## 14. Referensi & bantuan AI

* Materi kuliah Pemrograman Dasar (Python) Pertemuan 1, 3, 5, 7, 9, 11, 13 —
  Universitas Amikom Yogyakarta.
* Dokumentasi resmi Python: `csv`, `json`, `logging`, `argparse`, `pdb`,
  `codecs` (utf-8-sig) — https://docs.python.org/3/
* PEP 8 — Style Guide for Python Code — https://peps.python.org/pep-0008/
* Rentang suhu/kelembapan ruang server: rekomendasi umum ASHRAE TC 9.9
  (18–27 °C); spesifikasi rentang ukur sensor DHT22 (−40…80 °C, 0…100 %RH).
* Bantuan AI: Claude (Anthropic) dipakai untuk membantu menyusun kode,
  data contoh, pengujian, dan dokumentasi. Seluruh kode telah dijalankan dan
  diuji ulang.
