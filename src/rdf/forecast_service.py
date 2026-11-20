"""Unified Forecasting and Comparison Service.

Coordinates Chronos-2, Custom Recursive LightGBM, and Seasonal-Naive models.
Guarantees consistent output schemas and persists all forecasting experiments to SQLite.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .baseline import forecast_seasonal_naive
from .config import CONTEXT_LENGTH, DATA_DIR, MODEL_ID
from .data_loader import get_series as get_series_legacy
from .dataset_manager import get_dataset_version, get_series_history
from .db import get_db, init_db, now_iso
from .evaluation import compute_metrics
from .forecaster import DENSE_QUANTILES, ForecastError, forecast as forecast_chronos, load_pipeline
from .lgbm_forecaster import LightGBMForecaster, list_trained_models, load_trained_forecaster

_HASH_CACHE: dict[tuple[str, int, int], str] = {}
_PKG_VERSIONS_CACHE: dict[str, str] | None = None


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _engine_label(model_type: str) -> str:
    mt = (model_type or "").lower().strip()
    if mt == "chronos":
        return "Chronos-2"
    if mt in ("lightgbm", "custom", "custom_model"):
        return "Custom (LightGBM)"
    if mt == "baseline":
        return "Baseline (Seasonal-Naive)"
    return model_type or "Unknown"


def _file_sha256(path: Path) -> str | None:
    try:
        st = path.stat()
    except OSError:
        return None
    key = (str(path), st.st_mtime_ns, st.st_size)
    if key in _HASH_CACHE:
        return _HASH_CACHE[key]
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    digest = h.hexdigest()
    _HASH_CACHE[key] = digest
    return digest


def _resolve_dataset_file(dataset_id: str) -> tuple[str | None, str | None]:
    v_info = get_dataset_version(dataset_id) if dataset_id else None
    candidates: list[Path] = []
    if v_info:
        if v_info.get("original_file_path"):
            candidates.append(Path(v_info["original_file_path"]))
        if v_info.get("processed_file_path"):
            candidates.append(Path(v_info["processed_file_path"]))
    candidates.extend([DATA_DIR / "sales_train_validation.csv", DATA_DIR / "demand_history.csv"])

    for p in candidates:
        if p.exists() and p.is_file():
            return p.name, _file_sha256(p)
    return None, None


def _package_versions() -> dict[str, str]:
    global _PKG_VERSIONS_CACHE
    if _PKG_VERSIONS_CACHE is not None:
        return dict(_PKG_VERSIONS_CACHE)
    pkgs = ("chronos-forecasting", "torch", "pandas", "numpy", "lightgbm", "fastapi")
    versions: dict[str, str] = {}
    for pkg in pkgs:
        try:
            versions[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            versions[pkg] = "not installed"
    _PKG_VERSIONS_CACHE = versions
    return dict(versions)


def _build_reproducibility(
    dataset_id: str,
    model_type_clean: str,
    used_model_id: str,
    device: str,
    legacy: bool = False,
) -> dict[str, Any]:
    data_file, data_hash = _resolve_dataset_file(dataset_id)
    mt = (model_type_clean or "").lower().strip()
    return {
        "model_id": used_model_id,
        "engine": _engine_label(mt),
        "device": device,
        "packages": _package_versions(),
        "data_file": data_file,
        "data_sha256": data_hash,
        "parameters": {
            "context_length": CONTEXT_LENGTH if mt == "chronos" else (7 if mt == "baseline" else None),
            "quantile_levels": list(DENSE_QUANTILES) if mt == "chronos" else [0.1, 0.5, 0.9],
        },
        "post_processing": "Clip negative values at 0",
        "legacy_inferred": legacy,
    }


def generate_single_forecast(
    history_df: pd.DataFrame,
    horizon: int,
    model_type: str = "chronos",
    model_id: str | None = None,
    series_id: str = "item",
    chronos_pipeline_tuple: tuple[Any, str] | None = None,
    dataset_id: str = "default",
    version_id: str = "v1",
) -> dict[str, Any]:
    """Execute forecast using selected model engine and persist execution run."""
    init_db()
    start_time = time.time()
    run_id = f"fc-{uuid.uuid4().hex[:10]}"

    model_type_clean = model_type.lower().strip()
    is_custom_alias = model_type_clean in ("custom", "custom_model", "custom model")
    if is_custom_alias:
        model_type_clean = "lightgbm"

    device = "cpu"
    used_model_id = model_id or ("Custom Model" if is_custom_alias else model_type_clean)

    if model_type_clean == "chronos":
        if chronos_pipeline_tuple is None:
            pipeline, device = load_pipeline()
        else:
            pipeline, device = chronos_pipeline_tuple
        res_df = forecast_chronos(pipeline, history_df, horizon, series_id)
        used_model_id = MODEL_ID

    elif model_type_clean == "lightgbm":
        device = "cpu"
        if not model_id:
            models = list_trained_models(dataset_id)
            if not models:
                models = list_trained_models()
            if not models:
                # Auto-fit a default custom model so custom forecasting works immediately
                from .dataset_manager import load_dataset_data
                from .lgbm_forecaster import MODELS_DIR
                ds_data = load_dataset_data(dataset_id)
                auto_model = LightGBMForecaster(hyperparameters={"n_estimators": 50, "learning_rate": 0.08, "verbose": -1})
                auto_meta = auto_model.fit(ds_data, val_fraction=0.15)
                auto_id = f"custom-default-{dataset_id}"
                art_path = MODELS_DIR / auto_id / "model.pkl"
                auto_model.save(art_path)
                with get_db() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO models (id, name, model_type, dataset_id, version_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (auto_id, "Custom Model", "lightgbm", dataset_id, "v1", now_iso()),
                    )
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO model_training_runs (
                            id, model_id, dataset_id, version_id, status, duration_sec, num_samples, num_series,
                            validation_metrics_json, artifact_path, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            f"run-{auto_id}", auto_id, dataset_id, "v1", "COMPLETED",
                            auto_meta["duration_sec"], auto_meta["num_samples"], auto_meta["num_series"],
                            json.dumps(auto_meta["metrics"]), str(art_path), now_iso()
                        )
                    )
                model_id = auto_id
            else:
                model_id = models[0]["model_id"]
        used_model_id = "Custom Model" if is_custom_alias else model_id
        forecaster = load_trained_forecaster(model_id)
        res_df = forecaster.predict_recursive(history_df, horizon, series_id)

    elif model_type_clean == "baseline":
        device = "cpu"
        used_model_id = "seasonal-naive"
        res_df = forecast_seasonal_naive(history_df, horizon, frequency="D")

    else:
        raise ValueError(f"Unknown model_type '{model_type}'. Choose: chronos, lightgbm, baseline.")

    exec_duration = time.time() - start_time

    # Standardize result vectors
    dates = [pd.Timestamp(d).strftime("%Y-%m-%d") for d in res_df["date"]]
    median_vals = [float(v) for v in res_df["median"]]
    expected_vals = [float(v) for v in res_df.get("expected", res_df["median"])]
    q10_vals = [float(v) for v in res_df["q10"]]
    q50_vals = [float(v) for v in res_df["q50"]]
    q90_vals = [float(v) for v in res_df["q90"]]

    total_pred = float(np.sum(expected_vals))
    daily_avg = float(np.mean(expected_vals))

    # Persist into database
    hist_end = str(history_df["date"].max()) if "date" in history_df else ""
    fc_start = dates[0] if dates else ""
    repro = _build_reproducibility(dataset_id, model_type_clean, used_model_id, device, legacy=False)

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO forecast_runs (
                id, dataset_id, version_id, series_id, model_type, model_id,
                horizon, context_end, forecast_start, execution_time_sec,
                metrics_json, status, created_at, device, reproducibility_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                dataset_id,
                version_id,
                series_id,
                model_type_clean,
                used_model_id,
                horizon,
                hist_end,
                fc_start,
                round(exec_duration, 3),
                None,
                "COMPLETED",
                now_iso(),
                device,
                json.dumps(repro),
            ),
        )

        for d, m, exp, low, high in zip(dates, median_vals, expected_vals, q10_vals, q90_vals):
            conn.execute(
                """
                INSERT INTO forecast_values (
                    forecast_run_id, timestamp, predicted_median, lower_bound, upper_bound, expected
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, d, m, low, high, exp),
            )

    return {
        "run_id": run_id,
        "dates": dates,
        "median": median_vals,
        "expected": expected_vals,
        "q10": q10_vals,
        "q50": q50_vals,
        "q90": q90_vals,
        "total": total_pred,
        "daily_average": daily_avg,
        "device": device,
        "model": used_model_id,
        "model_type": "custom" if is_custom_alias else model_type_clean,
        "execution_time_sec": round(exec_duration, 3),
    }


