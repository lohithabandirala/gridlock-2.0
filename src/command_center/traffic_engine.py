"""
Traffic Engine — Smart City Command Center
==========================================
Generates realistic, multi-factor live traffic patterns and
short-term forecasts (15 / 30 / 60-minute horizons).

Factors applied:
  1. Time-of-day diurnal curve (rush hours, off-peak, night)
  2. Weather attenuation / amplification
  3. Active event overlay (crowd size, location, arrival mode)
  4. Road closure injection (random but seeded for consistency within a minute)
  5. Historical baseline per corridor (CITY_HUBS + ROAD_LIBRARY)

Forecast model:
  - AR(1) decay to historical mean, modulated by trend velocity
  - Separate confidence bands (±1σ) per horizon
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

from .config import CITY_HUBS, ROAD_LIBRARY, WEEKEND_RELIEF


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WEATHER_IMPACT: dict[str, float] = {
    "Clear":         0.0,
    "Cloudy":        3.0,
    "Windy":         5.0,
    "Rain":         12.0,
    "Heavy Rain":   20.0,
    "Storm Warning": 28.0,
}

EVENT_AMPLIFIER: dict[str, float] = {
    "Cricket Match":    1.30,
    "Concert":          1.22,
    "Political Rally":  1.18,
    "Festival":         1.15,
    "Metro Maintenance":1.25,
    "VIP Movement":     1.20,
    "Public Gathering": 1.12,
}

ARRIVAL_MODE_FACTOR: dict[str, float] = {
    "Mostly Public Transit":  0.80,
    "Mixed":                  1.00,
    "Mostly Private Vehicles":1.30,
}

# Road closure probability per minute seed bucket (keeps closures stable for ~5 min)
CLOSURE_PROB = 0.08   # 8 % of corridors might be partially closed during a major event


# ---------------------------------------------------------------------------
# Diurnal curve helpers
# ---------------------------------------------------------------------------

def _diurnal_weight(hour: float) -> float:
    """
    Smooth diurnal congestion weight [0–35] using overlapping Gaussians:
      - Morning peak  ~08:30 (σ=0.8h)
      - Evening peak  ~18:30 (σ=1.2h)
      - Night trough  below 6
    """
    morning = 20.0 * math.exp(-((hour - 8.5) ** 2) / (2 * 0.8 ** 2))
    evening = 35.0 * math.exp(-((hour - 18.5) ** 2) / (2 * 1.2 ** 2))
    midday  =  8.0 * math.exp(-((hour - 13.0) ** 2) / (2 * 1.5 ** 2))
    night   =  2.0 * math.exp(-((hour - 23.0) ** 2) / (2 * 2.0 ** 2))
    return morning + evening + midday + night


def _is_weekend(dt: datetime) -> bool:
    return dt.weekday() >= 5


# ---------------------------------------------------------------------------
# Core traffic state
# ---------------------------------------------------------------------------

@dataclass
class CorridorState:
    name: str
    lat: float
    lon: float
    baseline: float          # 0–100 historical baseline load
    zone: str
    congestion: float = 0.0  # current computed score 0–100
    delay_min: int = 0
    severity: str = "Green"
    is_closed: bool = False
    trend: float = 0.0       # Δ vs 5 min ago (positive = worsening)
    forecast_15: float = 0.0
    forecast_30: float = 0.0
    forecast_60: float = 0.0
    vehicle_count: int = 0
    average_speed: float = 0.0
    confidence_score: float = 0.0
    last_updated: str = ""

    def severity_label(self) -> str:
        if self.is_closed:
            return "Closed"
        if self.congestion >= 80:
            return "Critical"
        if self.congestion >= 60:
            return "Red"
        if self.congestion >= 35:
            return "Yellow"
        return "Green"


# ---------------------------------------------------------------------------
# Forecast model
# ---------------------------------------------------------------------------

def _ar1_forecast(
    current: float,
    baseline: float,
    trend: float,
    minutes_ahead: int,
    noise_σ: float = 3.0,
) -> tuple[float, float, float]:
    """
    Simple AR(1) mean-reversion forecast.
    Returns (point_estimate, lower_1σ, upper_1σ).

    Decay factor: λ = exp(-minutes_ahead / 45)  — 45-min half-life
    """
    λ = math.exp(-minutes_ahead / 45.0)
    forecast = current * λ + baseline * (1 - λ) + trend * λ * minutes_ahead / 60.0
    forecast = float(np.clip(forecast, 0, 100))
    # Uncertainty grows with horizon
    sigma = noise_σ * math.sqrt(minutes_ahead / 15.0)
    return forecast, max(0.0, forecast - sigma), min(100.0, forecast + sigma)


# ---------------------------------------------------------------------------
# Traffic engine
# ---------------------------------------------------------------------------

class TrafficEngine:
    """
    Stateful traffic simulation engine.
    Call `.snapshot()` to get the current live corridor states.
    Call `.live_update()` to trigger a fresh 30-second tick update.
    """

    def __init__(self) -> None:
        self._corridors: dict[str, CorridorState] = {}
        self._last_tick: float = 0.0
        self._tick_scores: dict[str, list[float]] = {}   # rolling 5-min history
        self._build_corridors()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _build_corridors(self) -> None:
        """Build corridor map from CITY_HUBS + ROAD_LIBRARY."""
        seen: set[str] = set()
        for name, h in CITY_HUBS.items():
            self._corridors[name] = CorridorState(
                name=name, lat=h["lat"], lon=h["lon"],
                baseline=float(h["baseline"]), zone=h["zone"],
            )
            seen.add(name)
        # Add road library corridors using exact mapped dict coordinates
        if isinstance(ROAD_LIBRARY, dict):
            for road, data in ROAD_LIBRARY.items():
                if road not in seen:
                    self._corridors[road] = CorridorState(
                        name=road,
                        lat=float(data["lat"]),
                        lon=float(data["lon"]),
                        baseline=float(data["baseline"]),
                        zone=data["zone"],
                    )
                    seen.add(road)

    # ------------------------------------------------------------------
    # Core computation
    # ------------------------------------------------------------------

    def _compute_congestion(
        self,
        corridor: CorridorState,
        now: datetime,
        weather: str,
        event_type: Optional[str],
        event_location: Optional[str],
        crowd_size: int,
        arrival_mode: str,
        road_closures: set[str],
        noise_seed: int,
    ) -> float:
        """
        Multi-factor congestion score for a single corridor.
        """
        hour = now.hour + now.minute / 60.0
        rng = np.random.default_rng(seed=noise_seed + hash(corridor.name) % 99991)

        # 1. Baseline component
        base = corridor.baseline * 0.55

        # 2. Time-of-day diurnal
        diurnal = _diurnal_weight(hour) * 0.95

        # 3. Weekend relief
        weekend_adj = -WEEKEND_RELIEF if _is_weekend(now) else 0.0

        # 4. Weather impact
        weather_adj = WEATHER_IMPACT.get(weather, 0.0)

        # 5. Event proximity amplification
        event_adj = 0.0
        if event_type and event_location:
            amp = EVENT_AMPLIFIER.get(event_type, 1.0)
            mode_factor = ARRIVAL_MODE_FACTOR.get(arrival_mode, 1.0)
            crowd_factor = math.sqrt(crowd_size / 10000.0) * 4.0
            # Attenuate by distance from event hub
            same_zone = (
                CITY_HUBS.get(event_location, {}).get("zone", "") == corridor.zone
            )
            name_match = event_location in corridor.name or corridor.name in event_location
            proximity = 1.0 if name_match else (0.65 if same_zone else 0.25)
            event_adj = (amp - 1.0) * crowd_factor * mode_factor * proximity * 30.0

        # 6. Road closure
        if corridor.name in road_closures:
            closure_adj = 25.0
        else:
            closure_adj = 0.0

        # 7. Fine-grained IoT Proxy (changes every minute, simulates Kafka feed)
        from .db import get_live_sensor_volume
        noise = get_live_sensor_volume(corridor.name)

        raw = base + diurnal + weekend_adj + weather_adj + event_adj + closure_adj + noise
        return float(np.clip(raw, 0, 100))

    def _road_closures(self, now: datetime, event_score: float) -> set[str]:
        """
        Deterministically fetch road closures for the current bucket via DB.
        """
        from .db import get_live_incidents
        closed: set[str] = set(get_live_incidents())
        
        # Add event-specific closures around the hub to simulate true gridlock
        if event_score > 85:
            closed.add("MG Road") # Example structural bypass
            
        return closed

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def live_update(
        self,
        weather: str = "Clear",
        event_type: Optional[str] = None,
        event_location: Optional[str] = None,
        crowd_size: int = 0,
        arrival_mode: str = "Mixed",
        event_congestion_score: float = 0.0,
    ) -> list[CorridorState]:
        """
        Compute a fresh traffic snapshot. Should be called every 30 seconds.
        Returns a list of updated CorridorState objects.
        """
        now = datetime.now()
        noise_seed = int(time.time() // 30)   # changes every 30 s
        road_closures = self._road_closures(now, event_congestion_score)
        updated_at = now.strftime("%H:%M:%S")

        updated: list[CorridorState] = []
        for name, corridor in self._corridors.items():
            prev_score = self._tick_scores.get(name, [corridor.baseline * 0.55])[-1]

            new_score = self._compute_congestion(
                corridor, now, weather,
                event_type, event_location, crowd_size, arrival_mode,
                road_closures, noise_seed,
            )

            # Rolling 5-min history (10 × 30s ticks)
            history = self._tick_scores.get(name, [])
            history.append(new_score)
            if len(history) > 10:
                history = history[-10:]
            self._tick_scores[name] = history

            trend = new_score - prev_score

            # Forecasts
            f15, f15_lo, f15_hi = _ar1_forecast(new_score, corridor.baseline * 0.55, trend, 15)
            f30, f30_lo, f30_hi = _ar1_forecast(new_score, corridor.baseline * 0.55, trend, 30)
            f60, f60_lo, f60_hi = _ar1_forecast(new_score, corridor.baseline * 0.55, trend, 60)

            corridor.congestion     = round(new_score, 1)
            corridor.trend          = round(trend, 1)
            corridor.is_closed      = name in road_closures
            corridor.delay_min      = int(max(0, round(new_score * 1.1 + abs(trend) * 2)))
            corridor.severity       = corridor.severity_label()
            corridor.forecast_15    = round(f15, 1)
            corridor.forecast_30    = round(f30, 1)
            corridor.forecast_60    = round(f60, 1)
            corridor.vehicle_count  = int((corridor.baseline / 100.0) * 800 * (1.0 + (new_score / 100.0)))
            corridor.average_speed  = round(max(5.0, 65.0 * (1.0 - (new_score / 110.0))), 1)
            corridor.confidence_score = round(max(0.0, min(100.0, 100.0 - (f15_hi - f15_lo) * 1.5)), 1)
            corridor.last_updated   = updated_at
            updated.append(corridor)

        self._last_tick = time.time()
        return updated

    def snapshot_df(
        self,
        weather: str = "Clear",
        event_type: Optional[str] = None,
        event_location: Optional[str] = None,
        crowd_size: int = 0,
        arrival_mode: str = "Mixed",
        event_congestion_score: float = 0.0,
    ) -> pd.DataFrame:
        """Return the current corridor states as a DataFrame."""
        states = self.live_update(
            weather, event_type, event_location,
            crowd_size, arrival_mode, event_congestion_score,
        )
        return pd.DataFrame([{
            "name":         s.name,
            "lat":          s.lat,
            "lon":          s.lon,
            "zone":         s.zone,
            "congestion":   s.congestion,
            "delay_min":    s.delay_min,
            "severity":     s.severity,
            "trend":        s.trend,
            "is_closed":    s.is_closed,
            "forecast_15":  s.forecast_15,
            "forecast_30":  s.forecast_30,
            "forecast_60":  s.forecast_60,
            "vehicle_count": s.vehicle_count,
            "average_speed": s.average_speed,
            "confidence_score": s.confidence_score,
            "last_updated": s.last_updated,
        } for s in states])


# ---------------------------------------------------------------------------
# Singleton (shared across Streamlit re-runs via @st.cache_resource)
# ---------------------------------------------------------------------------

def get_engine() -> TrafficEngine:
    """Return (or create) the singleton TrafficEngine."""
    return TrafficEngine()


# ---------------------------------------------------------------------------
# Forecast summary builder (for the dashboard timeline chart)
# ---------------------------------------------------------------------------

def build_forecast_timeline(
    engine: TrafficEngine,
    weather: str = "Clear",
    event_type: Optional[str] = None,
    event_location: Optional[str] = None,
    crowd_size: int = 0,
    arrival_mode: str = "Mixed",
    event_congestion_score: float = 0.0,
) -> pd.DataFrame:
    """
    Build a timeline DataFrame covering:
      now, +15 min, +30 min, +60 min
    with city-wide mean congestion and per-corridor band.
    """
    states = engine.live_update(
        weather, event_type, event_location,
        crowd_size, arrival_mode, event_congestion_score,
    )
    now = datetime.now()

    def _mean_at(attr: str) -> float:
        return float(np.mean([getattr(s, attr) for s in states]))

    rows = [
        {"label": "Now",    "minutes": 0,  "congestion": _mean_at("congestion"),
         "lower": max(0, _mean_at("congestion") - 3),
         "upper": min(100, _mean_at("congestion") + 3)},
        {"label": "+15 min","minutes": 15, "congestion": _mean_at("forecast_15"),
         "lower": max(0, _mean_at("forecast_15") - 5),
         "upper": min(100, _mean_at("forecast_15") + 5)},
        {"label": "+30 min","minutes": 30, "congestion": _mean_at("forecast_30"),
         "lower": max(0, _mean_at("forecast_30") - 8),
         "upper": min(100, _mean_at("forecast_30") + 8)},
        {"label": "+60 min","minutes": 60, "congestion": _mean_at("forecast_60"),
         "lower": max(0, _mean_at("forecast_60") - 12),
         "upper": min(100, _mean_at("forecast_60") + 12)},
    ]
    return pd.DataFrame(rows)
