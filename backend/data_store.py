"""In-memory artifact data store for Raphael API (Phase 6).

Loads all precomputed parquet and JSON artifacts once at server startup:
- Strictly read-only
- Instant response times (sub-millisecond)
- No runtime model training, no GPU required
"""
from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

logger = logging.getLogger("RaphaelDataStore")


class RaphaelDataStore:
    """Singleton in-memory cache of all Raphael precomputed artifacts."""

    def __init__(self, project_root: Optional[Path] = None):
        self.root = project_root or Path(__file__).resolve().parent.parent
        self.artifacts_dir = self.root / "artifacts"
        self.data_dir = self.root / "data" / "processed"

        # Cached containers
        self.meta: Dict[str, Any] = {}
        self.leaderboard: Dict[str, Any] = {}
        self.champion_selections: List[Dict[str, Any]] = []
        self.recommendations_df: pd.DataFrame = pd.DataFrame()
        self.forecasts_df: pd.DataFrame = pd.DataFrame()
        self.promo_scenarios_df: pd.DataFrame = pd.DataFrame()
        self.lead_time_profiles_df: pd.DataFrame = pd.DataFrame()
        self.demand_history_tail_df: pd.DataFrame = pd.DataFrame()
        self.lead_time_eval: Dict[str, Any] = {}
        self.interval_eval: Dict[str, Any] = {}

        # Indexed lookups for O(1) retrieval
        self.recommendations_by_pair: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.forecasts_by_pair: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        self.promo_by_pair: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.lt_by_pair: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.history_tail_by_pair: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        self.heldout_by_pair: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}

        self.materials: List[str] = []
        self.areas: List[str] = []
        self.pairs: List[Tuple[str, str]] = []
        self.is_loaded: bool = False

    def load_all(self) -> None:
        """Load all artifacts into memory and construct lookup indexes."""
        logger.info("Initializing Raphael in-memory data store from artifacts...")

        # 1. Meta
        meta_path = self.artifacts_dir / "meta.json"
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                self.meta = json.load(f)
        else:
            logger.warning(f"Meta JSON not found at {meta_path}")

        # 2. Leaderboard & Model Selection
        lb_path = self.artifacts_dir / "metrics" / "demand_leaderboard.json"
        if lb_path.exists():
            with open(lb_path, "r", encoding="utf-8") as f:
                self.leaderboard = json.load(f)

        sel_path = self.artifacts_dir / "metrics" / "champion_model_selection.json"
        if sel_path.exists():
            with open(sel_path, "r", encoding="utf-8") as f:
                self.champion_selections = json.load(f)

        # 3. Recommendations (Decision Table)
        rec_path = self.artifacts_dir / "recommendations.parquet"
        if not rec_path.exists():
            rec_path = self.artifacts_dir / "inventory" / "reorder_table.parquet"
        if rec_path.exists():
            self.recommendations_df = pd.read_parquet(rec_path)
            for _, row in self.recommendations_df.iterrows():
                p_key = (str(row["material"]), str(row["area"]))
                self.recommendations_by_pair[p_key] = row.to_dict()

        # 4. Forecasts
        fc_path = self.artifacts_dir / "forecasts" / "demand_forecasts_champion.parquet"
        if fc_path.exists():
            self.forecasts_df = pd.read_parquet(fc_path)
            # Ensure ds is string
            self.forecasts_df["ds_str"] = pd.to_datetime(self.forecasts_df["ds"]).dt.strftime("%Y-%m-%d")
            for (m, a), grp in self.forecasts_df.groupby(["material", "area"]):
                records = []
                for _, r in grp.iterrows():
                    l80 = float(r["yhat_lower_80"]) if "yhat_lower_80" in r and not pd.isna(r["yhat_lower_80"]) else None
                    u80 = float(r["yhat_upper_80"]) if "yhat_upper_80" in r and not pd.isna(r["yhat_upper_80"]) else None
                    l95 = float(r["yhat_lower_95"]) if "yhat_lower_95" in r and not pd.isna(r["yhat_lower_95"]) else None
                    u95 = float(r["yhat_upper_95"]) if "yhat_upper_95" in r and not pd.isna(r["yhat_upper_95"]) else None
                    method = str(r.get("interval_method", "empirical_residual"))
                    is_pooled = bool(r.get("pooled_residuals", False))
                    missing_reason = None if l80 is not None else "Missing interval estimates"

                    records.append({
                        "ds": r["ds_str"],
                        "yhat": float(r["yhat"]),
                        "yhat_lower_80": l80,
                        "yhat_upper_80": u80,
                        "yhat_lower_95": l95,
                        "yhat_upper_95": u95,
                        "interval_method": method,
                        "pooled_residuals": is_pooled,
                        "interval_missing_reason": missing_reason,
                    })
                self.forecasts_by_pair[(str(m), str(a))] = records

        # 5. Promo Scenarios
        promo_path = self.artifacts_dir / "promo_scenarios.parquet"
        if promo_path.exists():
            self.promo_scenarios_df = pd.read_parquet(promo_path)
            for _, row in self.promo_scenarios_df.iterrows():
                p_key = (str(row["material"]), str(row["area"]))
                self.promo_by_pair[p_key] = row.to_dict()

        # 6. Lead Time Profiles
        lt_prof_path = self.artifacts_dir / "lead_time" / "lead_time_pair_predictions.parquet"
        if lt_prof_path.exists():
            self.lead_time_profiles_df = pd.read_parquet(lt_prof_path)
            for _, row in self.lead_time_profiles_df.iterrows():
                p_key = (str(row["material"]), str(row["area"]))
                self.lt_by_pair[p_key] = row.to_dict()

        # 7. Demand History Tail (last 60 days before as_of_date 2016-04-24)
        demand_path = self.data_dir / "demand.parquet"
        if demand_path.exists():
            df_dem = pd.read_parquet(demand_path).sort_values("date")
            as_of_dt = pd.to_datetime("2016-04-24")
            tail_start = as_of_dt - pd.Timedelta(days=60)
            df_tail = df_dem[pd.to_datetime(df_dem["date"]) >= tail_start].copy()
            df_tail["date_str"] = pd.to_datetime(df_tail["date"]).dt.strftime("%Y-%m-%d")

            for (m, a), grp in df_tail.groupby(["material", "area"]):
                t_records = []
                for _, r in grp.iterrows():
                    t_records.append({
                        "date": r["date_str"],
                        "quantity": float(r["quantity"]),
                        "is_promotion": int(r["is_promotion"]),
                    })
                self.history_tail_by_pair[(str(m), str(a))] = t_records

        # 8. Held-out test window (actual vs champion prediction, saved evaluation file)
        test_path = self.artifacts_dir / "forecasts" / "demand_test_eval_champion.parquet"
        if test_path.exists():
            df_t = pd.read_parquet(test_path, columns=["ds", "y", "material", "area", "yhat_champion"])
            df_t["ds_str"] = pd.to_datetime(df_t["ds"]).dt.strftime("%Y-%m-%d")
            df_t = df_t.sort_values("ds_str")
            for (m, a), grp in df_t.groupby(["material", "area"]):
                self.heldout_by_pair[(str(m), str(a))] = [
                    {"ds": r.ds_str, "actual": float(r.y), "predicted": float(r.yhat_champion)}
                    for r in grp.itertuples()
                ]
        # 9. Lead Time Model Evaluation
        lt_path = self.artifacts_dir / "metrics" / "lead_time_model_evaluation.json"
        if lt_path.exists():
            with open(lt_path, "r", encoding="utf-8") as f:
                self.lead_time_eval = json.load(f)

        # 10. Interval Calibration Evaluation
        int_path = self.artifacts_dir / "metrics" / "interval_evaluation.json"
        if int_path.exists():
            with open(int_path, "r", encoding="utf-8") as f:
                self.interval_eval = json.load(f)

        # 10b. Patch champion_selections coverage from interval_evaluation (correct post-fix source).
        # champion_model_selection.json carries stale pre-fix coverage values (e.g. 0.01 instead of 0.86).
        # interval_evaluation.json pair_evaluations is the authoritative post-calibration source.
        if self.interval_eval and self.champion_selections:
            ie_map = {
                (str(r["material"]), str(r["area"])): r
                for r in self.interval_eval.get("pair_evaluations", [])
            }
            for rec in self.champion_selections:
                key = (str(rec.get("material", "")), str(rec.get("area", "")))
                if key in ie_map:
                    rec["coverage_80"] = ie_map[key]["coverage_80"]
                    rec["coverage_95"] = ie_map[key]["coverage_95"]

        # Dimensions
        if not self.recommendations_df.empty:
            self.materials = sorted(self.recommendations_df["material"].unique().tolist())
            self.areas = sorted(self.recommendations_df["area"].unique().tolist())
            self.pairs = list(self.recommendations_by_pair.keys())
        else:
            self.materials = []
            self.areas = []
            self.pairs = []

        self.is_loaded = True
        logger.info(f"RaphaelDataStore loaded: {len(self.pairs)} pairs, {len(self.materials)} materials, {len(self.areas)} areas.")

    def get_pair_recommendation(self, material: str, area: str) -> Optional[Dict[str, Any]]:
        return self.recommendations_by_pair.get((material, area))

    def get_pair_forecast(self, material: str, area: str) -> Optional[List[Dict[str, Any]]]:
        return self.forecasts_by_pair.get((material, area))

    def get_pair_promo_info(self, material: str, area: str) -> Optional[Dict[str, Any]]:
        return self.promo_by_pair.get((material, area))

    def get_pair_lead_time_profile(self, material: str, area: str) -> Optional[Dict[str, Any]]:
        return self.lt_by_pair.get((material, area))

    def get_pair_history_tail(self, material: str, area: str) -> List[Dict[str, Any]]:
        return self.history_tail_by_pair.get((material, area), [])

    def get_pair_heldout(self, material: str, area: str) -> List[Dict[str, Any]]:
        return self.heldout_by_pair.get((material, area), [])


# Global singleton instance
data_store = RaphaelDataStore()
