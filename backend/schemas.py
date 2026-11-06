"""Pydantic schemas for Raphael API (Phase 6)."""
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field("ok", description="Service health state")
    app: str = Field("Raphael API", description="API application title")
    version: str = Field("1.0.0", description="API semantic version")
    as_of_date: str = Field("2016-04-24", description="Dataset freeze date")
    artifacts_ready: bool = Field(True, description="Whether artifacts are loaded into memory")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class MetaProvenance(BaseModel):
    demand: str
    lead_time: str
    inventory: str
    disclaimer: str


class MetaDates(BaseModel):
    as_of_date: str
    forecast_start_date: str
    forecast_horizon_days: int
    test_days: int
    validation_days: int
    holiday_calendar: str


class MetaFleet(BaseModel):
    total_pairs: int
    total_materials: int
    total_areas: int
    total_demand_days_per_pair: int
    total_historical_orders: int


class MetaPolicyAssumptions(BaseModel):
    service_level: float
    z_score: float
    review_period_days: int
    cover_days_target: int
    ordering_cost_fixed: float
    holding_cost_annual_rate: float
    default_unit_cost: float


class MetaResponse(BaseModel):
    dataset_name: str
    provenance: MetaProvenance
    dates: MetaDates
    fleet_dimensions: MetaFleet
    model_architecture: Dict[str, str]
    policy_assumptions: MetaPolicyAssumptions
    status_summary: Dict[str, int]
    created_at: str


class MaterialsResponse(BaseModel):
    total_materials: int
    materials: List[str]


class AreasResponse(BaseModel):
    total_areas: int
    material_filter: Optional[str] = None
    areas: List[str]


class HistoryDataPoint(BaseModel):
    date: str
    quantity: float
    is_promotion: int


class ForecastDataPoint(BaseModel):
    ds: str
    yhat: float
    yhat_lower_80: Optional[float] = None
    yhat_upper_80: Optional[float] = None
    yhat_lower_95: Optional[float] = None
    yhat_upper_95: Optional[float] = None
    interval_method: str = "empirical_residual"
    pooled_residuals: bool = False
    interval_missing_reason: Optional[str] = None


class EmpiricalPromotionInfo(BaseModel):
    empirical_lift: float
    raw_lift: float
    lift_ci_lower_95: float
    lift_ci_upper_95: float
    has_measurable_effect: bool
    no_measurable_effect: bool
    historical_promo_share: float
    simulation_method: str = "Simulated, empirical lift"
    effect_description: str


class AccuracyMetrics(BaseModel):
    weekly_pooled_wape: Optional[float] = None
    weekly_pair_wape: Optional[float] = None
    daily_pair_wape: Optional[float] = None
    lead_time_window_pair_wape: Optional[float] = None
    champion_val_wape: Optional[float] = None


class HeldoutPoint(BaseModel):
    ds: str
    actual: float
    predicted: float


class ForecastResponse(BaseModel):
    material: str
    area: str
    as_of_date: str
    model_used: str
    interval_method: str = "empirical_residual"
    pooled_residuals: bool = False
    interval_missing_reason: Optional[str] = None
    low_confidence: bool
    weak_normal_assumption: bool
    accuracy: AccuracyMetrics
    empirical_promotion: EmpiricalPromotionInfo
    history_tail_60d: List[HistoryDataPoint]
    forecast_90d: List[ForecastDataPoint]
    heldout_test: List[HeldoutPoint] = []


class ReorderResponse(BaseModel):
    material: str
    area: str
    as_of_date: str
    current_stock: float
    status: str
    urgency_rank: int
    days_remaining: float
    days_remaining_label: str
    beyond_horizon: bool
    reorder_point_rop: float
    safety_stock_ss: float
    demand_rate_d: float
    demand_window_days: int
    demand_error_std_sigma_d: float
    predicted_lead_time_days: float
    calibrated_lead_time_std_sigma_l: float
    tree_spread_lead_time_std: float
    recommended_order_quantity: float
    raw_order_quantity_14d: float
    eoq_quantity: float
    hist_p5_order_quantity: float
    hist_p95_order_quantity: float
    is_quantity_extrapolation: bool
    champion_model: str
    low_confidence: bool
    zero_demand_share: float
    weak_normal_assumption: bool
    stock_to_rop_ratio: float
    # Disclosure flags
    service_level_target: float = 0.95
    service_level_assumed: bool = True
    costs_assumed: bool = True
    cover_days_assumed: bool = True
    cover_days_target: int = 14


