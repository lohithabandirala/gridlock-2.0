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
    EVENING_PEAK,
    MORNING_PEAK,
    RESOURCE_PLAN,
    RISK_BANDS,
    SCORE_CALIBRATION_FACTOR,
    TIME_PRESSURE,
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


def _resource_plan(score: float, crowd_size: int) -> dict:
    crowd = max(crowd_size, 1)
    esc_score = RESOURCE_PLAN["escalation_score"]
    esc_crowd = RESOURCE_PLAN["escalation_crowd"]
    if score >= esc_score or crowd >= esc_crowd:
        c = RESOURCE_PLAN["high_load"]
        over_crowd = max(0, crowd - esc_crowd)
        over_score = max(0, score - esc_score)
        officers = int(round(c["officers_base"] + over_crowd / c["officers_crowd_div"] + over_score / c["officers_score_div"]))
        barricades = int(round(c["barricades_base"] + over_crowd / c["barricades_crowd_div"] + over_score / c["barricades_score_div"]))
        marshals = int(round(c["marshals_base"] + over_crowd / c["marshals_crowd_div"] + over_score / c["marshals_score_div"]))
        emergency = int(round(max(c["emergency_min"], score / c["emergency_score_div"])))
    else:
        c = RESOURCE_PLAN["base_load"]
        officers = int(round(max(c["officers_min"], score * c["officers_score_coef"] + crowd / c["officers_crowd_div"])))
        barricades = int(round(max(c["barricades_min"], score * c["barricades_score_coef"] + crowd / c["barricades_crowd_div"])))
        marshals = int(round(max(c["marshals_min"], score * c["marshals_score_coef"] + crowd / c["marshals_crowd_div"])))
        emergency = int(round(max(c["emergency_min"], score / c["emergency_score_div"])))
    return {
        "Police Officers Required": officers,
        "Barricades Required": barricades,
        "Traffic Marshals Required": marshals,
        "Emergency Units Required": emergency,
    }


def _route_plan(location: str, score: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    snapshot = build_road_snapshot(score, location)
    affected = snapshot.sort_values("congestion", ascending=False).head(max(3, int(round(score / 30)))).copy()
    route_rows = []
    for _, row in affected.iterrows():
        route_rows.append(
            {
                "affected_road": row["name"],
                "alternate_route": f"Via {row['name']} service corridor",
                "time_saved_min": int(max(6, round(row["expected_delay_min"] * 0.6))),
                "blocked_lat": row["lat"],
                "blocked_lon": row["lon"],
                "diversion_lat": row["lat"] + 0.01,
                "diversion_lon": row["lon"] + 0.01,
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
    resources = _resource_plan(score, event.crowd_size)
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
