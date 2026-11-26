# Laporan Debugging SensorMon

Dokumen ini mencatat tiga skenario error nyata yang ditemukan saat pengujian,
lengkap dengan langkah debugging, akar masalah, perbaikan, dan verifikasi.
Strategi yang dipakai mengikuti materi Pertemuan 9: baca pesan error dan
traceback, periksa log, pasang *breakpoint* untuk inspeksi variabel, lalu uji
ulang dengan input sederhana.

---

## Skenario 1 — CSV hasil ekspor Excel dianggap tidak punya kolom `timestamp`

### 1. Gejala

Laboran mengekspor data sensor dari Microsoft Excel ("CSV UTF-8") lalu
menjalankan:

```text
$ python main.py report -i data/edge_bom_excel.csv -o output/bom
[ERROR DATA] kolom wajib tidak ditemukan di 'data/edge_bom_excel.csv': timestamp
[exit code: 1]
```

Padahal saat file dibuka di editor teks, baris pertamanya jelas
`timestamp,sensor_id,location,temperature,humidity`.

Isi `output/bom/sensormon.log`:

```text
2026-11-20 15:34:32 [INFO] sensormon.cli: Mulai perintah 'report' dengan input 'data/edge_bom_excel.csv'
2026-11-20 15:34:32 [ERROR] sensormon.cli: Gagal memproses file: kolom wajib tidak ditemukan di 'data/edge_bom_excel.csv': timestamp
2026-11-20 15:34:32 [INFO] sensormon.cli: Perintah 'report' selesai
```

Kode saat itu (versi sebelum perbaikan) di `sensormon/io_handler.py`:

```python
with open(path, "r", encoding="utf-8", newline="") as file:
    reader = csv.DictReader(file)
    ...
    headers = {name.strip() for name in reader.fieldnames if name}
    missing = [field for field in REQUIRED_FIELDS if field not in headers]
```

### 2. Hipotesis

Log menunjukkan error berasal dari pengecekan header, dan hanya kolom
**pertama** yang dianggap hilang. Kolom lain ditemukan. Jadi ada sesuatu yang
**"menempel" pada nama kolom pertama** yang tidak terlihat di editor.

### 3. Inspeksi dengan breakpoint (pdb)

Program dijalankan di bawah debugger dengan breakpoint di baris
`missing = [...]` (setara dengan menyisipkan `breakpoint()` di baris itu, atau
klik breakpoint lalu F5 di VS Code):

```text
$ python -m pdb main.py report -i data/edge_bom_excel.csv -o output/bom
(Pdb) break sensormon/io_handler.py:42
Breakpoint 1 at sensormon/io_handler.py:42
(Pdb) continue
> sensormon/io_handler.py(42)read_csv_file()
-> missing = [field for field in REQUIRED_FIELDS if field not in headers]
(Pdb) p reader.fieldnames
['\ufefftimestamp', 'sensor_id', 'location', 'temperature', 'humidity']
(Pdb) p headers
{'humidity', 'temperature', 'sensor_id', '\ufefftimestamp', 'location'}
(Pdb) p 'timestamp' in headers
False
(Pdb) p reader.fieldnames[0].encode('utf-8')
b'\xef\xbb\xbftimestamp'
(Pdb) clear 1
Deleted breakpoint 1 at sensormon/io_handler.py:42
(Pdb) continue
[ERROR DATA] kolom wajib tidak ditemukan di 'data/edge_bom_excel.csv': timestamp
```

Bukti tambahan, 24 byte pertama file:

```text
>>> open("data/edge_bom_excel.csv", "rb").read(24)
b'\xef\xbb\xbftimestamp,sensor_id,l'
```

### 4. Akar masalah

Excel menambahkan **BOM (Byte Order Mark) `EF BB BF`** di awal file
"CSV UTF-8". Jika dibaca dengan `encoding="utf-8"`, tiga byte itu menjadi
karakter tak terlihat `'\ufeff'` dan menempel pada nama kolom pertama,
sehingga `'timestamp' != '\ufefftimestamp'`. `.strip()` tidak menghapusnya
karena `\ufeff` tidak termasuk whitespace.

### 5. Perbaikan

Gunakan codec **`utf-8-sig`**, yang otomatis membuang BOM bila ada dan tetap
membaca file UTF-8 biasa tanpa BOM dengan benar:

```python
# sesudah (sensormon/io_handler.py, read_csv_file dan read_json_file)
with open(path, "r", encoding="utf-8-sig", newline="") as file:
```

### 6. Verifikasi

```text
$ python main.py report -i data/edge_bom_excel.csv -o output/edge_bom_excel
...
[Kualitas Data]
  Record dibaca     : 8
  Ditolak (invalid) : 0
  Duplikat dihapus  : 0
  Record bersih     : 8
...
[exit code: 0]
```

Regression test ditambahkan agar bug tidak muncul lagi:
`tests/test_sensormon.py::TestFileHandling.test_excel_bom_csv_is_read`.

---

## Skenario 2 — `BrokenPipeError` saat output di-pipe ke program lain

### 1. Gejala

Saat menguji, output dipotong dengan `head` (di Windows mirip dengan `| more`
yang ditutup lebih awal):

```text
$ python main.py report -o /tmp/bp | head -3
================================================================
LAPORAN MONITORING SUHU & KELEMBAPAN (SensorMon)
================================================================
[ERROR] Kesalahan tak terduga. Detail tercatat di /tmp/bp/sensormon.log
[exit codes: 3 0]
```

