"""Unit tests for the Smart City Command Center prediction service."""

import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from src.command_center.config import RISK_BANDS
from src.command_center.service import (
    EventRequest,
    _risk_level,
    demo_request,
    predict_event,
)


def test_risk_bands_monotonic():
    assert _risk_level(0) == "LOW"
    assert _risk_level(32) == "LOW"
    assert _risk_level(65) == "MEDIUM"
    assert _risk_level(89) == "HIGH"
    assert _risk_level(95) == "CRITICAL"
    assert _risk_level(33) == "MEDIUM"
    assert _risk_level(65.9) == "MEDIUM"
    assert _risk_level(66) == "HIGH"
    assert _risk_level(100) == "CRITICAL"


def test_demo_prediction_is_high_and_in_range():
    pred = predict_event(demo_request())
    assert 0 <= pred["congestion_score"] <= 100
    assert pred["risk_level"] in ("HIGH", "CRITICAL")
    # Demo (Cricket Match / 50k) is documented to land around 91/100.
    assert 85 <= pred["congestion_score"] <= 95


def test_prediction_has_required_fields():
    pred = predict_event(demo_request())
    for key in (
        "congestion_score",
        "risk_level",
        "expected_peak_time",
        "number_of_affected_roads",
        "estimated_delay_min",
        "affected_roads",
        "diversion_routes",
        "resources",
        "ai_summary",
    ):
        assert key in pred, f"missing field: {key}"
    assert pred["number_of_affected_roads"] == len(pred["affected_roads"])


def test_resources_scale_with_crowd():
    base = predict_event(
        EventRequest("Public Gathering", "Cubbon Park", 2000, "2026-06-19T11:00:00", 2, "Clear")
    )
    big = predict_event(
        EventRequest("Cricket Match", "M. Chinnaswamy Stadium", 60000, "2026-06-19T18:00:00", 4, "Clear")
    )
    assert big["resources"]["Police Officers Required"] >= base["resources"]["Police Officers Required"]
    for v in big["resources"].values():
        assert v >= 1


def test_dict_input_accepted():
    payload = {
        "event_type": "Concert",
        "event_location": "MG Road",
        "crowd_size": 15000,
        "event_start_time": "2026-06-19T19:00:00",
        "event_duration_hr": 3,
        "weather_condition": "Cloudy",
    }
    pred = predict_event(payload)
    assert pred["risk_level"] in {"LOW", "MEDIUM", "HIGH"}
