# -*- coding: utf-8 -*-
"""Planned-event impact scoring.

The score is a 0-100 operational risk estimate for planned events. It combines
road-closure burden, corridor congestion, weather, peak-hour timing and the
predicted clearance time from the trained Day-2 model when available.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, models

CAUSE_WEIGHTS = {
    "construction": 0.85,
    "public_event": 0.95,
    "political_event": 1.0,
    "road_work": 0.9,
    "utility_work": 0.8,
}

TIME_WEIGHTS = {
    "morning_peak": 1.0,
    "evening_peak": 1.0,
    "midday": 0.65,
    "night": 0.45,
}


def _scale(series: pd.Series, lo: float = 0.0, hi: float = 1.0) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").fillna(0.0)
    if s.max() == s.min():
        return pd.Series(np.full(len(s), lo), index=s.index)
    scaled = (s - s.min()) / (s.max() - s.min())
    return scaled * (hi - lo) + lo


def score_planned_events(df: pd.DataFrame, corridor_risk: pd.DataFrame | None = None) -> pd.DataFrame:
    planned = df[df.get("event_type", "").eq("planned")].copy()
    if planned.empty:
        empty = pd.DataFrame(columns=[
            "id", "corridor", "junction", "time_slot", "daily_rain_mm",
            "predicted_clearance_min", "impact_score", "impact_band",
        ])
        empty.to_csv(config.REPORT_DIR / "planned_event_impact.csv", index=False)
        (config.REPORT_DIR / "planned_event_impact_summary.json").write_text(
            json.dumps({"status": "empty"}, indent=2)
        )
        return empty

    if corridor_risk is not None and not corridor_risk.empty:
        corridor_map = corridor_risk.groupby("corridor")["risk_score"].max().to_dict()
        planned["planned_impact_baseline"] = planned["corridor"].map(corridor_map).fillna(0.0)
    else:
        planned["planned_impact_baseline"] = _scale(planned.get("corridor_freq", 0), 0, 100)

    if "clearance_regressor.joblib" in {p.name for p in config.MODEL_DIR.glob("*.joblib")}:
        try:
            planned["predicted_clearance_min"] = models.predict_clearance_minutes(planned)
        except Exception:
            planned["predicted_clearance_min"] = pd.to_numeric(planned.get("clearance_min", 0), errors="coerce").fillna(0.0)
    else:
        planned["predicted_clearance_min"] = pd.to_numeric(planned.get("clearance_min", 0), errors="coerce").fillna(0.0)

    weather = _scale(planned.get("daily_rain_mm", 0), 0, 100)
    clearance = _scale(planned["predicted_clearance_min"], 0, 100)
    closure = planned.get("requires_road_closure", False).astype(float).fillna(0.0) * 100
    time_bonus = planned.get("time_slot", "midday").map(TIME_WEIGHTS).fillna(0.6) * 100
    cause_bonus = planned.get("event_cause", "").map(CAUSE_WEIGHTS).fillna(0.6) * 100
    corridor = _scale(planned["planned_impact_baseline"], 0, 100)

    score = (
        0.30 * corridor +
        0.22 * closure +
        0.18 * clearance +
        0.15 * weather +
        0.08 * time_bonus +
        0.07 * cause_bonus
    )
    planned["impact_score"] = score.clip(0, 100).round(1)
    planned["impact_band"] = pd.cut(
        planned["impact_score"],
        bins=[-1, 33, 66, 100],
        labels=["Low", "Medium", "High"],
    ).astype(str)

    cols = [
        c for c in [
            "id", "event_type", "event_cause", "corridor", "junction", "zone",
            "time_slot", "requires_road_closure", "daily_rain_mm",
            "predicted_clearance_min", "planned_impact_baseline", "impact_score",
            "impact_band",
        ] if c in planned.columns
    ]
    out = planned[cols].sort_values("impact_score", ascending=False)
    out.to_csv(config.REPORT_DIR / "planned_event_impact.csv", index=False)
    summary = {
        "status": "ok",
        "rows": int(len(out)),
        "high": int((out["impact_band"] == "High").sum()),
        "medium": int((out["impact_band"] == "Medium").sum()),
        "low": int((out["impact_band"] == "Low").sum()),
        "max_score": float(out["impact_score"].max()),
        "median_score": float(out["impact_score"].median()),
    }
    (config.REPORT_DIR / "planned_event_impact_summary.json").write_text(
        json.dumps(summary, indent=2)
    )
    return out