### 2. Membaca traceback di log

Handler `except Exception` di `cli.main` mencatat traceback lengkap
(`exc_info=True`):

```text
2026-11-20 15:36:19 [CRITICAL] sensormon.cli: Kesalahan tak terduga
Traceback (most recent call last):
  File "sensormon/cli.py", line 425, in main
    return COMMANDS[args.command](args)
           ~~~~~~~~~~~~~~~~~~~~~~^^^^^^
  File "sensormon/cli.py", line 219, in command_report
    print(f"  - {path.as_posix()}")
    ~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^
BrokenPipeError: [Errno 32] Broken pipe
```

Cara membaca: jenis exception `BrokenPipeError` di baris terakhir, lokasi
paling dalam `command_report` baris 219 (sebuah `print`), dipanggil dari
`main` baris 425.

### 3. Akar masalah

`head -3` berhenti membaca setelah 3 baris dan menutup pipe. Ketika program
masih menulis ke stdout, sistem operasi mengirim **`EPIPE`**. Ini **bukan**
kesalahan logika aplikasi; laporan sudah selesai dibuat dan file keluaran
sudah tersimpan. Namun program melaporkannya sebagai **"kesalahan tak terduga"**
dan keluar dengan exit code 3.

### 4. Perbaikan

Tangani **`BrokenPipeError` secara spesifik** di `cli.main`, sebelum handler
umum. Stdout diarahkan ke `os.devnull` agar *flush* terakhir saat interpreter
berhenti tidak memicu error kedua (pola yang direkomendasikan dokumentasi
Python untuk `SIGPIPE`):

```python
except BrokenPipeError:
    logger.warning("Output terminal ditutup lebih awal oleh program penerima (broken pipe)")
    os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return EXIT_OK
```

### 5. Verifikasi

```text
$ python main.py report -o /tmp/bp | head -3
================================================================
LAPORAN MONITORING SUHU & KELEMBAPAN (SensorMon)
================================================================
[exit codes: 0 0]

# log:
2026-11-20 15:36:26 [WARNING] sensormon.cli: Output terminal ditutup lebih awal oleh program penerima (broken pipe)
```

---

## Skenario 3 — Unit test gagal di Windows: `PermissionError` WinError 32

### 1. Gejala

Di Linux seluruh test lulus, tetapi di laptop Windows (Anaconda Python):

```text
PS> python -m unittest discover -s tests -v
test_error_exit_codes (test_sensormon.TestCommandLine.test_error_exit_codes) ... ERROR
test_report_writes_all_outputs (test_sensormon.TestCommandLine.test_report_writes_all_outputs) ... ERROR
...
Ran 20 tests in 0.394s
FAILED (errors=2)
```

### 2. Membaca traceback

```text
Traceback (most recent call last):
  File "E:\Anaconda\Lib\shutil.py", line 633, in _rmtree_unsafe
    os.unlink(fullname)
PermissionError: [WinError 32] The process cannot access the file because it is
being used by another process: 'D:\\Temp\\tmpt2rqekdu\\sensormon.log'

During handling of the above exception, another exception occurred:
  File "tests\test_sensormon.py", line 210, in test_error_exit_codes
    with tempfile.TemporaryDirectory() as folder:
  ...
PermissionError: [WinError 32] ... 'D:\\Temp\\tmpt2rqekdu\\sensormon.log'
```

Error tidak terjadi di logika aplikasi, melainkan saat `TemporaryDirectory`
menghapus folder sementara: file `sensormon.log` masih dipegang proses lain.

### 3. Akar masalah

`setup_logging` membuka `sensormon.log` lewat `logging.FileHandler`, tetapi
handler tidak pernah ditutup setelah `main()` selesai. Linux mengizinkan file
yang masih terbuka dihapus, sedangkan Windows menolaknya (WinError 32).

### 4. Perbaikan

* `sensormon/logger.py`: fungsi baru `close_logging()` yang melepas dan
  menutup semua handler root logger.
* `sensormon/cli.py`: `close_logging()` dipanggil di blok `finally` pada
  `main()`, sehingga file log selalu dilepas, baik program sukses maupun error.
* `sensormon/__init__.py`: menambahkan `logging.NullHandler()` pada logger
  package agar pesan WARNING tidak tercetak ke layar ketika fungsi dipanggil
  langsung (mis. dari unit test) sebelum logging diatur.

```python
def close_logging() -> None:
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
```

### 5. Verifikasi

Regression test `test_log_file_is_released` ditambahkan: setelah `main()`
selesai, root logger tidak lagi memiliki handler dan file log dapat dihapus.

```text
PS> python -m unittest discover -s tests -v
...
Ran 21 tests in 0.205s

OK
```

---

## Pelajaran

1. Baca traceback dari bawah (jenis exception) lalu ke atas (lokasi).
2. Log dengan `exc_info=True` menyimpan traceback walau pengguna hanya melihat
   pesan singkat.
3. Breakpoint + `p repr(...)`/`.encode()` membantu melihat karakter tak terlihat.
4. Setiap bug yang diperbaiki diberi regression test.
5. Tangkap exception yang **spesifik** dulu; `except Exception` hanya di batas
   terluar aplikasi dan wajib mencatat detail ke log.
6. Uji program di sistem operasi yang dipakai pengguna (Windows), bukan hanya di
   lingkungan pengembang; perilaku file berbeda antar-OS.
