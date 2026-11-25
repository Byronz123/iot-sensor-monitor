"""Memungkinkan package dijalankan dengan ``python -m sensormon``."""

from .cli import main

raise SystemExit(main())
