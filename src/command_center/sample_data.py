"""Synthetic smart-city traffic data used for the demo dashboard."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import (
    CITY_HUBS,
    EVENT_TYPES,
    WEATHER_TYPES,
    ROAD_LIBRARY,
    REPORT_DIR,
    ARRIVAL_MODES,
    ARRIVAL_MODE_LOAD,
    WEEKEND_RELIEF,
    HOLIDAY_RELIEF,
)


@dataclass(frozen=True)
class RoadPoint:
    name: str
    lat: float
    lon: float
    severity: str
    expected_delay_min: int
    congestion: int


def _event_weights(event_type: str) -> float:
    return {
        "Cricket Match": 26,
        "Concert": 22,
        "Political Rally": 19,
        "Festival": 18,
        "Metro Maintenance": 12,
        "VIP Movement": 16,
        "Public Gathering": 14,
    }.get(event_type, 15)


def _mode_weights(mode: str) -> float:
    return ARRIVAL_MODE_LOAD.get(mode, 6.0)


def _weather_weights(weather: str) -> float:
    return {
        "Clear": 0,
        "Cloudy": 3,
        "Rain": 8,
        "Heavy Rain": 14,
        "Windy": 4,
        "Storm Warning": 18,
    }.get(weather, 4)


def _hour_weights(hour: int) -> float:
    if 17 <= hour <= 20:
        return 16
    if 8 <= hour <= 10:
        return 9
    if 12 <= hour <= 15:
        return 6
    return 2


def _location_row(location: str) -> dict:
    base = CITY_HUBS.get(location, CITY_HUBS["MG Road"])
    return {
        "location": location,
        "lat": base["lat"],
        "lon": base["lon"],
        "location_baseline": base["baseline"],
        "zone": base["zone"],
    }


def _load_report_roads(limit: int = 6) -> list[str]:
    """Prefer roads/corridors surfaced by the existing Day-2 reports."""
    candidates: list[str] = []
    for filename, column in (("blackspots.csv", "corridor"), ("corridor_risk.csv", "corridor")):
        path = REPORT_DIR / filename
        if not path.exists():
            continue
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if column in df.columns:
            values = (
                df[column]
                .dropna()
                .astype(str)
                .value_counts()
                .index.tolist()
            )
            candidates.extend(values)
    out = []
    seen = set()
    for name in candidates + ROAD_LIBRARY:
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
        if len(out) >= limit:
            break
    return out


def historical_traffic_profile(location: str, hour: int) -> float:
    base = CITY_HUBS.get(location, CITY_HUBS["MG Road"])["baseline"]
    rush = _hour_weights(hour)
    return round(min(100, base * 0.55 + rush * 2.5), 1)


def build_training_frame(n_rows: int = 2200, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    locations = list(CITY_HUBS.keys())
    rows = []
    for idx in range(n_rows):
        event_type = rng.choice(EVENT_TYPES, p=[0.22, 0.12, 0.14, 0.18, 0.12, 0.08, 0.14])
        location = rng.choice(locations)
        weather = rng.choice(WEATHER_TYPES, p=[0.42, 0.16, 0.18, 0.09, 0.09, 0.06])
        hour = int(rng.integers(6, 23))
        crowd = int(np.clip(rng.normal(loc=_event_weights(event_type) * 1800, scale=4200), 120, 80000))
        duration = int(np.clip(rng.normal(loc=3.0 + crowd / 22000, scale=1.2), 1, 10))
        arrival_mode = rng.choice(ARRIVAL_MODES, p=[0.30, 0.45, 0.25])
        is_weekend = int(rng.random() < 0.30)
        is_holiday = int(rng.random() < 0.08)
        hist = historical_traffic_profile(location, hour)
        score = (
            8
            + _event_weights(event_type) * 0.65
            + math.sqrt(crowd / 1000.0) * 3.6
            + _weather_weights(weather) * 0.85
            + _hour_weights(hour) * 1.25
            + hist * 0.18
            + duration * 1.8
            + _mode_weights(arrival_mode) * (0.6 + crowd / 55000.0)
            - is_weekend * WEEKEND_RELIEF
            - is_holiday * HOLIDAY_RELIEF
            + rng.normal(0, 4.0)
        )
        congestion = float(np.clip(score, 0, 100))
        roads_hit = int(np.clip(round(congestion / 22 + rng.normal(0, 0.6)), 1, 6))
        peak_hour = int(np.clip(hour + max(1, duration // 2), 6, 23))
        rows.append(
            {
                "id": f"SIM{idx:05d}",
                "event_type": event_type,
                "event_location": location,
                "event_lat": CITY_HUBS[location]["lat"] + rng.normal(0, 0.01),
                "event_lon": CITY_HUBS[location]["lon"] + rng.normal(0, 0.01),
                "crowd_size": crowd,
                "event_hour": hour,
                "event_duration_hr": duration,
                "weather_condition": weather,
                "arrival_mode": arrival_mode,
                "is_weekend": is_weekend,
                "is_holiday": is_holiday,
                "historical_traffic": hist,
                "location_baseline": CITY_HUBS[location]["baseline"],
                "time_pressure": _hour_weights(hour),
                "road_density": min(100, CITY_HUBS[location]["baseline"] + rng.integers(0, 12)),
                "congestion_score": congestion,
                "affected_roads": roads_hit,
                "peak_hour": peak_hour,
                "delay_min": round(congestion * 1.8 + roads_hit * 7 + rng.normal(0, 15), 1),
            }
        )
    return pd.DataFrame(rows)


def build_road_snapshot(score: float, location: str, seed: int | None = None) -> pd.DataFrame:
    from .db import get_live_sensor_volume
    from .config import ROAD_LIBRARY, CITY_HUBS
    import time
    
    hub = CITY_HUBS.get(location, CITY_HUBS["MG Road"])
    rows = []
    
    # We will pick roads that are physically close to the event location
    candidates = []
    for name, data in ROAD_LIBRARY.items():
        from .spatial_engine import haversine
        dist = haversine(hub["lat"], hub["lon"], data["lat"], data["lon"])
        if dist < 12.0: # Only roads within 12km
            candidates.append((name, data, dist))
            
    # Sort by distance and take the closest 6
    candidates.sort(key=lambda x: x[2])
    base_roads = candidates[:6]
    
    for idx, (name, data, dist) in enumerate(base_roads):
        severity = "Green"
        
        # Read live volume proxy from DB instead of random noise
        # get_live_sensor_volume expects a string, so we pass the road name.
        # It returns a jitter, so we add it to baseline.
        live_vol = data["baseline"] + get_live_sensor_volume(name)
        
        # Local score is influenced by live volume and proximity to the event (dist)
        dist_factor = max(0.2, 1.0 - (dist / 12.0))
        local_score = float(np.clip(score * dist_factor * (live_vol / data["baseline"]), 0, 100))
        
        if local_score >= 70:
            severity = "Red"
        elif local_score >= 40:
            severity = "Yellow"
        
        # Exact delay is a function of the local congestion minus baseline, bounded
        delay = int(max(4, round((local_score - 20) * 0.4)))
        
        rows.append(
            RoadPoint(
                name=name,
                lat=data["lat"], # Exact coordinates!
                lon=data["lon"], # Exact coordinates!
                severity=severity,
                expected_delay_min=delay,
                congestion=int(round(local_score)),
            ).__dict__
        )
    return pd.DataFrame(rows)


