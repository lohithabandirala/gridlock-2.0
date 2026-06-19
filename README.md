# Predictive Incident & Response Platform - Bengaluru

End-to-end Day 1-5 solution for the **Event-Driven Congestion** problem using the Astram incident dataset.
The repository now also includes a Smart City Command Center layer with:

- an event input dashboard
- XGBoost-based congestion prediction
- heatmap and route visualisation
- police deployment guidance
- AI command narration
- analytics charts
- FastAPI prediction endpoints
- SQLite logging for predictions and model metrics

## What this project does

The system turns historical incident records into an operational response platform:

- cleans and engineers the dataset
- trains prediction models for clearance time and severity
- mines chronic blackspots and corridor risk
- scores planned events for operational impact
- detects surge/anomaly patterns in unplanned incidents
- allocates manpower and barricades
- plans diversion routes
- simulates closure what-if scenarios
- logs predicted-vs-actual outcomes into SQLite
- exposes the results in a Streamlit dashboard

## Quick start

```bash
pip install -r requirements.txt
python run_all.py
streamlit run app/dashboard.py
```

Smart City backend API:

```bash
uvicorn backend.api:app --reload
```

Run a single stage:

```bash
python pipelines/run_day1.py
python pipelines/run_day2.py
python pipelines/run_day3.py
python pipelines/run_day4.py
python pipelines/run_day5.py
```

## Project structure

```text
data/raw/astram_events.csv        Raw Astram incident dataset
data/processed/events_features.csv Day-1 cleaned + engineered dataset
src/                              Core implementation modules
pipelines/                        Day 1-5 pipeline entry points
app/dashboard.py                  Streamlit dashboard
outputs/figures                   Charts and visualizations
outputs/reports                   CSV / JSON / Markdown report artifacts
outputs/models                    Trained models and road graph files
outputs/db                        SQLite learning loop database
outputs/sumo                      SUMO-ready scenario bundle
run_all.py                        Orchestrates Day 1 -> Day 5
make_project_report.py            Generates the PDF report
```

## Day-by-day summary

| Day | Modules | Outputs |
|-----|---------|---------|
| 1 | `data_loader`, `features`, `eda`, `weather` | cleaned data, weather join, engineered features, EDA report, figures |
| 2 | `models`, `impact`, `anomaly` | clearance model, severity classifier, blackspots, corridor risk, junction forecast, planned-event score, surge alerts |
| 3 | `optimize`, `diversion` | OR-Tools manpower plan, OSMnx/NetworkX diversion plan |
| 4 | `simulate`, `app/dashboard` | time-stepped micro-sim, SUMO-ready bundle, dashboard |
| 5 | `learn` | SQLite report card and retraining loop |

## Outputs you should expect

After `python run_all.py`, the project writes:

- `outputs/reports/day1_eda_report.md`
- `outputs/reports/day2_metrics.json`
- `outputs/reports/blackspots.csv`
- `outputs/reports/corridor_risk.csv`
- `outputs/reports/junction_time_forecast.csv`
- `outputs/reports/planned_event_impact.csv`
- `outputs/reports/surge_alerts.csv`
- `outputs/reports/manpower_allocation.csv`
- `outputs/reports/diversion_summary.csv`
- `outputs/reports/whatif_demo.json`
- `outputs/reports/day5_report_card.json`
- `outputs/models/*.joblib`
- `outputs/models/road_graph.gml`
- `outputs/db/learning.sqlite`

## Technology stack

- `pandas`, `numpy`, `scikit-learn`, `lightgbm`
- `DBSCAN` for hotspot discovery
- `TF-IDF` + dense embeddings for text features
- `OR-Tools` for manpower allocation
- `NetworkX` for routing
- `Open-Meteo` weather archive join with offline fallback
- `Streamlit` and `Folium` for the dashboard
- `SQLite` for the learning loop

## Notes

- The dataset contains mostly unplanned incidents, so the system focuses on incident risk and clearance time.
- Diversion prefers OSMnx when it is available and falls back to the offline proximity graph otherwise.
- The simulator uses a time-stepped queue model and also writes a SUMO-ready scenario bundle.
- Weather features are joined from Open-Meteo archive data with a deterministic offline fallback.
- The Smart City Command Center uses synthetic training samples to demonstrate a full government-style event workflow even when event-specific historical labels are not available.

## Deployment

This repository includes:

- `Dockerfile`
- `Procfile`
- `.streamlit/config.toml`

That makes it straightforward to deploy to Streamlit Cloud, Render, or Docker-based hosting.

## Requirements

Install with:

```bash
pip install -r requirements.txt
```

The dependency list is intentionally small and fully free.
