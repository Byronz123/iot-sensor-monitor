"""Entry point SensorMon.

Jalankan dari folder project, contoh::

    python main.py report --input data/sensor_readings.csv
"""

from sensormon.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
