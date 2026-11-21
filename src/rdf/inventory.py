"""Inventory & Reorder engine for Stage 1.

Uses simulated baseline inventory (`data/current_inventory.csv`), historical
lead times (`data/lead_time_history.csv`), stored 28-day Chronos-2 forecasts,
and Stage 0 validation-only backtest error windows (`series_calibration`).
"""
from __future__ import annotations

import json
import math
import statistics
import threading
import time
import uuid
from typing import Any, Sequence

import numpy as np
import pandas as pd

from .calibration import (
    apply_interval_calibration,
    calibrate_series_validation,
    compute_lead_time_error_std,
    get_series_calibration,
)
from .config import DATA_DIR, MODEL_ID
from .data_loader import load_sales
from .db import get_db, init_db, now_iso
from .forecaster import forecast as forecast_chronos, load_pipeline


def load_inventory_baseline() -> list[dict[str, Any]]:
    """Read simulated baseline inventory from data/current_inventory.csv."""
    path = DATA_DIR / "current_inventory.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path)
    rows: list[dict[str, Any]] = []
    for rec in df.to_dict(orient="records"):
        material = str(rec["material"]).strip()
        area = str(rec["area"]).strip()
        rows.append({
            "series_id": f"{material} | {area}",
            "material": material,
            "area": area,
            "current_stock": float(rec["current_stock"]),
            "last_updated": str(rec["last_updated"]).strip(),
            "stock_status_simulated": str(rec["stock_status_simulated"]).strip().lower(),
        })
    return rows


def load_lead_time_stats() -> dict[str, dict[str, Any]]:
    """Compute per-series lead-time mean, std, order count, and median order qty."""
    path = DATA_DIR / "lead_time_history.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    df["series_id"] = df["material"].astype(str).str.strip() + " | " + df["area"].astype(str).str.strip()
    stats: dict[str, dict[str, Any]] = {}
    for sid, grp in df.groupby("series_id", sort=False):
        lt = grp["lead_time_days"].dropna().astype(float)
        oq = grp["order_quantity"].dropna().astype(float)
        cnt = int(len(lt))
        l_mean = float(lt.mean()) if cnt > 0 else 0.0
        l_std = float(lt.std(ddof=1)) if cnt > 1 else 0.0
        med_oq = float(oq.median()) if len(oq) > 0 else 0.0
        stats[str(sid)] = {
            "L_mean": l_mean,
            "L_std": l_std,
            "order_count": cnt,
            "median_order_qty": med_oq,
            "low_confidence_lt": cnt < 30,
        }
    return stats


def walk_demand(daily_values: Sequence[float], duration_days: float) -> float:
    """Sum daily demand over a continuous duration (fractional last day)."""
    vals = [max(0.0, float(v)) for v in daily_values]
    if not vals or duration_days <= 0:
        return 0.0
    full_days = int(math.floor(duration_days))
    frac = float(duration_days) - full_days
    tail_mean = float(np.mean(vals))

    total = 0.0
    for i in range(full_days):
        total += vals[i] if i < len(vals) else tail_mean
    if frac > 1e-9:
        next_val = vals[full_days] if full_days < len(vals) else tail_mean
        total += frac * next_val
    return float(total)


def walk_runway_eta(
    on_hand: float,
    daily_values: Sequence[float],
    fallback_daily_mean: float | None = None,
) -> float | None:
    """Walk daily demand starting at day 0 and return fractional days until stockout."""
    rem = float(on_hand)
    if rem <= 0.0:
        return 0.0
    vals = [max(0.0, float(v)) for v in daily_values]
    for i, d in enumerate(vals):
        if d > 1e-9 and rem <= d:
            return float(i + (rem / d))
        rem -= d

    mean_d = fallback_daily_mean if fallback_daily_mean is not None else (float(np.mean(vals)) if vals else 0.0)
    if mean_d > 1e-9:
        return float(len(vals) + (rem / mean_d))
    return None


