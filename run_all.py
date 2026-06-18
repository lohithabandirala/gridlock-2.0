# -*- coding: utf-8 -*-
"""Run the entire Day 1-5 pipeline in order.

  python run_all.py

(The Streamlit dashboard is interactive, launch separately:
  streamlit run app/dashboard.py)
"""
import sys
import pathlib
import os

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipelines"))
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

from pipelines import run_day1, run_day2, run_day3, run_day4, run_day5  # noqa: E402


def main():
    steps = [("DAY 1", run_day1.main), ("DAY 2", run_day2.main),
             ("DAY 3", run_day3.main), ("DAY 4", run_day4.main),
             ("DAY 5", run_day5.main)]
    for name, fn in steps:
        print("\n" + "#" * 64)
        print(f"# {name}")
        print("#" * 64)
        rc = fn()
        if rc != 0:
            print(f"!! {name} failed with code {rc}; stopping.")
            return rc
    print("\n" + "=" * 64)
    print("ALL DAYS COMPLETE - full pipeline ran end-to-end.")
    print("Launch dashboard:  streamlit run app/dashboard.py")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
