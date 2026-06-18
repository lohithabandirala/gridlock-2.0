# -*- coding: utf-8 -*-
"""Exploratory data analysis: text report + figures (matplotlib only, free)."""
import matplotlib
matplotlib.use("Agg")              # no display needed
import matplotlib.pyplot as plt
import pandas as pd
from . import config


def _save_bar(series, title, fname, xlabel="count", top=12):
    series = series.head(top)[::-1]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.barh(series.index.astype(str), series.values, color="#0d6efd")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    fig.tight_layout()
    fig.savefig(config.FIG_DIR / fname, dpi=110)
    plt.close(fig)


def make_figures(df: pd.DataFrame) -> list:
    figs = []
    if "event_cause" in df:
        _save_bar(df["event_cause"].value_counts(), "Incidents by cause", "cause.png"); figs.append("cause.png")
    if "zone" in df:
        _save_bar(df["zone"].value_counts(), "Incidents by zone", "zone.png"); figs.append("zone.png")
    if "corridor" in df:
        _save_bar(df["corridor"].value_counts(), "Incidents by corridor", "corridor.png"); figs.append("corridor.png")

    # hour-of-day distribution
    if "hour" in df:
        fig, ax = plt.subplots(figsize=(7, 4.2))
        df["hour"].dropna().astype(int).value_counts().sort_index().plot(kind="bar", ax=ax, color="#6f42c1")
        ax.set_title("Incidents by hour of day"); ax.set_xlabel("hour"); ax.set_ylabel("count")
        fig.tight_layout(); fig.savefig(config.FIG_DIR / "hour.png", dpi=110); plt.close(fig)
        figs.append("hour.png")

    # clearance-time histogram
    if "clearance_min" in df:
        ct = df["clearance_min"].dropna()
        ct = ct[ct <= ct.quantile(0.95)]      # trim long tail for readability
        fig, ax = plt.subplots(figsize=(7, 4.2))
        ax.hist(ct, bins=40, color="#0d9689")
        ax.set_title("Clearance time (min, <=95th pct)"); ax.set_xlabel("minutes"); ax.set_ylabel("count")
        fig.tight_layout(); fig.savefig(config.FIG_DIR / "clearance.png", dpi=110); plt.close(fig)
        figs.append("clearance.png")
    return figs


def make_report(df: pd.DataFrame, figs: list) -> str:
    n = len(df)
    lines = []
    A = lines.append
    A("# Day 1 EDA Report - Astram Incident Data\n")
    A(f"- Total records: **{n}**")
    A(f"- Columns: **{df.shape[1]}**")
    if "event_type" in df:
        vc = df["event_type"].value_counts(dropna=False)
        unplanned = vc.get("unplanned", 0)
        A(f"- Unplanned vs planned: **{unplanned} unplanned** "
          f"({unplanned/n*100:.1f}%) / {vc.get('planned',0)} planned")
    if "requires_road_closure" in df:
        rc = df["requires_road_closure"].sum()
        A(f"- Require road closure: **{int(rc)}** ({rc/n*100:.1f}%)")
    if "clearance_min" in df:
        ct = df["clearance_min"].dropna()
        A(f"- Clearance time available for **{len(ct)}** rows | "
          f"median **{ct.median():.0f} min**, mean **{ct.mean():.0f} min**")
    A("")
    A("## Top causes")
    if "event_cause" in df:
        for k, v in df["event_cause"].value_counts().head(8).items():
            A(f"  - {k}: {v}")
    A("\n## Data completeness (non-null %) - key columns")
    for col in ["start_datetime", "latitude", "junction", "corridor", "zone",
                "clearance_min", "veh_type", "priority"]:
        if col in df.columns:
            pct = df[col].notna().mean() * 100
            A(f"  - {col}: {pct:.1f}%")
    A("\n## Engineered features added")
    for col in ["hour", "dow", "is_weekend", "month", "is_monsoon", "time_slot",
                "clearance_min", "junction_freq", "corridor_freq", "zone_freq",
                "text_len", "kw_breakdown", "kw_water", "kw_accident"]:
        if col in df.columns:
            A(f"  - {col}")
    A("\n## Figures generated")
    for f in figs:
        A(f"  - outputs/figures/{f}")
    report = "\n".join(lines)
    (config.REPORT_DIR / "day1_eda_report.md").write_text(report, encoding="utf-8")
    return report
