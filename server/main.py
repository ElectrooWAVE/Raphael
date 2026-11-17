"""FastAPI backend for Retail Product Demand Forecasting.

Run: uvicorn server.main:app --reload
"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
WEB_DIR = PROJECT_ROOT / "web"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from rdf import config
from rdf.data_loader import get_series, list_series, load_sales, series_summary
from rdf.forecaster import ForecastError, forecast, load_pipeline


class ForecastRequest(BaseModel):
    series_id: str = Field(..., min_length=1)
    horizon: int = Field(default=config.DEFAULT_HORIZON, ge=config.MIN_HORIZON, le=config.MAX_HORIZON)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.sales = load_sales()
    try:
        pipeline, device = load_pipeline()
        app.state.pipeline = pipeline
        app.state.device = device
        app.state.load_error = None
    except ForecastError as e:
        app.state.pipeline = None
        app.state.device = None
        app.state.load_error = str(e)
    yield


app = FastAPI(title="Retail Product Demand Forecasting", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request, exc: RequestValidationError) -> JSONResponse:
    messages = "; ".join(
        f"{'.'.join(str(p) for p in err.get('loc', []))}: {err.get('msg', 'invalid input')}"
        for err in exc.errors()
    )
    return JSONResponse(status_code=400, content={"detail": messages or "Invalid request input."})


@app.get("/api/series")
def api_series() -> list[str]:
    return list_series(app.state.sales)


@app.get("/api/history")
def api_history(series_id: str = Query(..., min_length=1)) -> dict[str, Any]:
    try:
        history = get_series(app.state.sales, series_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Unknown series: {series_id}") from e

    summary = series_summary(history)
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in history["date"]],
        "sales": [None if pd.isna(v) else float(v) for v in history["sales"]],
        "summary": {
            "days": summary["days"],
            "start": summary["start"].isoformat(),
            "end": summary["end"].isoformat(),
            "zero_days": summary["zero_days"],
            "missing_days": summary["missing_days"],
            "total_units": summary["total_units"],
        },
    }


@app.post("/api/forecast")
def api_forecast(req: ForecastRequest) -> dict[str, Any]:
    try:
        history = get_series(app.state.sales, req.series_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Unknown series: {req.series_id}") from e

    if app.state.pipeline is None:
        raise HTTPException(status_code=500, detail=app.state.load_error or "Model pipeline failed to load.")

    try:
        res = forecast(app.state.pipeline, history, req.horizon, req.series_id)
    except ForecastError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {
        "dates": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in res["date"]],
        "mean": [float(v) for v in res["mean"]],
        "q10": [float(v) for v in res["q10"]],
        "q50": [float(v) for v in res["q50"]],
        "q90": [float(v) for v in res["q90"]],
        "total": float(res["mean"].sum()),
        "daily_average": float(res["mean"].mean()),
        "device": app.state.device,
        "model": config.MODEL_ID,
    }


WEB_DIR.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
