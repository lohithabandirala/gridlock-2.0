"""Configuration for the Smart City Command Center layer."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"
MODEL_DIR = OUTPUT_DIR / "models"
REPORT_DIR = OUTPUT_DIR / "reports"
DB_DIR = OUTPUT_DIR / "db"
CACHE_DIR = OUTPUT_DIR / "cache"
DB_PATH = DB_DIR / "smart_city_command_center.sqlite"

for _path in (MODEL_DIR, REPORT_DIR, DB_DIR, CACHE_DIR):
    _path.mkdir(parents=True, exist_ok=True)

EVENT_TYPES = [
    "Cricket Match",
    "Concert",
    "Political Rally",
    "Festival",
    "Metro Maintenance",
    "VIP Movement",
    "Public Gathering",
]

WEATHER_TYPES = ["Clear", "Cloudy", "Rain", "Heavy Rain", "Windy", "Storm Warning"]

CITY_HUBS = {
    "M. Chinnaswamy Stadium": {"lat": 12.9788, "lon": 77.5990, "baseline": 92, "zone": "Central"},
    "Cubbon Park": {"lat": 12.9763, "lon": 77.5946, "baseline": 68, "zone": "Central"},
    "MG Road": {"lat": 12.9758, "lon": 77.6067, "baseline": 88, "zone": "Central"},
    "Koramangala": {"lat": 12.9352, "lon": 77.6245, "baseline": 84, "zone": "South"},
    "Indiranagar": {"lat": 12.9784, "lon": 77.6408, "baseline": 80, "zone": "East"},
    "Outer Ring Road": {"lat": 12.9197, "lon": 77.6448, "baseline": 95, "zone": "East"},
    "Yeshwanthpur": {"lat": 13.0287, "lon": 77.5467, "baseline": 72, "zone": "West"},
    "Whitefield": {"lat": 12.9698, "lon": 77.7500, "baseline": 90, "zone": "East"},
    "Hebbal": {"lat": 13.0358, "lon": 77.5970, "baseline": 82, "zone": "North"},
    "Silk Board": {"lat": 12.9171, "lon": 77.6245, "baseline": 93, "zone": "South"},
}

ROAD_LIBRARY = [
    "Outer Ring Road",
    "Hosur Road",
    "Tumkur Road",
    "Bellary Road",
    "Mysore Road",
    "MG Road",
    "Koramangala 80 Feet Road",
    "Indiranagar 100 Feet Road",
    "Old Airport Road",
    "Whitefield Main Road",
]

DEPLOYMENT_TYPES = ["Police Officers", "Barricades", "Traffic Marshals", "Emergency Units"]

DEMO_PRESET = {
    "event_type": "Cricket Match",
    "event_location": "M. Chinnaswamy Stadium",
    "crowd_size": 50000,
    "event_duration_hr": 4.0,
    "weather_condition": "Clear",
    "event_start_hour": 17,
}

# --- Scoring / heuristic configuration (previously hard-coded in service.py) ---

# Calibration factor applied to the raw model score so the headline congestion
# number lines up with the historically observed peaks used to tune the demo.
# This is a presentation calibration only, NOT a modelling correction. Set to
# 1.0 to report the raw model output unchanged.
SCORE_CALIBRATION_FACTOR = 0.965

# Risk-band thresholds applied to the (calibrated) 0-100 congestion score.
RISK_BANDS = {"LOW": 40, "MEDIUM": 70}  # < 40 LOW, < 70 MEDIUM, else HIGH

# Peak-hour windows (inclusive start hour, inclusive end hour) -> time pressure.
EVENING_PEAK = (17, 20)
MORNING_PEAK = (8, 10)
TIME_PRESSURE = {"evening": 16, "morning": 8, "offpeak": 3}

# ---------------------------------------------------------------------------
# Realistic resource-deployment plan.
#
# The formula uses a crowd-proportional base (officers ≈ 1 per 100 attendees)
# adjusted by an event-type multiplier, a congestion-severity factor, and
# weather/time-of-day modifiers.  Minimum floors prevent under-staffing for
# small gatherings and caps prevent runaway numbers.
# ---------------------------------------------------------------------------

# Per-event-type force multiplier.  VIP / political events need tighter
# security ratios; festivals / concerts are slightly lower.
EVENT_TYPE_MULTIPLIER = {
    "Cricket Match":     1.00,
    "Concert":           0.85,
    "Political Rally":   1.30,
    "Festival":          0.90,
    "Metro Maintenance": 0.50,
    "VIP Movement":      1.50,
    "Public Gathering":  1.10,
}

# Weather multiplier applied on top (bad weather → more marshals/emergency).
WEATHER_RESOURCE_MULTIPLIER = {
    "Clear":         1.00,
    "Cloudy":        1.00,
    "Rain":          1.15,
    "Heavy Rain":    1.30,
    "Windy":         1.05,
    "Storm Warning": 1.40,
}

RESOURCE_PLAN = {
    # --- Officers: 1 per 100 crowd (base), scaled by event multiplier & score
    "officers_per_crowd":  0.010,    # 1 officer per 100 people
    "officers_score_coef": 1.5,      # extra officers per congestion-score point
    "officers_min":        8,
    "officers_max":        1200,

    # --- Barricades: roughly 1 per 400 crowd
    "barricades_per_crowd":  0.0025,
    "barricades_score_coef": 0.3,
    "barricades_min":        4,
    "barricades_max":        300,

    # --- Traffic Marshals: 1 per 200 crowd
    "marshals_per_crowd":  0.005,
    "marshals_score_coef": 0.8,
    "marshals_min":        4,
    "marshals_max":        600,

    # --- Emergency Units: 1 per 10k crowd, min 2 for large events
    "emergency_per_crowd": 0.0001,
    "emergency_score_coef": 0.04,
    "emergency_min":       1,
    "emergency_max":       20,
}

# Offset (in degrees lat/lon) used to draw detour bypass geometry.
DIVERSION_OFFSET = 0.006