def compute_reorder_metrics(
    *,
    on_hand: float,
    in_transit: float,
    daily_expected: Sequence[float],
    daily_q90: Sequence[float] | None,
    L_mean: float,
    L_std: float,
    sigma_D: float,
    review_period: float = 7.0,
    service_level: float = 0.95,
    pack_size: int = 1,
    moq: int = 0,
    excess_days_threshold: float = 60.0,
    start_date: str = "2016-04-25",
) -> dict[str, Any]:
    """Compute Safety Stock, ROP, Order-up-to S, Order Qty, Runway ETA, and Status."""
    exp_vals = [max(0.0, float(v)) for v in daily_expected]
    q90_vals = [max(0.0, float(v)) for v in (daily_q90 if daily_q90 is not None else exp_vals)]

    svc = min(0.9999, max(0.50, float(service_level)))
    z = float(statistics.NormalDist().inv_cdf(svc))

    avg_daily = float(np.mean(exp_vals)) if exp_vals else 0.0
    D_L = walk_demand(exp_vals, L_mean)
    D_LR = walk_demand(exp_vals, L_mean + float(review_period))

    variance = (float(sigma_D) ** 2) + ((avg_daily ** 2) * (float(L_std) ** 2))
    safety_stock = z * math.sqrt(max(0.0, variance))
    rop = D_L + safety_stock
    order_up_to_S = D_LR + safety_stock

    inv_position = float(on_hand) + float(in_transit)
    raw_order_qty = max(0.0, order_up_to_S - inv_position)

    pack = max(1, int(pack_size))
    min_oq = max(0, int(moq))
    if raw_order_qty <= 0.0:
        order_qty = 0
    else:
        qty = max(raw_order_qty, float(min_oq))
        order_qty = int(math.ceil(qty / pack) * pack)

    eta_expected = walk_runway_eta(on_hand, exp_vals, avg_daily)
    q90_mean = float(np.mean(q90_vals)) if q90_vals else 0.0
    eta_q90 = walk_runway_eta(on_hand, q90_vals, q90_mean)

    days_of_cover = (
        float(on_hand) / avg_daily
        if avg_daily > 1e-9
        else (float("inf") if on_hand > 0 else 0.0)
    )
    s_days = (order_up_to_S / avg_daily) if avg_daily > 1e-9 else 0.0
    excess_limit_days = max(float(excess_days_threshold), 3.0 * s_days)

    # Status evaluation strictly in order: CRITICAL -> LOW -> EXCESS -> HEALTHY
    if (eta_expected is not None and eta_expected < L_mean) or (
        eta_q90 is not None and eta_q90 <= L_mean
    ):
        status = "CRITICAL"
    elif inv_position <= rop:
        status = "LOW"
    elif (avg_daily <= 1e-9 and on_hand > 0) or (days_of_cover > excess_limit_days):
        status = "EXCESS"
    else:
        status = "HEALTHY"

    stockout_date = None
    if eta_expected is not None and math.isfinite(eta_expected):
        stockout_date = (
            pd.Timestamp(start_date) + pd.Timedelta(days=int(math.floor(eta_expected)))
        ).strftime("%Y-%m-%d")

    return {
        "on_hand": round(float(on_hand), 2),
        "in_transit": round(float(in_transit), 2),
        "inventory_position": round(inv_position, 2),
        "avg_daily_demand": round(avg_daily, 3),
        "demand_over_lead_time": round(D_L, 2),
        "demand_over_L_plus_R": round(D_LR, 2),
        "z_score": round(z, 4),
        "variance": round(variance, 4),
        "sigma_D": round(float(sigma_D), 4),
        "safety_stock": round(safety_stock, 2),
        "rop": round(rop, 2),
        "order_up_to_S": round(order_up_to_S, 2),
        "review_period": float(review_period),
        "raw_order_qty": round(raw_order_qty, 2),
        "order_qty": order_qty,
        "pack_size": pack,
        "moq": min_oq,
        "service_level": svc,
        "excess_days_threshold": float(excess_days_threshold),
        "excess_limit_days": round(excess_limit_days, 2) if math.isfinite(excess_limit_days) else None,
        "days_of_cover": round(days_of_cover, 2) if math.isfinite(days_of_cover) else None,
        "eta_expected_days": round(eta_expected, 2) if eta_expected is not None else None,
        "eta_q90_days": round(eta_q90, 2) if eta_q90 is not None else None,
        "stockout_date": stockout_date,
        "status": status,
    }


