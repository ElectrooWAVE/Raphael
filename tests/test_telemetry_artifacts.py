"""Automated Parity Test: Verifies that API telemetry endpoints match underlying JSON artifacts."""
import json
import unittest
from pathlib import Path
from starlette.testclient import TestClient
from backend.main import app


class TestTelemetryParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_ctx = TestClient(app)
        cls.client = cls.client_ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_ctx.__exit__(None, None, None)

    def test_accuracy_matches_artifacts(self):
        resp = self.client.get("/accuracy")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        lb_path = Path("artifacts/metrics/demand_leaderboard.json")
        self.assertTrue(lb_path.exists())
        with open(lb_path, "r", encoding="utf-8") as f:
            lb_json = json.load(f)

        self.assertEqual(data["total_pairs"], 75)
        self.assertEqual(data["pairs_flagged_low_confidence"], lb_json["pairs_flagged_low_confidence"])
        self.assertEqual(data["model_selection_breakdown"], lb_json["model_selection_breakdown"])

        # Check LightGBM note presence
        self.assertIn("disqualification_notes", data)
        self.assertIn("LightGBM Global", data["disqualification_notes"])
        self.assertIn("36.92%", data["disqualification_notes"]["LightGBM Global"])

    def test_leadtime_metrics_match_artifacts(self):
        resp = self.client.get("/metrics/leadtime")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        lt_path = Path("artifacts/metrics/lead_time_model_evaluation.json")
        self.assertTrue(lt_path.exists())
        with open(lt_path, "r", encoding="utf-8") as f:
            lt_json = json.load(f)

        self.assertAlmostEqual(data["overall"]["rf_mae"], lt_json["overall"]["rf_mae"], places=3)
        self.assertAlmostEqual(data["overall"]["rf_rmse"], lt_json["overall"]["rf_rmse"], places=3)
        self.assertAlmostEqual(data["overall"]["rf_r2"], lt_json["overall"]["rf_r2"], places=3)
        self.assertAlmostEqual(data["overall"]["tree_std_coverage_95"], lt_json["overall"]["tree_std_coverage_95"], places=3)
        self.assertAlmostEqual(data["overall"]["calibrated_coverage_95"], lt_json["overall"]["calibrated_coverage_95"], places=3)

    def test_interval_metrics_match_artifacts(self):
        resp = self.client.get("/metrics/intervals")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        iv_path = Path("artifacts/metrics/interval_evaluation.json")
        self.assertTrue(iv_path.exists())
        with open(iv_path, "r", encoding="utf-8") as f:
            iv_json = json.load(f)

        self.assertAlmostEqual(data["fleet_coverage"]["overall_80"], iv_json["fleet_coverage"]["overall_80"], places=3)
        self.assertAlmostEqual(data["fleet_coverage"]["overall_95"], iv_json["fleet_coverage"]["overall_95"], places=3)

    def test_benchmarks_match_artifacts(self):
        resp = self.client.get("/benchmarks")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        bm_path = Path("artifacts/benchmarks.json")
        if bm_path.exists():
            with open(bm_path, "r", encoding="utf-8") as f:
                bm_json = json.load(f)
            self.assertEqual(data["status"], "completed")
            self.assertEqual(data["detected_hardware"]["cpu_model"], bm_json["benchmark_environment"]["cpu_model"])


if __name__ == "__main__":
    unittest.main()