class UrgencyResponse(BaseModel):
    as_of_date: str
    total_pairs: int
    filtered_pairs: int
    status_breakdown: Dict[str, int]
    items: List[ReorderResponse]


class LeadTimeResponse(BaseModel):
    material: str
    area: str
    as_of_date: str
    predicted_lead_time_upcoming_days: float
    calibrated_lead_time_std: float
    tree_spread_lead_time_std: float
    lead_time_holiday_peak_days: float
    seasonal_holiday_surge_days: float
    typical_order_quantity: float
    hist_p5_order_quantity: float
    hist_p95_order_quantity: float
    is_extrapolation_warning: bool
    caveat_note: str = (
        "Tree spread standard deviation reflects ensemble disagreement and understates real variability. "
        "The calibrated residual std is derived empirically from held-out operational residuals and is used in safety stock calculations."
    )


class LeaderboardItem(BaseModel):
    model: str
    val_weekly_mean_wape: float
    weekly_pooled_wape: float
    weekly_mean_pair_wape: float
    daily_pooled_wape: float
    daily_mean_pair_wape: float
    lead_time_pooled_wape: float


class AccuracyResponse(BaseModel):
    as_of_date: str
    test_days: int
    timestamp: str
    leaderboard: List[LeaderboardItem]
    model_selection_breakdown: Dict[str, int]
    pairs_flagged_low_confidence: int
    total_pairs: int
    per_pair_metrics: List[Dict[str, Any]]
    disqualification_notes: Optional[Dict[str, str]] = None


class WhatIfRequest(BaseModel):
    material: Optional[str] = None
    area: Optional[str] = None
    demand_rate: Optional[float] = None
    demand_std: Optional[float] = None
    lead_time: Optional[float] = None
    lead_time_std: Optional[float] = None
    service_level: Optional[float] = 0.95
    current_stock: Optional[float] = None
    daily_forecasts: Optional[List[float]] = None
    ordering_cost_fixed: Optional[float] = 50.0
    holding_cost_annual_unit: Optional[float] = 2.0
    demand_shock_pct: Optional[float] = 0.0 # e.g. +20.0 for 20% demand surge


class WhatIfResponse(BaseModel):
    demand_rate: float
    demand_std: float
    lead_time: float
    lead_time_std: float
    service_level: float
    current_stock: float
    safety_stock_ss: float
    reorder_point_rop: float
    eoq_quantity: float
    days_remaining: float
    beyond_horizon: bool
    days_remaining_label: str
    status: str
    stockout_probability_per_cycle: float
    demand_shock_pct_applied: float
    recommended_order_quantity: Optional[float] = None
    order_up_to_level: Optional[float] = None
    is_quantity_extrapolation: Optional[bool] = False
    stockout_model_note: str = (
        "Stockout probability is computed via the normal lead-time demand model P(LTD > stock) = 1 - Phi((stock - mu_LTD) / sigma_LTD). "
        "Assumes normally distributed lead-time demand; weak approximation for intermittent or zero-demand items."
    )


class BenchmarkResponse(BaseModel):
    status: str = "not computed yet"
    message: str = (
        "Hardware benchmarks and live inference latency timings will be populated "
        "when scripts/07_benchmark.py is executed in Phase 7/8 on actual deployment hardware."
    )
    detected_hardware: Optional[Dict[str, Any]] = None
    benchmarks: Optional[Dict[str, Any]] = None
    details: Optional[Dict[str, Any]] = None
