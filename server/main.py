"""FastAPI backend for Retail Product Demand Forecasting & Model Comparison Platform.

Maintains 100% backward compatibility with existing Chronos-2 endpoints while adding:
- Universal Dataset Management (CSV, XLSX, Parquet)
- Custom Recursive LightGBM Training & Inference
- Seasonal-Naive Baseline Benchmarking
- Multi-Model Side-by-Side Comparison
- Walk-Forward Backtesting & Error Metrics Evaluation
- Persistent Forecast & Experiment History
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
WEB_DIR = PROJECT_ROOT / "web"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from rdf import config
from rdf.baseline import forecast_seasonal_naive
from rdf.data_loader import get_series as get_series_legacy, list_series as list_series_legacy, load_sales, series_summary
from rdf.dataset_manager import (
    delete_dataset,
    ensure_default_dataset,
    get_dataset_series_list,
    get_dataset_version,
    get_series_history,
    import_dataset,
    inspect_file,
    list_datasets,
    read_raw_file,
    sanitize_filename,
    validate_dataset_frame,
)
from rdf.db import get_db, init_db, now_iso
from rdf.evaluation import compute_metrics, generate_backtest_cutoffs
from rdf.forecast_service import (
    compare_models,
    count_forecast_runs,
    delete_forecast_run,
    generate_single_forecast,
    get_forecast_run_details,
    list_forecast_runs,
)
from rdf.forecaster import ForecastError, forecast as forecast_chronos, load_pipeline
from rdf.lgbm_forecaster import (
    get_training_job_status,
    list_trained_models,
    start_training_job,
)


# --- Request & Response Models ---

class ForecastRequest(BaseModel):
    series_id: str = Field(..., min_length=1)
    horizon: int = Field(default=config.DEFAULT_HORIZON, ge=1, le=365)
    model_type: str = Field(default="chronos")
    model_id: Optional[str] = None
    dataset_id: Optional[str] = None


class CompareRequest(BaseModel):
    series_id: str = Field(..., min_length=1)
    horizon: int = Field(default=28, ge=1, le=180)
    dataset_id: Optional[str] = None
    cutoff_index: Optional[int] = None


class BacktestRequest(BaseModel):
    series_id: str = Field(..., min_length=1)
    horizon: int = Field(default=28, ge=7, le=90)
    dataset_id: Optional[str] = None
    num_cutoffs: int = Field(default=3, ge=1, le=6)
    models: list[str] = Field(default_factory=lambda: ["baseline", "lightgbm", "chronos"])


class TrainModelRequest(BaseModel):
    dataset_id: str = Field(..., min_length=1)
    model_name: Optional[str] = None
    n_estimators: int = Field(default=100, ge=10, le=500)
    learning_rate: float = Field(default=0.05, ge=0.001, le=0.5)
    max_depth: int = Field(default=6, ge=2, le=15)
    num_leaves: int = Field(default=31, ge=7, le=127)
    min_child_samples: int = Field(default=20, ge=2, le=100)
    val_fraction: float = Field(default=0.15, ge=0.05, le=0.4)
    lags: Optional[list[int]] = None
    rolling_windows: Optional[list[int]] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        app.state.default_dataset_id = ensure_default_dataset()
    except Exception as e:
        app.state.default_dataset_id = None
        print(f"Warning: Default dataset seeding skipped: {e}")

    try:
        app.state.sales = load_sales()
    except Exception:
        app.state.sales = pd.DataFrame(columns=["series_id", "date", "sales"])

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


app = FastAPI(title="Retail Product Demand Forecasting Platform", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request, exc: RequestValidationError) -> JSONResponse:
    messages = "; ".join(
        f"{'.'.join(str(p) for p in err.get('loc', []))}: {err.get('msg', 'invalid input')}"
        for err in exc.errors()
    )
    return JSONResponse(status_code=400, content={"detail": messages or "Invalid request input."})


# --- Backward-Compatible Legacy Endpoints ---

@app.get("/api/series")
def api_series(dataset_id: Optional[str] = Query(None)) -> list[str]:
    """List series for active or default dataset."""
    if dataset_id:
        try:
            return get_dataset_series_list(dataset_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
    if hasattr(app.state, "sales") and not app.state.sales.empty:
        return list_series_legacy(app.state.sales)
    if app.state.default_dataset_id:
        return get_dataset_series_list(app.state.default_dataset_id)
    return []


@app.get("/api/history")
def api_history(series_id: str = Query(..., min_length=1), dataset_id: Optional[str] = Query(None)) -> dict[str, Any]:
    """Retrieve history for series."""
    try:
        if dataset_id and dataset_id != "default":
            history = get_series_history(dataset_id, series_id)
        else:
            history = get_series_legacy(app.state.sales, series_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Unknown series: {series_id}") from e
    except Exception as e:
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
    """Generate forecast using selected model (Chronos-2, LightGBM, or Baseline)."""
    model_type = (req.model_type or "chronos").lower().strip()

    if model_type == "chronos" and (req.horizon < config.MIN_HORIZON or req.horizon > config.MAX_HORIZON):
        raise HTTPException(
            status_code=400,
            detail=f"Chronos-2 forecast horizon must be between {config.MIN_HORIZON} and {config.MAX_HORIZON} days.",
        )

    dataset_id = req.dataset_id or app.state.default_dataset_id or "retail-demand-m5"

    # Fetch history
    try:
        if req.dataset_id and req.dataset_id != "default":
            history = get_series_history(req.dataset_id, req.series_id)
        else:
            history = get_series_legacy(app.state.sales, req.series_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Unknown series: {req.series_id}") from e
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Unknown series: {req.series_id}") from e

    # If Chronos-2 is requested, verify pipeline
    if model_type == "chronos" and app.state.pipeline is None:
        raise HTTPException(status_code=500, detail=app.state.load_error or "Chronos-2 model failed to load.")

    chronos_tuple = (app.state.pipeline, app.state.device) if app.state.pipeline else None

    try:
        return generate_single_forecast(
            history_df=history,
            horizon=req.horizon,
            model_type=model_type,
            model_id=req.model_id,
            series_id=req.series_id,
            dataset_id=dataset_id,
            chronos_pipeline_tuple=chronos_tuple,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# --- Universal Dataset Management & Health Helpers ---

ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".xlsx", ".parquet"}


def _device_health() -> dict[str, Any]:
    chronos_loaded = getattr(app.state, "pipeline", None) is not None
    raw_dev = getattr(app.state, "device", None)
    chronos_device = raw_dev.upper() if (chronos_loaded and raw_dev) else "UNAVAILABLE"
    custom_device = "CPU"
    if not chronos_loaded:
        device_label = f"Chronos-2: UNAVAILABLE | Custom: {custom_device}"
    elif chronos_device != custom_device:
        device_label = f"Chronos-2: {chronos_device} | Custom: {custom_device}"
    else:
        device_label = chronos_device
    return {
        "status": "ok",
        "chronos_loaded": chronos_loaded,
        "chronos_device": chronos_device,
        "custom_device": custom_device,
        "device_label": device_label,
        "model_id": config.MODEL_ID,
    }


async def _save_validated_upload(file: UploadFile) -> tuple[Path, str]:
    try:
        safe_name = sanitize_filename(file.filename or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{suffix or 'unknown'}'. Allowed extensions: .csv, .xlsx, .parquet.",
        )

    max_bytes = int(getattr(app.state, "max_upload_bytes", config.MAX_UPLOAD_BYTES))
    tmp_path: Path | None = None
    total_bytes = 0
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = Path(tmp.name)
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum allowed size ({max_bytes // (1024 * 1024) or 1} MB / {max_bytes:,} bytes).",
                    )
                tmp.write(chunk)

        if total_bytes == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        return tmp_path, safe_name
    except HTTPException:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()
        raise
    except Exception as e:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()
        raise HTTPException(status_code=400, detail=f"Failed to read uploaded file: {e}") from e


def _parse_covariates_field(raw_cov: str) -> list[Any]:
    text = (raw_cov or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
    return [c.strip() for c in text.split(",") if c.strip()]


@app.get("/api/health")
def api_health() -> dict[str, Any]:
    """Single source of truth for model engine availability and compute devices."""
    return _device_health()


@app.get("/api/datasets")
def api_list_datasets() -> list[dict[str, Any]]:
    """List all imported datasets and their latest versions."""
    return list_datasets()


@app.get("/api/datasets/{dataset_id}")
def api_get_dataset(dataset_id: str) -> dict[str, Any]:
    """Retrieve metadata for a specific dataset."""
    v_info = get_dataset_version(dataset_id)
    if not v_info:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found.")
    return v_info


@app.delete("/api/datasets/{dataset_id}")
def api_delete_dataset(dataset_id: str) -> dict[str, Any]:
    """Delete a dataset, its versions, and stored files."""
    res = delete_dataset(dataset_id)
    if not res:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found.")
    return res


@app.post("/api/datasets/inspect")
async def api_inspect_dataset(file: UploadFile = File(...)) -> dict[str, Any]:
    """Inspect an uploaded CSV/XLSX/Parquet file and suggest column mappings."""
    tmp_path, safe_name = await _save_validated_upload(file)
    try:
        return inspect_file(tmp_path, display_name=safe_name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to inspect file: {e}") from e
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


@app.post("/api/datasets/validate")
async def api_validate_dataset(
    file: UploadFile = File(...),
    time_col: str = Form(...),
    target_col: str = Form(...),
    series_cols: str = Form(""),
    covariates: str = Form(""),
    frequency: str = Form("D"),
) -> dict[str, Any]:
    """Validate column mappings and data quality before importing."""
    tmp_path, _safe_name = await _save_validated_upload(file)
    sc_list = [c.strip() for c in series_cols.split(",") if c.strip()] if series_cols else []
    cov_list = _parse_covariates_field(covariates)
    try:
        raw_df = read_raw_file(tmp_path)
        return validate_dataset_frame(
            raw_df,
            time_col=time_col,
            target_col=target_col,
            series_cols=sc_list,
            covariates=cov_list,
            frequency=frequency,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Validation failed: {e}") from e
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


@app.post("/api/datasets/import")
async def api_import_dataset(
    file: UploadFile = File(...),
    dataset_name: str = Form(...),
    time_col: str = Form(...),
    target_col: str = Form(...),
    series_cols: str = Form(""),
    covariates: str = Form(""),
    frequency: str = Form("D"),
    description: str = Form(""),
) -> dict[str, Any]:
    """Upload, validate, standardize, and store a new dataset version."""
    tmp_path, safe_name = await _save_validated_upload(file)
    sc_list = [c.strip() for c in series_cols.split(",") if c.strip()] if series_cols else []
    cov_list = _parse_covariates_field(covariates)

    try:
        return import_dataset(
            file_path=tmp_path,
            dataset_name=dataset_name,
            time_col=time_col,
            target_col=target_col,
            series_cols=sc_list,
            covariates=cov_list,
            frequency=frequency,
            description=description,
            strict=True,
            original_filename=safe_name,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Dataset import failed: {e}") from e
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


@app.get("/api/datasets/{dataset_id}/series")
def api_dataset_series(dataset_id: str) -> list[str]:
    """List series in a specific dataset."""
    try:
        return get_dataset_series_list(dataset_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# --- Custom LightGBM Model Training Endpoints ---

@app.get("/api/models")
def api_list_models(dataset_id: Optional[str] = Query(None)) -> list[dict[str, Any]]:
    """List trained custom LightGBM models."""
    return list_trained_models(dataset_id)


@app.post("/api/models/train")
def api_train_model(req: TrainModelRequest) -> dict[str, Any]:
    """Launch asynchronous training of custom recursive forecasting model."""
    try:
        feature_config = None
        if req.lags or req.rolling_windows:
            from src.rdf.features import get_default_feature_config
            from src.rdf.dataset_manager import get_dataset_version
            v = get_dataset_version(req.dataset_id)
            freq = v["frequency"] if v else "D"
            feature_config = get_default_feature_config(freq)
            if req.lags:
                feature_config["lags"] = req.lags
            if req.rolling_windows:
                feature_config["rolling_windows"] = req.rolling_windows

        run_id = start_training_job(
            dataset_id=req.dataset_id,
            model_name=req.model_name or "",
            hyperparameters={
                "n_estimators": req.n_estimators,
                "learning_rate": req.learning_rate,
                "max_depth": req.max_depth,
                "num_leaves": req.num_leaves,
                "min_child_samples": req.min_child_samples,
            },
            feature_config=feature_config,
            val_fraction=req.val_fraction,
        )
        return {"run_id": run_id, "status": "QUEUED"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/models/train/{run_id}")
def api_get_train_status(run_id: str) -> dict[str, Any]:
    """Poll status and validation metrics of model training run."""
    try:
        return get_training_job_status(run_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# --- Model Comparison & Evaluation Endpoints ---

@app.post("/api/compare")
def api_compare_models(req: CompareRequest) -> dict[str, Any]:
    """Compare Chronos-2, LightGBM, and Seasonal-Naive models side-by-side."""
    dataset_id = req.dataset_id or app.state.default_dataset_id or "retail-demand-m5"
    try:
        history = get_series_history(dataset_id, req.series_id)
    except Exception:
        try:
            history = get_series_legacy(app.state.sales, req.series_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Unknown series: {req.series_id}") from e

    chronos_tuple = (app.state.pipeline, app.state.device) if app.state.pipeline else None

    try:
        return compare_models(
            history_df=history,
            horizon=req.horizon,
            series_id=req.series_id,
            dataset_id=dataset_id,
            cutoff_index=req.cutoff_index,
            chronos_pipeline_tuple=chronos_tuple,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/evaluation/backtest")
def api_backtest(req: BacktestRequest) -> dict[str, Any]:
    """Perform walk-forward backtesting across historical rolling cutoffs."""
    dataset_id = req.dataset_id or app.state.default_dataset_id or "retail-demand-m5"
    try:
        history = get_series_history(dataset_id, req.series_id)
    except Exception:
        history = get_series_legacy(app.state.sales, req.series_id)

    dates = list(history["date"])
    try:
        cutoffs = generate_backtest_cutoffs(dates, req.horizon, req.num_cutoffs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    chronos_tuple = (app.state.pipeline, app.state.device) if app.state.pipeline else None

    cutoff_evaluations = []
    for c_idx in cutoffs:
        cutoff_date = dates[c_idx].strftime("%Y-%m-%d")
        comp = compare_models(
            history_df=history,
            horizon=req.horizon,
            series_id=req.series_id,
            dataset_id=dataset_id,
            cutoff_index=c_idx,
            chronos_pipeline_tuple=chronos_tuple,
        )
        cutoff_evaluations.append({
            "cutoff_index": c_idx,
            "cutoff_date": cutoff_date,
            "metrics": comp["metrics"],
            "best_models": comp.get("best_models", {}),
            "actual_test_values": comp.get("actual_test_values", []),
            "actual_test_dates": comp.get("actual_test_dates", []),
            "forecasts": {
                m: comp["forecasts"][m].get("median", [])
                for m in comp["forecasts"]
                if "median" in comp["forecasts"][m]
            },
        })

    # Compute overall mean metrics across cutoffs
    aggregated_metrics: dict[str, dict[str, float]] = {}
    for item in cutoff_evaluations:
        for mtype, mdict in item["metrics"].items():
            if mtype not in aggregated_metrics:
                aggregated_metrics[mtype] = {}
            for k, v in mdict.items():
                if isinstance(v, (int, float)):
                    aggregated_metrics[mtype].setdefault(k, []).append(v)  # type: ignore

    mean_metrics: dict[str, dict[str, float]] = {}
    for mtype, mdict in aggregated_metrics.items():
        mean_metrics[mtype] = {
            k: round(float(np.mean(vals)), 4) for k, vals in mdict.items()  # type: ignore
        }

    return {
        "dataset_id": dataset_id,
        "series_id": req.series_id,
        "horizon": req.horizon,
        "num_cutoffs": len(cutoffs),
        "cutoff_evaluations": cutoff_evaluations,
        "mean_metrics": mean_metrics,
    }


# --- Forecast History Endpoints ---

@app.get("/api/history/runs")
def api_list_runs(
    dataset_id: Optional[str] = Query(None),
    series_id: Optional[str] = Query(None),
    model_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort: str = Query("newest"),
    paginated: bool = Query(False),
) -> Any:
    """Query past forecast runs."""
    if sort not in ("newest", "oldest"):
        raise HTTPException(status_code=400, detail="sort must be 'newest' or 'oldest'.")
    items = list_forecast_runs(
        dataset_id=dataset_id,
        series_id=series_id,
        model_type=model_type,
        limit=limit,
        offset=offset,
        sort=sort,
    )
    if not paginated:
        return items
    total = count_forecast_runs(dataset_id=dataset_id, series_id=series_id, model_type=model_type)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/history/runs/{run_id}")
def api_run_details(run_id: str) -> dict[str, Any]:
    """Retrieve full details of a specific forecast run."""
    sales_df = getattr(app.state, "sales", None)
    run = get_forecast_run_details(run_id, sales_df=sales_df)
    if not run:
        raise HTTPException(status_code=404, detail=f"Forecast run '{run_id}' not found.")
    return run


@app.delete("/api/history/runs/{run_id}")
def api_delete_run(run_id: str) -> dict[str, Any]:
    """Delete a stored forecast run."""
    if not delete_forecast_run(run_id):
        raise HTTPException(status_code=404, detail=f"Forecast run '{run_id}' not found.")
    return {"deleted": True, "run_id": run_id}


@app.post("/api/history/runs/{run_id}/rerun")
def api_rerun_forecast(run_id: str) -> dict[str, Any]:
    """Re-run a historical forecast with the same settings, creating a new run."""
    original = get_forecast_run_details(run_id, history_tail_days=0)
    if not original:
        raise HTTPException(status_code=404, detail=f"Forecast run '{run_id}' not found.")

    dataset_id = original.get("dataset_id") or app.state.default_dataset_id or "retail-demand-m5"
    series_id = original["series_id"]
    horizon = int(original["horizon"])
    model_type = (original.get("model_type") or "chronos").lower().strip()

    try:
        if dataset_id and dataset_id != "default":
            history = get_series_history(dataset_id, series_id)
        else:
            history = get_series_legacy(app.state.sales, series_id)
    except Exception:
        try:
            history = get_series_legacy(app.state.sales, series_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Unknown series: {series_id}") from e

    if model_type == "chronos" and app.state.pipeline is None:
        raise HTTPException(status_code=500, detail=app.state.load_error or "Chronos-2 model failed to load.")

    chronos_tuple = (app.state.pipeline, app.state.device) if app.state.pipeline else None
    stored_model_id = original.get("model_id")
    model_id_arg = stored_model_id if (model_type == "lightgbm" and stored_model_id and stored_model_id != "Custom Model") else None

    try:
        new_run = generate_single_forecast(
            history_df=history,
            horizon=horizon,
            model_type=model_type,
            model_id=model_id_arg,
            series_id=series_id,
            dataset_id=dataset_id,
            version_id=original.get("version_id") or "v1",
            chronos_pipeline_tuple=chronos_tuple,
        )
        new_run["rerun_of"] = run_id
        return new_run
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# --- Overview & Statistics Endpoint ---

@app.get("/api/overview")
def api_overview() -> dict[str, Any]:
    """System-wide summary metrics for Overview dashboard."""
    init_db()
    with get_db() as conn:
        ds_count = conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
        v_row = conn.execute("SELECT SUM(num_records), SUM(num_series) FROM dataset_versions").fetchone()
        model_count = conn.execute("SELECT COUNT(*) FROM models").fetchone()[0]
        run_count = conn.execute("SELECT COUNT(*) FROM forecast_runs").fetchone()[0]

        recent_runs = conn.execute(
            "SELECT id, dataset_id, series_id, model_type, horizon, created_at FROM forecast_runs ORDER BY created_at DESC LIMIT 5"
        ).fetchall()

    health = _device_health()
    return {
        "total_datasets": ds_count,
        "total_records": v_row[0] or 0,
        "total_series": v_row[1] or 0,
        "total_models": model_count,
        "total_forecasts": run_count,
        "recent_runs": [dict(r) for r in recent_runs],
        "chronos_status": "LOADED" if health["chronos_loaded"] else "UNAVAILABLE",
        "chronos_device": health["chronos_device"],
        "custom_device": health["custom_device"],
        "device_label": health["device_label"],
        "device": health["device_label"],
    }


WEB_DIR.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