def compare_models(
    history_df: pd.DataFrame,
    horizon: int,
    series_id: str,
    dataset_id: str = "default",
    version_id: str = "v1",
    cutoff_index: int | None = None,
    chronos_pipeline_tuple: tuple[Any, str] | None = None,
) -> dict[str, Any]:
    """Execute side-by-side comparison between Chronos-2, LightGBM, and Baseline."""
    df = history_df.sort_values(by="date").reset_index(drop=True)
    n = len(df)

    has_ground_truth = False
    test_actuals: list[float] = []

    if cutoff_index is not None and cutoff_index < n:
        context_df = df.iloc[:cutoff_index].copy()
        test_df = df.iloc[cutoff_index : min(n, cutoff_index + horizon)].copy()
        test_actuals = [float(v) for v in test_df["sales"]]
        has_ground_truth = len(test_actuals) == horizon
    else:
        context_df = df.copy()

    models_to_run = ["baseline", "chronos", "custom"]
    results: dict[str, Any] = {}
    metrics_by_model: dict[str, Any] = {}

    for mtype in models_to_run:
        try:
            fc = generate_single_forecast(
                history_df=context_df,
                horizon=horizon,
                model_type=mtype,
                series_id=series_id,
                dataset_id=dataset_id,
                version_id=version_id,
                chronos_pipeline_tuple=chronos_pipeline_tuple,
            )
            key_name = "custom" if mtype in ("custom", "lightgbm") else mtype
            results[key_name] = fc

            if has_ground_truth:
                m = compute_metrics(
                    actual=test_actuals,
                    predicted_median=fc["median"],
                    q10=fc["q10"],
                    q90=fc["q90"],
                    in_sample_actual=list(context_df["sales"]),
                )
                m["execution_time_sec"] = fc["execution_time_sec"]
                metrics_by_model[key_name] = m
            else:
                metrics_by_model[key_name] = {
                    "total_predicted": fc["total"],
                    "daily_average": fc["daily_average"],
                    "execution_time_sec": fc["execution_time_sec"],
                }
        except Exception as e:
            key_name = "custom" if mtype in ("custom", "lightgbm") else mtype
            results[key_name] = {"error": str(e)}

    # Determine best model per metric if ground truth exists
    best_models: dict[str, str] = {}
    if has_ground_truth and metrics_by_model:
        for metric in ["mae", "rmse", "wape", "mase", "pinball_loss"]:
            valid = {m: metrics_by_model[m][metric] for m in metrics_by_model if metric in metrics_by_model[m]}
            if valid:
                best_models[metric] = min(valid, key=valid.get)  # type: ignore

        if any("coverage_80" in metrics_by_model[m] for m in metrics_by_model):
            # Best coverage is closest to 0.80
            cov_diffs = {
                m: abs(metrics_by_model[m]["coverage_80"] - 0.80)
                for m in metrics_by_model
                if "coverage_80" in metrics_by_model[m]
            }
            if cov_diffs:
                best_models["coverage_80"] = min(cov_diffs, key=cov_diffs.get)  # type: ignore

    return {
        "series_id": series_id,
        "horizon": horizon,
        "has_ground_truth": has_ground_truth,
        "actual_test_dates": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in test_df["date"]] if has_ground_truth else [],
        "actual_test_values": test_actuals,
        "forecasts": results,
        "metrics": metrics_by_model,
        "best_models": best_models,
    }


