"""Prediction client used by the dashboard.

By default the dashboard runs the model in-process (single-command demo). If the
environment variable ``SMART_CITY_API_URL`` is set (e.g. ``http://127.0.0.1:8000``)
the client routes predictions through the FastAPI ``/predict`` endpoint instead,
so the Streamlit UI becomes a real HTTP client of the backend rather than
bypassing it. Any network/HTTP failure falls back to in-process scoring so the
demo never breaks.
"""

from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass

from .service import EventRequest, predict_event

API_URL = os.environ.get("SMART_CITY_API_URL", "").rstrip("/")


def _as_payload(event: EventRequest | dict) -> dict:
    if is_dataclass(event):
        return asdict(event)
    if isinstance(event, dict):
        return dict(event)
    raise TypeError(f"Unsupported event type: {type(event)!r}")


def using_api() -> bool:
    """True when predictions are routed through the HTTP backend."""
    return bool(API_URL)


def get_prediction(event: EventRequest | dict) -> dict:
    """Return a prediction, preferring the HTTP API when configured."""
    if API_URL:
        try:
            import requests

            resp = requests.post(f"{API_URL}/predict", json=_as_payload(event), timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            # Backend unreachable / errored -> fall back to in-process scoring.
            pass
    return predict_event(event)
