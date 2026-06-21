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

# How the crowd is expected to arrive. Private vehicles load the road network far
# more than public transit, so this is one of the strongest realism levers.
ARRIVAL_MODES = ["Mostly Public Transit", "Mixed", "Mostly Private Vehicles"]
ARRIVAL_MODE_LOAD = {
    "Mostly Public Transit": 0.0,
    "Mixed": 6.0,
    "Mostly Private Vehicles": 12.0,
}

# Weekday commuter background lifts congestion; weekends and public holidays remove
# that overlap, so they reduce the predicted event congestion.
WEEKEND_RELIEF = 6.0
HOLIDAY_RELIEF = 5.0

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

ROAD_LIBRARY = {
    "Outer Ring Road": {"lat": 12.9250, "lon": 77.6440, "baseline": 95, "zone": "East"},
    "Hosur Road": {"lat": 12.9050, "lon": 77.6250, "baseline": 90, "zone": "South"},
    "Tumkur Road": {"lat": 13.0450, "lon": 77.5300, "baseline": 85, "zone": "West"},
    "Bellary Road": {"lat": 13.0550, "lon": 77.5950, "baseline": 88, "zone": "North"},
    "Mysore Road": {"lat": 12.9500, "lon": 77.5350, "baseline": 80, "zone": "West"},
    "MG Road": {"lat": 12.9750, "lon": 77.6050, "baseline": 85, "zone": "Central"},
    "Koramangala 80 Feet Road": {"lat": 12.9350, "lon": 77.6250, "baseline": 82, "zone": "South"},
    "Indiranagar 100 Feet Road": {"lat": 12.9750, "lon": 77.6400, "baseline": 80, "zone": "East"},
    "Old Airport Road": {"lat": 12.9600, "lon": 77.6500, "baseline": 85, "zone": "East"},
    "Whitefield Main Road": {"lat": 12.9700, "lon": 77.7450, "baseline": 88, "zone": "East"},
}

DEPLOYMENT_TYPES = ["Police Officers", "Barricades", "Traffic Marshals", "Emergency Units"]

DEMO_PRESET = {
    "event_type": "Cricket Match",
    "event_location": "M. Chinnaswamy Stadium",
    "crowd_size": 50000,
    "event_duration_hr": 4.0,
    "weather_condition": "Clear",
    "event_start_hour": 17,
    "arrival_mode": "Mostly Private Vehicles",
    "is_holiday": False,
}

# --- Scoring / heuristic configuration (previously hard-coded in service.py) ---

# Calibration factor applied to the raw model score so the headline congestion
# number lines up with the historically observed peaks used to tune the demo.
# This is a presentation calibration only, NOT a modelling correction. Set to
# 1.0 to report the raw model output unchanged.
SCORE_CALIBRATION_FACTOR = 1.0

# Risk-band thresholds applied to the (calibrated) 0-100 congestion score.
RISK_BANDS = {"LOW": 40, "MEDIUM": 70}  # < 40 LOW, < 70 MEDIUM, else HIGH

# Peak-hour windows (inclusive start hour, inclusive end hour) -> time pressure.
EVENING_PEAK = (17, 20)
MORNING_PEAK = (8, 10)
TIME_PRESSURE = {"evening": 16, "morning": 8, "offpeak": 3}

# Resource-deployment plan coefficients. "high_load" applies when the score or
# crowd crosses the escalation threshold; "base_load" otherwise.
RESOURCE_PLAN = {
    "escalation_score": 85,
    "escalation_crowd": 40000,
    "high_load": {
        "officers_base": 18, "officers_crowd_div": 12000, "officers_score_div": 6,
        "barricades_base": 9, "barricades_crowd_div": 18000, "barricades_score_div": 10,
        "marshals_base": 8, "marshals_crowd_div": 20000, "marshals_score_div": 12,
        "emergency_score_div": 45, "emergency_min": 2,
    },
    "base_load": {
        "officers_score_coef": 0.11, "officers_crowd_div": 10000, "officers_min": 6,
        "barricades_score_coef": 0.055, "barricades_crowd_div": 12000, "barricades_min": 3,
        "marshals_score_coef": 0.06, "marshals_crowd_div": 14000, "marshals_min": 3,
        "emergency_score_div": 55, "emergency_min": 1,
    },
}
