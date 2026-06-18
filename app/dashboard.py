# -*- coding: utf-8 -*-
"""Day 4b - Streamlit dashboard tying every module together (free, local).

Launch:  streamlit run app/dashboard.py
"""
import sys
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st
import folium
import streamlit.components.v1 as components
from src import config, simulate

st.set_page_config(page_title="Bengaluru Incident & Response", layout="wide")


@st.cache_data
def load_processed():
    if config.DATA_PROCESSED.exists():
        return pd.read_csv(config.DATA_PROCESSED, low_memory=False)
    return None


def _read_csv(p):
    return pd.read_csv(p) if pathlib.Path(p).exists() else None


def _read_json(p):
    p = pathlib.Path(p)
    return json.loads(p.read_text()) if p.exists() else None


df = load_processed()
st.title("🚦 Predictive Incident & Response Platform — Bengaluru")
st.caption("Built on the Astram dataset (8,173 incidents). 100% free / open-source.")

if df is None:
    st.error("Processed dataset not found. Run:  python run_all.py")
    st.stop()

# ---------------- KPI row ----------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total incidents", f"{len(df):,}")
unplanned = (df["event_type"] == "unplanned").mean() * 100 if "event_type" in df else 0
c2.metric("Unplanned", f"{unplanned:.1f}%")
if "requires_road_closure" in df:
    c3.metric("Need road closure", f"{df['requires_road_closure'].sum():,.0f}")
if "clearance_min" in df:
    c4.metric("Median clearance", f"{df['clearance_min'].median():.0f} min")

tabs = st.tabs(["📊 Overview", "🗺️ Blackspots", "👮 Deployment",
                "🔀 Diversion", "🧪 What-if", "📈 Learning",
                "🎫 Planned Events", "⚠️ Surge Alerts"])

# ---------------- Overview ----------------
with tabs[0]:
    a, b = st.columns(2)
    if "event_cause" in df:
        a.subheader("Incidents by cause")
        a.bar_chart(df["event_cause"].value_counts().head(10))
    if "time_slot" in df:
        b.subheader("Incidents by time-slot")
        b.bar_chart(df["time_slot"].value_counts())
    if "weather_risk_score" in df:
        st.subheader("Weather risk distribution")
        st.line_chart(df.groupby("event_date")["weather_risk_score"].mean() if "event_date" in df else df["weather_risk_score"])
    metrics = _read_json(config.REPORT_DIR / "day2_metrics.json")
    if metrics:
        st.subheader("Model metrics (Day 2)")
        st.json(metrics)
    jt = _read_csv(config.REPORT_DIR / "junction_time_forecast.csv")
    if jt is not None and not jt.empty:
        st.subheader("Junction x time forecast")
        st.dataframe(jt.head(20), width="stretch")

# ---------------- Blackspots map ----------------
with tabs[1]:
    bs = _read_csv(config.REPORT_DIR / "blackspots.csv")
    if bs is None or bs.empty:
        st.info("Run Day 2 to generate blackspots.")
    else:
        st.subheader(f"Top chronic blackspots ({len(bs)} clusters)")
        st.dataframe(bs.head(20), width="stretch")
        m = folium.Map(location=[bs["lat"].mean(), bs["lon"].mean()], zoom_start=11,
                       tiles="cartodbpositron")
        for _, r in bs.head(60).iterrows():
            folium.CircleMarker(
                [r["lat"], r["lon"]], radius=4 + (r["incidents"] ** 0.5),
                color="#d63c3c", fill=True, fill_opacity=0.6,
                popup=f"{int(r['incidents'])} incidents | {r.get('top_cause','')}",
            ).add_to(m)
        components.html(m._repr_html_(), height=480)

# ---------------- Deployment ----------------
with tabs[2]:
    alloc = _read_csv(config.REPORT_DIR / "manpower_allocation.csv")
    if alloc is None or alloc.empty:
        st.info("Run Day 3 to generate the deployment plan.")
    else:
        st.subheader("Recommended officer / barricade deployment")
        cols = [c for c in ["corridor", "top_cause", "incidents", "officers", "barricade",
                            "avg_clearance_min", "lat", "lon"] if c in alloc.columns]
        st.dataframe(alloc[cols], width="stretch")
        st.caption(f"Engine: {alloc['_engine'].iat[0] if '_engine' in alloc else 'n/a'}")

# ---------------- Diversion ----------------
with tabs[3]:
    dv = _read_csv(config.REPORT_DIR / "diversion_summary.csv")
    if dv is None or dv.empty:
        st.info("Run Day 3 to generate a diversion plan.")
    else:
        st.subheader("Diversion plan (offline road graph)")
        st.dataframe(dv, width="stretch")

# ---------------- What-if ----------------
with tabs[4]:
    st.subheader("Closure 'what-if' simulator (micro-sim + emissions)")
    cc1, cc2 = st.columns(2)
    vol = cc1.slider("Main-road volume (veh/hr)", 500, 4000, 2100, 100)
    dur = cc2.slider("Closure duration (min)", 15, 240, 90, 15)
    cap_d = cc1.slider("Detour capacity (veh/hr)", 500, 3000, 1500, 100)
    len_d = cc2.slider("Detour length (km)", 1.0, 10.0, 4.2, 0.2)
    main = simulate.Segment("main", 3.0, 4.0, 2400, vol)
    det = simulate.Segment("detour", len_d, 7.0, cap_d, 600)
    res = simulate.micro_simulate(main, det, 1.0, dur)
    k1, k2, k3 = st.columns(3)
    k1.metric("Delay saved", f"{res['delay_saved_vehhr']} veh-hr")
    k2.metric("CO2 saved", f"{res['co2_saved_kg']} kg")
    k3.metric("Recommend diversion", "YES" if res["recommend_diversion"] else "NO")
    st.json(res)

# ---------------- Learning ----------------
with tabs[5]:
    card = _read_json(config.REPORT_DIR / "day5_report_card.json")
    if card is None:
        st.info("Run Day 5 to generate the report card.")
    else:
        st.subheader("Self-learning report card (predicted vs actual)")
        st.json(card)

# ---------------- Planned events ----------------
with tabs[6]:
    pe = _read_csv(config.REPORT_DIR / "planned_event_impact.csv")
    summary = _read_json(config.REPORT_DIR / "planned_event_impact_summary.json")
    if pe is None or pe.empty:
        st.info("Run Day 2 to generate planned-event impact scores.")
    else:
        st.subheader("Planned-event impact score")
        if summary:
            st.json(summary)
        cols = [c for c in [
            "event_cause", "corridor", "junction", "time_slot",
            "requires_road_closure", "daily_rain_mm", "predicted_clearance_min",
            "impact_score", "impact_band",
        ] if c in pe.columns]
        st.dataframe(pe[cols].head(50), width="stretch")
        st.bar_chart(pe["impact_score"].value_counts(bins=10).sort_index())

# ---------------- Surge alerts ----------------
with tabs[7]:
    surge = _read_csv(config.REPORT_DIR / "surge_alerts.csv")
    summary = _read_json(config.REPORT_DIR / "surge_summary.json")
    if surge is None or surge.empty:
        st.info("Run Day 2 to generate surge alerts.")
    else:
        st.subheader("Unplanned surge / anomaly detection")
        if summary:
            st.json(summary)
        st.dataframe(surge.head(50), width="stretch")
        if "severity" in surge:
            st.bar_chart(surge["severity"].value_counts())