def _get_all_overrides(dataset_id: str) -> dict[str, dict[str, Any]]:
    init_db()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM inventory_overrides WHERE dataset_id = ?",
            (dataset_id,),
        ).fetchall()
    return {r["series_id"]: dict(r) for r in rows}


def save_inventory_override(
    *,
    series_id: str,
    dataset_id: str = "retail-demand-m5",
    on_hand: float | None = None,
    in_transit: float = 0.0,
    review_period: float = 7.0,
    pack_size: int = 1,
    moq: int = 0,
    service_level: float = 0.95,
    excess_days_threshold: float = 60.0,
) -> dict[str, Any]:
    """Persist editable inventory/reorder parameters for a series."""
    init_db()
    updated = now_iso()
    with get_db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO inventory_overrides (
                series_id, dataset_id, on_hand, in_transit, review_period,
                pack_size, moq, service_level, excess_days_threshold, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                series_id,
                dataset_id,
                float(on_hand) if on_hand is not None else None,
                max(0.0, float(in_transit)),
                max(1.0, float(review_period)),
                max(1, int(pack_size)),
                max(0, int(moq)),
                min(0.9999, max(0.50, float(service_level))),
                max(1.0, float(excess_days_threshold)),
                updated,
            ),
        )
    return {
        "series_id": series_id,
        "dataset_id": dataset_id,
        "on_hand": on_hand,
        "in_transit": max(0.0, float(in_transit)),
        "review_period": max(1.0, float(review_period)),
        "pack_size": max(1, int(pack_size)),
        "moq": max(0, int(moq)),
        "service_level": min(0.9999, max(0.50, float(service_level))),
        "excess_days_threshold": max(1.0, float(excess_days_threshold)),
        "updated_at": updated,
    }


def _get_latest_stored_forecasts(
    dataset_id: str = "retail-demand-m5",
    model_type: str = "chronos",
    horizon: int = 28,
) -> dict[str, dict[str, Any]]:
    init_db()
    with get_db() as conn:
        runs = conn.execute(
            """
            SELECT r.id, r.series_id, r.forecast_start, r.created_at, r.model_id
            FROM forecast_runs r
            INNER JOIN (
                SELECT series_id, MAX(created_at) AS max_created
                FROM forecast_runs
                WHERE dataset_id = ? AND model_type = ? AND horizon = ? AND status = 'completed'
                  AND series_id NOT LIKE 'BATCH%'
                GROUP BY series_id
            ) latest ON r.series_id = latest.series_id AND r.created_at = latest.max_created
            WHERE r.dataset_id = ? AND r.model_type = ? AND r.horizon = ? AND r.status = 'completed'
            """,
            (dataset_id, model_type, horizon, dataset_id, model_type, horizon),
        ).fetchall()

        if not runs:
            return {}

        run_map = {r["id"]: dict(r) for r in runs}
        placeholders = ",".join("?" for _ in run_map)
        vals = conn.execute(
            f"""
            SELECT forecast_run_id, timestamp, predicted_median, lower_bound, upper_bound, expected
            FROM forecast_values
            WHERE forecast_run_id IN ({placeholders})
            ORDER BY id ASC
            """,
            tuple(run_map.keys()),
        ).fetchall()

    grouped: dict[str, dict[str, list[Any]]] = {}
    for v in vals:
        rid = v["forecast_run_id"]
        g = grouped.setdefault(
            rid,
            {"dates": [], "median": [], "expected": [], "q10": [], "q90": []},
        )
        g["dates"].append(v["timestamp"])
        med = float(v["predicted_median"] or 0.0)
        exp = float(v["expected"]) if v["expected"] is not None else med
        g["median"].append(med)
        g["expected"].append(exp)
        g["q10"].append(float(v["lower_bound"] or 0.0))
        g["q90"].append(float(v["upper_bound"] or 0.0))

    by_series: dict[str, dict[str, Any]] = {}
    for rid, meta in run_map.items():
        if rid in grouped:
            by_series[meta["series_id"]] = {
                "run_id": rid,
                "forecast_start": meta["forecast_start"] or (grouped[rid]["dates"][0] if grouped[rid]["dates"] else "2016-04-25"),
                "created_at": meta["created_at"],
                "model_id": meta["model_id"],
                **grouped[rid],
            }
    return by_series


