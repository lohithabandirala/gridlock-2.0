# -*- coding: utf-8 -*-
"""Central paths & constants for the Predictive Incident & Response platform."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw" / "astram_events.csv"
DATA_PROCESSED = ROOT / "data" / "processed" / "events_features.csv"
FIG_DIR = ROOT / "outputs" / "figures"
REPORT_DIR = ROOT / "outputs" / "reports"
MODEL_DIR = ROOT / "outputs" / "models"
DB_DIR = ROOT / "outputs" / "db"
CACHE_DIR = ROOT / "outputs" / "cache"
DB_PATH = DB_DIR / "learning.sqlite"

for _d in (FIG_DIR, REPORT_DIR, MODEL_DIR, DB_DIR, CACHE_DIR, DATA_PROCESSED.parent):
    _d.mkdir(parents=True, exist_ok=True)

# Values treated as missing in this dataset
NA_TOKENS = {"", "NULL", "null", "None", "NaN", "nan"}

# Timestamp columns present in the raw data
TIME_COLS = [
    "start_datetime", "end_datetime", "modified_datetime", "created_date",
    "closed_datetime", "resolved_datetime",
]

# Bengaluru monsoon months (heavy rain -> waterlogging / tree_fall spikes)
MONSOON_MONTHS = {6, 7, 8, 9, 10}

# Bengaluru city center used for weather and road-network fallbacks.
CITY_CENTER = (12.9716, 77.5946)
OSM_RADIUS_KM = 12.0

# Keywords used for lightweight (free, no-download) text features
TEXT_KEYWORDS = {
    "kw_breakdown": ["breakdown", "break down", "starting problem", "mechanical", "engine"],
    "kw_tyre":      ["puncture", "puncher", "tyre", "tire", "tire burst", "flat"],
    "kw_accident":  ["accident", "collision", "hit", "dash"],
    "kw_water":     ["water", "flood", "logging", "rain"],
    "kw_tree":      ["tree", "branch", "fall"],
}

# Free-text columns fused for TF-IDF (Day 2 NLP, all local / free)
TEXT_COLS = ["description", "comment", "reason_breakdown"]

# Feature sets used by Day-2 models
CAT_FEATURES = ["event_cause", "veh_type", "time_slot", "corridor", "zone",
                "is_monsoon", "is_weekend", "requires_road_closure"]
NUM_FEATURES = ["hour", "dow", "month", "junction_freq", "corridor_freq",
                "zone_freq", "text_len", "daily_rain_mm", "daily_temp_max_c",
                "daily_temp_min_c", "daily_wind_kph", "weather_risk_score",
                "planned_impact_baseline", "surge_score"]
