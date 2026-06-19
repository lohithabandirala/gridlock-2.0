"""Tests for the FastAPI endpoints and SQLite persistence."""

import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

httpx = pytest.importorskip("httpx")  # FastAPI TestClient requires httpx
from fastapi.testclient import TestClient

from backend.api import app
from src.command_center.db import init_db, log_prediction, recent_predictions


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_predict_endpoint(client):
    r = client.post(
        "/predict",
        json={
            "event_type": "Cricket Match",
            "event_location": "M. Chinnaswamy Stadium",
            "crowd_size": 50000,
            "event_start_time": "2026-06-19T17:00:00",
            "event_duration_hr": 4,
            "weather_condition": "Clear",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["risk_level"] == "HIGH"
    assert 0 <= body["congestion_score"] <= 100


def test_predict_validation_rejects_negative_crowd(client):
    r = client.post(
        "/predict",
        json={
            "event_type": "Concert",
            "event_location": "MG Road",
            "crowd_size": -5,
            "event_start_time": "2026-06-19T19:00:00",
            "event_duration_hr": 3,
            "weather_condition": "Clear",
        },
    )
    assert r.status_code == 422


def test_db_logging_roundtrip():
    init_db()
    before = len(recent_predictions(limit=100))
    log_prediction(
        {"event_type": "Test", "crowd_size": 1},
        {"congestion_score": 12.0, "ai_summary": "unit-test entry"},
    )
    after = recent_predictions(limit=100)
    assert len(after) == before + 1
    assert after[0]["prediction_json"]
