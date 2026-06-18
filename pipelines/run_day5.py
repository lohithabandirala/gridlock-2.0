# -*- coding: utf-8 -*-
"""Day 5 pipeline: self-learning loop (predicted vs actual -> SQLite report card)."""
import sys
import pandas as pd
import _bootstrap  # noqa: F401
from src import config, learn


def main():
    print("=" * 60); print("DAY 5 - SELF-LEARNING LOOP"); print("=" * 60)
    if not config.DATA_PROCESSED.exists():
        print("ERROR: run Day 1 first"); return 1
    df = pd.read_csv(config.DATA_PROCESSED, low_memory=False)
    card = learn.log_and_score(df)
    print("\nReport card:", card)
    print("Logged to  ->", config.DB_PATH.relative_to(config.ROOT))
    print("DAY 5 COMPLETE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
