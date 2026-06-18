# -*- coding: utf-8 -*-
"""Phase 2 feature engineering: derive the columns the Day-2 models will use."""
import numpy as np
import pandas as pd
from . import config, weather


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    s = df["start_datetime"]
    df["event_date"] = s.dt.date
    df["hour"] = s.dt.hour
    df["dow"] = s.dt.dayofweek                 # 0=Mon
    df["is_weekend"] = df["dow"].isin([5, 6])
    df["month"] = s.dt.month
    df["is_monsoon"] = df["month"].isin(config.MONSOON_MONTHS)

    # coarse time-slot used by the forecasting model
    def slot(h):
        if pd.isna(h):
            return np.nan
        h = int(h)
        if 6 <= h < 10:   return "morning_peak"
        if 10 <= h < 16:  return "midday"
        if 16 <= h < 21:  return "evening_peak"
        return "night"
    df["time_slot"] = df["hour"].map(slot)
    return df


def add_weather_features(df: pd.DataFrame) -> pd.DataFrame:
    """Join daily Bengaluru weather and derive a compact weather risk signal."""
    df = weather.join_weather(df, "start_datetime")
    rain = pd.to_numeric(df.get("daily_rain_mm", 0), errors="coerce").fillna(0.0)
    wind = pd.to_numeric(df.get("daily_wind_kph", 0), errors="coerce").fillna(0.0)
    temp_span = (
        pd.to_numeric(df.get("daily_temp_max_c", 0), errors="coerce").fillna(0.0)
        - pd.to_numeric(df.get("daily_temp_min_c", 0), errors="coerce").fillna(0.0)
    ).abs()
    df["weather_risk_score"] = (
        (rain.clip(0, 50) * 1.8)
        + (wind.clip(0, 40) * 0.7)
        + (temp_span.clip(0, 20) * 0.5)
    ).round(2)
    df["rain_alert"] = rain.ge(10.0) | df["is_monsoon"].astype(bool)
    return df


def add_clearance_time(df: pd.DataFrame) -> pd.DataFrame:
    """Minutes from report (start) to resolution/closure - the target for the ETA model."""
    df = df.copy()
    end = df["resolved_datetime"].fillna(df["closed_datetime"]).fillna(df["end_datetime"])
    delta = (end - df["start_datetime"]).dt.total_seconds() / 60.0
    # guard against negative / absurd values (data noise)
    delta = delta.where((delta >= 0) & (delta <= 7 * 24 * 60))
    df["clearance_min"] = delta
    return df


def add_frequency_features(df: pd.DataFrame) -> pd.DataFrame:
    """How chronically problematic each location is - a strong blackspot signal."""
    df = df.copy()
    for col in ["junction", "corridor", "zone", "police_station"]:
        if col in df.columns:
            counts = df[col].value_counts()
            df[f"{col}_freq"] = df[col].map(counts).fillna(0).astype(int)
    return df


def add_text_keyword_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Lightweight, free (no model download) text signals from the free-text fields.
    A proper sentence-transformer embedding is added on Day 2."""
    df = df.copy()
    text = (
        df.get("description", "").fillna("") + " "
        + df.get("comment", "").fillna("") + " "
        + df.get("reason_breakdown", "").fillna("")
    ).str.lower()
    df["text_len"] = text.str.strip().str.len()
    for flag, kws in config.TEXT_KEYWORDS.items():
        pattern = "|".join(kws)
        df[flag] = text.str.contains(pattern, regex=True, na=False)
    return df


def add_planning_placeholders(df: pd.DataFrame) -> pd.DataFrame:
    """Initialize columns consumed later by impact/anomaly scoring."""
    df = df.copy()
    for col in ["planned_impact_baseline", "surge_score"]:
        if col not in df.columns:
            df[col] = 0.0
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = add_time_features(df)
    df = add_clearance_time(df)
    df = add_frequency_features(df)
    df = add_weather_features(df)
    df = add_text_keyword_flags(df)
    df = add_planning_placeholders(df)
    return df
