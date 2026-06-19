"""SQLite persistence for Smart City Command Center predictions."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

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
        (json.dumps(request_payload, ensure_ascii=False), json.dumps(prediction_payload, ensure_ascii=False), created_at),
    )
    con.commit()
    request_id = int(cur.lastrowid)
    con.execute(
        "INSERT INTO ai_messages (request_id, message, created_at) VALUES (?,?,?)",
        (request_id, prediction_payload.get("ai_summary", ""), created_at),
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

