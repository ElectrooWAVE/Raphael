from __future__ import annotations

from fastapi.testclient import TestClient

from rdf.inventory import run_what_if_scenario


def test_what_if_demand_shock_and_lead_time_delay():
    base_exp = [10.0] * 28
    base_q90 = [13.0] * 28

    shock = run_what_if_scenario(
        series_id="FOODS_2_019 | California - CA_1",
        demand_multiplier=1.25,
        lead_time_delta_days=3.0,
        service_level=0.98,
        review_period=7.0,
        on_hand_override=60.0,
        daily_expected_override=base_exp,
        daily_q90_override=base_q90,
    )
    assert shock["delta"]["rop"] > 0
    assert shock["delta"]["order_up_to_S"] > 0
    assert shock["delta"]["safety_stock"] > 0
    assert shock["delta"]["eta_expected_days"] < 0
    assert shock["assumptions"]["demand_multiplier"] == 1.25
    assert shock["assumptions"]["lead_time_delta_days"] == 3.0


def test_what_if_endpoint_validation_when_no_forecast(client: TestClient):
    res = client.post(
        "/api/inventory/what-if",
        json={
            "series_id": "NON_EXISTENT_SERIES",
            "demand_multiplier": 1.2,
            "lead_time_delta_days": 2.0,
        },
    )
    assert res.status_code == 400
    assert "No stored 28-day forecast" in res.json()["detail"]
