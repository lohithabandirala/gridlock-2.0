# -*- coding: utf-8 -*-
"""Put the project root on sys.path so `from src import ...` works when a
pipeline is executed directly (python pipelines/run_dayX.py)."""
import sys
import pathlib
import os

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
