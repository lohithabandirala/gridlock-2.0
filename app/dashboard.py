"""Smart City Command Center dashboard."""

from __future__ import annotations

import json
import pathlib
from datetime import datetime

import folium
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

try:
    import plotly.express as px
    import plotly.graph_objects as go

    HAS_PLOTLY = True
except Exception:  # pragma: no cover
    px = None
    go = None
    HAS_PLOTLY = False

ROOT = pathlib.Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(ROOT))

from src.command_center.config import CITY_HUBS, EVENT_TYPES, WEATHER_TYPES, REPORT_DIR, DEMO_PRESET
from src.command_center.ml import METRICS_PATH, load_model, train
from src.command_center.sample_data import build_road_snapshot, build_trend_frame
from src.command_center.service import EventRequest, demo_request
from src.command_center.client import get_prediction, using_api
from src.command_center.db import recent_predictions

st.set_page_config(
    page_title="Smart City Command Center",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(31, 111, 235, 0.16), transparent 28%),
                radial-gradient(circle at top right, rgba(0, 207, 163, 0.12), transparent 24%),
                linear-gradient(180deg, #07111f 0%, #0b1729 48%, #081019 100%);
            color: #eef4ff;
        }
        [data-testid="stHeader"] { background: rgba(0,0,0,0); }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #07101d 0%, #09121f 100%);
            border-right: 1px solid rgba(255,255,255,0.08);
        }
        .hero {
            padding: 22px 24px;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 22px;
            background: linear-gradient(135deg, rgba(12,22,40,0.96), rgba(8,16,28,0.92));
            box-shadow: 0 16px 46px rgba(0,0,0,0.28);
        }
        .hero h1 {
            margin: 0;
            font-size: 2.25rem;
            letter-spacing: -0.03em;
        }
        .hero p {
            margin: 6px 0 0 0;
            color: #9fb2d4;
        }
        .section-title {
            font-size: 1.15rem;
            font-weight: 700;
            color: #f2f7ff;
            margin: 0 0 10px 0;
        }
        .metric-card {
            padding: 18px 18px 16px 18px;
            border-radius: 18px;
            border: 1px solid rgba(255,255,255,0.08);
            background: linear-gradient(180deg, rgba(16,27,44,0.95), rgba(10,18,31,0.95));
            box-shadow: 0 10px 24px rgba(0,0,0,0.22);
        }
        .metric-card .label {
            color: #9cb1d6;
            font-size: 0.84rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .metric-card .value {
            font-size: 1.9rem;
            font-weight: 800;
            margin-top: 6px;
            color: white;
        }
        .metric-card .hint {
            color: #7f94b9;
            font-size: 0.85rem;
            margin-top: 2px;
        }
        .status-low { color: #44d58c; }
        .status-medium { color: #f7cf57; }
        .status-high { color: #ff6b6b; }
        .chat-wrap {
            border-left: 4px solid #37a2ff;
            background: linear-gradient(180deg, rgba(10,20,35,0.96), rgba(8,14,24,0.96));
            border-radius: 16px;
            padding: 16px 18px;
            border: 1px solid rgba(255,255,255,0.08);
        }
        .chat-meta {
            color: #88a0c4;
            font-size: 0.8rem;
            margin-bottom: 8px;
        }
        .chat-bubble {
            padding: 12px 14px;
            border-radius: 14px;
            background: rgba(56, 118, 214, 0.12);
            color: #edf3ff;
            line-height: 1.6;
        }
        .pill {
            display:inline-block;
            padding: 5px 10px;
            border-radius: 999px;
            font-size: 0.76rem;
            margin-right: 6px;
            border: 1px solid rgba(255,255,255,0.09);
            background: rgba(255,255,255,0.04);
        }
        .card-row {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 14px;
        }
        @media (max-width: 1100px) {
            .card-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
        @media (max-width: 680px) {
            .card-row { grid-template-columns: 1fr; }
        }
        /* Gradient call-to-action button (form submit + primary buttons) */
        div[data-testid="stForm"] button {
            background: linear-gradient(90deg, #1f6feb, #00cfa3) !important;
            color: #ffffff !important;
            border: none !important;
            font-weight: 700 !important;
            letter-spacing: 0.05em;
            border-radius: 12px !important;
            box-shadow: 0 8px 22px rgba(31,111,235,0.35);
            transition: transform .15s ease, box-shadow .15s ease;
        }
        div[data-testid="stForm"] button:hover {
            transform: translateY(-2px);
            box-shadow: 0 12px 30px rgba(0,207,163,0.45);
        }
        /* Live alert banner */
        .alert-banner {
            background: linear-gradient(90deg, rgba(255,77,77,0.20), rgba(255,107,107,0.05));
            border: 1px solid rgba(255,107,107,0.55);
            border-left: 5px solid #ff5b5b;
            color: #ffe1e1;
            padding: 12px 16px;
            border-radius: 14px;
            margin: 8px 0 6px 0;
            font-weight: 600;
            animation: pulseGlow 2.2s infinite;
        }
        .alert-ok {
            background: linear-gradient(90deg, rgba(68,213,140,0.16), rgba(68,213,140,0.03));
            border: 1px solid rgba(68,213,140,0.5);
            border-left: 5px solid #44d58c;
            color: #d6ffe9;
            padding: 12px 16px; border-radius: 14px; margin: 8px 0 6px 0; font-weight: 600;
        }
        @keyframes pulseGlow {
            0%, 100% { box-shadow: 0 0 0 rgba(255,91,91,0); }
            50% { box-shadow: 0 0 20px rgba(255,91,91,0.40); }
        }
        /* System-status dots */
        .status-line { display:flex; align-items:center; gap:9px; margin:7px 0; color:#cfe0ff; font-size:0.9rem; }
        .dot { width:10px; height:10px; border-radius:50%; background:#44d58c; box-shadow:0 0 8px #44d58c; }
        /* Impact progress bar */
        .impact-track { background:rgba(255,255,255,0.08); border-radius:999px; height:18px; overflow:hidden; border:1px solid rgba(255,255,255,0.10); margin-top:6px; }
        .impact-fill { height:100%; border-radius:999px; background:linear-gradient(90deg,#44d58c,#f7cf57,#ff6b6b); transition:width .6s ease; }
        /* Ranked road list */
        .road-rank { display:flex; justify-content:space-between; padding:10px 14px; margin:6px 0; border-radius:12px;
            background:linear-gradient(180deg, rgba(16,27,44,0.95), rgba(10,18,31,0.95)); border:1px solid rgba(255,255,255,0.08); }
        .road-rank b { color:#f2f7ff; }
        .road-rank .delay { color:#ff9f9f; font-weight:700; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, hint: str = "", tone: str = "") -> str:
    tone_class = {"LOW": "status-low", "MEDIUM": "status-medium", "HIGH": "status-high"}.get(tone, "")
    return f"""
    <div class="metric-card">
      <div class="label">{label}</div>
      <div class="value {tone_class}">{value}</div>
      <div class="hint">{hint}</div>
    </div>
    """


def load_metrics() -> dict:
    if METRICS_PATH.exists():
        return json.loads(METRICS_PATH.read_text())
    return train()


@st.cache_resource(show_spinner=False)
def bootstrap():
    metrics = load_metrics()
    model = load_model()
    if model is None:
        metrics = train()
        model = load_model()
    return model, metrics


def _center_for(location: str) -> tuple[float, float]:
    hub = CITY_HUBS.get(location, CITY_HUBS["MG Road"])
    return hub["lat"], hub["lon"]


def _folium_html(map_obj, height=540):
    components.html(map_obj._repr_html_(), height=height, scrolling=False)


def render_heatmap(prediction: dict, snapshot: pd.DataFrame) -> None:
    center = _center_for(st.session_state.get("event_location", "MG Road"))
    m = folium.Map(location=center, zoom_start=12, tiles="cartodbpositron")
    color_map = {"Red": "#e74c3c", "Yellow": "#f1c40f", "Green": "#2ecc71"}
    for _, row in snapshot.iterrows():
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=8 + row["congestion"] / 18,
            color=color_map.get(row["severity"], "#3498db"),
            fill=True,
            fill_color=color_map.get(row["severity"], "#3498db"),
            fill_opacity=0.8,
            popup=folium.Popup(
                f"<b>Road Name:</b> {row['name']}<br>"
                f"<b>Congestion Level:</b> {row['congestion']}/100<br>"
                f"<b>Expected Delay:</b> {row['expected_delay_min']} min",
                max_width=300,
            ),
            tooltip=row["name"],
        ).add_to(m)

    for hotspot in prediction["affected_roads"]:
        folium.Marker(
            [hotspot["lat"], hotspot["lon"]],
            icon=folium.Icon(color="red", icon="exclamation-sign"),
            popup=folium.Popup(
                f"<b>{hotspot['road_name']}</b><br>"
                f"Congestion Level: {hotspot['congestion_level']}<br>"
                f"Expected Delay: {hotspot['expected_delay']} min",
                max_width=260,
            ),
        ).add_to(m)
    _folium_html(m, 560)


def render_diversion_map(prediction: dict) -> None:
    if not prediction["diversion_routes"]:
        st.info("No diversion routes available for this scenario.")
        return
    first = prediction["diversion_routes"][0]
    m = folium.Map(location=[first["blocked_lat"], first["blocked_lon"]], zoom_start=13, tiles="cartodbpositron")
    for route in prediction["diversion_routes"]:
        folium.PolyLine(
            [[route["blocked_lat"], route["blocked_lon"]], [route["blocked_lat"] + 0.006, route["blocked_lon"] + 0.006]],
            color="#ff4d4d",
            weight=7,
            opacity=0.9,
            tooltip=f"Blocked route: {route['affected_road']}",
        ).add_to(m)
        folium.PolyLine(
            [[route["blocked_lat"], route["blocked_lon"]], [route["diversion_lat"], route["diversion_lon"]]],
            color="#4da3ff",
            weight=6,
            opacity=0.95,
            tooltip=f"Recommended diversion: {route['alternate_route']}",
        ).add_to(m)
        folium.Marker(
            [route["diversion_lat"], route["diversion_lon"]],
            icon=folium.Icon(color="blue", icon="flag"),
            popup=route["alternate_route"],
        ).add_to(m)
    _folium_html(m, 520)


def render_deployment_map(snapshot: pd.DataFrame, resources: dict) -> None:
    center = [snapshot["lat"].mean(), snapshot["lon"].mean()]
    m = folium.Map(location=center, zoom_start=12, tiles="cartodbpositron")
    for _, row in snapshot.head(6).iterrows():
        folium.Marker(
            [row["lat"], row["lon"]],
            icon=folium.Icon(color="darkred", icon="shield"),
            popup=(
                f"<b>{row['name']}</b><br>"
                f"Officers: {resources['Police Officers Required']}<br>"
                f"Barricades: {resources['Barricades Required']}<br>"
                f"Marshals: {resources['Traffic Marshals Required']}"
            ),
        ).add_to(m)
    _folium_html(m, 500)


def render_ai_panel(summary: str, prediction: dict) -> None:
    bubbles = [
        ("AI Traffic Commander", summary),
        (
            "Recommended Action",
            f"Peak window: {prediction['expected_peak_time']} | Diversions: {len(prediction['diversion_routes'])} | "
            f"Delay: {prediction['estimated_delay_min']} min",
        ),
    ]
    for title, body in bubbles:
        st.markdown(
            f"""
            <div class="chat-wrap">
              <div class="chat-meta">{title}</div>
              <div class="chat-bubble">{body}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


RISK_COLOR = {"LOW": "#44d58c", "MEDIUM": "#f7cf57", "HIGH": "#ff6b6b"}

SCENARIO_PRESETS = {
    "🏏 Cricket Match": dict(event_type="Cricket Match", event_location="M. Chinnaswamy Stadium", crowd_size=50000, weather="Clear", hour=17, dur=4.0),
    "🎤 Concert": dict(event_type="Concert", event_location="Whitefield", crowd_size=35000, weather="Cloudy", hour=19, dur=3.0),
    "🏛 Political Rally": dict(event_type="Political Rally", event_location="MG Road", crowd_size=25000, weather="Clear", hour=11, dur=3.0),
    "🎉 Festival": dict(event_type="Festival", event_location="Koramangala", crowd_size=40000, weather="Clear", hour=18, dur=5.0),
}


def apply_scenario(p: dict) -> None:
    st.session_state.event_type = p["event_type"]
    st.session_state.event_location = p["event_location"]
    st.session_state.crowd_size = p["crowd_size"]
    st.session_state.weather_condition = p["weather"]
    st.session_state.event_start_time = datetime.now().replace(hour=p["hour"], minute=0, second=0, microsecond=0)
    st.session_state.event_duration_hr = p["dur"]
    ev = EventRequest(
        event_type=p["event_type"], event_location=p["event_location"], crowd_size=p["crowd_size"],
        event_start_time=st.session_state.event_start_time.isoformat(), event_duration_hr=p["dur"],
        weather_condition=p["weather"],
    )
    st.session_state.last_prediction = get_prediction(ev)
    st.session_state.last_request = ev.__dict__


def prediction_confidence(score: float, metrics: dict) -> float:
    """A transparent, deterministic confidence proxy: anchored on the model R2 and
    boosted when the score sits well clear of a risk-band boundary."""
    base = 60.0 + float(metrics.get("r2", 0.85)) * 35.0
    edge = min(abs(score - 40), abs(score - 70))
    return float(min(99.0, round(base + min(8.0, edge * 0.3), 0)))


def gauge_figure(score: float, risk: str):
    color = RISK_COLOR.get(risk, "#37a2ff")
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            number={"suffix": "/100", "font": {"size": 38, "color": "white"}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#9cb1d6"},
                "bar": {"color": color, "thickness": 0.28},
                "bgcolor": "rgba(0,0,0,0)",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 40], "color": "rgba(68,213,140,0.25)"},
                    {"range": [40, 70], "color": "rgba(247,207,87,0.25)"},
                    {"range": [70, 100], "color": "rgba(255,107,107,0.25)"},
                ],
            },
            title={"text": f"Congestion — {risk}", "font": {"size": 16, "color": "#9cb1d6"}},
        )
    )
    fig.update_layout(template="plotly_dark", height=300, margin=dict(l=20, r=20, t=55, b=10), paper_bgcolor="rgba(0,0,0,0)")
    return fig


def render_city_overview() -> None:
    m = folium.Map(location=[12.9716, 77.5946], zoom_start=11, tiles="cartodbpositron")
    for name, h in CITY_HUBS.items():
        load = h["baseline"]
        color = "#e74c3c" if load >= 85 else "#f1c40f" if load >= 70 else "#2ecc71"
        folium.CircleMarker(
            [h["lat"], h["lon"]],
            radius=6 + load / 12,
            color=color, fill=True, fill_color=color, fill_opacity=0.75,
            popup=folium.Popup(f"<b>{name}</b><br>Baseline load: {load}/100<br>Zone: {h['zone']}", max_width=240),
            tooltip=f"{name} — {load}/100",
        ).add_to(m)
    _folium_html(m, 420)


def city_kpis(snapshot: pd.DataFrame, prediction: dict) -> tuple[int, int, int, str]:
    hotspots = int((snapshot["severity"] == "Red").sum()) if "severity" in snapshot else 0
    avg_load = int(round(snapshot["congestion"].mean())) if "congestion" in snapshot else 0
    try:
        events_today = len(recent_predictions(limit=100))
    except Exception:
        events_today = 0
    return events_today, avg_load, hotspots, prediction["risk_level"]


def render_alert_banner(prediction: dict) -> None:
    risk = prediction["risk_level"]
    if risk == "HIGH":
        st.markdown(
            f'<div class="alert-banner">⚠ HIGH CONGESTION ALERT — {prediction["congestion_score"]:.0f}/100 expected during '
            f'{prediction["expected_peak_time"]}. Activate diversions and stage resources now.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="alert-ok">● City status {risk} — congestion {prediction["congestion_score"]:.0f}/100. '
            f'Monitoring active, no emergency staging required.</div>',
            unsafe_allow_html=True,
        )


def main():
    inject_css()
    model, metrics = bootstrap()

    if "event_type" not in st.session_state:
        st.session_state.event_type = DEMO_PRESET["event_type"]
    if "event_location" not in st.session_state:
        st.session_state.event_location = DEMO_PRESET["event_location"]
    if "crowd_size" not in st.session_state:
        st.session_state.crowd_size = DEMO_PRESET["crowd_size"]
    if "weather_condition" not in st.session_state:
        st.session_state.weather_condition = DEMO_PRESET["weather_condition"]
    if "event_start_time" not in st.session_state:
        st.session_state.event_start_time = datetime.now().replace(hour=DEMO_PRESET["event_start_hour"], minute=0, second=0, microsecond=0)
    if "event_duration_hr" not in st.session_state:
        st.session_state.event_duration_hr = DEMO_PRESET["event_duration_hr"]

    # Ensure a prediction always exists so the top ribbon and tabs have data.
    if "last_prediction" not in st.session_state:
        default_event = demo_request()
        st.session_state.last_prediction = get_prediction(default_event)
        st.session_state.last_request = default_event.__dict__

    prediction = st.session_state.last_prediction
    snapshot = build_road_snapshot(prediction["congestion_score"], st.session_state.last_request["event_location"])
    trend_df, allocation_df = build_trend_frame()
    confidence = prediction_confidence(prediction["congestion_score"], metrics)

    st.markdown(
        """
        <div class="hero">
          <h1>Smart City Command Center</h1>
          <p>Government-grade traffic impact prediction, route planning, deployment guidance, and AI command support.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Live alert + city KPI ribbon (always visible, above the tabs).
    render_alert_banner(prediction)
    events_today, avg_load, hotspots, city_risk = city_kpis(snapshot, prediction)
    st.markdown(
        f"""
        <div class="card-row">
            {metric_card("Events Tracked Today", str(events_today), "Logged to the command DB")}
            {metric_card("Avg City Traffic Load", f"{avg_load}%", "Across monitored corridors")}
            {metric_card("Active Hotspots", str(hotspots), "Corridors in red zone")}
            {metric_card("City Risk Level", city_risk, "Current operational posture", city_risk)}
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<br/>", unsafe_allow_html=True)

    with st.sidebar:
        st.subheader("System Status")
        for label in ("Model Online", "API " + ("Connected" if using_api() else "Standby (in-process)"),
                      "Prediction Engine Active", "Map Service Running", "Resource Planner Active"):
            st.markdown(f'<div class="status-line"><span class="dot"></span>{label}</div>', unsafe_allow_html=True)
        st.divider()
        st.subheader("Quick Scenarios")
        for name, preset in SCENARIO_PRESETS.items():
            if st.button(name, use_container_width=True, key=f"scn_{name}"):
                apply_scenario(preset)
                st.rerun()
        st.divider()
        st.subheader("Model")
        st.write(f"Engine: **{metrics['model_name']}**")
        st.write(f"Accuracy (binned LOW/MED/HIGH): **{metrics['accuracy']:.3f}**")
        st.write(f"RMSE: **{metrics['rmse']:.3f}**  ·  R2: **{metrics['r2']:.3f}**")
        st.write(f"Prediction source: **{'FastAPI backend' if using_api() else 'in-process'}**")
        st.caption(
            "Metrics reflect fit on synthetic training data and a demo calibration factor; "
            "revalidate on real labelled traffic before any production claim."
        )

    screen1, screen2, screen3, screen4, screen5, screen6, screen7 = st.tabs(
        [
            "Screen 1: Event Input",
            "Screen 2: Impact Prediction",
            "Screen 3: Traffic Heatmap",
            "Screen 4: Diversion",
            "Screen 5: Police Deployment",
            "Screen 6: AI Commander",
            "Screen 7: Analytics",
        ]
    )

    with screen1:
        st.markdown('<div class="section-title">Event Input & City Overview</div>', unsafe_allow_html=True)
        st.caption("One-click scenarios (auto-fill the form, then re-run instantly):")
        scn_cols = st.columns(len(SCENARIO_PRESETS))
        for col, (name, preset) in zip(scn_cols, SCENARIO_PRESETS.items()):
            if col.button(name, use_container_width=True, key=f"home_{name}"):
                apply_scenario(preset)
                st.rerun()

        form_col, map_col = st.columns([1.05, 0.95])
        with form_col:
            with st.form("event_input_form", border=False):
                c1, c2 = st.columns(2)
                event_type = c1.selectbox("Event Type", EVENT_TYPES, index=EVENT_TYPES.index(st.session_state.event_type))
                event_location = c2.selectbox("Event Location", list(CITY_HUBS.keys()), index=list(CITY_HUBS.keys()).index(st.session_state.event_location))
                crowd_size = c1.slider("Expected Crowd Size", 500, 100000, int(st.session_state.crowd_size), step=500)
                event_date = c2.date_input("Event Date", value=datetime.now().date())
                event_time = c1.time_input("Event Start Time", value=st.session_state.event_start_time.time())
                event_duration_hr = c2.slider("Event Duration (hours)", 1.0, 12.0, float(st.session_state.event_duration_hr), 0.5)
                weather_condition = c1.selectbox("Weather Condition", WEATHER_TYPES, index=WEATHER_TYPES.index(st.session_state.weather_condition))
                submitted = st.form_submit_button("🚦 ANALYZE EVENT IMPACT", use_container_width=True)

            if submitted:
                st.session_state.event_type = event_type
                st.session_state.event_location = event_location
                st.session_state.crowd_size = crowd_size
                st.session_state.weather_condition = weather_condition
                st.session_state.event_start_time = datetime.combine(event_date, event_time)
                st.session_state.event_duration_hr = event_duration_hr
                event = EventRequest(
                    event_type=event_type,
                    event_location=event_location,
                    crowd_size=crowd_size,
                    event_start_time=st.session_state.event_start_time.isoformat(),
                    event_duration_hr=event_duration_hr,
                    weather_condition=weather_condition,
                )
                st.session_state.last_prediction = get_prediction(event)
                st.session_state.last_request = event.__dict__
                st.rerun()

            st.markdown(
                """
                <div class="pill">Dark command center</div>
                <div class="pill">Live ML scoring</div>
                <div class="pill">Map-based decisions</div>
                <div class="pill">Official dashboard UI</div>
                """,
                unsafe_allow_html=True,
            )
        with map_col:
            st.caption("Live city corridor load — 🔴 severe · 🟡 moderate · 🟢 normal")
            render_city_overview()

    with screen2:
        st.markdown('<div class="section-title">Traffic Impact Prediction</div>', unsafe_allow_html=True)
        gauge_col, kpi_col = st.columns([0.9, 1.1])
        with gauge_col:
            if HAS_PLOTLY:
                st.plotly_chart(gauge_figure(prediction["congestion_score"], prediction["risk_level"]), use_container_width=True)
            else:
                st.metric("Congestion Score", f"{prediction['congestion_score']:.0f}/100", prediction["risk_level"])
            st.markdown(
                f'<div style="text-align:center;color:#9cb1d6;">Model confidence '
                f'<b style="color:#37a2ff;">{confidence:.0f}%</b></div>',
                unsafe_allow_html=True,
            )
        with kpi_col:
            st.markdown(
                f"""
                <div class="card-row" style="grid-template-columns:repeat(2,minmax(0,1fr));">
                    {metric_card("Risk Level", prediction["risk_level"], "Operational severity", prediction["risk_level"])}
                    {metric_card("Expected Peak Time", prediction["expected_peak_time"], "Resource staging window")}
                    {metric_card("Affected Roads", str(prediction["number_of_affected_roads"]), "Corridors requiring control")}
                    {metric_card("Estimated Delay", f"{prediction['estimated_delay_min']} min", "Projected commuter delay")}
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                f"""
                <div style="margin-top:14px;color:#9cb1d6;">Overall Impact Score
                  <b style="color:#fff;float:right;">{prediction['congestion_score']:.0f}%</b></div>
                <div class="impact-track"><div class="impact-fill" style="width:{prediction['congestion_score']:.0f}%;"></div></div>
                """,
                unsafe_allow_html=True,
            )
        st.markdown("#### Affected roads detail")
        st.dataframe(pd.DataFrame(prediction["affected_roads"]), use_container_width=True)

    with screen3:
        st.markdown('<div class="section-title">Traffic Heatmap</div>', unsafe_allow_html=True)
        map_c, list_c = st.columns([1.4, 0.6])
        with map_c:
            render_heatmap(prediction, snapshot)
            st.caption("Red = congested · Yellow = moderate · Green = free. Hover for hotspot details.")
        with list_c:
            st.markdown("##### Top Impacted Roads")
            top_roads = snapshot.sort_values("congestion", ascending=False).head(5)
            for i, (_, r) in enumerate(top_roads.iterrows(), start=1):
                st.markdown(
                    f'<div class="road-rank"><span><b>{i}. {r["name"]}</b><br>'
                    f'<span style="color:#9cb1d6;font-size:0.82rem;">{int(r["congestion"])}/100 load</span></span>'
                    f'<span class="delay">{int(r["expected_delay_min"])} min</span></div>',
                    unsafe_allow_html=True,
                )

    with screen4:
        st.markdown('<div class="section-title">Diversion Recommendations</div>', unsafe_allow_html=True)
        left, right = st.columns([1.1, 0.9])
        with left:
            routes_df = pd.DataFrame(prediction["diversion_routes"])
            st.dataframe(
                routes_df[["affected_road", "alternate_route", "time_saved_min"]],
                use_container_width=True,
            )
        with right:
            render_diversion_map(prediction)

    with screen5:
        st.markdown('<div class="section-title">Police Deployment</div>', unsafe_allow_html=True)
        res = prediction["resources"]
        st.markdown(
            f"""
            <div class="card-row">
                {metric_card("👮 Police Officers", str(res["Police Officers Required"]), "Staging for traffic control")}
                {metric_card("🚧 Barricades", str(res["Barricades Required"]), "Primary closure points")}
                {metric_card("🚦 Traffic Marshals", str(res["Traffic Marshals Required"]), "Pedestrian & junction support")}
                {metric_card("🚑 Emergency Units", str(res["Emergency Units Required"]), "On-standby response")}
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_deployment_map(snapshot, res)

    with screen6:
        st.markdown('<div class="section-title">AI Traffic Commander</div>', unsafe_allow_html=True)
        render_ai_panel(prediction["ai_summary"], prediction)
        st.markdown("### Human-readable directives")
        st.write(
            f"Deploy {prediction['resources']['Police Officers Required']} officers and "
            f"{prediction['resources']['Barricades Required']} barricades near {prediction['affected_roads'][0]['road_name'] if prediction['affected_roads'] else st.session_state.event_location}."
        )
        st.write(
            f"Use {len(prediction['diversion_routes'])} diversion routes and stage emergency units near the outer access roads."
        )

    with screen7:
        st.markdown('<div class="section-title">Analytics Dashboard</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        if HAS_PLOTLY:
            trend_fig = go.Figure()
            trend_fig.add_trace(go.Scatter(x=trend_df["hour"], y=trend_df["congestion_score"], mode="lines+markers", name="Congestion"))
            trend_fig.update_layout(template="plotly_dark", height=320, margin=dict(l=10, r=10, t=30, b=10), title="Congestion Trend")
            c1.plotly_chart(trend_fig, use_container_width=True)

            vol_fig = go.Figure()
            vol_fig.add_trace(go.Bar(x=trend_df["hour"], y=trend_df["traffic_volume"], marker_color="#37a2ff"))
            vol_fig.update_layout(template="plotly_dark", height=320, margin=dict(l=10, r=10, t=30, b=10), title="Traffic Volume Trend")
            c2.plotly_chart(vol_fig, use_container_width=True)
        else:
            c1.line_chart(trend_df.set_index("hour")["congestion_score"])
            c2.bar_chart(trend_df.set_index("hour")["traffic_volume"])

        c3, c4 = st.columns(2)
        impact_df = pd.DataFrame(
            {
                "Road": [x["road_name"] for x in prediction["affected_roads"]],
                "Expected Delay": [x["expected_delay"] for x in prediction["affected_roads"]],
            }
        )
        if not impact_df.empty:
            if HAS_PLOTLY:
                impact_fig = px.bar(impact_df, x="Road", y="Expected Delay", color="Road", template="plotly_dark", title="Event Impact Analysis")
                impact_fig.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10), showlegend=False)
                c3.plotly_chart(impact_fig, use_container_width=True)
            else:
                c3.bar_chart(impact_df.set_index("Road")["Expected Delay"])
        if HAS_PLOTLY:
            alloc_fig = px.bar(
                allocation_df.melt(id_vars="hour", var_name="Resource", value_name="Count"),
                x="hour",
                y="Count",
                color="Resource",
                barmode="stack",
                template="plotly_dark",
                title="Resource Allocation Summary",
            )
            alloc_fig.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10))
            c4.plotly_chart(alloc_fig, use_container_width=True)
        else:
            c4.bar_chart(allocation_df.set_index("hour"))

        st.markdown("### Model Metrics")
        metric_cols = st.columns(4)
        metric_cols[0].metric("Accuracy", f"{metrics['accuracy']:.3f}")
        metric_cols[1].metric("RMSE", f"{metrics['rmse']:.3f}")
        metric_cols[2].metric("R2", f"{metrics['r2']:.3f}")
        metric_cols[3].metric("Model", metrics["model_name"])

        if metrics.get("feature_importance"):
            importance_df = pd.DataFrame(metrics["feature_importance"])
            if HAS_PLOTLY:
                imp_fig = px.bar(importance_df[::-1], x="importance", y="feature", orientation="h", template="plotly_dark", title="Feature Importance")
                imp_fig.update_layout(height=360, margin=dict(l=10, r=10, t=30, b=10))
                st.plotly_chart(imp_fig, use_container_width=True)
            else:
                st.bar_chart(importance_df.set_index("feature")["importance"])

    st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
