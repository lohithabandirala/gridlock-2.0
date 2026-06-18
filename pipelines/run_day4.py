# -*- coding: utf-8 -*-
"""Day 4 pipeline: what-if simulation (the dashboard is launched separately)."""
import sys
import _bootstrap  # noqa: F401
from src import simulate


def main():
    print("=" * 60); print("DAY 4 - WHAT-IF SIMULATION"); print("=" * 60)
    res = simulate.demo()
    print("\nScenario: Outer Ring Road full closure for 90 min, diverted to service road")
    for k, v in res.items():
        print(f"  {k:32s}: {v}")
    print("\nDashboard:  streamlit run app/dashboard.py")
    print("DAY 4 COMPLETE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
