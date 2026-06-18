# -*- coding: utf-8 -*-
"""Day 1 pipeline: load -> clean -> feature-engineer -> EDA -> save processed dataset.

Run from project root:  python run_day1.py
"""
import sys
import _bootstrap  # noqa: F401  (adds project root to sys.path)
from src import config, data_loader, features, eda


def main():
    print("=" * 60)
    print("DAY 1 PIPELINE - Predictive Incident & Response platform")
    print("=" * 60)

    print("\n[1/4] Loading + cleaning raw CSV ...")
    df = data_loader.load_clean()
    print(f"      loaded {df.shape[0]} rows x {df.shape[1]} cols")

    print("\n[2/4] Engineering features ...")
    df = features.build_features(df)
    new_cols = ["hour", "dow", "is_weekend", "month", "is_monsoon", "time_slot",
                "clearance_min", "junction_freq", "corridor_freq", "zone_freq",
                "text_len", "kw_breakdown"]
    print(f"      added features: {', '.join(c for c in new_cols if c in df.columns)}")

    print("\n[3/4] Generating EDA figures + report ...")
    figs = eda.make_figures(df)
    report = eda.make_report(df, figs)
    print(f"      {len(figs)} figures -> outputs/figures/")
    print(f"      report      -> outputs/reports/day1_eda_report.md")

    print("\n[4/4] Saving processed dataset ...")
    df.to_csv(config.DATA_PROCESSED, index=False)
    print(f"      processed   -> {config.DATA_PROCESSED.relative_to(config.ROOT)}  "
          f"({df.shape[0]} rows x {df.shape[1]} cols)")

    print("\n" + "-" * 60)
    print("REPORT PREVIEW")
    print("-" * 60)
    print(report)
    print("\nDAY 1 COMPLETE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
