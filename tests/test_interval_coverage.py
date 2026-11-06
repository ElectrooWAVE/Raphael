"""Test: interval coverage consistency between per-pair data and fleet summary.

Asserts:
- interval_evaluation.json pair_evaluations coverage values are in [0, 1]
- Fleet 80%/95% coverage re-computed from per-pair values matches the fleet_coverage
  summary within 0.5 percentage points
- champion_model_selection.json coverage values (post-patch in data_store) match
  interval_evaluation.json for every pair
"""

import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
INTERVAL_PATH = ROOT / "artifacts" / "metrics" / "interval_evaluation.json"
CHAMPION_PATH = ROOT / "artifacts" / "metrics" / "champion_model_selection.json"


class TestIntervalCoverageParity(unittest.TestCase):
    def setUp(self):
        with open(INTERVAL_PATH, "r", encoding="utf-8") as f:
            self.ie = json.load(f)
        with open(CHAMPION_PATH, "r", encoding="utf-8") as f:
            self.cs = json.load(f)

    # ------------------------------------------------------------------
    # 1. Per-pair coverage values must be in [0, 1]
    # ------------------------------------------------------------------
    def test_per_pair_coverage_in_unit_range(self):
        pairs = self.ie.get("pair_evaluations", [])
        self.assertGreater(len(pairs), 0, "pair_evaluations must not be empty")
        for p in pairs:
            mat, area = p["material"], p["area"]
            c80 = p["coverage_80"]
            c95 = p["coverage_95"]
            self.assertGreaterEqual(
                c80, 0.0, f"{mat} {area}: coverage_80 {c80} < 0"
            )
            self.assertLessEqual(
                c80, 1.0, f"{mat} {area}: coverage_80 {c80} > 1"
            )
            self.assertGreaterEqual(
                c95, 0.0, f"{mat} {area}: coverage_95 {c95} < 0"
            )
            self.assertLessEqual(
                c95, 1.0, f"{mat} {area}: coverage_95 {c95} > 1"
            )

    # ------------------------------------------------------------------
    # 2. Re-computed fleet coverage == fleet_coverage summary within 0.5 pp
    # ------------------------------------------------------------------
    def test_fleet_coverage_parity(self):
        pairs = self.ie.get("pair_evaluations", [])
        fleet = self.ie.get("fleet_coverage", {})

        n = len(pairs)
        self.assertGreater(n, 0)

        mean_80 = sum(p["coverage_80"] for p in pairs) / n
        mean_95 = sum(p["coverage_95"] for p in pairs) / n

        reported_80 = fleet["overall_80"]
        reported_95 = fleet["overall_95"]

        TOLERANCE = 0.005  # 0.5 percentage points
        self.assertAlmostEqual(
            mean_80,
            reported_80,
            delta=TOLERANCE,
            msg=(
                f"Fleet 80% coverage re-computed from pairs ({mean_80:.4f}) "
                f"differs from summary ({reported_80:.4f}) by more than {TOLERANCE:.3f}"
            ),
        )
        self.assertAlmostEqual(
            mean_95,
            reported_95,
            delta=TOLERANCE,
            msg=(
                f"Fleet 95% coverage re-computed from pairs ({mean_95:.4f}) "
                f"differs from summary ({reported_95:.4f}) by more than {TOLERANCE:.3f}"
            ),
        )

    # ------------------------------------------------------------------
    # 3. champion_model_selection coverage should NOT be the authoritative
    #    post-fix source (values may differ); data_store patches them at load.
    #    Verify interval_evaluation.json pair values are plausible (>= 0.5).
    # ------------------------------------------------------------------
    def test_interval_evaluation_coverage_plausible(self):
        pairs = self.ie.get("pair_evaluations", [])
        low_pairs = [
            (p["material"], p["area"], p["coverage_80"])
            for p in pairs
            if p["coverage_80"] < 0.50
        ]
        # Allow at most 5 pairs below 50% (intermittent series edge cases)
        self.assertLessEqual(
            len(low_pairs),
            5,
            f"Too many pairs with coverage_80 < 50%: {low_pairs}",
        )

    # ------------------------------------------------------------------
    # 4. interval_evaluation.json must cover all 75 material-area pairs
    # ------------------------------------------------------------------
    def test_all_75_pairs_present(self):
        pairs = self.ie.get("pair_evaluations", [])
        self.assertEqual(
            len(pairs),
            75,
            f"Expected 75 pair_evaluations, got {len(pairs)}",
        )

    # ------------------------------------------------------------------
    # 5. champion_model_selection.json coverage values must match
    #    interval_evaluation.json for every single pair within 0.001,
    #    and fleet coverage computed from champion_model_selection
    #    must match interval summary within 0.5 percentage points.
    # ------------------------------------------------------------------
    def test_champion_selection_matches_interval_evaluation(self):
        cs_map = {
            (r["material"], r["area"]): r
            for r in self.cs
        }
        ie_pairs = self.ie.get("pair_evaluations", [])
        self.assertEqual(len(cs_map), 75)
        self.assertEqual(len(ie_pairs), 75)

        for p in ie_pairs:
            key = (p["material"], p["area"])
            cs_rec = cs_map.get(key)
            self.assertIsNotNone(cs_rec, f"Missing pair {key} in champion_model_selection.json")
            self.assertAlmostEqual(
                cs_rec["coverage_80"],
                p["coverage_80"],
                delta=0.001,
                msg=f"{key}: coverage_80 mismatch between champion_model_selection ({cs_rec['coverage_80']}) and interval_eval ({p['coverage_80']})"
            )
            self.assertAlmostEqual(
                cs_rec["coverage_95"],
                p["coverage_95"],
                delta=0.001,
                msg=f"{key}: coverage_95 mismatch between champion_model_selection ({cs_rec['coverage_95']}) and interval_eval ({p['coverage_95']})"
            )

        # Fleet coverage re-computed from champion_model_selection matches fleet summary
        mean_cs_80 = sum(r["coverage_80"] for r in self.cs) / len(self.cs)
        mean_cs_95 = sum(r["coverage_95"] for r in self.cs) / len(self.cs)
        rep_80 = self.ie["fleet_coverage"]["overall_80"]
        rep_95 = self.ie["fleet_coverage"]["overall_95"]

        self.assertAlmostEqual(mean_cs_80, rep_80, delta=0.005)
        self.assertAlmostEqual(mean_cs_95, rep_95, delta=0.005)


if __name__ == "__main__":
    unittest.main()
