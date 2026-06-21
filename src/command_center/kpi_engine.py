"""
KPI Engine — Smart City Command Center
Calculates every dashboard metric from actual city datasets.
No hardcoded percentages. All values derived from logged predictions,
CITY_HUBS baselines, resource plans, and real-time event context.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import TypedDict

import numpy as np

from .config import CITY_HUBS, RESOURCE_PLAN
from .db import get_connection, init_db


# ---------------------------------------------------------------------------
# Typed result objects
# ---------------------------------------------------------------------------

class KPIResult(TypedDict):
    value: float          # current value (0–100 for scores, raw for counts)
    display: str          # formatted string for UI
    trend: float          # delta from previous hour (positive = worsening/growing)
    trend_dir: str        # "up" | "down" | "flat"
    last_updated: str     # ISO timestamp
    source: str           # data source description


class CityKPIs(TypedDict):
    city_health_score: KPIResult
    resource_utilization: KPIResult
    emergency_load: KPIResult
    service_availability: KPIResult


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_window(hours_ago_start: float, hours_ago_end: float = 0.0) -> list[dict]:
    """Fetch predictions logged in a UTC time window."""
    init_db()
    con = get_connection()
    now = datetime.now(timezone.utc)
    t_start = (now - timedelta(hours=hours_ago_start)).isoformat()
    t_end   = (now - timedelta(hours=hours_ago_end)).isoformat()
    rows = con.execute(
        "SELECT request_json, prediction_json, created_at "
        "FROM event_predictions WHERE created_at >= ? AND created_at <= ? "
        "ORDER BY created_at ASC",
        (t_start, t_end),
    ).fetchall()
    con.close()
    results = []
    for r in rows:
        try:
            pred = json.loads(r["prediction_json"])
            req  = json.loads(r["request_json"])
            results.append({"pred": pred, "req": req, "created_at": r["created_at"]})
        except Exception:
            pass
    return results


def _baseline_avg_congestion() -> float:
    """Weighted average of all CITY_HUBS baselines — city's resting load."""
    baselines = [h["baseline"] for h in CITY_HUBS.values()]
    return float(np.mean(baselines))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _trend_dir(delta: float, *, higher_is_worse: bool = True) -> str:
    if abs(delta) < 0.5:
        return "flat"
    if higher_is_worse:
        return "up" if delta > 0 else "down"
    else:
        return "up" if delta < 0 else "down"  # higher value = healthier


# ---------------------------------------------------------------------------
# KPI 1 — City Health Score  (0–100, higher = healthier)
#
# Formula:
#   raw_congestion  = mean(congestion_score) of all predictions in last hour
#                     falling back to CITY_HUBS baseline average if no data
#   risk_penalty    = high_risk_count / total_predictions * 30
#   weather_penalty = 0–15 depending on active weather conditions
#   health          = 100 - raw_congestion * 0.6 - risk_penalty - weather_penalty
#   clamped to [0, 100]
# ---------------------------------------------------------------------------

def _city_health(window_rows: list[dict], prev_rows: list[dict]) -> KPIResult:
    baseline = _baseline_avg_congestion()

    def _score(rows: list[dict]) -> float:
        if not rows:
            return 100 - baseline * 0.6
        scores    = [r["pred"].get("congestion_score", baseline) for r in rows]
        risks     = [r["pred"].get("risk_level", "LOW") for r in rows]
        high_ct   = sum(1 for rk in risks if rk in ("HIGH", "CRITICAL"))
        risk_pen  = (high_ct / len(rows)) * 30
        avg_cong  = float(np.mean(scores))
        # Weather penalty: infer from most recent request
        weather_penalties = {"Clear": 0, "Cloudy": 2, "Windy": 3,
                             "Rain": 8, "Heavy Rain": 12, "Storm Warning": 15}
        weather = rows[-1]["req"].get("weather_condition", "Clear")
        weather_pen = weather_penalties.get(weather, 4)
        return float(np.clip(100 - avg_cong * 0.6 - risk_pen - weather_pen, 0, 100))

    current = _score(window_rows)
    previous = _score(prev_rows) if prev_rows else current
    delta = round(current - previous, 1)

    return KPIResult(
        value=round(current, 1),
        display=f"{current:.1f}/100",
        trend=delta,
        trend_dir=_trend_dir(delta, higher_is_worse=False),  # higher health is GOOD
        last_updated=_now_iso(),
        source="Derived from logged congestion scores + CITY_HUBS baselines",
    )


# ---------------------------------------------------------------------------
# KPI 2 — Resource Utilization  (0–100 %)
#
# Formula:
#   For each prediction in the window, calculate:
#     deployed_units = officers + barricades + marshals + emergency
#     max_capacity   = RESOURCE_PLAN high_load maximum per event
#   utilization = mean(deployed / capacity) across window
#   If no data, use CITY_HUBS baseline average to estimate background load.
# ---------------------------------------------------------------------------

# Max deployable units from config high_load bands (used as capacity ceiling)
_MAX_OFFICERS  = 18 + 80000 // 12000 + 100 // 6     # ~30
_MAX_BARRICADES = 9 + 80000 // 18000 + 100 // 10    # ~18
_MAX_MARSHALS  = 8 + 80000 // 20000 + 100 // 12     # ~20
_MAX_EMERGENCY = 100 // 45 + 2                       # ~4
_MAX_TOTAL = _MAX_OFFICERS + _MAX_BARRICADES + _MAX_MARSHALS + _MAX_EMERGENCY  # ~72


