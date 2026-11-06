"""Raphael API - FastAPI Backend Application (Phase 6).

Title: Raphael API
Provides high-performance, read-only analytical endpoints over precomputed artifacts:
- Instant in-memory lookups (< 2ms latency)
- No runtime machine learning training or GPU dependencies
- Pure arithmetic decision engine for scenario simulation (/whatif)
"""
from contextlib import asynccontextmanager
from datetime import datetime
import io
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
import numpy as np
import pandas as pd
import scipy.stats as stats

from backend.data_store import data_store
from backend.schemas import (
    AccuracyMetrics,
    AccuracyResponse,
    AreasResponse,
    BenchmarkResponse,
    EmpiricalPromotionInfo,
    ForecastDataPoint,
    ForecastResponse,
    HeldoutPoint,
    HealthResponse,
    HistoryDataPoint,
    LeaderboardItem,
    LeadTimeResponse,
    MaterialsResponse,
    MetaResponse,
    ReorderResponse,
    UrgencyResponse,
    WhatIfRequest,
    WhatIfResponse,
)
from src.inventory.engine import (
    classify_inventory_status,
    compute_days_remaining,
    compute_eoq,
    compute_order_up_to_level,
    compute_planned_order_quantity,
    compute_recommended_order_quantity,
    compute_reorder_point,
    compute_safety_stock,
)

