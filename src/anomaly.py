# -*- coding: utf-8 -*-
"""Surge / anomaly detection for unplanned incidents.

This is a lightweight offline detector that flags corridor/time-slot/date
combinations whose incident counts are materially above the historical median.
It is designed as a practical stand-in for a streaming early-warning layer.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import config


def _robust_zscore(value: float, median: float, mad: float) -> float:
    if mad <= 0:
        return 0.0
    return 0.6745 * (value - median) / mad


def detect_surge(df: pd.DataFrame, min_incidents: int = 3) -> pd.DataFrame:
    d = df[df.get("event_type", "").eq("unplanned")].copy()
    if d.empty or "start_datetime" not in d.columns:
        out = pd.DataFrame(columns=[
            "event_date", "corridor", "time_slot", "incidents", "baseline",
            "z_score", "surge_score", "severity",
        ])
        out.to_csv(config.REPORT_DIR / "surge_alerts.csv", index=False)
        (config.REPORT_DIR / "surge_summary.json").write_text(json.dumps({"status": "empty"}, indent=2))
        return out

    d["event_date"] = pd.to_datetime(d["start_datetime"], errors="coerce").dt.date
    grp = d.groupby(["event_date", "corridor", "time_slot"]).size().reset_index(name="incidents")
    if grp.empty:
        return grp

    stats = grp.groupby(["corridor", "time_slot"])["incidents"].agg(["median", "count"]).reset_index()
    mad = grp.groupby(["corridor", "time_slot"])["incidents"].apply(
        lambda s: float(np.median(np.abs(s - np.median(s))))
    ).reset_index(name="mad")
    out = grp.merge(stats, on=["corridor", "time_slot"], how="left").merge(
        mad, on=["corridor", "time_slot"], how="left"
    )
    out["baseline"] = out["median"].fillna(0.0)
    out["z_score"] = out.apply(lambda r: _robust_zscore(r["incidents"], r["baseline"], r["mad"]), axis=1)
    out["surge_score"] = (50 + 10 * out["z_score"]).clip(0, 100).round(1)
    out = out[out["incidents"] >= min_incidents].copy()
    out = out.sort_values(["surge_score", "incidents"], ascending=False)
    out["severity"] = pd.cut(
        out["surge_score"],
        bins=[-1, 40, 70, 100],
        labels=["Watch", "Alert", "Critical"],
    ).astype(str)
    cols = ["event_date", "corridor", "time_slot", "incidents", "baseline", "z_score", "surge_score", "severity"]
    out[cols].to_csv(config.REPORT_DIR / "surge_alerts.csv", index=False)
    summary = {
        "status": "ok",
        "rows": int(len(out)),
        "critical": int((out["severity"] == "Critical").sum()),
        "alert": int((out["severity"] == "Alert").sum()),
        "watch": int((out["severity"] == "Watch").sum()),
    }
    (config.REPORT_DIR / "surge_summary.json").write_text(json.dumps(summary, indent=2))
    return out[cols]

