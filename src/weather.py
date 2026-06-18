# -*- coding: utf-8 -*-
"""Weather enrichment using Open-Meteo with an offline fallback.

The project only needs daily weather context for Bengaluru, so we fetch a
single daily archive series for the date range in the dataset and join it back
on the event date. If the network is unavailable, we fall back to a deterministic
seasonal proxy so the pipeline still runs offline.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from . import config

try:  # requests is optional but preferred when present
    import requests
except Exception:  # pragma: no cover
    requests = None


def _cache_path(start_date: str, end_date: str) -> Path:
    return config.CACHE_DIR / f"weather_{start_date}_{end_date}.json"


def _fallback_weather(dates: pd.DatetimeIndex) -> pd.DataFrame:
    rows = []
    for ts in dates.normalize().unique():
        day = pd.Timestamp(ts)
        month = int(day.month)
        monsoon = month in config.MONSOON_MONTHS
        rain = 10.0 if monsoon else 1.5
        if day.dayofweek >= 5:
            rain += 0.8
        temp_max = 27.0 + 4.0 * np.sin((month - 1) / 12 * 2 * np.pi)
        temp_min = temp_max - 8.0
        wind = 10.0 + (2.0 if monsoon else 0.0)
        rows.append({
            "event_date": day.date().isoformat(),
            "daily_rain_mm": round(float(rain), 1),
            "daily_temp_max_c": round(float(temp_max), 1),
            "daily_temp_min_c": round(float(temp_min), 1),
            "daily_wind_kph": round(float(wind), 1),
            "weather_live": False,
        })
    return pd.DataFrame(rows)


def fetch_daily_weather(start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch daily Bengaluru weather from Open-Meteo archive API.

    Returns a dataframe with one row per date. Falls back to a seasonal proxy if
    the request fails for any reason.
    """
    cache = _cache_path(start_date, end_date)
    if cache.exists():
        try:
            return pd.DataFrame(json.loads(cache.read_text()))
        except Exception:
            pass

    if requests is None:
        return _fallback_weather(pd.date_range(start_date, end_date, freq="D"))

    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": config.CITY_CENTER[0],
        "longitude": config.CITY_CENTER[1],
        "start_date": start_date,
        "end_date": end_date,
        "daily": [
            "precipitation_sum",
            "temperature_2m_max",
            "temperature_2m_min",
            "windspeed_10m_max",
        ],
        "timezone": "Asia/Kolkata",
    }
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        daily = payload.get("daily", {})
        dates = daily.get("time", [])
        out = pd.DataFrame({
            "event_date": dates,
            "daily_rain_mm": daily.get("precipitation_sum", []),
            "daily_temp_max_c": daily.get("temperature_2m_max", []),
            "daily_temp_min_c": daily.get("temperature_2m_min", []),
            "daily_wind_kph": daily.get("windspeed_10m_max", []),
        })
        out["weather_live"] = True
        out = out.fillna(0)
        cache.write_text(out.to_json(orient="records"))
        return out
    except Exception:
        return _fallback_weather(pd.date_range(start_date, end_date, freq="D"))


def join_weather(df: pd.DataFrame, date_col: str = "start_datetime") -> pd.DataFrame:
    """Join daily weather context to a dataframe with datetime data."""
    out = df.copy()
    if date_col not in out.columns or out[date_col].dropna().empty:
        out["daily_rain_mm"] = 0.0
        out["daily_temp_max_c"] = 0.0
        out["daily_temp_min_c"] = 0.0
        out["daily_wind_kph"] = 0.0
        out["weather_live"] = False
        return out

    dates = pd.to_datetime(out[date_col], errors="coerce")
    start_date = dates.min().date().isoformat()
    end_date = dates.max().date().isoformat()
    weather = fetch_daily_weather(start_date, end_date)
    weather["event_date"] = pd.to_datetime(weather["event_date"], errors="coerce").dt.date
    out["event_date"] = dates.dt.date
    out = out.merge(weather, on="event_date", how="left")
    for col in ["daily_rain_mm", "daily_temp_max_c", "daily_temp_min_c", "daily_wind_kph"]:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    if "weather_live" in out.columns:
        out["weather_live"] = pd.Series(out["weather_live"], index=out.index).astype("boolean").fillna(False).astype(bool)
    else:
        out["weather_live"] = False
    return out