def get_inventory_dashboard(
    dataset_id: str = "retail-demand-m5",
    model_type: str = "chronos",
) -> dict[str, Any]:
    """Build the full Stage 1 Inventory & Reorder table and agreement matrix."""
    init_db()
    if dataset_id != "retail-demand-m5":
        return {
            "has_inventory_data": False,
            "dataset_id": dataset_id,
            "message": "No inventory data for this dataset. Use the Manual calculator below.",
            "items": [],
            "summary": {"total": 0, "critical": 0, "low": 0, "healthy": 0, "excess": 0, "needs_forecast": 0},
            "agreement_matrix": {},
        }

    baseline = load_inventory_baseline()
    lt_stats = load_lead_time_stats()
    overrides = _get_all_overrides(dataset_id)
    stored_forecasts = _get_latest_stored_forecasts(dataset_id, model_type=model_type, horizon=28)

    items: list[dict[str, Any]] = []
    summary = {"total": len(baseline), "critical": 0, "low": 0, "healthy": 0, "excess": 0, "needs_forecast": 0}
    engine_statuses = ["CRITICAL", "LOW", "HEALTHY", "EXCESS"]
    file_labels = ["critical", "low", "medium", "healthy"]
    agreement: dict[str, dict[str, int]] = {
        es: {fl: 0 for fl in file_labels} for es in engine_statuses
    }

    for row in baseline:
        sid = row["series_id"]
        ov = overrides.get(sid, {})
        lt = lt_stats.get(sid, {"L_mean": 5.0, "L_std": 0.0, "order_count": 0, "median_order_qty": 0.0, "low_confidence_lt": True})

        on_hand = float(ov["on_hand"]) if ov.get("on_hand") is not None else row["current_stock"]
        in_transit = float(ov.get("in_transit", 0.0))
        review_period = float(ov.get("review_period", 7.0))
        pack_size = int(ov.get("pack_size", 1))
        moq = int(ov.get("moq", 0))
        service_level = float(ov.get("service_level", 0.95))
        excess_days = float(ov.get("excess_days_threshold", 60.0))

        fc = stored_forecasts.get(sid)
        cal = get_series_calibration(sid, model_type=model_type, dataset_id=dataset_id)
        sigma_D, sigma_source = compute_lead_time_error_std(cal, lt["L_mean"])

        base_item = {
            "series_id": sid,
            "material": row["material"],
            "area": row["area"],
            "snapshot_date": row["last_updated"],
            "simulated_label": row["stock_status_simulated"],
            "L_mean": round(lt["L_mean"], 2),
            "L_std": round(lt["L_std"], 2),
            "order_count": lt["order_count"],
            "low_confidence_lt": lt["low_confidence_lt"],
            "median_order_qty": round(lt["median_order_qty"], 1),
            "sigma_D_source": sigma_source,
            "calibrated": bool(cal and cal.get("calibrated")),
            "scale_k": cal["scale_k"] if cal else 1.0,
        }

        if not fc:
            summary["needs_forecast"] += 1
            items.append({
                **base_item,
                "has_forecast": False,
                "on_hand": round(on_hand, 2),
                "in_transit": round(in_transit, 2),
                "inventory_position": round(on_hand + in_transit, 2),
                "review_period": review_period,
                "pack_size": pack_size,
                "moq": moq,
                "service_level": service_level,
                "excess_days_threshold": excess_days,
                "avg_daily_demand": None,
                "sigma_D": round(sigma_D, 2),
                "safety_stock": None,
                "rop": None,
                "order_up_to_S": None,
                "order_qty": None,
                "days_of_cover": None,
                "eta_expected_days": None,
                "stockout_date": None,
                "status": "NEEDS_FORECAST",
            })
            continue

        metrics = compute_reorder_metrics(
            on_hand=on_hand,
            in_transit=in_transit,
            daily_expected=fc["expected"],
            daily_q90=fc["q90"],
            L_mean=lt["L_mean"],
            L_std=lt["L_std"],
            sigma_D=sigma_D,
            review_period=review_period,
            service_level=service_level,
            pack_size=pack_size,
            moq=moq,
            excess_days_threshold=excess_days,
            start_date=fc["forecast_start"],
        )
        st = metrics["status"]
        summary[st.lower()] += 1
        fl = row["stock_status_simulated"]
        if st in agreement and fl in agreement[st]:
            agreement[st][fl] += 1

        items.append({
            **base_item,
            "has_forecast": True,
            "forecast_created_at": fc["created_at"],
            **metrics,
        })

    return {
        "has_inventory_data": True,
        "dataset_id": dataset_id,
        "model_type": model_type,
        "snapshot_date": "2016-04-24",
        "forecast_start": "2016-04-25",
        "items": items,
        "summary": summary,
        "agreement_matrix": agreement,
    }


