# -*- coding: utf-8 -*-
"""Day 2 - predictive models on the real Astram data (all free / local).

  * Clearance-time regressor   -> how long an incident blocks the road (ETA)
  * Priority classifier        -> data-driven High/Low severity
  * Blackspot mining (DBSCAN)  -> chronic incident hotspots
  * Corridor x time risk table -> expected incidents per corridor / time-slot

Uses scikit-learn (+ LightGBM if present, else HistGradientBoosting). TF-IDF
on the free-text fields provides the lightweight NLP signal.
"""
import json
import warnings
import numpy as np
import pandas as pd
import joblib

# LightGBM + ColumnTransformer emit a harmless feature-name warning at predict
warnings.filterwarnings("ignore", message="X does not have valid feature names")
warnings.filterwarnings("ignore", message="Could not find the number of physical cores*")
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import TruncatedSVD
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score, classification_report, f1_score
from sklearn.cluster import DBSCAN

try:
    from lightgbm import LGBMRegressor, LGBMClassifier
    _HAS_LGBM = True
except Exception:  # pragma: no cover
    from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier
    _HAS_LGBM = False

from . import config


# ---------------------------------------------------------------- helpers
def _fuse_text(df: pd.DataFrame) -> pd.Series:
    parts = [df[c].fillna("") if c in df.columns else "" for c in config.TEXT_COLS]
    out = parts[0]
    for p in parts[1:]:
        out = out + " " + p
    return out.astype(str).str.lower()


class TextEmbeddingTransformer(BaseEstimator, TransformerMixin):
    """Compact semantic text embedding from TF-IDF + truncated SVD.

    This is an offline replacement for a heavier transformer encoder. It still
    captures the semantics that matter for the clearance model better than a
    pure bag-of-words vectorizer and is fast enough to fit on the full dataset.
    """

    def __init__(self, max_features: int = 4000, n_components: int = 24):
        self.max_features = max_features
        self.n_components = n_components
        self.vectorizer = TfidfVectorizer(
            max_features=max_features,
            ngram_range=(1, 2),
            min_df=4,
            stop_words="english",
        )
        self.svd = None

    def _to_text(self, X):
        if isinstance(X, pd.DataFrame):
            if X.shape[1] == 1:
                X = X.iloc[:, 0]
            else:
                X = X.astype(str).agg(" ".join, axis=1)
        if isinstance(X, pd.Series):
            return X.fillna("").astype(str).tolist()
        arr = np.asarray(X)
        if arr.ndim == 2 and arr.shape[1] == 1:
            arr = arr[:, 0]
        return pd.Series(arr.ravel()).fillna("").astype(str).tolist()

    def fit(self, X, y=None):
        text = self._to_text(X)
        tfidf = self.vectorizer.fit_transform(text)
        n_components = max(2, min(self.n_components, max(1, tfidf.shape[1] - 1)))
        self.svd = TruncatedSVD(n_components=n_components, random_state=42)
        self.svd.fit(tfidf)
        return self

    def transform(self, X):
        text = self._to_text(X)
        tfidf = self.vectorizer.transform(text)
        emb = self.svd.transform(tfidf)
        return emb


def _build_preprocessor(cat_features=None, num_features=None):
    cats = list(cat_features if cat_features is not None else config.CAT_FEATURES)
    nums = list(num_features if num_features is not None else config.NUM_FEATURES)
    return ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=10), cats),
            ("num", "passthrough", nums),
            ("txt", TextEmbeddingTransformer(max_features=3500, n_components=24), "text_all"),
        ],
        remainder="drop",
        sparse_threshold=0.2,
    )


def _prep_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["text_all"] = _fuse_text(df)
    # ensure bool cats are strings for the encoder
    for c in ["is_monsoon", "is_weekend", "requires_road_closure"]:
        if c in df.columns:
            df[c] = df[c].astype("string").fillna("na")
    for c in config.CAT_FEATURES:
        if c not in df.columns:
            df[c] = "na"
        df[c] = df[c].astype("string").fillna("na")
    for c in config.NUM_FEATURES:
        if c not in df.columns:
            df[c] = 0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    return df


