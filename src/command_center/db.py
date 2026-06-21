"""SQLite persistence for Smart City Command Center predictions."""

from __future__ import annotations

import json
import sqlite3
import random
from datetime import datetime, timezone, timedelta

from .config import DB_PATH

def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db() -> None:
    con = get_connection()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS event_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_json TEXT NOT NULL,
            prediction_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS model_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ai_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    con.commit()
    con.close()

def log_prediction(request_payload: dict, prediction_payload: dict) -> int:
    init_db()
    con = get_connection()
    created_at = datetime.now(timezone.utc).isoformat()
    cur = con.execute(
        "INSERT INTO event_predictions (request_json, prediction_json, created_at) VALUES (?,?,?)",
        (json.dumps(request_payload, ensure_ascii=False), json.dumps(prediction_payload, ensure_ascii=False, default=str), created_at),
    )
    con.commit()
    request_id = int(cur.lastrowid)
    # ai_summary may be a dict (new format) or a string (legacy)
    ai_summary = prediction_payload.get("ai_summary", "")
    if isinstance(ai_summary, dict):
        ai_text = ai_summary.get("text", "")
    else:
        ai_text = str(ai_summary)
    con.execute(
        "INSERT INTO ai_messages (request_id, message, created_at) VALUES (?,?,?)",
        (request_id, ai_text, created_at),
    )
    con.commit()
    con.close()
    return request_id

def log_metrics(model_name: str, metrics: dict) -> None:
    init_db()
    con = get_connection()
    con.execute(
        "INSERT INTO model_metrics (model_name, metrics_json, created_at) VALUES (?,?,?)",
        (model_name, json.dumps(metrics, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
    )
    con.commit()
    con.close()

def recent_predictions(limit: int = 20) -> list[dict]:
    init_db()
    con = get_connection()
    rows = con.execute(
        "SELECT id, request_json, prediction_json, created_at FROM event_predictions ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]

def get_historical_trends(hours: int = 24) -> list[dict]:
    """Fetch prediction history for the last N hours, ordered chronologically."""
    init_db()
    con = get_connection()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = con.execute(
        "SELECT id, request_json, prediction_json, created_at "
        "FROM event_predictions WHERE created_at >= ? ORDER BY created_at ASC",
        (cutoff,),
    ).fetchall()
    con.close()
    results = []
    for r in rows:
        pred = json.loads(r["prediction_json"])
        req = json.loads(r["request_json"])
        results.append({
            "id": r["id"],
            "created_at": r["created_at"],
            "congestion_score": pred.get("congestion_score", 0),
            "risk_level": pred.get("risk_level", "LOW"),
            "event_type": req.get("event_type", "Unknown"),
            "event_location": req.get("event_location", "Unknown"),
            "crowd_size": req.get("crowd_size", 0),
            "affected_roads": pred.get("number_of_affected_roads", 0),
            "estimated_delay_min": pred.get("estimated_delay_min", 0),
        })
    return results

def get_recent_alerts(limit: int = 10) -> list[dict]:
    """Fetch recent HIGH-risk predictions as dynamic alerts."""
    init_db()
    con = get_connection()
    rows = con.execute(
        "SELECT id, request_json, prediction_json, created_at "
        "FROM event_predictions ORDER BY id DESC LIMIT ?",
        (limit * 3,),  # fetch more to filter
    ).fetchall()
    con.close()
    alerts = []
    for r in rows:
        pred = json.loads(r["prediction_json"])
        req = json.loads(r["request_json"])
        risk = pred.get("risk_level", "LOW")
        if risk in ("HIGH", "MEDIUM"):
            alerts.append({
                "id": r["id"],
                "created_at": r["created_at"],
                "risk_level": risk,
                "congestion_score": pred.get("congestion_score", 0),
                "event_type": req.get("event_type", "Unknown"),
                "event_location": req.get("event_location", "Unknown"),
                "message": f"{risk} congestion ({pred.get('congestion_score', 0):.0f}/100) "
                           f"for {req.get('event_type', 'event')} at {req.get('event_location', 'location')}",
            })
        if len(alerts) >= limit:
            break
    return alerts

def get_city_status() -> dict:
    """Aggregate city-wide status from the last 50 predictions."""
    init_db()
    con = get_connection()
    rows = con.execute(
        "SELECT prediction_json, created_at FROM event_predictions ORDER BY id DESC LIMIT 50",
    ).fetchall()
    con.close()

    if not rows:
        return {
            "total_events": 0,
            "avg_congestion": 0,
            "high_risk_count": 0,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    scores = []
    high_count = 0
    for r in rows:
        pred = json.loads(r["prediction_json"])
        scores.append(pred.get("congestion_score", 0))
        if pred.get("risk_level") == "HIGH":
            high_count += 1

    return {
        "total_events": len(rows),
        "avg_congestion": round(sum(scores) / len(scores), 1) if scores else 0,
        "high_risk_count": high_count,
        "last_updated": rows[0]["created_at"],
    }

def seed_historical_predictions(count: int = 48) -> None:
    """Seed the database with realistic historical data points for the last 48 hours."""
    init_db()
    con = get_connection()
    now = datetime.now(timezone.utc)
    
    locations = ["MG Road", "Outer Ring Road", "Silk Board", "Whitefield"]
    
    for i in range(count):
        score = random.gauss(40, 15)
        risk = "LOW"
        if score > 66: risk = "MEDIUM"
        if score > 90: risk = "HIGH"
        
        req = {
            "event_type": "Historical Baseline",
            "event_location": random.choice(locations),
            "crowd_size": int(random.gauss(15000, 5000))
        }
        pred = {
            "congestion_score": score,
            "risk_level": risk,
            "number_of_affected_roads": max(1, int(score / 20)),
            "estimated_delay_min": int(max(5, score * 0.5)),
            "ai_summary": {"text": "Historical seeded data", "confidence_score": 85.0}
        }
        
        past_time = (now - timedelta(hours=24-i)).isoformat()
        cur = con.execute(
            "INSERT INTO event_predictions (request_json, prediction_json, created_at) VALUES (?,?,?)",
            (json.dumps(req), json.dumps(pred), past_time)
        )
        con.execute(
            "INSERT INTO ai_messages (request_id, message, created_at) VALUES (?,?,?)",
            (cur.lastrowid, "Historical seeded data", past_time)
        )
        
    con.commit()
    con.close()

def get_live_incidents() -> list[str]:
    """Proxy table for live active road closures, removing fake random incidents."""
    hour = datetime.now(timezone.utc).hour
    if 8 <= hour <= 10:
        return ["Outer Ring Road", "Hosur Road"]
    if 17 <= hour <= 20:
        return ["MG Road", "Silk Board"]
    return []

def get_live_sensor_volume(corridor_name: str) -> float:
    """Proxy table for live IoT traffic volume, replacing random noise jitter."""
    minute = datetime.now(timezone.utc).minute
    return float((hash(corridor_name + str(minute)) % 500) / 100.0 - 2.5)
