"""Unit tests for Raphael inventory decision layer.

Validates pure arithmetic functions against hand-checkable cases in tests/inventory_fixtures.json.
Supports both standard library unittest and pytest.
"""
import json
from pathlib import Path
import unittest

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


def load_fixtures():
    fixtures_path = Path(__file__).parent / "inventory_fixtures.json"
    with open(fixtures_path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestInventoryDecisionLayer(unittest.TestCase):
    """Test suite for inventory arithmetic decision engine."""

    def setUp(self):
        self.fixtures = load_fixtures()

    def test_fixtures_count(self):
        self.assertGreaterEqual(len(self.fixtures), 8, f"Expected at least 8 fixtures, got {len(self.fixtures)}")

    def test_inventory_fixtures(self):
        """Test all hand-crafted fixtures from tests/inventory_fixtures.json."""
        for case in self.fixtures:
            cid = case["id"]
            inp = case["inputs"]
            exp = case["expected"]

            if "D" in inp:
                ss = compute_safety_stock(
                    demand_rate=inp["D"],
                    demand_std=inp["sigma_D"],
                    lead_time=inp["L"],
                    lead_time_std=inp["sigma_L"],
                    service_level=inp["service_level"],
                )
                self.assertAlmostEqual(ss, exp["safety_stock"], places=2, msg=f"[{cid}] SS mismatch")

                rop = compute_reorder_point(
                    demand_rate=inp["D"],
                    lead_time=inp["L"],
                    safety_stock=ss,
                )
                self.assertAlmostEqual(rop, exp["rop"], places=2, msg=f"[{cid}] ROP mismatch")

                d_rem, beyond, label = compute_days_remaining(
                    current_stock=inp["stock"],
                    daily_forecasts=inp["daily_forecasts"],
                )
                self.assertAlmostEqual(d_rem, exp["days_remaining"], places=2, msg=f"[{cid}] days_remaining mismatch")
                self.assertEqual(beyond, exp["beyond_horizon"], msg=f"[{cid}] beyond_horizon mismatch")
                self.assertEqual(label, exp["label"], msg=f"[{cid}] label mismatch")

                status = classify_inventory_status(
                    current_stock=inp["stock"],
                    rop=rop,
                    days_remaining=d_rem,
                    lead_time=inp["L"],
                )
                self.assertEqual(status, exp["status"], msg=f"[{cid}] status mismatch")

            elif "forecast_14d" in inp:
                raw, clip, extrap = compute_planned_order_quantity(
                    forecast_daily_demands=inp["forecast_14d"],
                    cover_days=14,
                    hist_p5=inp["hist_p5"],
                    hist_p95=inp["hist_p95"],
                )
                self.assertAlmostEqual(raw, exp["raw_order_quantity"], places=2)
                self.assertAlmostEqual(clip, exp["clipped_order_quantity"], places=2)
                self.assertEqual(extrap, exp["is_extrapolation"])

            elif "annual_demand" in inp:
                eoq = compute_eoq(
                    annual_demand=inp["annual_demand"],
                    ordering_cost_fixed=inp["ordering_cost"],
                    holding_cost_annual_unit=inp["holding_cost"],
                )
                self.assertAlmostEqual(eoq, exp["eoq"], places=2)

            elif "order_up_to_level" in exp:
                out_order_up_to = compute_order_up_to_level(
                    rop=inp["rop"],
                    demand_rate=inp["demand_rate"],
                    review_period_days=inp.get("review_period_days", 7),
                )
                self.assertAlmostEqual(out_order_up_to, exp["order_up_to_level"], places=2, msg=f"[{cid}] order_up_to mismatch")

                rec_qty, is_extrap = compute_recommended_order_quantity(
                    planned_quantity=inp["planned_quantity"],
                    order_up_to_level=out_order_up_to,
                    current_stock=inp["current_stock"],
                    hist_p5=inp.get("hist_p5"),
                    hist_p95=inp.get("hist_p95"),
                )
                self.assertAlmostEqual(rec_qty, exp["recommended_order_quantity"], places=2, msg=f"[{cid}] rec_qty mismatch")
                self.assertEqual(is_extrap, exp["is_extrapolation"], msg=f"[{cid}] is_extrap mismatch")

    def test_safety_stock_properties(self):
        """Verify mathematical boundaries: SS >= 0 and ROP >= D*L."""
        ss_zero = compute_safety_stock(0.0, 0.0, 5.0, 0.0, 0.95)
        self.assertEqual(ss_zero, 0.0)
        rop_zero = compute_reorder_point(0.0, 5.0, ss_zero)
        self.assertEqual(rop_zero, 0.0)

        # Monotonicity with respect to variability
        ss_low = compute_safety_stock(10.0, 1.0, 5.0, 0.5, 0.95)
        ss_high = compute_safety_stock(10.0, 3.0, 5.0, 1.5, 0.95)
        self.assertGreater(ss_high, ss_low)
        self.assertGreaterEqual(compute_reorder_point(10.0, 5.0, ss_low), 10.0 * 5.0)

    def test_status_precedence(self):
        """Verify that CRITICAL always overrides REORDER when stock depletes before lead time."""
        # Stock is below ROP (REORDER condition), but days_remaining (1.5) < lead_time (4.0) -> MUST BE CRITICAL
        status = classify_inventory_status(current_stock=15.0, rop=50.0, days_remaining=1.5, lead_time=4.0)
        self.assertEqual(status, "CRITICAL")

        # Stock is below ROP, but days_remaining (6.0) >= lead_time (4.0) -> REORDER
        status = classify_inventory_status(current_stock=35.0, rop=50.0, days_remaining=6.0, lead_time=4.0)
        self.assertEqual(status, "REORDER")

        # Stock is above ROP -> OK
        status = classify_inventory_status(current_stock=80.0, rop=50.0, days_remaining=12.0, lead_time=4.0)
        self.assertEqual(status, "OK")

    def test_real_artifact_mutual_consistency(self):
        """Assert that for all 75 pairs in recommendations.parquet: abs(ROP - (D*L + SS)) < 0.01."""
        rec_path = Path("artifacts/recommendations.parquet")
        if not rec_path.exists():
            self.skipTest("artifacts/recommendations.parquet does not exist yet")
        import pandas as pd
        df = pd.read_parquet(rec_path)
        self.assertEqual(len(df), 75, "Expected exactly 75 pairs in recommendations table")
        for idx, row in df.iterrows():
            d = float(row["demand_rate_d"])
            l = float(row["predicted_lead_time_days"])
            ss = float(row["safety_stock_ss"])
            rop = float(row["reorder_point_rop"])
            expected = (d * l) + ss
            diff = abs(rop - expected)
            self.assertLess(
                diff,
                0.01,
                msg=f"Mutual consistency failed for {row['material']} {row['area']}: ROP={rop}, D*L+SS={expected}, diff={diff}",
            )

    def test_real_artifact_reorder_pushes_above_rop(self):
        """Assert that for every REORDER and CRITICAL pair: current_stock + recommended_order_quantity > ROP."""
        rec_path = Path("artifacts/recommendations.parquet")
        if not rec_path.exists():
            self.skipTest("artifacts/recommendations.parquet does not exist yet")
        import pandas as pd
        df = pd.read_parquet(rec_path)
        urgent_rows = df[df["status"].isin(["CRITICAL", "REORDER"])]
        self.assertGreaterEqual(len(urgent_rows), 20, "Expected at least 20 urgent items")
        for idx, row in urgent_rows.iterrows():
            stock = float(row["current_stock"])
            rec_qty = float(row["recommended_order_quantity"])
            rop = float(row["reorder_point_rop"])
            post_order_stock = stock + rec_qty
            self.assertGreater(
                post_order_stock,
                rop,
                msg=f"Replenishment failed to push stock above ROP for {row['material']} {row['area']}: stock({stock}) + order({rec_qty}) = {post_order_stock} <= ROP({rop})",
            )


if __name__ == "__main__":
    unittest.main()

