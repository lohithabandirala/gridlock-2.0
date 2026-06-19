"""Business logic for dashboard, API and AI command responses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import ceil

import numpy as np
import pandas as pd

from .config import (
    CITY_HUBS,
    DEMO_PRESET,
    DIVERSION_OFFSET,
    EVENT_TYPE_MULTIPLIER,
    EVENING_PEAK,
    MORNING_PEAK,
    RESOURCE_PLAN,
    RISK_BANDS,
    ROAD_LIBRARY,
    SCORE_CALIBRATION_FACTOR,
    TIME_PRESSURE,
    WEATHER_RESOURCE_MULTIPLIER,
)
from .db import log_prediction
from .ml import load_model, predict_one, train
from .sample_data import build_road_snapshot, build_trend_frame, historical_traffic_profile


def _risk_level(score: float) -> str:
    if score < RISK_BANDS["LOW"]:
        return "LOW"
    if score < RISK_BANDS["MEDIUM"]:
        return "MEDIUM"
    return "HIGH"


@dataclass
class EventRequest:
    event_type: str
    event_location: str
    crowd_size: int
    event_start_time: str
    event_duration_hr: float
    weather_condition: str


def ensure_model():
    model = load_model()
    if model is None:
        train()
        model = load_model()
    return model


def _parse_hour(value: str) -> int:
    try:
        dt = datetime.fromisoformat(value)
        return dt.hour
    except Exception:
        return 18


def _prediction_input(req: EventRequest) -> dict:
    hour = _parse_hour(req.event_start_time)
    return {
        "event_type": req.event_type,
        "event_location": req.event_location,
        "weather_condition": req.weather_condition,
        "crowd_size": int(req.crowd_size),
        "event_hour": hour,
        "event_duration_hr": float(req.event_duration_hr),
        "historical_traffic": historical_traffic_profile(req.event_location, hour),
        "location_baseline": CITY_HUBS.get(req.event_location, CITY_HUBS["MG Road"])["baseline"],
        "time_pressure": (
            TIME_PRESSURE["evening"] if EVENING_PEAK[0] <= hour <= EVENING_PEAK[1]
            else TIME_PRESSURE["morning"] if MORNING_PEAK[0] <= hour <= MORNING_PEAK[1]
            else TIME_PRESSURE["offpeak"]
        ),
        "road_density": min(100, CITY_HUBS.get(req.event_location, CITY_HUBS["MG Road"])["baseline"] + 8),
    }


def _resource_plan(score: float, crowd_size: int,
                   event_type: str = "Public Gathering",
                   weather: str = "Clear") -> dict:
    """Crowd-proportional resource allocation with event and weather scaling.

    Base ratios (per RESOURCE_PLAN):
        Officers  ≈ 1 per 100 attendees
        Marshals  ≈ 1 per 200 attendees
        Barricades ≈ 1 per 400 attendees
        Emergency ≈ 1 per 10 000 attendees

    These are then multiplied by:
        * event-type multiplier  (VIP 1.5×, Concert 0.85×, etc.)
        * weather multiplier     (Storm Warning 1.4×, Heavy Rain 1.3×, etc.)
        * congestion-score additive bonus
    """
    crowd = max(crowd_size, 1)
    c = RESOURCE_PLAN
    evt_mul = EVENT_TYPE_MULTIPLIER.get(event_type, 1.0)
    wx_mul = WEATHER_RESOURCE_MULTIPLIER.get(weather, 1.0)

    def _calc(per_crowd_key, score_coef_key, min_key, max_key):
        raw = crowd * c[per_crowd_key] * evt_mul * wx_mul + score * c[score_coef_key]
        return int(round(min(c[max_key], max(c[min_key], raw))))

    officers    = _calc("officers_per_crowd",   "officers_score_coef",   "officers_min",   "officers_max")
    barricades  = _calc("barricades_per_crowd", "barricades_score_coef", "barricades_min", "barricades_max")
    marshals    = _calc("marshals_per_crowd",   "marshals_score_coef",   "marshals_min",   "marshals_max")
    emergency   = _calc("emergency_per_crowd",  "emergency_score_coef",  "emergency_min",  "emergency_max")

    return {
        "Police Officers Required": officers,
        "Barricades Required": barricades,
        "Traffic Marshals Required": marshals,
        "Emergency Units Required": emergency,
    }


def _route_plan(location: str, score: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build affected-road snapshot and structured diversion routes.

    Each diversion is a rectangular bypass around the blocked segment:
        blocked segment  →  A ──(red)── B
        detour path      →  A → C → D → B  (blue bypass around blockade)
    The bypass shifts perpendicular to the blocked segment by DIVERSION_OFFSET.
    """
    snapshot = build_road_snapshot(score, location)
    affected = snapshot.sort_values("congestion", ascending=False).head(
        max(3, int(round(score / 30)))
    ).copy()

    # Pick plausible alternate road names from the library.
    alt_names = [r for r in ROAD_LIBRARY if r not in affected["name"].values]
    route_rows = []
    off = DIVERSION_OFFSET
    for idx, (_, row) in enumerate(affected.iterrows()):
        a_lat, a_lon = row["lat"], row["lon"]
        # End of the blocked segment (shifted slightly along the road direction).
        b_lat = a_lat + off * 0.6
        b_lon = a_lon + off * 0.4
        # Bypass waypoints: perpendicular shift to form a rectangle.
        c_lat = a_lat - off * 0.5
        c_lon = a_lon + off * 0.8
        d_lat = b_lat - off * 0.5
        d_lon = b_lon + off * 0.8

        alt_road = alt_names[idx % len(alt_names)] if alt_names else "Service Lane"
        route_rows.append(
            {
                "affected_road": row["name"],
                "alternate_route": f"Via {alt_road}",
                "time_saved_min": int(max(6, round(row["expected_delay_min"] * 0.55))),
                # Blocked segment endpoints
                "blocked_lat": a_lat,
                "blocked_lon": a_lon,
                "blocked_end_lat": b_lat,
                "blocked_end_lon": b_lon,
                # Bypass waypoints
                "bypass_c_lat": c_lat,
                "bypass_c_lon": c_lon,
                "bypass_d_lat": d_lat,
                "bypass_d_lon": d_lon,
                # Rejoin point (same as blocked segment end)
                "diversion_lat": b_lat,
                "diversion_lon": b_lon,
            }
        )
    return affected, pd.DataFrame(route_rows)


