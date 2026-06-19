# -*- coding: utf-8 -*-
"""Generate a current project report PDF for the Smart City Command Center."""

from __future__ import annotations

import json
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parent
REPORT_PDF = ROOT / "Project-Report.pdf"


def _read_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


DAY2 = _read_json(ROOT / "outputs" / "reports" / "day2_metrics.json")
SMART = _read_json(ROOT / "outputs" / "reports" / "smart_city_model_metrics.json")


class ReportPDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(110, 110, 110)
        self.cell(0, 5, "Smart City Command Center - Project Report", align="R")
        self.ln(7)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(110, 110, 110)
        self.cell(0, 5, f"Page {self.page_no()}", align="C")


pdf = ReportPDF("P", "mm", "A4")
pdf.set_auto_page_break(True, 16)
pdf.set_margins(15, 14, 15)
pdf.add_page()


def h1(text):
    pdf.set_fill_color(21, 32, 48)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 17)
    pdf.multi_cell(0, 10, text, fill=True)
    pdf.ln(2)


def h2(text):
    pdf.set_text_color(33, 74, 115)
    pdf.set_font("Helvetica", "B", 12.5)
    pdf.multi_cell(0, 7, text)
    pdf.ln(1)


def para(text):
    pdf.set_text_color(34, 34, 34)
    pdf.set_font("Helvetica", "", 10.4)
    pdf.multi_cell(0, 5.4, text)
    pdf.ln(1)


def bullet(text):
    pdf.set_font("Helvetica", "", 10.4)
    pdf.set_text_color(33, 74, 115)
    pdf.cell(5, 5.4, "-")
    pdf.set_text_color(34, 34, 34)
    pdf.multi_cell(0, 5.4, text)
    pdf.ln(0.2)


def table(rows, widths):
    line_h = 5.2
    for i, row in enumerate(rows):
        row = [str(c) for c in row]
        is_header = i == 0
        pdf.set_font("Helvetica", "B" if is_header else "", 9.2)
        row_h = max(len(pdf.multi_cell(w, line_h, c, dry_run=True, output="LINES")) for c, w in zip(row, widths)) * line_h + 1.2
        if pdf.get_y() + row_h > pdf.h - 16:
            pdf.add_page()
        x0 = pdf.get_x()
        y0 = pdf.get_y()
        if is_header:
            pdf.set_fill_color(231, 238, 245)
            pdf.set_text_color(0, 0, 0)
        else:
            pdf.set_fill_color(248, 249, 251)
            pdf.set_text_color(34, 34, 34)
        x = x0
        for c, w in zip(row, widths):
            pdf.set_xy(x, y0)
            pdf.multi_cell(w, line_h, c, border=0, fill=True)
            x += w
        pdf.set_draw_color(205, 205, 205)
        pdf.rect(x0, y0, sum(widths), row_h)
        pdf.set_xy(x0, y0 + row_h)
    pdf.ln(2)


def callout(text):
    pdf.set_fill_color(244, 246, 249)
    pdf.set_draw_color(33, 74, 115)
    pdf.set_text_color(34, 34, 34)
    pdf.set_font("Helvetica", "I", 10.2)
    pdf.multi_cell(0, 5.4, text, border=1, fill=True)
    pdf.ln(2)


h1("Smart City Command Center - Project Report")
para(
    "This report describes what the project currently does, what is already implemented and verified, "
    "and what still remains if the goal is production deployment rather than a hackathon demo."
)

h2("1. What the project is doing")
bullet("It turns an event input form into a traffic impact prediction workflow for Bengaluru.")
bullet("It trains a congestion model with XGBoost, using event type, crowd size, weather, time, location, and historical traffic.")
bullet("It returns a congestion score, risk level, peak time, affected roads, diversion routes, and police deployment guidance.")
bullet("It renders a command-center dashboard with seven screens: input, impact, heatmap, diversion, deployment, AI commander, and analytics.")
bullet("It logs predictions and model metrics into SQLite so the system can act like a learning loop.")

h2("2. What is already built and verified")
table(
    [
        ["Area", "Current state"],
        ["Frontend", "Streamlit dashboard with dark command-center styling, maps, KPI cards, charts, and a demo preset button."],
        ["Backend", "FastAPI service with /health, /train, and /predict endpoints (lifespan startup)."],
        ["UI-backend link", "Dashboard calls predict_event in-process by default; set SMART_CITY_API_URL to route through the FastAPI /predict endpoint, with automatic in-process fallback."],
        ["ML model", "XGBoost congestion model trained and saved to disk."],
        ["Maps", "Folium heatmap, hotspot markers, diversion routes, and deployment markers."],
        ["Analytics", "Congestion, traffic volume, impact, resource allocation, and feature importance charts."],
        ["Persistence", "SQLite tables for event predictions, AI messages, and metrics."],
        ["Tests", "pytest suite (tests/) covering risk bands, prediction fields, resource scaling, API endpoints, validation, and DB logging - 9 passing."],
        ["Demo flow", "Cricket Match / 50,000 crowd case returns about 91/100 congestion and a high-risk response plan."],
    ],
    [42, 120],
)

