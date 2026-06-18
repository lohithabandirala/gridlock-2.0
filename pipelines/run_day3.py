# -*- coding: utf-8 -*-
"""Day 3 pipeline: manpower optimization + diversion planning."""
import sys
import pandas as pd
import _bootstrap  # noqa: F401
from src import config, optimize, diversion


def main():
    print("=" * 60); print("DAY 3 - OPTIMIZER + DIVERSION"); print("=" * 60)
    if not config.DATA_PROCESSED.exists():
        print("ERROR: run Day 1 first"); return 1
    df = pd.read_csv(config.DATA_PROCESSED, low_memory=False)

    print("\n[1/2] Manpower / barricade allocation (budget=20 officers) ...")
    opt = optimize.run(budget=20)
    print("     ", opt)

    print("\n[2/2] Building offline road graph + diversion plan ...")
    div = diversion.run(df)
    print("     ", div)

    print("\nArtifacts -> outputs/reports/manpower_allocation.csv, diversion_summary.csv")
    print("DAY 3 COMPLETE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