logger = logging.getLogger("RaphaelAPI")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load artifacts into memory on startup."""
    data_store.load_all()
    yield


app = FastAPI(
    title="Raphael API",
    version="1.0.0",
    description="Raphael Materials Demand Forecasting, Lead-Time Prediction & Inventory Decisions Platform API",
    lifespan=lifespan,
)

# 1. GZip Compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 2. CORS Middleware - configurable via CORS_ORIGINS or RAPHAEL_CORS_ORIGINS (default http://localhost:3000)
cors_origins_str = os.getenv("CORS_ORIGINS", os.getenv("RAPHAEL_CORS_ORIGINS", "http://localhost:3000"))
cors_origins = [o.strip() for o in cors_origins_str.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if cors_origins else ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# ENDPOINTS
# =============================================================================


@app.get("/", tags=["System"])
def get_root():
    """Root entrypoint providing navigation to documentation and status."""
    return {
        "app": "Raphael API",
        "version": "1.0.0",
        "status": "online",
        "documentation": "/docs",
        "health": "/health",
        "meta": "/meta",
        "message": "Raphael Demand Forecasting & Inventory Decision API. Navigate to /docs for interactive Swagger documentation.",
    }


@app.get("/health", response_model=HealthResponse, tags=["System"])
def get_health() -> HealthResponse:
    """System health check and artifact cache readiness."""
    return HealthResponse(
        status="ok",
        app="Raphael API",
        version="1.0.0",
        as_of_date="2016-04-24",
        artifacts_ready=data_store.is_loaded,
    )


@app.get("/meta", response_model=MetaResponse, tags=["System"])
def get_meta() -> MetaResponse:
    """Dataset provenance, time-series horizons, model architecture, and policy defaults."""
    if not data_store.meta:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Platform metadata not loaded",
        )
    return MetaResponse(**data_store.meta)


@app.get("/materials", response_model=MaterialsResponse, tags=["Catalog"])
def get_materials() -> MaterialsResponse:
    """List of all 25 materials in the catalog."""
    mats = data_store.materials
    return MaterialsResponse(total_materials=len(mats), materials=mats)


@app.get("/areas", response_model=AreasResponse, tags=["Catalog"])
def get_areas(material: Optional[str] = Query(None, description="Optional material filter")) -> AreasResponse:
    """List areas, optionally filtered by material."""
    if material:
        if material not in data_store.materials:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Material '{material}' not found",
            )
        matched_areas = sorted([a for (m, a) in data_store.pairs if m == material])
        return AreasResponse(total_areas=len(matched_areas), material_filter=material, areas=matched_areas)
    return AreasResponse(total_areas=len(data_store.areas), material_filter=None, areas=data_store.areas)


@app.get("/forecast/{material}/{area}", response_model=ForecastResponse, tags=["Forecast"])
def get_forecast(material: str, area: str) -> ForecastResponse:
    """Get recent demand history (last 60 days) and future 90-day forecast with empirical 80%/95% bands."""
    rec = data_store.get_pair_recommendation(material, area)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pair ({material}, {area}) not found in Raphael catalog",
        )

    fc_points = data_store.get_pair_forecast(material, area) or []
    history_tail = data_store.get_pair_history_tail(material, area)
    promo_info = data_store.get_pair_promo_info(material, area) or {}

    promo_obj = EmpiricalPromotionInfo(
        empirical_lift=float(promo_info.get("empirical_lift", 1.0)),
        raw_lift=float(promo_info.get("raw_lift", 1.0)),
        lift_ci_lower_95=float(promo_info.get("lift_ci_lower_95", 1.0)),
        lift_ci_upper_95=float(promo_info.get("lift_ci_upper_95", 1.0)),
        has_measurable_effect=bool(promo_info.get("has_measurable_effect", False)),
        no_measurable_effect=bool(promo_info.get("no_measurable_effect", True)),
        historical_promo_share=float(promo_info.get("historical_promo_share", 0.3293)),
        simulation_method=str(promo_info.get("simulation_method", "Simulated, empirical lift")),
        effect_description=str(promo_info.get("effect_description", "No measurable effect")),
    )

    acc_obj = AccuracyMetrics(
        weekly_pooled_wape=0.2920,
        weekly_pair_wape=rec.get("test_weekly_wape"),
        daily_pair_wape=rec.get("test_daily_wape"),
        lead_time_window_pair_wape=rec.get("test_lead_time_wape"),
        champion_val_wape=rec.get("champion_val_wape"),
    )

    first_pt = fc_points[0] if fc_points else {}
    interval_method = str(first_pt.get("interval_method", "empirical_residual"))
    pooled_residuals = bool(first_pt.get("pooled_residuals", False))
    interval_missing_reason = first_pt.get("interval_missing_reason", None)

    return ForecastResponse(
        material=material,
        area=area,
        as_of_date=str(rec.get("as_of_date", "2016-04-24")),
        model_used=str(rec.get("model_used", rec.get("champion_model", "weekday_mean_8w"))),
        interval_method=interval_method,
        pooled_residuals=pooled_residuals,
        interval_missing_reason=interval_missing_reason,
        low_confidence=bool(rec.get("low_confidence", False)),
        weak_normal_assumption=bool(rec.get("weak_normal_assumption", False)),
        accuracy=acc_obj,
        empirical_promotion=promo_obj,
        history_tail_60d=[HistoryDataPoint(**pt) for pt in history_tail],
        forecast_90d=[ForecastDataPoint(**pt) for pt in fc_points],
        heldout_test=[HeldoutPoint(**pt) for pt in data_store.get_pair_heldout(material, area)],
    )


@app.get("/reorder/{material}/{area}", response_model=ReorderResponse, tags=["Inventory"])
def get_reorder(material: str, area: str) -> ReorderResponse:
    """Get complete inventory decision metrics: ROP, SS, days_remaining, status, L, sigma_L."""
    rec = data_store.get_pair_recommendation(material, area)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pair ({material}, {area}) not found",
        )
    return ReorderResponse(**rec)


@app.get("/urgency", response_model=UrgencyResponse, tags=["Inventory"])
def get_urgency(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by OK, REORDER, CRITICAL"),
    material_filter: Optional[str] = Query(None, alias="material", description="Filter by material code"),
    area_filter: Optional[str] = Query(None, alias="area", description="Filter by geographic area"),
) -> UrgencyResponse:
    """Get full inventory table ranked by urgency (status severity first, then days_remaining)."""
    df = data_store.recommendations_df.copy()
    if df.empty:
        raise HTTPException(status_code=503, detail="Recommendations table not loaded")

    total_pairs = len(df)
    status_counts = df["status"].value_counts().to_dict()

    if status_filter:
        s_upper = status_filter.upper()
        df = df[df["status"] == s_upper]
    if material_filter:
        df = df[df["material"] == material_filter]
    if area_filter:
        df = df[df["area"] == area_filter]

    df = df.sort_values("urgency_rank", kind="stable")
    items = [ReorderResponse(**r) for r in df.to_dict(orient="records")]
    return UrgencyResponse(
        as_of_date="2016-04-24",
        total_pairs=total_pairs,
        filtered_pairs=len(items),
        status_breakdown=status_counts,
        items=items,
    )


@app.get("/accuracy", response_model=AccuracyResponse, tags=["Telemetry"])
def get_accuracy() -> AccuracyResponse:
    """Get model competition leaderboard and per-pair accuracy metrics with explicit aggregation levels."""
    lb = data_store.leaderboard.get("leaderboard", [])
    lb_items = [LeaderboardItem(**item) for item in lb]
    per_pair = data_store.champion_selections

    return AccuracyResponse(
        as_of_date="2016-04-24",
        test_days=int(data_store.leaderboard.get("test_days", 84)),
        timestamp=str(data_store.leaderboard.get("timestamp", datetime.now().isoformat())),
        leaderboard=lb_items,
        model_selection_breakdown=data_store.leaderboard.get("model_selection_breakdown", {}),
        pairs_flagged_low_confidence=int(data_store.leaderboard.get("pairs_flagged_low_confidence", 30)),
        total_pairs=len(data_store.pairs),
        per_pair_metrics=per_pair,
        disqualification_notes=data_store.leaderboard.get("disqualification_notes", {}),
    )


@app.get("/metrics/leadtime", tags=["Telemetry"])
def get_leadtime_metrics() -> Dict[str, Any]:
    """Get lead-time model evaluation metrics (MAE, RMSE, R2 vs baseline, tree spread vs calibrated coverage)."""
    return data_store.lead_time_eval or {}


@app.get("/metrics/intervals", tags=["Telemetry"])
def get_interval_metrics() -> Dict[str, Any]:
    """Get prediction interval coverage calibration summary (fleet and by group)."""
    return data_store.interval_eval or {}


@app.get("/leadtime/{material}/{area}", response_model=LeadTimeResponse, tags=["LeadTime"])
def get_lead_time(material: str, area: str) -> LeadTimeResponse:
    """Get Random Forest lead-time prediction, dual spreads, seasonal surge, and quantity bounds."""
    rec = data_store.get_pair_recommendation(material, area)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pair ({material}, {area}) not found",
        )

    lt_prof = data_store.get_pair_lead_time_profile(material, area) or {}
    l_up = float(rec.get("predicted_lead_time_days", lt_prof.get("lead_time_upcoming_days", 5.0)))
    l_hol = float(lt_prof.get("lead_time_holiday_peak_days", l_up + 1.34))
    surge = round(max(0.0, l_hol - l_up), 2)

    return LeadTimeResponse(
        material=material,
        area=area,
        as_of_date="2016-04-24",
        predicted_lead_time_upcoming_days=l_up,
        calibrated_lead_time_std=float(rec.get("calibrated_lead_time_std_sigma_l", 1.0)),
        tree_spread_lead_time_std=float(rec.get("tree_spread_lead_time_std", 0.6)),
        lead_time_holiday_peak_days=l_hol,
        seasonal_holiday_surge_days=surge,
        typical_order_quantity=float(lt_prof.get("typical_order_quantity", rec.get("recommended_order_quantity", 50.0))),
        hist_p5_order_quantity=float(rec.get("hist_p5_order_quantity", 10.0)),
        hist_p95_order_quantity=float(rec.get("hist_p95_order_quantity", 200.0)),
        is_extrapolation_warning=bool(rec.get("is_quantity_extrapolation", False)),
    )


@app.post("/whatif", response_model=WhatIfResponse, tags=["Simulator"])
def post_whatif(req: WhatIfRequest) -> WhatIfResponse:
    """Recompute inventory decisions (SS, ROP, EOQ, days_remaining, status, stockout probability).

    Accepts raw parameters directly (matching tests/inventory_fixtures.json)
    or resolves defaults from a specified material & area.
    """
    # 1. Resolve parameters from pair if supplied
    D = req.demand_rate
    sigma_D = req.demand_std
    L = req.lead_time
    sigma_L = req.lead_time_std
    stock = req.current_stock
    forecasts = req.daily_forecasts

    if req.material and req.area:
        rec = data_store.get_pair_recommendation(req.material, req.area)
        if not rec:
            raise HTTPException(status_code=404, detail=f"Pair ({req.material}, {req.area}) not found")
        if D is None:
            D = float(rec["demand_rate_d"])
        if sigma_D is None:
            sigma_D = float(rec["demand_error_std_sigma_d"])
        if L is None:
            L = float(rec["predicted_lead_time_days"])
        if sigma_L is None:
            sigma_L = float(rec["calibrated_lead_time_std_sigma_l"])
        if stock is None:
            stock = float(rec["current_stock"])
        if forecasts is None:
            fc_list = data_store.get_pair_forecast(req.material, req.area)
            if fc_list:
                forecasts = [float(x["yhat"]) for x in fc_list]

    # Validate mandatory inputs
    if D is None or sigma_D is None or L is None or sigma_L is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Parameters demand_rate (D), demand_std (sigma_D), lead_time (L), and lead_time_std (sigma_L) are required",
        )

    # Apply demand shock if specified
    shock_pct = float(req.demand_shock_pct or 0.0)
    multiplier = max(0.0, 1.0 + (shock_pct / 100.0))
    D_adj = max(0.0, D * multiplier)
    sigma_D_adj = max(0.0, sigma_D * np.sqrt(multiplier))

    # Daily forecast list for depletion
    if forecasts is None:
        forecasts = [D_adj] * 90
    else:
        forecasts = [max(0.0, float(x) * multiplier) for x in forecasts]

    if stock is None:
        stock = D_adj * 10.0 # Default 10 days of stock if not provided

    service_level = float(req.service_level or 0.95)
    order_cost = float(req.ordering_cost_fixed or 50.0)
    holding_cost = float(req.holding_cost_annual_unit or 2.0)

    # 2. Pure arithmetic calculations
    ss = compute_safety_stock(
        demand_rate=D_adj,
        demand_std=sigma_D_adj,
        lead_time=L,
        lead_time_std=sigma_L,
        service_level=service_level,
    )
    rop = compute_reorder_point(demand_rate=D_adj, lead_time=L, safety_stock=ss)

    eoq = compute_eoq(
        annual_demand=D_adj * 365.0,
        ordering_cost_fixed=order_cost,
        holding_cost_annual_unit=holding_cost,
    )

    days_rem, beyond, rem_label = compute_days_remaining(
        current_stock=stock,
        daily_forecasts=forecasts,
        max_horizon_days=90,
    )

    status_str = classify_inventory_status(
        current_stock=stock,
        rop=rop,
        days_remaining=days_rem,
        lead_time=L,
    )

    # Order-up-to level & recommended order quantity
    raw_14d_planned = float(np.sum(forecasts[:14]))
    order_up_to = compute_order_up_to_level(
        rop=rop,
        demand_rate=D_adj,
        review_period_days=7,
        daily_forecasts=forecasts,
    )
    rec_qty, is_rec_extrap = compute_recommended_order_quantity(
        planned_quantity=raw_14d_planned,
        order_up_to_level=order_up_to,
        current_stock=stock,
    )

    # 3. Stockout probability via normal lead-time demand model
    mu_ltd = D_adj * L
    sigma_ltd = float(np.sqrt(max(0.0, (L * (sigma_D_adj ** 2)) + ((D_adj ** 2) * (sigma_L ** 2)))))
    if stock <= 0.0:
        p_stockout = 1.0
    elif sigma_ltd > 0.0:
        z_curr = (stock - mu_ltd) / sigma_ltd
        p_stockout = float(stats.norm.sf(z_curr)) # 1 - CDF
    else:
        p_stockout = 0.0 if stock >= mu_ltd else 1.0

    return WhatIfResponse(
        demand_rate=round(D_adj, 2),
        demand_std=round(sigma_D_adj, 3),
        lead_time=round(L, 2),
        lead_time_std=round(sigma_L, 3),
        service_level=round(service_level, 4),
        current_stock=round(stock, 1),
        safety_stock_ss=round(ss, 2),
        reorder_point_rop=round(rop, 2),
        eoq_quantity=round(eoq, 1),
        days_remaining=round(days_rem, 2),
        beyond_horizon=beyond,
        days_remaining_label=rem_label,
        status=status_str,
        stockout_probability_per_cycle=round(p_stockout, 4),
        demand_shock_pct_applied=shock_pct,
        recommended_order_quantity=round(rec_qty, 1),
        order_up_to_level=round(order_up_to, 1),
        is_quantity_extrapolation=is_rec_extrap,
    )


@app.get("/export/recommendations.csv", tags=["Export"])
def export_recommendations_csv(
    status_filter: Optional[str] = Query(None, alias="status"),
    material_filter: Optional[str] = Query(None, alias="material"),
    area_filter: Optional[str] = Query(None, alias="area"),
):
    """Download full recommendations table as a CSV file with all assumption flags."""
    df = data_store.recommendations_df.copy()
    if df.empty:
        raise HTTPException(status_code=503, detail="Recommendations table not loaded")

    if status_filter:
        df = df[df["status"] == status_filter.upper()]
    if material_filter:
        df = df[df["material"] == material_filter]
    if area_filter:
        df = df[df["area"] == area_filter]

    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    filename = f"raphael_recommendations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/benchmarks", response_model=BenchmarkResponse, tags=["Telemetry"])
def get_benchmarks() -> BenchmarkResponse:
    """Return hardware benchmarks or explicit placeholder."""
    for path in [Path("artifacts/benchmarks.json"), Path("artifacts/benchmark_telemetry.json")]:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    b_data = json.load(f)
                return BenchmarkResponse(
                    status="completed",
                    message="Hardware, model training, and inference latency benchmarks from local execution.",
                    detected_hardware=b_data.get("benchmark_environment") or b_data.get("hardware"),
                    benchmarks=b_data.get("model_timings") or b_data.get("benchmarks"),
                    details=b_data,
                )
            except Exception as e:
                logger.error(f"Error loading benchmarks from {path}: {e}")
    return BenchmarkResponse(
        status="not computed yet",
        message="Hardware benchmarks and inference timings will be generated during Phase 7/8 benchmark execution.",
    )