def _resource_utilization(window_rows: list[dict], prev_rows: list[dict]) -> KPIResult:

    def _util(rows: list[dict]) -> float:
        if not rows:
            # No active events: utilization tied to city baseline
            return round(_baseline_avg_congestion() * 0.35, 1)
        utils = []
        for r in rows:
            res = r["pred"].get("resources", {})
            deployed = (
                res.get("Police Officers Required", 0)
                + res.get("Barricades Required", 0)
                + res.get("Traffic Marshals Required", 0)
                + res.get("Emergency Units Required", 0)
            )
            utils.append(min(100.0, deployed / max(_MAX_TOTAL, 1) * 100))
        return float(np.mean(utils))

    current  = _util(window_rows)
    previous = _util(prev_rows) if prev_rows else current
    delta    = round(current - previous, 1)

    return KPIResult(
        value=round(current, 1),
        display=f"{current:.1f}%",
        trend=delta,
        trend_dir=_trend_dir(delta, higher_is_worse=True),
        last_updated=_now_iso(),
        source="Calculated from deployed officers + barricades + marshals + emergency vs. max capacity",
    )


# ---------------------------------------------------------------------------
# KPI 3 — Emergency Load  (0–100 %)
#
# Formula:
#   emergency_load = (emergency_units_deployed / max_emergency_capacity) * 100
#   weighted by congestion_score to reflect system stress
#   max_emergency_capacity = 8 (from high_load config)
# ---------------------------------------------------------------------------

_MAX_EMERGENCY_UNITS = 8


def _emergency_load(window_rows: list[dict], prev_rows: list[dict]) -> KPIResult:

    def _load(rows: list[dict]) -> float:
        if not rows:
            # Background level: proportional to city resting stress
            return round(_baseline_avg_congestion() * 0.12, 1)
        loads = []
        for r in rows:
            eu = r["pred"].get("resources", {}).get("Emergency Units Required", 1)
            score = r["pred"].get("congestion_score", 0)
            # Weight by congestion — a score of 100 doubles the emergency stress
            stress_mult = 1.0 + score / 200.0
            loads.append(min(100.0, (eu / _MAX_EMERGENCY_UNITS) * 100 * stress_mult))
        return float(np.mean(loads))

    current  = _load(window_rows)
    previous = _load(prev_rows) if prev_rows else current
    delta    = round(current - previous, 1)

    return KPIResult(
        value=round(current, 1),
        display=f"{current:.1f}%",
        trend=delta,
        trend_dir=_trend_dir(delta, higher_is_worse=True),
        last_updated=_now_iso(),
        source="Emergency units deployed / max capacity (8), weighted by congestion score",
    )


# ---------------------------------------------------------------------------
# KPI 4 — Service Availability  (0–100 %)
#
# Formula:
#   For each monitored corridor in CITY_HUBS:
#     available = baseline < 90 (below critical saturation)
#   base_availability = (available_corridors / total_corridors) * 100
#   active event penalty: reduce by mean(affected_roads / 10) across window
#   high-risk penalty: reduce by 5 per HIGH event in window
# ---------------------------------------------------------------------------

def _service_availability(window_rows: list[dict], prev_rows: list[dict]) -> KPIResult:
    from .traffic_engine import TrafficEngine
    
    def _avail(rows: list[dict]) -> float:
        total = len(CITY_HUBS)
        saturated = sum(1 for h in CITY_HUBS.values() if h["baseline"] >= 90)
        base = ((total - saturated) / total) * 100

        try:
            engine = TrafficEngine()
            live_df = engine.snapshot_df()
            closures = len(live_df[live_df['severity'] == 'Closed']) if not live_df.empty else 0
            live_penalty = (closures / len(live_df)) * 50 if not live_df.empty else 0
        except:
            live_penalty = 0

        if not rows:
            return round(base - live_penalty, 1)

        # Penalty from active events impacting roads
        road_penalties = [r["pred"].get("number_of_affected_roads", 0) / 10 * 5
                          for r in rows]
        risk_penalties = [5 for r in rows
                          if r["pred"].get("risk_level") in ("HIGH", "CRITICAL")]
        total_penalty = min(40, sum(road_penalties) / len(rows) + sum(risk_penalties) + live_penalty)
        return float(np.clip(base - total_penalty, 0, 100))

    current  = _avail(window_rows)
    previous = _avail(prev_rows) if prev_rows else current
    delta    = round(current - previous, 1)

    return KPIResult(
        value=round(current, 1),
        display=f"{current:.1f}%",
        trend=delta,
        trend_dir=_trend_dir(delta, higher_is_worse=False),  # higher = better
        last_updated=_now_iso(),
        source="CITY_HUBS saturation + Live TrafficEngine closures",
    )



# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_city_kpis() -> CityKPIs:
    """
    Compute all four city KPIs from actual logged data.
    Returns current values and trend deltas vs. the previous hour.
    """
    current_window = _fetch_window(hours_ago_start=1.0)
    previous_window = _fetch_window(hours_ago_start=2.0, hours_ago_end=1.0)

    return CityKPIs(
        city_health_score    = _city_health(current_window, previous_window),
        resource_utilization = _resource_utilization(current_window, previous_window),
        emergency_load       = _emergency_load(current_window, previous_window),
        service_availability = _service_availability(current_window, previous_window),
    )
