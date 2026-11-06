"""Global gradient boosting forecasting models for Raphael (LightGBM).

Implements global model across all (material, area) series with:
- Global unified categorical encodings across train, val, and test slices
- Log1p target transformation (eliminates division by near-zero scale blowup)
- Lags, rolling window summary statistics, and weekday profile features
- Calendar features: day of week, day, month, step ahead
- US country holidays and promotion regressors
- Empirical residual quantile intervals (80% and 95%) from validation
- Strict upper clipping at 3x historical maximum to guarantee sanity
"""
import logging
from pathlib import Path
import pickle
from typing import Any, Dict, List, Optional, Tuple
import holidays
import numpy as np
import pandas as pd
from src.models.registry import BaseModel, ModelRegistry


@ModelRegistry.register("global_gradient_boosting")
class GlobalGradientBoostingModel(BaseModel):
    """Global LightGBM demand forecaster across all materials and areas."""

    def __init__(
        self,
        n_estimators: int = 150,
        learning_rate: float = 0.04,
        num_leaves: int = 15,
        random_state: int = 42,
    ):
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.num_leaves = num_leaves
        self.random_state = random_state

        self.model: Any = None
        self.feature_cols: List[str] = []
        self.cat_cols: List[str] = ["material", "area"]
        self.val_residuals: Optional[np.ndarray] = None
        self.quantile_intervals: Dict[str, Tuple[float, float]] = {}
        self.hist_max_map: Dict[Tuple[str, str], float] = {}

        # Prepare US holiday set
        self.us_holidays = holidays.country_holidays("US", years=range(2011, 2020))
        self.mat_dtype: Optional[pd.CategoricalDtype] = None
        self.area_dtype: Optional[pd.CategoricalDtype] = None

    def setup_categorical_dtypes(self, materials: List[str], areas: List[str]):
        """Ensure global, unified categorical codes across all train/val/test slices."""
        self.mat_dtype = pd.CategoricalDtype(categories=sorted(materials), ordered=False)
        self.area_dtype = pd.CategoricalDtype(categories=sorted(areas), ordered=False)

    def _extract_series_stats(self, df_past: pd.DataFrame) -> Dict[str, Any]:
        """Compute summary features from historical period before forecast origin."""
        df_sorted = df_past.sort_values("date")
        q = df_sorted["quantity"].to_numpy(dtype=float)
        n = len(q)

        mean_7 = float(np.mean(q[-7:])) if n >= 7 else float(np.mean(q))
        mean_28 = float(np.mean(q[-28:])) if n >= 28 else float(np.mean(q))
        mean_91 = float(np.mean(q[-91:])) if n >= 91 else float(np.mean(q))
        std_28 = float(np.std(q[-28:], ddof=1)) if n >= 28 else 0.0
        zero_share_91 = float(np.mean(q[-91:] == 0)) if n >= 91 else float(np.mean(q == 0))
        hist_max = float(np.max(q)) if n > 0 else 50.0

        # Day-of-week averages over last 8 weeks (56 days)
        last_8w = df_sorted.iloc[-56:] if n >= 56 else df_sorted
        dow_series = last_8w["date"].dt.dayofweek
        dow_means = last_8w.groupby(dow_series)["quantity"].mean().to_dict()

        return {
            "mean_7": mean_7,
            "mean_28": mean_28,
            "mean_91": mean_91,
            "std_28": std_28,
            "zero_share_91": zero_share_91,
            "dow_means": dow_means,
            "hist_max": hist_max,
        }

    def build_feature_frame(
        self,
        df_target: pd.DataFrame,
        history_map: Dict[Tuple[str, str], pd.DataFrame],
    ) -> pd.DataFrame:
        """Create tabular feature matrix for target forecast window without lookahead leakage."""
        rows = []
        for (mat, area), grp in df_target.groupby(["material", "area"]):
            grp_sorted = grp.sort_values("date").copy()
            past = history_map.get((mat, area))
            if past is None or len(past) == 0:
                continue

            stats = self._extract_series_stats(past)
            dow_means = stats["dow_means"]
            hist_max = stats["hist_max"]
            self.hist_max_map[(mat, area)] = hist_max

            for step, (_, r) in enumerate(grp_sorted.iterrows(), 1):
                dt = r["date"]
                dow = dt.dayofweek
                wm8w = dow_means.get(dow, stats["mean_28"])
                is_hol = int(dt.date() in self.us_holidays)
                actual_qty = float(r.get("quantity", 0.0))

                row_dict = {
                    "material": str(mat),
                    "area": str(area),
                    "date": dt,
                    "quantity": actual_qty,
                    "is_promotion": int(r.get("is_promotion", 0)),
                    "is_holiday": is_hol,
                    "dayofweek": dow,
                    "month": dt.month,
                    "day": dt.day,
                    "step_ahead": step,
                    "mean_7": stats["mean_7"],
                    "mean_28": stats["mean_28"],
                    "mean_91": stats["mean_91"],
                    "std_28": stats["std_28"],
                    "zero_share_91": stats["zero_share_91"],
                    "wm8w": wm8w,
                    "log_wm8w": np.log1p(wm8w),
                    "hist_max": hist_max,
                    "log_target": np.log1p(actual_qty),
                }
                rows.append(row_dict)

        df_out = pd.DataFrame(rows)
        if self.mat_dtype and "material" in df_out.columns:
            df_out["material"] = df_out["material"].astype(self.mat_dtype)
        if self.area_dtype and "area" in df_out.columns:
            df_out["area"] = df_out["area"].astype(self.area_dtype)
        return df_out

    def fit_global(
        self,
        train_features: pd.DataFrame,
        val_features: Optional[pd.DataFrame] = None,
    ) -> "GlobalGradientBoostingModel":
        """Train global model across all pairs on log-transformed targets."""
        import lightgbm as lgb

        self.feature_cols = [
            "material", "area", "dayofweek", "month", "day", "is_holiday",
            "is_promotion", "step_ahead", "log_wm8w", "zero_share_91",
            "mean_7", "mean_28", "mean_91", "std_28"
        ]

        self.model = lgb.LGBMRegressor(
            objective="regression_l1",
            n_estimators=self.n_estimators,
            learning_rate=self.learning_rate,
            num_leaves=self.num_leaves,
            random_state=self.random_state,
            verbose=-1,
            n_jobs=-1,
        )

        X_tr = train_features[self.feature_cols]
        y_tr = train_features["log_target"]

        if val_features is not None and not val_features.empty:
            X_val = val_features[self.feature_cols]
            y_val = val_features["log_target"]
            self.model.fit(
                X_tr, y_tr,
                eval_set=[(X_val, y_val)],
                callbacks=[lgb.early_stopping(stopping_rounds=20, verbose=False)],
            )
            val_preds = np.maximum(0.0, np.expm1(self.model.predict(X_val)))
            actuals = val_features["quantity"].to_numpy()
            self.val_residuals = actuals - val_preds

            self.quantile_intervals["80"] = (
                float(np.percentile(self.val_residuals, 10)),
                float(np.percentile(self.val_residuals, 90)),
            )
            self.quantile_intervals["95"] = (
                float(np.percentile(self.val_residuals, 2.5)),
                float(np.percentile(self.val_residuals, 97.5)),
            )
        else:
            self.model.fit(X_tr, y_tr)
            self.quantile_intervals["80"] = (-0.5, 0.5)
            self.quantile_intervals["95"] = (-1.0, 1.0)

        return self

    def predict_features(self, test_features: pd.DataFrame) -> pd.DataFrame:
        """Predict demand with sanity guardrails (non-negative and capped at 3x historical max)."""
        X_test = test_features[self.feature_cols]
        raw_preds = np.maximum(0.0, np.expm1(self.model.predict(X_test)))

        # Sanity guardrail: cap at 3x historical max for each series
        capped_preds = []
        for i, pred_val in enumerate(raw_preds):
            mat = test_features["material"].iloc[i]
            area = test_features["area"].iloc[i]
            h_max = self.hist_max_map.get((mat, area), 100.0)
            capped_preds.append(min(pred_val, h_max * 3.0))

        res = test_features[["material", "area", "date"]].copy()
        res.rename(columns={"date": "ds"}, inplace=True)
        res["yhat"] = np.array(capped_preds, dtype=float)

        q80_low, q80_high = self.quantile_intervals.get("80", (-0.5, 0.5))
        q95_low, q95_high = self.quantile_intervals.get("95", (-1.0, 1.0))

        res["yhat_lower_80"] = np.maximum(0.0, res["yhat"] + q80_low)
        res["yhat_upper_80"] = np.maximum(0.0, res["yhat"] + q80_high)
        res["yhat_lower_95"] = np.maximum(0.0, res["yhat"] + q95_low)
        res["yhat_upper_95"] = np.maximum(0.0, res["yhat"] + q95_high)
        return res

    def fit(self, df: pd.DataFrame, **kwargs) -> "GlobalGradientBoostingModel":
        return self

    def predict(self, df_future: pd.DataFrame, **kwargs) -> pd.DataFrame:
        return pd.DataFrame()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({
                "model": self.model,
                "feature_cols": self.feature_cols,
                "quantile_intervals": self.quantile_intervals,
                "hist_max_map": self.hist_max_map,
            }, f)

    @classmethod
    def load(cls, path: Path) -> "GlobalGradientBoostingModel":
        with open(path, "rb") as f:
            data = pickle.load(f)
        inst = cls()
        inst.model = data["model"]
        inst.feature_cols = data["feature_cols"]
        inst.quantile_intervals = data["quantile_intervals"]
        inst.hist_max_map = data.get("hist_max_map", {})
        return inst