def _ai_summary(req: EventRequest, score: float, risk: str, affected: pd.DataFrame, resources: dict) -> str:
    peak_start = "5 PM" if _parse_hour(req.event_start_time) >= 16 else "2 PM"
    peak_end = "8 PM" if _parse_hour(req.event_start_time) >= 16 else "6 PM"
    roads = ", ".join(affected["name"].head(3).tolist()) if not affected.empty else "primary corridor"
    return (
        f"Based on the expected crowd size of {req.crowd_size:,}, the historical traffic profile of "
        f"{req.event_location}, and corridor signals surfaced in the existing incident reports, "
        f"severe congestion is expected between {peak_start} and {peak_end}. "
        f"The predicted congestion score is {score:.0f}/100 ({risk}). "
        f"Deploy {resources['Police Officers Required']} officers, {resources['Barricades Required']} barricades, "
        f"and {resources['Traffic Marshals Required']} marshals near {roads}. "
        f"Activate diversion planning immediately and keep {resources['Emergency Units Required']} emergency unit(s) on standby."
    )


def predict_event(event: EventRequest | dict) -> dict:
    if isinstance(event, dict):
        event = EventRequest(**event)

    model = ensure_model()
    payload = _prediction_input(event)
    pred = predict_one(model, payload)
    # SCORE_CALIBRATION_FACTOR is a presentation calibration (see config.py),
    # not a modelling correction; set it to 1.0 to report the raw model score.
    score = float(np.clip(pred["congestion_score"] * SCORE_CALIBRATION_FACTOR, 0, 100))
    risk = _risk_level(score)
    affected, routes = _route_plan(event.event_location, score)
    resources = _resource_plan(score, event.crowd_size, event.event_type, event.weather_condition)
    ai_summary = _ai_summary(event, score, risk, affected, resources)
    peak_time = "5 PM - 8 PM" if _parse_hour(event.event_start_time) >= 16 else "2 PM - 5 PM"

    prediction = {
        "congestion_score": score,
        "risk_level": risk,
        "expected_peak_time": peak_time,
        "number_of_affected_roads": int(len(affected)),
        "estimated_delay_min": int(round(max(12, score * 2.1))),
        "affected_roads": affected[["name", "severity", "expected_delay_min", "lat", "lon"]].rename(
            columns={"name": "road_name", "severity": "congestion_level", "expected_delay_min": "expected_delay"}
        ).to_dict(orient="records"),
        "diversion_routes": routes.to_dict(orient="records"),
        "resources": resources,
        "ai_summary": ai_summary,
    }
    log_prediction(event.__dict__, prediction)
    return prediction


def demo_request() -> EventRequest:
    start = datetime.now().replace(hour=DEMO_PRESET["event_start_hour"], minute=0, second=0, microsecond=0)
    return EventRequest(
        event_type=DEMO_PRESET["event_type"],
        event_location=DEMO_PRESET["event_location"],
        crowd_size=DEMO_PRESET["crowd_size"],
        event_start_time=start.isoformat(),
        event_duration_hr=DEMO_PRESET["event_duration_hr"],
        weather_condition=DEMO_PRESET["weather_condition"],
    )


def dashboard_snapshot(event: EventRequest | dict) -> dict:
    prediction = predict_event(event)
    trend_df, allocation_df = build_trend_frame()
    traffic_map = build_road_snapshot(prediction["congestion_score"], event.event_location if isinstance(event, EventRequest) else event["event_location"])
    return {
        "prediction": prediction,
        "trend_df": trend_df,
        "allocation_df": allocation_df,
        "traffic_map_df": traffic_map,
    }