def _reg():
    if _HAS_LGBM:
        return LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
                             subsample=0.8, colsample_bytree=0.8, random_state=42, verbose=-1)
    return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, random_state=42)


def _clf():
    if _HAS_LGBM:
        return LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
                              subsample=0.8, colsample_bytree=0.8, random_state=42, verbose=-1)
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=42)


# ---------------------------------------------------------------- 1. clearance time
def train_clearance(df: pd.DataFrame) -> dict:
    d = _prep_frame(df)
    # focus on operationally relevant incidents: cap the long tail at 24h
    # (mean is skewed by a handful of never-properly-closed records)
    CAP_MIN = 24 * 60
    d = d[d["clearance_min"].notna() & (d["clearance_min"] > 0) & (d["clearance_min"] <= CAP_MIN)]
    if len(d) < 100:
        return {"status": "skipped", "reason": "too few labelled rows"}
    y = np.log1p(d["clearance_min"].values)        # log target tames the long tail
    pipe = Pipeline([("pre", _build_preprocessor()), ("reg", _reg())])
    Xtr, Xte, ytr, yte = train_test_split(d, y, test_size=0.2, random_state=42)
    pipe.fit(Xtr, ytr)
    pred = pipe.predict(Xte)
    mae_min = mean_absolute_error(np.expm1(yte), np.expm1(pred))
    r2 = r2_score(yte, pred)
    joblib.dump(pipe, config.MODEL_DIR / "clearance_regressor.joblib")
    return {"status": "ok", "model": "LightGBM" if _HAS_LGBM else "HistGBR",
            "rows": len(d), "mae_minutes": round(float(mae_min), 1),
            "r2_log": round(float(r2), 3)}


# ---------------------------------------------------------------- 2. priority
def train_priority(df: pd.DataFrame) -> dict:
    d = _prep_frame(df)
    d = d[d["priority"].isin(["High", "Low"])]
    if d["priority"].nunique() < 2:
        return {"status": "skipped", "reason": "single class"}
    y = (d["priority"] == "High").astype(int).values
    # Exclude corridor/corridor_freq: priority is ~99.9% a per-corridor policy label,
    # so including them just memorises the rule. We predict priority from the
    # *incident's own* characteristics instead - a genuinely useful model.
    cats = [c for c in config.CAT_FEATURES if c != "corridor"]
    nums = [c for c in config.NUM_FEATURES if c != "corridor_freq"]
    pipe = Pipeline([("pre", _build_preprocessor(cats, nums)), ("clf", _clf())])
    Xtr, Xte, ytr, yte = train_test_split(d, y, test_size=0.2, random_state=42, stratify=y)
    pipe.fit(Xtr, ytr)
    pred = pipe.predict(Xte)
    f1 = f1_score(yte, pred)
    rep = classification_report(yte, pred, output_dict=True, zero_division=0)
    joblib.dump(pipe, config.MODEL_DIR / "priority_classifier.joblib")
    return {"status": "ok", "model": "LightGBM" if _HAS_LGBM else "HistGBC",
            "rows": len(d), "f1_high": round(float(f1), 3),
            "accuracy": round(float(rep["accuracy"]), 3)}


# ---------------------------------------------------------------- 3. blackspots
def mine_blackspots(df: pd.DataFrame, eps_m: float = 150, min_samples: int = 8) -> pd.DataFrame:
    d = df.dropna(subset=["latitude", "longitude"]).copy()
    coords = np.radians(d[["latitude", "longitude"]].values)
    eps_rad = eps_m / 6_371_000.0                  # metres -> radians (earth radius)
    db = DBSCAN(eps=eps_rad, min_samples=min_samples, metric="haversine").fit(coords)
    d["cluster"] = db.labels_
    clusters = d[d["cluster"] >= 0].groupby("cluster").agg(
        incidents=("cluster", "size"),
        lat=("latitude", "mean"),
        lon=("longitude", "mean"),
        avg_clearance_min=("clearance_min", "median"),
        top_cause=("event_cause", lambda s: s.mode().iat[0] if len(s.mode()) else "na"),
        corridor=("corridor", lambda s: s.mode().iat[0] if len(s.mode()) else "na"),
    ).reset_index().sort_values("incidents", ascending=False)
    clusters["avg_clearance_min"] = clusters["avg_clearance_min"].round(0)
    clusters.to_csv(config.REPORT_DIR / "blackspots.csv", index=False)
    return clusters