def _build_run_where(
    dataset_id: str | None = None,
    series_id: str | None = None,
    model_type: str | None = None,
) -> tuple[str, list[Any]]:
    clause = " WHERE 1=1"
    params: list[Any] = []
    if dataset_id:
        clause += " AND fr.dataset_id = ?"
        params.append(dataset_id)
    if series_id:
        clause += " AND fr.series_id = ?"
        params.append(series_id)
    if model_type:
        mt = model_type.lower().strip()
        if mt in ("custom", "custom_model", "lightgbm"):
            clause += " AND fr.model_type IN ('lightgbm', 'custom')"
        else:
            clause += " AND fr.model_type = ?"
            params.append(mt)
    return clause, params


def count_forecast_runs(
    dataset_id: str | None = None,
    series_id: str | None = None,
    model_type: str | None = None,
) -> int:
    """Count total forecasting runs matching filters."""
    init_db()
    where_sql, params = _build_run_where(dataset_id=dataset_id, series_id=series_id, model_type=model_type)
    with get_db() as conn:
        row = conn.execute(f"SELECT COUNT(*) AS cnt FROM forecast_runs fr{where_sql}", params).fetchone()
    return int(row["cnt"]) if row else 0


def list_forecast_runs(
    dataset_id: str | None = None,
    series_id: str | None = None,
    model_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort: str = "newest",
) -> list[dict[str, Any]]:
    """Query recent forecasting runs from database."""
    init_db()
    where_sql, params = _build_run_where(dataset_id=dataset_id, series_id=series_id, model_type=model_type)
    order_dir = "ASC" if sort == "oldest" else "DESC"
    query = f"""
        SELECT fr.*,
               COUNT(fv.id) as point_count
        FROM forecast_runs fr
        LEFT JOIN forecast_values fv ON fr.id = fv.forecast_run_id
        {where_sql}
        GROUP BY fr.id
        ORDER BY fr.created_at {order_dir}
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()

    items: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["engine_label"] = _engine_label(d.get("model_type", ""))
        if not d.get("device"):
            d["device"] = "cpu" if d.get("model_type") in ("lightgbm", "custom", "baseline") else "unknown"
        d["execution_time_sec"] = _safe_float(d.get("execution_time_sec"))
        items.append(d)
    return items


def _load_history_tail(
    dataset_id: str,
    series_id: str,
    context_end: str | None,
    history_tail_days: int,
    sales_df: pd.DataFrame | None = None,
) -> dict[str, list[Any]]:
    if history_tail_days <= 0:
        return {"dates": [], "sales": []}

    hist_df: pd.DataFrame | None = None
    try:
        hist_df = get_series_history(dataset_id, series_id)
    except Exception:
        hist_df = None

    if (hist_df is None or hist_df.empty) and sales_df is not None and not sales_df.empty:
        try:
            hist_df = get_series_legacy(sales_df, series_id)
        except Exception:
            hist_df = None

    if hist_df is None or hist_df.empty:
        return {"dates": [], "sales": []}

    hist_df = hist_df.sort_values("date").reset_index(drop=True)
    if context_end:
        try:
            cutoff = pd.Timestamp(context_end)
            hist_df = hist_df[hist_df["date"] <= cutoff]
        except Exception:
            pass

    tail = hist_df.tail(history_tail_days)
    return {
        "dates": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in tail["date"]],
        "sales": [_safe_float(v) for v in tail["sales"]],
    }


def get_forecast_run_details(
    run_id: str,
    history_tail_days: int = 60,
    sales_df: pd.DataFrame | None = None,
) -> dict[str, Any] | None:
    """Fetch complete details, reproducibility metadata, history tail, and curves of a run."""
    init_db()
    with get_db() as conn:
        run = conn.execute("SELECT * FROM forecast_runs WHERE id = ?", (run_id,)).fetchone()
        if not run:
            return None
        res = dict(run)
        values = conn.execute(
            "SELECT * FROM forecast_values WHERE forecast_run_id = ? ORDER BY timestamp ASC",
            (run_id,),
        ).fetchall()

    clean_values: list[dict[str, Any]] = []
    for row in values:
        v = dict(row)
        for col in ("predicted_median", "lower_bound", "upper_bound", "expected", "actual"):
            v[col] = _safe_float(v.get(col))
        clean_values.append(v)

    repro: dict[str, Any] | None = None
    raw_repro = res.get("reproducibility_json")
    if raw_repro:
        try:
            repro = json.loads(raw_repro)
        except (TypeError, json.JSONDecodeError):
            repro = None

    inferred_device = res.get("device") or (
        "cpu" if res.get("model_type") in ("lightgbm", "custom", "baseline") else "unknown"
    )
    if repro is None:
        repro = _build_reproducibility(
            dataset_id=res.get("dataset_id", ""),
            model_type_clean=res.get("model_type", ""),
            used_model_id=res.get("model_id") or "",
            device=inferred_device,
            legacy=True,
        )

    parsed_metrics: dict[str, Any] | None = None
    if res.get("metrics_json"):
        try:
            parsed_metrics = json.loads(res["metrics_json"])
        except (TypeError, json.JSONDecodeError):
            parsed_metrics = None

    exp_vals = [
        v["expected"] if v["expected"] is not None else v["predicted_median"]
        for v in clean_values
        if v["expected"] is not None or v["predicted_median"] is not None
    ]

    res["values"] = clean_values
    res["engine_label"] = _engine_label(res.get("model_type", ""))
    res["device"] = res.get("device") or repro.get("device") or inferred_device
    res["execution_time_sec"] = _safe_float(res.get("execution_time_sec"))
    res["reproducibility"] = repro
    res["metrics"] = parsed_metrics
    res["summary"] = {
        "point_count": len(clean_values),
        "total_expected": _safe_float(sum(exp_vals)) if exp_vals else None,
        "daily_average_expected": _safe_float(sum(exp_vals) / len(exp_vals)) if exp_vals else None,
        "forecast_start": clean_values[0]["timestamp"] if clean_values else res.get("forecast_start"),
        "forecast_end": clean_values[-1]["timestamp"] if clean_values else None,
    }
    res["history_tail"] = _load_history_tail(
        dataset_id=res.get("dataset_id", ""),
        series_id=res.get("series_id", ""),
        context_end=res.get("context_end"),
        history_tail_days=history_tail_days,
        sales_df=sales_df,
    )
    return res


def delete_forecast_run(run_id: str) -> bool:
    """Delete a stored forecast run and its values. Returns True if deleted."""
    init_db()
    with get_db() as conn:
        conn.execute("DELETE FROM forecast_values WHERE forecast_run_id = ?", (run_id,))
        cur = conn.execute("DELETE FROM forecast_runs WHERE id = ?", (run_id,))
        return cur.rowcount > 0
