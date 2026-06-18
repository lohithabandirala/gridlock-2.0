# -*- coding: utf-8 -*-
"""Day 2 pipeline: train predictive models on the processed dataset."""
import sys
import pandas as pd
import _bootstrap  # noqa: F401
from src import config, models


def main():
    print("=" * 60); print("DAY 2 - MODELS"); print("=" * 60)
    if not config.DATA_PROCESSED.exists():
        print("ERROR: run Day 1 first (processed dataset missing)"); return 1
    df = pd.read_csv(config.DATA_PROCESSED, low_memory=False)
    print(f"loaded processed: {df.shape[0]} rows x {df.shape[1]} cols\n")

    res = models.train_all(df)
    print("Clearance-time regressor:", res["clearance"])
    print("Priority classifier     :", res["priority"])
    print("Blackspots (DBSCAN)     :", res["blackspots"])
    print("Risk table              :", res["risk_table"])
    print("\nArtifacts -> outputs/models/ , outputs/reports/")
    print("DAY 2 COMPLETE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
