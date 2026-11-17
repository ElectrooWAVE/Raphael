# Retail Product Demand Forecasting - Project Rules

PROJECT: Retail Product Demand Forecasting (Phase 1). Python, Streamlit, Plotly, Pandas, NumPy.
Forecasting model: Amazon Chronos-2 (`amazon/chronos-2`) via the official `chronos-forecasting` package.

## Hard rules
1. Every forecast shown anywhere must come from real inference by the official
   amazon/chronos-2 model via `Chronos2Pipeline.predict_df`. NEVER add mock, random,
   placeholder, hard-coded, moving-average or "fallback" forecasts, and never substitute
   another model (Chronos-Bolt, T5, Prophet, ARIMA, etc.). If inference fails, show a clear error.
2. Do not edit `src/rdf/forecaster.py` without re-running `scripts/smoke_test.py`
   and reporting its real printed output.
3. Never delete genuine zero-sales rows. A truly missing day is NaN, never 0.
4. Do not install or reinstall torch. It is already installed with CUDA 12.8 for an
   NVIDIA RTX 5060 Ti. If another dependency change is needed, ask me first.
5. Use the project virtual environment (`.venv`). Never install packages globally.
6. UI code lives in `web/` (HTML/CSS/JS) and the API in `server/`; business logic stays in `src/rdf/`. Keep `app.py` (Streamlit) untouched.
7. Light, minimal, or subtle neumorphic (soft-UI) styling with mandatory WCAG AA contrast; short purposeful 2D animations (chart reveal, number count-up, hover/press) allowed and disabled under prefers-reduced-motion.
8. After every change run `pytest -q`. Do not say "done" unless tests pass, and paste the actual output.
9. Never invent results. If something could not be run, say so plainly.
10. Tests of the forecast endpoint use the real Chronos-2 model. Never use mocks or stubs for forecasting.

## Environment
- Windows, PowerShell. Python 3.12 virtual environment in `.venv`.
- 32 GB RAM, 16 GB GPU. Chronos-2 is a 120M-parameter model, so no quantisation or offloading is needed.

## Data
- `data/demand_history.csv`: long format (date, material, area, quantity, is_promotion), 75 series x 1913 days.
- Also supported: official M5 `data/sales_train_validation.csv`.
- Other CSVs in `data/` (inventory, lead times, calendar events) are NOT used in Phase 1.

## Workflow
- Work on one task at a time, show real command output, then stop for review.
- Do not add features beyond what was asked.