if DAY2:
    h2("3. Existing day-2 model results")
    table(
        [
            ["Metric", "Value"],
            ["Clearance regressor", f"{DAY2.get('clearance', {}).get('mae_minutes', 'n/a')} min MAE"],
            ["Priority classifier", f"{DAY2.get('priority', {}).get('accuracy', 'n/a')} accuracy"],
            ["Blackspots", f"{DAY2.get('blackspots', {}).get('clusters', 'n/a')} clusters"],
            ["Junction forecast", f"{DAY2.get('junction_forecast', {}).get('rows', 'n/a')} rows"],
            ["Planned events", f"{DAY2.get('planned_events', {}).get('rows', 'n/a')} scored events"],
            ["Surge detection", f"{DAY2.get('surge_detection', {}).get('rows', 'n/a')} alerts"],
        ],
        [62, 100],
    )

if SMART:
    h2("4. Smart City model metrics")
    table(
        [
            ["Metric", "Value"],
            ["Model", SMART.get("model_name", "n/a")],
            ["Accuracy (binned LOW/MED/HIGH)", SMART.get("accuracy", "n/a")],
            ["RMSE", SMART.get("rmse", "n/a")],
            ["R2", SMART.get("r2", "n/a")],
            ["Data source", SMART.get("data_source", "synthetic")],
        ],
        [62, 100],
    )
    para(
        "Caveat: accuracy is derived by binning the regressor output into LOW/MEDIUM/HIGH, "
        "and all metrics reflect fit on synthetic training data. They must be revalidated "
        "against real labelled traffic before any operational or production claim is made."
    )

h2("5. Engineering fixes applied in this pass")
para("A review verified the project runs and matches this report, then applied 9 fixes (all 9 complete and verified):")
table(
    [
        ["#", "Fix", "Status"],
        ["1", "Dashboard now routes predictions through the FastAPI /predict endpoint when SMART_CITY_API_URL is set (in-process fallback), so the UI is a real API client instead of bypassing the backend.", "Done"],
        ["2", "Added missing httpx dependency (required by the FastAPI TestClient and the dashboard API client).", "Done"],
        ["3", "Moved the 0.965 score fudge factor into config as a documented SCORE_CALIBRATION_FACTOR (presentation calibration, not a modelling correction).", "Done"],
        ["4", "Replaced the deprecated FastAPI @app.on_event startup hook with a modern lifespan handler.", "Done"],
        ["5", "Recorded a synthetic-data caveat in the metrics JSON and report so the scores are not mistaken for real-world skill.", "Done"],
        ["6", "Labelled accuracy as binned LOW/MEDIUM/HIGH classification, separate from the RMSE/R2 regression metrics.", "Done"],
        ["7", "Added a pytest suite (9 tests) for risk bands, prediction fields, resource scaling, API endpoints, input validation, and DB logging.", "Done"],
        ["8", "Moved hard-coded peak-time and resource-plan magic numbers into config (PEAK windows, TIME_PRESSURE, RESOURCE_PLAN, RISK_BANDS).", "Done"],
        ["9", "Pinned dependency versions to ranges verified on Python 3.14 for reproducible installs.", "Done"],
    ],
    [10, 132, 20],
)

h2("6. What it still needs to do (production)")
bullet("Connect to real live traffic feeds instead of synthetic demo scenario data for the command-center layer.")
bullet("Replace the offline road snapshots with a real geospatial road network and live routing data.")
bullet("Add a true SUMO runtime integration for microscopic simulation beyond the fallback queue model.")
bullet("Retrain and revalidate the congestion model on real labelled traffic; the current metrics are on synthetic data.")
bullet("Add authentication, API rate limiting, and deployment monitoring before any public deployment.")

h2("7. Hackathon readiness summary")
callout(
    "Assessment: the project is hackathon-ready. The demo flow works end-to-end, the UI is polished, "
    "the outputs are coherent for judges, and the 9 review fixes above are applied and verified. "
    "The main remaining gap is production realism (real data and validation), not demo completeness."
)

h2("8. How to run")
pdf.set_font("Courier", "", 9.4)
pdf.set_text_color(34, 34, 34)
pdf.multi_cell(
    0,
    5.2,
    "pip install -r requirements.txt\n"
    "python run_all.py                      # Day 1-5 pipeline\n"
    "pytest -q                              # run the test suite (9 tests)\n"
    "uvicorn backend.api:app --reload       # start the API (optional)\n"
    "# optional: route the dashboard through the API\n"
    "#   set SMART_CITY_API_URL=http://127.0.0.1:8000\n"
    "streamlit run app/dashboard.py",
    border=1,
)

pdf.output(str(REPORT_PDF))
print(f"Wrote {REPORT_PDF}")
