"""Lead-time prediction model for Raphael (Random Forest + Uncertainty Calibration).

Predicts supplier lead times per (material, area, order_quantity, calendar season) with:
- Ensemble mean prediction from decision trees
- Uncalibrated tree-spread standard deviation (measures ensemble disagreement)
- Empirically calibrated residual standard deviation (calibrated per area / season)
- Historical quantity range tracking and extrapolation boundary detection
"""
from pathlib import Path
import pickle
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import OrdinalEncoder
from src.models.registry import BaseModel, ModelRegistry


@ModelRegistry.register("leadtime_rf")
class LeadTimeRandomForestModel(BaseModel):
    """Random Forest regressor for procurement lead-time prediction and uncertainty estimation."""

    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: Optional[int] = 12,
        min_samples_split: int = 5,
        min_samples_leaf: int = 2,
        random_state: int = 42,
        n_jobs: int = -1,
    ):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.min_samples_leaf = min_samples_leaf
        self.random_state = random_state
        self.n_jobs = n_jobs

        self.model: Optional[RandomForestRegressor] = None
        self.encoder: Optional[OrdinalEncoder] = None
        self.feature_cols: List[str] = [
            "mat_code", "area_code", "order_quantity",
            "month", "is_holiday_season", "quarter", "dayofweek", "day"
        ]
        self.hist_ranges: Dict[Tuple[str, str], Tuple[float, float]] = {}
        self.calibrated_stds: Dict[str, float] = {}
        self.overall_calibrated_std: float = 1.0

    def _extract_calendar_features(self, df: pd.DataFrame, date_col: str = "order_date") -> pd.DataFrame:
        """Derive non-leaking calendar attributes from order date."""
        df_out = df.copy()
        dt_series = pd.to_datetime(df_out[date_col])
        df_out["month"] = dt_series.dt.month
        df_out["day"] = dt_series.dt.day
        df_out["dayofweek"] = dt_series.dt.dayofweek
        df_out["quarter"] = dt_series.dt.quarter
        df_out["is_holiday_season"] = dt_series.dt.month.isin([11, 12]).astype(int)
        return df_out

    def fit(self, df: pd.DataFrame, target_col: str = "lead_time_days", **kwargs) -> "LeadTimeRandomForestModel":
        """Fit Random Forest on historical order data and record pair quantity bounds."""
        df_clean = self._extract_calendar_features(df, date_col="order_date")

        # Record historical order quantity range per pair for extrapolation detection
        for (mat, area), grp in df_clean.groupby(["material", "area"]):
            min_q = float(grp["order_quantity"].min())
            max_q = float(grp["order_quantity"].max())
            self.hist_ranges[(str(mat), str(area))] = (min_q, max_q)

        self.encoder = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
        encoded_cats = self.encoder.fit_transform(df_clean[["material", "area"]])
        df_clean["mat_code"] = encoded_cats[:, 0]
        df_clean["area_code"] = encoded_cats[:, 1]

        self.model = RandomForestRegressor(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            min_samples_split=self.min_samples_split,
            min_samples_leaf=self.min_samples_leaf,
            random_state=self.random_state,
            n_jobs=self.n_jobs,
        )

        X = df_clean[self.feature_cols].to_numpy()
        y = df_clean[target_col].to_numpy(dtype=float)
        self.model.fit(X, y)
        return self

    def fit_with_calibration(
        self,
        train_df: pd.DataFrame,
        target_col: str = "lead_time_days",
        n_splits: int = 5,
    ) -> Dict[str, Any]:
        """Fit Random Forest and calibrate residual uncertainty via K-fold out-of-fold validation on train data."""
        from sklearn.model_selection import KFold

        # 1. Compute out-of-fold predictions on training data to establish honest residual distributions
        kf = KFold(n_splits=n_splits, shuffle=True, random_state=self.random_state)
        oof_preds = np.zeros(len(train_df))

        for tr_idx, val_idx in kf.split(train_df):
            sub_model = LeadTimeRandomForestModel(
                n_estimators=self.n_estimators,
                max_depth=self.max_depth,
                min_samples_split=self.min_samples_split,
                min_samples_leaf=self.min_samples_leaf,
                random_state=self.random_state,
                n_jobs=self.n_jobs,
            )
            sub_model.fit(train_df.iloc[tr_idx], target_col=target_col)
            pred_val = sub_model.predict(train_df.iloc[val_idx])
            oof_preds[val_idx] = pred_val["predicted_lead_time"].to_numpy()

        oof_df = train_df.copy()
        oof_df["residual"] = oof_df[target_col].to_numpy() - oof_preds
        oof_df["is_holiday_season"] = pd.to_datetime(oof_df["order_date"]).dt.month.isin([11, 12]).astype(int)

        self.overall_calibrated_std = float(np.std(oof_df["residual"].to_numpy(), ddof=1))
        self.calibrated_stds = {}
        for (area, is_hol), grp in oof_df.groupby(["area", "is_holiday_season"]):
            res_grp = grp["residual"].to_numpy()
            std_grp = float(np.std(res_grp, ddof=1)) if len(res_grp) > 1 else self.overall_calibrated_std
            self.calibrated_stds[f"{area}_holiday_{is_hol}"] = round(std_grp, 4)

        # 2. Fit final model on the full training set
        self.fit(train_df, target_col=target_col)

        return {
            "overall_calibrated_std": round(self.overall_calibrated_std, 4),
            "segmented_calibrated_stds": self.calibrated_stds,
        }

    def calibrate_uncertainty(self, df_held_out: pd.DataFrame, target_col: str = "lead_time_days") -> Dict[str, float]:
        """Calibrate empirical uncertainty from held-out test residuals across areas and seasons."""
        preds = self.predict(df_held_out)
        y_true = df_held_out[target_col].to_numpy(dtype=float)
        y_hat = preds["predicted_lead_time"].to_numpy(dtype=float)
        residuals = y_true - y_hat

        # Fleet-wide calibrated residual std
        self.overall_calibrated_std = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 1.0

        # Segmented calibrated std by area and holiday season
        df_eval = df_held_out.copy()
        df_eval["residual"] = residuals
        df_eval["is_holiday_season"] = pd.to_datetime(df_eval["order_date"]).dt.month.isin([11, 12]).astype(int)

        self.calibrated_stds = {}
        for (area, is_hol), grp in df_eval.groupby(["area", "is_holiday_season"]):
            res_grp = grp["residual"].to_numpy()
            std_grp = float(np.std(res_grp, ddof=1)) if len(res_grp) > 1 else self.overall_calibrated_std
            self.calibrated_stds[f"{area}_holiday_{is_hol}"] = round(std_grp, 4)

        return {
            "overall_calibrated_std": round(self.overall_calibrated_std, 4),
            "segmented_calibrated_stds": self.calibrated_stds,
        }

    def predict(self, df_future: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Predict mean lead time, tree-spread std, calibrated std, and extrapolation flags."""
        if self.model is None or self.encoder is None:
            raise RuntimeError("Model must be fitted before predict.")

        df_input = self._extract_calendar_features(df_future, date_col=kwargs.get("date_col", "order_date"))
        encoded_cats = self.encoder.transform(df_input[["material", "area"]])
        df_input["mat_code"] = encoded_cats[:, 0]
        df_input["area_code"] = encoded_cats[:, 1]

        X = df_input[self.feature_cols].to_numpy()

        # Extract predictions across individual decision trees
        tree_preds = np.array([tree.predict(X) for tree in self.model.estimators_])  # shape: (n_trees, n_samples)
        pred_means = np.maximum(1.0, np.mean(tree_preds, axis=0))  # lead times >= 1 day
        tree_stds = np.std(tree_preds, axis=0, ddof=1)

        # Map calibrated uncertainty
        calibrated_stds = []
        is_extrapolations = []
        hist_min_qs = []
        hist_max_qs = []

        for i, r in df_input.iterrows():
            mat = str(r["material"])
            area = str(r["area"])
            is_hol = int(r["is_holiday_season"])
            q_val = float(r["order_quantity"])

            cal_key = f"{area}_holiday_{is_hol}"
            c_std = self.calibrated_stds.get(cal_key, self.overall_calibrated_std)
            calibrated_stds.append(c_std)

            # Historical range extrapolation check
            h_range = self.hist_ranges.get((mat, area), (1.0, 500.0))
            hist_min_qs.append(h_range[0])
            hist_max_qs.append(h_range[1])
            is_extrap = bool(q_val < h_range[0] or q_val > h_range[1])
            is_extrapolations.append(is_extrap)

        res = df_future[["material", "area"]].copy()
        if "order_date" in df_future.columns:
            res["order_date"] = df_future["order_date"].values
        res["order_quantity"] = df_future["order_quantity"].values
        res["predicted_lead_time"] = np.round(pred_means, 2)
        res["tree_spread_std"] = np.round(tree_stds, 3)
        res["calibrated_lead_time_std"] = np.round(calibrated_stds, 3)
        res["hist_min_quantity"] = hist_min_qs
        res["hist_max_quantity"] = hist_max_qs
        res["is_extrapolation"] = is_extrapolations

        # Dual 95% intervals for comparison
        res["tree_lower_95"] = np.maximum(1.0, np.round(pred_means - 1.96 * tree_stds, 2))
        res["tree_upper_95"] = np.round(pred_means + 1.96 * tree_stds, 2)
        res["calibrated_lower_95"] = np.maximum(1.0, np.round(pred_means - 1.96 * np.array(calibrated_stds), 2))
        res["calibrated_upper_95"] = np.round(pred_means + 1.96 * np.array(calibrated_stds), 2)

        return res

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "config": {
                "n_estimators": self.n_estimators,
                "max_depth": self.max_depth,
                "min_samples_split": self.min_samples_split,
                "min_samples_leaf": self.min_samples_leaf,
                "random_state": self.random_state,
                "n_jobs": self.n_jobs,
            },
            "model": self.model,
            "encoder": self.encoder,
            "hist_ranges": self.hist_ranges,
            "calibrated_stds": self.calibrated_stds,
            "overall_calibrated_std": self.overall_calibrated_std,
            "feature_cols": self.feature_cols,
        }
        with open(path, "wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, path: Path) -> "LeadTimeRandomForestModel":
        with open(path, "rb") as f:
            data = pickle.load(f)
        inst = cls(**data["config"])
        inst.model = data["model"]
        inst.encoder = data["encoder"]
        inst.hist_ranges = data["hist_ranges"]
        inst.calibrated_stds = data["calibrated_stds"]
        inst.overall_calibrated_std = data["overall_calibrated_std"]
        inst.feature_cols = data["feature_cols"]
        return inst
