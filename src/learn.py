# -*- coding: utf-8 -*-
"""Day 5 - self-learning loop.

Logs predicted-vs-actual clearance times to SQLite, computes a rolling error
metric (the post-event 'report card' from NCHRP Synthesis 309), and exposes a
retrain hook. Using a time-based holdout we *simulate* the learning loop on the
historical data so the mechanism is demonstrable end-to-end.
"""
import sqlite3
import json
import warnings
import numpy as np
import pandas as pd
import joblib

warnings.filterwarnings("ignore", message="X does not have valid feature names")
from sklearn.metrics import mean_absolute_error
from . import config, models


def _init_db():
    con = sqlite3.connect(config.DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS predictions(
        id TEXT, predicted_min REAL, actual_min REAL, abs_err REAL, logged_at TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS report_card(
        run TEXT, n INTEGER, mae REAL, median_err REAL)""")
    con.commit()
    return con


def log_and_score(df: pd.DataFrame) -> dict:
    """Train on the earlier 80% (by time), predict the latest 20%, log results."""
    CAP_MIN = 24 * 60          # same operational cap as the Day-2 regressor
    d = df[df["clearance_min"].notna() & (df["clearance_min"] > 0)
           & (df["clearance_min"] <= CAP_MIN)].copy()
    d = d.dropna(subset=["start_datetime"]).sort_values("start_datetime")
    if len(d) < 200:
        return {"status": "skipped", "reason": "too few labelled rows"}

    split = int(len(d) * 0.8)
    train, holdout = d.iloc[:split], d.iloc[split:]

    # reuse Day-2 training machinery on the training slice only
    prep = models._prep_frame(train)
    prep = prep[prep["clearance_min"] > 0]
    y = np.log1p(prep["clearance_min"].values)
    from sklearn.pipeline import Pipeline
    pipe = Pipeline([("pre", models._build_preprocessor()), ("reg", models._reg())])
    pipe.fit(prep, y)

    hp = models._prep_frame(holdout)
    pred = np.expm1(pipe.predict(hp))
    actual = holdout["clearance_min"].values
    abs_err = np.abs(pred - actual)
    mae = float(mean_absolute_error(actual, pred))

    con = _init_db()
    ids = holdout["id"].astype(str).tolist() if "id" in holdout else [str(i) for i in range(len(holdout))]
    rows = list(zip(ids, pred.tolist(), actual.tolist(), abs_err.tolist(),
                    ["holdout"] * len(pred)))
    con.executemany("INSERT INTO predictions VALUES (?,?,?,?,?)", rows)
    con.execute("INSERT INTO report_card VALUES (?,?,?,?)",
                ("holdout", len(pred), mae, float(np.median(abs_err))))
    con.commit()
    con.close()

    card = {"status": "ok", "trained_on": len(train), "evaluated_on": len(holdout),
            "mae_minutes": round(mae, 1), "median_abs_err_min": round(float(np.median(abs_err)), 1)}
    (config.REPORT_DIR / "day5_report_card.json").write_text(json.dumps(card, indent=2))
    joblib.dump(pipe, config.MODEL_DIR / "clearance_regressor_learned.joblib")
    return card
