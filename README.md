# Retail Product Demand Forecasting

Web dashboard and FastAPI backend for retail demand forecasting using the official pretrained **amazon/chronos-2** model (`chronos-forecasting`).

## Website Features
- **Controls:** Product & Store selectors, Horizon segmented radio control (`7`, `14`, `28`, `56`, `90` days), and **Generate Forecast**.
- **KPIs:** Total predicted demand (expected demand from dense `0.05–0.95` quantiles), average daily predicted demand, and percent change vs the previous N real days.
- **Interactive Chart (`plotly-2.35.2.min.js`):** Historical sales (`#1F4E79`), Chronos-2 median forecast (`#C2571A`), 80% prediction interval, `1M / 3M / 6M / 1Y / All` zoom buttons, thin range slider, adaptive date ticks, and unified hover tooltips (`1 decimal`, `units`).
- **Animations (`motion@11.13.5`):** Left-to-right forecast line reveal (`requestAnimationFrame` + `Plotly.restyle`), interval fade-in, KPI number count-up, sliding horizon highlight, and staggered panel entrance—all skipped automatically under `prefers-reduced-motion`.
- **Data & Export:** Collapsible `Forecast data` table (`Date`, `Median`, `Expected`, `Low (10th)`, `High (90th)`) with client-side **Download CSV**.
- **Forecasting History & Run Inspector:** Filter runs by series or engine (`Chronos-2`, `Custom (LightGBM)`, `Baseline`), sort newest/oldest, paginate, delete runs with confirmation, and click **Inspect** to view run metadata, reproducibility info (package versions, dataset SHA-256, parameters), stored forecast chart + table, CSV download, and **Re-run with same settings** (creates a new run).
- **80% Interval Calibration (Validation-Only):** Computes per-series validation backtest error statistics (`sigma_d`, MAE, WAPE, Bias, raw vs calibrated 80% coverage) and scales `[q10, q90]` around the median so empirical 80% interval coverage targets ~80% without ever touching the test window.

## Windows Setup & Run Commands
```powershell
cd E:\projects\Raphael
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pytest tests/test_calibration.py -v -s
.venv\Scripts\python.exe -m pytest tests/test_history_api.py -q
.venv\Scripts\python.exe scripts/smoke_test.py
.venv\Scripts\python.exe -m uvicorn server.main:app
```
Open **`http://127.0.0.1:8000`** for the web dashboard (or **`http://127.0.0.1:8000/docs`** for the FastAPI Swagger UI).

## Layout
- `server/main.py` — FastAPI backend (`/api/series`, `/api/history`, `/api/forecast`, static `web/` at `/`)
- `web/` — Plain HTML/CSS/JS frontend (`index.html`, `style.css`, `app.js`)
- `src/rdf/` — `config.py`, `data_loader.py`, `forecaster.py`, `plotting.py`
- `app.py` — Legacy Streamlit dashboard (kept untouched)
- `tests/` — `test_data_loader.py`, `test_app_render.py`, `test_api.py`
- `scripts/` — `smoke_test.py`, `run_checks.py`, `evaluate.py`, `eval_covariates.py`, `experiments.py`, `finetune.py`, `final_report.py`