# ---------------------------------------------------------------- 4. risk table
def build_risk_table(df: pd.DataFrame) -> pd.DataFrame:
    d = df.dropna(subset=["corridor", "time_slot"]).copy()
    risk = d.groupby(["corridor", "time_slot"]).size().reset_index(name="incidents")
    # normalise 0-100 risk score
    mx = risk["incidents"].max() or 1
    risk["risk_score"] = (risk["incidents"] / mx * 100).round(1)
    risk = risk.sort_values("incidents", ascending=False)
    risk.to_csv(config.REPORT_DIR / "corridor_risk.csv", index=False)
    return risk


# ---------------------------------------------------------------- 5. probabilistic forecast
def build_junction_time_forecast(df: pd.DataFrame, alpha: float = 1.0) -> pd.DataFrame:
    """Smoothed risk forecast per junction x time-slot.

    The dataset contains positive incident records rather than a binary exposure
    table, so we produce a probability-style intensity estimate:

    P(incident | junction, time-slot) = (count + alpha) / (junction_total + alpha * K)

    where K is the number of observed time slots. The result is normalized to a
    0-100 score for dashboard/report consumption.
    """
    d = df.dropna(subset=["junction", "time_slot"]).copy()
    if d.empty:
        out = pd.DataFrame(columns=["junction", "time_slot", "incidents", "junction_total",
                                    "probability", "forecast_score"])
        out.to_csv(config.REPORT_DIR / "junction_time_forecast.csv", index=False)
        return out

    slots = sorted([s for s in d["time_slot"].dropna().unique()])
    K = max(len(slots), 1)
    counts = d.groupby(["junction", "time_slot"]).size().reset_index(name="incidents")
    totals = d.groupby("junction").size().reset_index(name="junction_total")
    out = counts.merge(totals, on="junction", how="left")
    out["probability"] = (out["incidents"] + alpha) / (out["junction_total"] + alpha * K)
    out["forecast_score"] = (out["probability"] / out["probability"].max() * 100).round(1)
    out = out.sort_values(["forecast_score", "incidents"], ascending=False)
    out.to_csv(config.REPORT_DIR / "junction_time_forecast.csv", index=False)
    return out


# ---------------------------------------------------------------- orchestrator
def train_all(df: pd.DataFrame) -> dict:
    results = {
        "clearance": train_clearance(df),
        "priority": train_priority(df),
    }
    bs = mine_blackspots(df)
    rt = build_risk_table(df)
    jt = build_junction_time_forecast(df)
    from . import impact, anomaly

    planned = impact.score_planned_events(df, corridor_risk=rt)
    surge = anomaly.detect_surge(df)
    results["blackspots"] = {"status": "ok", "clusters": int(len(bs)),
                             "top_incidents": int(bs["incidents"].max()) if len(bs) else 0}
    results["risk_table"] = {"status": "ok", "rows": int(len(rt))}
    results["junction_forecast"] = {"status": "ok", "rows": int(len(jt))}
    results["planned_events"] = {
        "status": "ok",
        "rows": int(len(planned)),
        "high": int((planned["impact_band"] == "High").sum()) if len(planned) else 0,
    }
    results["surge_detection"] = {
        "status": "ok",
        "rows": int(len(surge)),
        "critical": int((surge["severity"] == "Critical").sum()) if len(surge) else 0,
    }
    (config.REPORT_DIR / "day2_metrics.json").write_text(json.dumps(results, indent=2))
    return results


def predict_clearance_minutes(df: pd.DataFrame) -> np.ndarray:
    """Predict clearance minutes for any prepared frame using the saved model."""
    model_path = config.MODEL_DIR / "clearance_regressor.joblib"
    if not model_path.exists():
        raise FileNotFoundError(model_path)
    pipe = joblib.load(model_path)
    d = _prep_frame(df)
    pred = pipe.predict(d)
    return np.expm1(pred)