def _run_batch_worker(job_id: str, dataset_id: str, horizon: int) -> None:
    t0 = time.perf_counter()
    init_db()
    try:
        pipeline, device = load_pipeline()
        sales_df = load_sales()
        baseline = load_inventory_baseline()
        total = len(baseline)

        from tqdm import tqdm

        for idx, row in enumerate(
            tqdm(baseline, desc="Batch Chronos-2 (75 series)", unit="series"),
            start=1,
        ):
            sid = row["series_id"]
            with get_db() as conn:
                conn.execute(
                    "UPDATE inventory_batch_jobs SET completed_series = ?, current_series = ? WHERE id = ?",
                    (idx - 1, sid, job_id),
                )

            hist_df = sales_df[sales_df["series_id"] == sid][["date", "sales"]].sort_values("date").reset_index(drop=True)
            if len(hist_df) < 30:
                continue

            fc_df = forecast_chronos(pipeline, hist_df, horizon=horizon, series_id=sid)
            cal = get_series_calibration(sid, model_type="chronos", dataset_id=dataset_id)
            if cal is None or not cal.get("val_errors_json"):
                if len(hist_df) > (2 * horizon + 30):
                    cal = calibrate_series_validation(
                        hist_df,
                        series_id=sid,
                        model_type="chronos",
                        dataset_id=dataset_id,
                        horizon=horizon,
                        num_cutoffs=2,
                        chronos_pipeline_tuple=(pipeline, device),
                    )

            med = [float(v) for v in fc_df["median"].to_numpy()]
            exp = [float(v) for v in fc_df["expected"].to_numpy()]
            q10 = [float(v) for v in fc_df["q10"].to_numpy()]
            q90 = [float(v) for v in fc_df["q90"].to_numpy()]
            if cal and cal.get("calibrated"):
                q10, q90 = apply_interval_calibration(med, q10, q90, float(cal["scale_k"]))

            dates = [pd.Timestamp(d).strftime("%Y-%m-%d") for d in fc_df["date"]]
            run_id = str(uuid.uuid4())
            created = now_iso()
            ctx_end = pd.Timestamp(hist_df["date"].iloc[-1]).strftime("%Y-%m-%d")

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
                        "v1",
                        sid,
                        "chronos",
                        MODEL_ID,
                        horizon,
                        ctx_end,
                        dates[0],
                        0.0,
                        json.dumps({"batch_job_id": job_id}),
                        "completed",
                        created,
                        device,
                        json.dumps({"batch_job_id": job_id, "model_id": MODEL_ID, "horizon": horizon}),
                    ),
                )
                conn.executemany(
                    """
                    INSERT INTO forecast_values (
                        forecast_run_id, timestamp, predicted_median, lower_bound, upper_bound, expected
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (run_id, dt, m, lo, hi, ex)
                        for dt, m, lo, hi, ex in zip(dates, med, q10, q90, exp)
                    ],
                )

        duration_sec = round(time.perf_counter() - t0, 2)
        completed_at = now_iso()

        # Log batch summary entry in Forecasting History
        batch_run_id = str(uuid.uuid4())
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
                    batch_run_id,
                    dataset_id,
                    "v1",
                    f"BATCH ({total} series)",
                    "chronos",
                    MODEL_ID,
                    horizon,
                    "2016-04-24",
                    "2016-04-25",
                    duration_sec,
                    json.dumps({"batch_job_id": job_id, "total_series": total}),
                    "completed",
                    completed_at,
                    device,
                    json.dumps({"batch_job_id": job_id, "model_id": MODEL_ID, "total_series": total, "horizon": horizon}),
                ),
            )
            conn.execute(
                """
                UPDATE inventory_batch_jobs
                SET status = 'completed', completed_series = ?, current_series = NULL,
                    duration_sec = ?, completed_at = ?
                WHERE id = ?
                """,
                (total, duration_sec, completed_at, job_id),
            )
    except Exception as exc:
        with get_db() as conn:
            conn.execute(
                """
                UPDATE inventory_batch_jobs
                SET status = 'failed', error_message = ?, completed_at = ?
                WHERE id = ?
                """,
                (str(exc), now_iso(), job_id),
            )


def start_batch_forecast_job(
    dataset_id: str = "retail-demand-m5",
    horizon: int = 28,
) -> dict[str, Any]:
    """Start a background 75-series Chronos-2 batch forecast job."""
    init_db()
    baseline = load_inventory_baseline()
    job_id = str(uuid.uuid4())
    created = now_iso()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO inventory_batch_jobs (
                id, dataset_id, model_type, model_id, horizon, status,
                total_series, completed_series, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, dataset_id, "chronos", MODEL_ID, horizon, "running", len(baseline), 0, created),
        )
    t = threading.Thread(target=_run_batch_worker, args=(job_id, dataset_id, horizon), daemon=True)
    t.start()
    return {
        "job_id": job_id,
        "status": "running",
        "total_series": len(baseline),
        "completed_series": 0,
        "horizon": horizon,
    }


def get_batch_job_status(job_id: str) -> dict[str, Any] | None:
    """Return status and progress of an inventory batch forecast job."""
    init_db()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM inventory_batch_jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def run_what_if_scenario(
    *,
    series_id: str,
    dataset_id: str = "retail-demand-m5",
    model_type: str = "chronos",
    demand_multiplier: float = 1.0,
    lead_time_delta_days: float = 0.0,
    service_level: float = 0.95,
    review_period: float = 7.0,
    on_hand_override: float | None = None,
    in_transit_override: float | None = None,
    pack_size: int = 1,
    moq: int = 0,
    excess_days_threshold: float = 60.0,
    daily_expected_override: Sequence[float] | None = None,
    daily_q90_override: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Compare baseline vs. user-adjusted What-If scenario (Stage 3)."""
    init_db()
    baseline_rows = {r["series_id"]: r for r in load_inventory_baseline()}
    lt_stats = load_lead_time_stats()
    overrides = _get_all_overrides(dataset_id)

    row = baseline_rows.get(series_id)
    ov = overrides.get(series_id, {})
    lt = lt_stats.get(series_id, {"L_mean": 5.0, "L_std": 0.0, "order_count": 0, "low_confidence_lt": True})

    base_on_hand = float(ov["on_hand"]) if ov.get("on_hand") is not None else (row["current_stock"] if row else 0.0)
    base_in_transit = float(ov.get("in_transit", 0.0))
    base_L = float(lt["L_mean"])
    base_L_std = float(lt["L_std"])
    base_R = float(ov.get("review_period", 7.0))
    base_svc = float(ov.get("service_level", 0.95))
    base_pack = int(ov.get("pack_size", 1))
    base_moq = int(ov.get("moq", 0))

    if daily_expected_override is not None:
        base_exp = [max(0.0, float(v)) for v in daily_expected_override]
        base_q90 = [max(0.0, float(v)) for v in (daily_q90_override or daily_expected_override)]
        dates = [
            (pd.Timestamp("2016-04-25") + pd.Timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(len(base_exp))
        ]
        fc_start = dates[0] if dates else "2016-04-25"
    else:
        stored = _get_latest_stored_forecasts(dataset_id, model_type=model_type, horizon=28)
        fc = stored.get(series_id)
        if not fc:
            raise ValueError(
                f"No stored 28-day forecast found for '{series_id}'. "
                "Generate a forecast or click 'Refresh forecasts' first."
            )
        base_exp = [float(v) for v in fc["expected"]]
        base_q90 = [float(v) for v in fc["q90"]]
        dates = list(fc["dates"])
        fc_start = fc["forecast_start"]

    cal = get_series_calibration(series_id, model_type=model_type, dataset_id=dataset_id)
    base_sigma_D, sigma_source = compute_lead_time_error_std(cal, base_L)

    baseline_metrics = compute_reorder_metrics(
        on_hand=base_on_hand,
        in_transit=base_in_transit,
        daily_expected=base_exp,
        daily_q90=base_q90,
        L_mean=base_L,
        L_std=base_L_std,
        sigma_D=base_sigma_D,
        review_period=base_R,
        service_level=base_svc,
        pack_size=base_pack,
        moq=base_moq,
        excess_days_threshold=excess_days_threshold,
        start_date=fc_start,
    )

    mult = max(0.0, float(demand_multiplier))
    scen_L = max(0.5, base_L + float(lead_time_delta_days))
    scen_sigma_D_raw, _ = compute_lead_time_error_std(cal, scen_L)
    scen_sigma_D = scen_sigma_D_raw * mult
    scen_exp = [round(v * mult, 4) for v in base_exp]
    scen_q90 = [round(v * mult, 4) for v in base_q90]

    scen_on_hand = float(on_hand_override) if on_hand_override is not None else base_on_hand
    scen_in_transit = float(in_transit_override) if in_transit_override is not None else base_in_transit

    scenario_metrics = compute_reorder_metrics(
        on_hand=scen_on_hand,
        in_transit=scen_in_transit,
        daily_expected=scen_exp,
        daily_q90=scen_q90,
        L_mean=scen_L,
        L_std=base_L_std,
        sigma_D=scen_sigma_D,
        review_period=float(review_period),
        service_level=float(service_level),
        pack_size=max(1, int(pack_size)),
        moq=max(0, int(moq)),
        excess_days_threshold=excess_days_threshold,
        start_date=fc_start,
    )

    def _diff(a: float | None, b: float | None) -> float | None:
        if a is None or b is None:
            return None
        return round(float(a) - float(b), 2)

    return {
        "series_id": series_id,
        "dataset_id": dataset_id,
        "sigma_D_source": sigma_source,
        "dates": dates,
        "baseline_daily_expected": base_exp,
        "scenario_daily_expected": scen_exp,
        "baseline": {**baseline_metrics, "L_mean": round(base_L, 2)},
        "scenario": {**scenario_metrics, "L_mean": round(scen_L, 2)},
        "delta": {
            "safety_stock": _diff(scenario_metrics["safety_stock"], baseline_metrics["safety_stock"]),
            "rop": _diff(scenario_metrics["rop"], baseline_metrics["rop"]),
            "order_up_to_S": _diff(scenario_metrics["order_up_to_S"], baseline_metrics["order_up_to_S"]),
            "order_qty": int(scenario_metrics["order_qty"]) - int(baseline_metrics["order_qty"]),
            "eta_expected_days": _diff(scenario_metrics["eta_expected_days"], baseline_metrics["eta_expected_days"]),
        },
        "assumptions": {
            "demand_multiplier": mult,
            "lead_time_delta_days": float(lead_time_delta_days),
            "service_level": float(service_level),
            "review_period": float(review_period),
            "note": "User-supplied scenario assumptions applied to stored baseline forecast & lead-time data.",
        },
    }
