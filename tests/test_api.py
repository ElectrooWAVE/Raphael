"""API unit tests for Raphael FastAPI backend.

Verifies:
1. All endpoints return 200 with correct schema structures
2. 404 error handling for unknown pairs
3. /whatif endpoint exactly reproduces all fixtures in tests/inventory_fixtures.json
"""
import json
from pathlib import Path
import unittest
from starlette.testclient import TestClient

from backend.main import app


class TestRaphaelAPI(unittest.TestCase):
    """Test suite for Raphael FastAPI endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        # Trigger lifespan
        with cls.client:
            cls.live_client = cls.client

    def setUp(self):
        self.client = TestClient(app)

    def test_01_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["app"], "Raphael API")
        self.assertTrue(data["artifacts_ready"])

    def test_02_meta(self):
        resp = self.client.get("/meta")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["dates"]["as_of_date"], "2016-04-24")
        self.assertEqual(data["fleet_dimensions"]["total_pairs"], 75)
        self.assertIn("Walmart M5", data["provenance"]["demand"])

    def test_03_materials_and_areas(self):
        resp_m = self.client.get("/materials")
        self.assertEqual(resp_m.status_code, 200)
        data_m = resp_m.json()
        self.assertEqual(data_m["total_materials"], 25)

        resp_a = self.client.get("/areas")
        self.assertEqual(resp_a.status_code, 200)
        data_a = resp_a.json()
        self.assertEqual(data_a["total_areas"], 3)

        # Filter areas by material
        resp_a_filtered = self.client.get("/areas?material=FOODS_2_019")
        self.assertEqual(resp_a_filtered.status_code, 200)
        self.assertEqual(resp_a_filtered.json()["total_areas"], 3)

    def test_04_forecast(self):
        resp = self.client.get("/forecast/FOODS_3_099/California - CA_1")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["material"], "FOODS_3_099")
        self.assertEqual(data["area"], "California - CA_1")
        self.assertEqual(len(data["forecast_90d"]), 90)
        self.assertGreater(len(data["history_tail_60d"]), 0)
        self.assertIn("empirical_lift", data["empirical_promotion"])

    def test_05_reorder(self):
        resp = self.client.get("/reorder/FOODS_3_099/California - CA_1")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "CRITICAL")
        self.assertEqual(data["urgency_rank"], 2)
        self.assertAlmostEqual(data["reorder_point_rop"], 140.05, places=1)
        self.assertAlmostEqual(data["safety_stock_ss"], 37.24, places=1)

    def test_06_urgency(self):
        resp = self.client.get("/urgency")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_pairs"], 75)
        self.assertEqual(data["status_breakdown"]["CRITICAL"], 25)
        self.assertEqual(data["status_breakdown"]["REORDER"], 5)
        self.assertEqual(data["status_breakdown"]["OK"], 45)

        # Test filter
        resp_crit = self.client.get("/urgency?status=CRITICAL")
        self.assertEqual(resp_crit.status_code, 200)
        self.assertEqual(resp_crit.json()["filtered_pairs"], 25)

    def test_07_accuracy(self):
        resp = self.client.get("/accuracy")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(len(data["leaderboard"]), 0)
        self.assertEqual(data["total_pairs"], 75)

    def test_08_leadtime(self):
        resp = self.client.get("/leadtime/FOODS_3_099/California - CA_1")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertAlmostEqual(data["predicted_lead_time_upcoming_days"], 7.03, places=1)
        self.assertGreater(data["lead_time_holiday_peak_days"], 0)

    def test_09_whatif_reproduces_fixtures(self):
        """Verify /whatif reproduces all fixtures in tests/inventory_fixtures.json."""
        fixtures_path = Path(__file__).parent / "inventory_fixtures.json"
        with open(fixtures_path, "r", encoding="utf-8") as f:
            fixtures = json.load(f)

        for case in fixtures:
            cid = case["id"]
            inp = case["inputs"]
            exp = case["expected"]

            # Only test cases that have decision layer inputs
            if "D" in inp:
                payload = {
                    "demand_rate": inp["D"],
                    "demand_std": inp["sigma_D"],
                    "lead_time": inp["L"],
                    "lead_time_std": inp["sigma_L"],
                    "service_level": inp["service_level"],
                    "current_stock": inp["stock"],
                    "daily_forecasts": inp["daily_forecasts"],
                }
                resp = self.client.post("/whatif", json=payload)
                self.assertEqual(resp.status_code, 200, f"[{cid}] /whatif failed: {resp.text}")
                data = resp.json()

                self.assertAlmostEqual(data["safety_stock_ss"], exp["safety_stock"], places=2, msg=f"[{cid}] SS mismatch")
                self.assertAlmostEqual(data["reorder_point_rop"], exp["rop"], places=2, msg=f"[{cid}] ROP mismatch")
                self.assertAlmostEqual(data["days_remaining"], exp["days_remaining"], places=2, msg=f"[{cid}] days_remaining mismatch")
                self.assertEqual(data["beyond_horizon"], exp["beyond_horizon"], msg=f"[{cid}] beyond_horizon mismatch")
                self.assertEqual(data["status"], exp["status"], msg=f"[{cid}] status mismatch")

    def test_10_csv_export(self):
        resp = self.client.get("/export/recommendations.csv?status=CRITICAL")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["content-type"], "text/csv; charset=utf-8")
        lines = resp.text.strip().split("\n")
        self.assertEqual(len(lines), 26) # Header + 25 critical rows

    def test_11_benchmarks(self):
        resp = self.client.get("/benchmarks")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn(data["status"], ["completed", "not computed yet"])
        if data["status"] == "completed":
            self.assertIn("detected_hardware", data)
            self.assertIn("benchmarks", data)

    def test_12_404_error_handling(self):
        resp = self.client.get("/forecast/NON_EXISTENT_MATERIAL/NON_EXISTENT_AREA")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json()["detail"].lower())

    def test_13_all_pairs_have_valid_ordered_nonnegative_bands(self):
        """Phase 5b: Verify all 75 pairs return non-null, ordered, non-negative 80% & 95% bands."""
        resp_urgency = self.client.get("/urgency")
        self.assertEqual(resp_urgency.status_code, 200)
        pairs = resp_urgency.json()["items"]
        self.assertEqual(len(pairs), 75)

        for item in pairs:
            mat = item["material"]
            area = item["area"]
            resp = self.client.get(f"/forecast/{mat}/{area}")
            self.assertEqual(resp.status_code, 200, f"Failed for {mat} / {area}")
            data = resp.json()
            
            self.assertIn(data["interval_method"], ["prophet_native", "empirical_residual"])
            self.assertIsInstance(data["pooled_residuals"], bool)
            self.assertIsNone(data["interval_missing_reason"])
            
            f_points = data["forecast_90d"]
            self.assertEqual(len(f_points), 90)
            
            for pt in f_points:
                yhat = pt["yhat"]
                l80 = pt["yhat_lower_80"]
                u80 = pt["yhat_upper_80"]
                l95 = pt["yhat_lower_95"]
                u95 = pt["yhat_upper_95"]
                
                # Check non-null
                self.assertIsNotNone(l80)
                self.assertIsNotNone(u80)
                self.assertIsNotNone(l95)
                self.assertIsNotNone(u95)
                
                # Check non-negative
                self.assertGreaterEqual(l95, 0.0)
                self.assertGreaterEqual(l80, 0.0)
                self.assertGreaterEqual(yhat, 0.0)
                
                # Check ordering: lower_95 <= lower_80 <= yhat <= upper_80 <= upper_95
                self.assertLessEqual(l95, l80 + 1e-6, f"l95 > l80 in {mat} / {area}")
                self.assertLessEqual(l80, yhat + 1e-6, f"l80 > yhat in {mat} / {area}")
                self.assertLessEqual(yhat, u80 + 1e-6, f"yhat > u80 in {mat} / {area}")
                self.assertLessEqual(u80, u95 + 1e-6, f"u80 > u95 in {mat} / {area}")


if __name__ == "__main__":
    unittest.main()

