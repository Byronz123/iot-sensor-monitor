"""Lapisan presentasi: mengubah data menjadi teks tabel untuk terminal.

Fungsi di sini hanya MENGEMBALIKAN string; pencetakan ke layar dilakukan
oleh ``cli.py``. Dengan begitu format laporan mudah diuji.
"""

from __future__ import annotations

from .config import STATUS_CRITICAL, STATUS_WARNING, STATUSES

READING_COLUMNS = (
    ("timestamp", "Waktu"),
    ("sensor_id", "Sensor"),
    ("location", "Lokasi"),
    ("temperature", "Suhu(°C)"),
    ("humidity", "RH(%)"),
    ("status", "Status"),
)


def format_value(value: object) -> str:
    """Ubah satu nilai menjadi teks sel tabel.

    Args:
        value: Nilai apa pun.

    Returns:
        ``-`` untuk ``None``, angka float 1 desimal, atau ``str(value)``.
    """
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def format_table(rows: list[dict], columns: tuple = READING_COLUMNS) -> str:
    """Susun list of dict menjadi tabel teks rata kiri bernomor.

    Args:
        rows: Data yang ditampilkan.
        columns: Tuple pasangan ``(kunci, judul_kolom)``.

    Returns:
        Tabel dalam bentuk string, atau pesan bila ``rows`` kosong.
    """
    if not rows:
        return "(tidak ada data yang cocok)"

    headers = ["No"] + [title for _, title in columns]
    body = [
        [str(number)] + [format_value(row.get(key)) for key, _ in columns]
        for number, row in enumerate(rows, start=1)
    ]
    widths = [max(len(cell) for cell in column) for column in zip(headers, *body)]

    def render(cells: list[str]) -> str:
        return " | ".join(cell.ljust(width) for cell, width in zip(cells, widths)).rstrip()

    separator = "-+-".join("-" * width for width in widths)
    return "\n".join([render(headers), separator, *(render(line) for line in body)])


def format_stats(stats: dict | None, unit: str) -> str:
    """Format statistik ``calculate_stats`` menjadi satu baris.

    Args:
        stats: Hasil ``calculate_stats`` atau ``None``.
        unit: Satuan, mis. ``°C``.

    Returns:
        Teks ringkas, atau ``belum ada data`` bila ``stats`` None.
    """
    if stats is None:
        return "belum ada data"
    return (
        f"min {stats['min']:.1f}{unit} | maks {stats['max']:.1f}{unit} | "
        f"rata-rata {stats['avg']:.2f}{unit}"
    )


def format_summary(summary: dict) -> str:
    """Susun laporan rekapitulasi lengkap untuk ditampilkan di terminal.

    Args:
        summary: Hasil ``processing.build_summary``.

    Returns:
        Laporan multi-baris.
    """
    quality = summary["data_quality"]
    overall = summary["overall"]
    period = summary["period"]
    thresholds = summary["thresholds"]

    lines = [
        "=" * 64,
        "LAPORAN MONITORING SUHU & KELEMBAPAN (SensorMon)",
        "=" * 64,
        f"Periode data      : {period['start'] or '-'} s.d. {period['end'] or '-'}",
        f"Ambang batas      : WASPADA >= {thresholds['warning_temp']} °C, "
        f"KRITIS >= {thresholds['critical_temp']} °C, "
        f"RH aman {thresholds['safe_humidity'][0]:.0f}-{thresholds['safe_humidity'][1]:.0f} %",
        "",
        "[Kualitas Data]",
        f"  Record dibaca     : {quality['raw_records']}",
        f"  Ditolak (invalid) : {quality['rejected_records']}",
        f"  Duplikat dihapus  : {quality['duplicates_removed']}",
        f"  Record bersih     : {quality['clean_records']}",
        "",
        "[Ringkasan Keseluruhan]",
        f"  Suhu       : {format_stats(overall['temperature'], '°C')}",
        f"  Kelembapan : {format_stats(overall['humidity'], '%')}",
        "  Status     : " + ", ".join(
            f"{status}={overall['status_count'][status]}" for status in STATUSES
        ),
        "",
        "[Rekap per Sensor]",
    ]

    sensor_rows = [
        {
            "sensor": sensor,
            "location": ", ".join(info["locations"]),
            "readings": info["readings"],
            "avg_temp": f"{info['temperature']['avg']:.2f}",
            "max_temp": info["temperature"]["max"],
            "avg_rh": f"{info['humidity']['avg']:.2f}",
            "alerts": sum(
                info["status_count"][status] for status in (STATUS_WARNING, STATUS_CRITICAL)
            ),
        }
        for sensor, info in summary["by_sensor"].items()
    ]
    sensor_columns = (
        ("sensor", "Sensor"),
        ("location", "Lokasi"),
        ("readings", "Data"),
        ("avg_temp", "Rata2 Suhu"),
        ("max_temp", "Maks Suhu"),
        ("avg_rh", "Rata2 RH"),
        ("alerts", "Peringatan"),
    )
    lines.append(format_table(sensor_rows, sensor_columns))

    first = summary["first_critical_event"]
    lines += [
        "",
        "[Kejadian KRITIS Pertama]",
        (
            f"  {first['timestamp']} - {first['sensor_id']} ({first['location']}) "
            f"suhu {first['temperature']:.1f} °C"
            if first
            else "  Tidak ada kejadian KRITIS."
        ),
        "=" * 64,
    ]
    return "\n".join(lines)


def format_rejected(rejected: list[dict], limit: int = 10) -> str:
    """Tampilkan daftar baris yang ditolak beserta alasannya.

    Args:
        rejected: Hasil ``processing.validate_records`` bagian kedua.
        limit: Jumlah maksimum baris yang ditampilkan.

    Returns:
        Teks daftar penolakan.
    """
    if not rejected:
        return "Tidak ada baris yang ditolak."
    shown = [f"  - baris {item['line']}: {item['reason']}" for item in rejected[:limit]]
    hidden = len(rejected) - limit
    if hidden > 0:
        shown.append(f"  ... dan {hidden} baris lain (lihat rejected_rows.csv)")
    return "Baris yang ditolak:\n" + "\n".join(shown)
