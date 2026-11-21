from __future__ import annotations

import json
import math

from fastapi.testclient import TestClient

from rdf.calibration import compute_lead_time_error_std
from rdf.inventory import compute_reorder_metrics, walk_demand


def test_hand_computed_safety_stock_rop_and_pack_rounding():
    # Demand 10/day, forecast-error std 3, L=4, L_std=1, z=1.645 -> variance=136, SS~19.18, ROP~59.18
    sigma_D = 3.0 * math.sqrt(4.0)
    res = compute_reorder_metrics(
        on_hand=35.0,
        in_transit=40.0,
        daily_expected=[10.0] * 28,
        daily_q90=[12.0] * 28,
        L_mean=4.0,
        L_std=1.0,
        sigma_D=sigma_D,
        review_period=6.0816,  # D_LR = 100.816 -> S = 120.0
        service_level=0.95,
        pack_size=12,
        moq=0,
    )
    assert abs(res["variance"] - 136.0) < 1e-6
    assert 19.15 <= res["safety_stock"] <= 19.22
    assert 59.15 <= res["rop"] <= 59.22
    assert abs(res["order_up_to_S"] - 120.0) < 0.05
    assert res["order_qty"] == 48  # 120 - (35 + 40) = 45 -> rounded up to pack 12 = 48

    # MOQ takes precedence before pack rounding
    res_moq = compute_reorder_metrics(
        on_hand=35.0,
        in_transit=40.0,
        daily_expected=[10.0] * 28,
        daily_q90=[12.0] * 28,
        L_mean=4.0,
        L_std=1.0,
        sigma_D=sigma_D,
        review_period=6.0816,
        service_level=0.95,
        pack_size=12,
        moq=55,
    )
    assert res_moq["order_qty"] == 60


def test_fractional_lead_time_walk_and_stockout_eta():
    assert abs(walk_demand([10.0] * 10, 4.5) - 45.0) < 1e-9
    res = compute_reorder_metrics(
        on_hand=25.0,
        in_transit=0.0,
        daily_expected=[10.0] * 28,
        daily_q90=[12.0] * 28,
        L_mean=4.5,
        L_std=0.5,
        sigma_D=4.0,
        start_date="2016-04-25",
    )
    assert abs(res["demand_over_lead_time"] - 45.0) < 1e-6
    assert abs(res["eta_expected_days"] - 2.5) < 1e-6
    assert res["stockout_date"] == "2016-04-27"
    assert res["status"] == "CRITICAL"


def test_status_rules_all_four_states():
    # 1. CRITICAL via conservative q90 walk even when expected walk > L_mean
    crit_q90 = compute_reorder_metrics(
        on_hand=45.0,
        in_transit=0.0,
        daily_expected=[10.0] * 28,
        daily_q90=[15.0] * 28,  # 45/15 = 3.0 <= L_mean=4.0
        L_mean=4.0,
        L_std=0.5,
        sigma_D=4.0,
    )
    assert crit_q90["status"] == "CRITICAL"

    # 2. LOW (inv_pos <= rop, not critical)
    low = compute_reorder_metrics(
        on_hand=50.0,
        in_transit=0.0,
        daily_expected=[10.0] * 28,
        daily_q90=[11.0] * 28,
        L_mean=4.0,
        L_std=1.0,
        sigma_D=6.0,
    )
    assert low["status"] == "LOW"

    # 3. EXCESS (days_of_cover > max(60, 3*S_days))
    excess = compute_reorder_metrics(
        on_hand=1000.0,
        in_transit=0.0,
        daily_expected=[10.0] * 28,
        daily_q90=[12.0] * 28,
        L_mean=4.0,
        L_std=0.5,
        sigma_D=4.0,
        review_period=7.0,
        excess_days_threshold=60.0,
    )
    assert excess["status"] == "EXCESS"

    # 4. HEALTHY
    healthy = compute_reorder_metrics(
        on_hand=150.0,
        in_transit=0.0,
        daily_expected=[10.0] * 28,
        daily_q90=[12.0] * 28,
        L_mean=4.0,
        L_std=0.5,
        sigma_D=4.0,
        review_period=7.0,
    )
    assert healthy["status"] == "HEALTHY"


def test_sparse_demand_expected_vs_median():
    # Intermittent item: median is 0.0 every day, but expected demand is 0.6/day
    res = compute_reorder_metrics(
        on_hand=5.0,
        in_transit=0.0,
        daily_expected=[0.6] * 28,
        daily_q90=[1.8] * 28,
        L_mean=5.0,
        L_std=1.0,
        sigma_D=1.5,
        review_period=7.0,
    )
    assert res["avg_daily_demand"] > 0.5
    assert res["demand_over_lead_time"] == 3.0
    assert res["rop"] > 3.0


def test_sigma_d_from_validation_windows():
    cal = {
        "val_errors_json": json.dumps([[1.0, -1.0, 2.0, -2.0, 1.0, -1.0, 0.5, -0.5]]),
        "sigma_d": 99.0,  # Should NOT be used when validation windows are available
    }
    sigma_D, source = compute_lead_time_error_std(cal, lead_time_days=3.5)
    assert source == "validation_windows"
    assert sigma_D < 10.0


def test_inventory_non_m5_dataset_and_manual_calculate_api(client: TestClient):
    res = client.get("/api/inventory?dataset_id=other-dataset")
    assert res.status_code == 200
    data = res.json()
    assert data["has_inventory_data"] is False

    calc = client.post(
        "/api/inventory/calculate",
        json={
            "on_hand": 35,
            "in_transit": 40,
            "daily_demand_mean": 10,
            "daily_demand_std": 3,
            "lead_time_mean": 4,
            "lead_time_std": 1,
            "review_period": 6.0816,
            "service_level": 0.95,
            "pack_size": 12,
            "moq": 0,
        },
    )
    assert calc.status_code == 200
    body = calc.json()
    assert body["order_qty"] == 48
    assert 19.15 <= body["safety_stock"] <= 19.22
