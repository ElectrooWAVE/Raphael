import sys
sys.path.insert(0, ".")
import json
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from src.evaluation.metrics import compute_wape, compute_coverage
from src.models.baselines import (
    WeekdayMean8WModel,
    MovingAverage91DModel,
    CrostonSBAModel,
    SeasonalNaiveModel,
)
from src.models.blends import blend_predictions
from src.models.demand_prophet import ProphetDemandModel

df_demand = pd.read_parquet("data/processed/demand.parquet")
df_lt = pd.read_parquet("data/processed/lead_time.parquet")
lt_means = df_lt.groupby(["material", "area"])["lead_time_days"].mean().to_dict()

test_days = 84
total_len = 1913
train_full_len = total_len - test_days  # 1829

# 4 folds of 21 days each ending before test
fold_len = 21
n_folds = 4
fold_ends = [train_full_len - (n_folds - 1 - i) * fold_len for i in range(n_folds)]
# fold_ends: [1766, 1787, 1808, 1829]
# Fold 0: test [1745:1766], train [:1745]
# Fold 1: test [1766:1787], train [:1766]
# Fold 2: test [1787:1808], train [:1787]
# Fold 3: test [1808:1829], train [:1808]

pairs = df_demand[["material", "area"]].drop_duplicates().values.tolist()

def eval_rolling_pair(mat, area):
    df_sub = df_demand[(df_demand["material"] == mat) & (df_demand["area"] == area)].sort_values("date").reset_index(drop=True)
    df_train_full = df_sub.iloc[:train_full_len].copy()
    df_test = df_sub.iloc[train_full_len:].copy()
    hist_max = float(df_train_full["quantity"].max())
    max_allowed = max(10.0, hist_max * 3.0)

    # 1. Evaluate candidate models on 4 rolling folds
    candidate_names = [
        "weekday_mean_8w",
        "moving_average_91d",
        "croston_sba",
        "seasonal_naive",
        "prophet_tuned",
        "blend_prophet_wm8w"
    ]
    
    fold_errors = {c: [] for c in candidate_names}
    fold_actuals = []
    fold_weekly_wapes = {c: [] for c in candidate_names}

    for f_idx in range(n_folds):
        f_end = fold_ends[f_idx]
        f_start = f_end - fold_len
        f_train = df_sub.iloc[:f_start].copy()
        f_val = df_sub.iloc[f_start:f_end].copy()
        
        val_input = pd.DataFrame({"ds": f_val["date"], "is_promotion": f_val["is_promotion"]})
        y_val = f_val["quantity"].values
        y_w = y_val.reshape(-1, 7).sum(axis=1)
        fold_actuals.append(y_w)

        # Baseline fits
        p_wm = WeekdayMean8WModel().fit(f_train, target_col="quantity", date_col="date").predict(val_input, date_col="ds")["yhat"].values
        p_ma = MovingAverage91DModel().fit(f_train, target_col="quantity").predict(val_input)["yhat"].values
        p_cs = CrostonSBAModel().fit(f_train, target_col="quantity").predict(val_input)["yhat"].values
        p_sn = SeasonalNaiveModel(season_length=7).fit(f_train, target_col="quantity").predict(val_input)["yhat"].values
        
        # Prophet
        mean_vol = float(f_train["quantity"].mean())
        m = ProphetDemandModel(
            growth="linear",
            yearly_seasonality=(mean_vol >= 4.0),
            weekly_seasonality=True,
            daily_seasonality=False,
            country_holidays="US",
            changepoint_prior_scale=0.01,
            clip_lower_bound=0.0,
        )
        fit_sub = f_train if len(f_train) <= 730 else f_train.iloc[-730:]
        m.fit(pd.DataFrame({"ds": fit_sub["date"], "y": fit_sub["quantity"], "is_promotion": fit_sub["is_promotion"]}))
        p_pr = m.predict(val_input)["yhat"].values
        p_bl = 0.5 * p_pr + 0.5 * p_wm

        preds_dict = {
            "weekday_mean_8w": p_wm,
            "moving_average_91d": p_ma,
            "croston_sba": p_cs,
            "seasonal_naive": p_sn,
            "prophet_tuned": p_pr,
            "blend_prophet_wm8w": p_bl,
        }

        for c in candidate_names:
            p_w = preds_dict[c].reshape(-1, 7).sum(axis=1)
            fold_errors[c].append(np.abs(y_w - p_w))
            wape_f = float(np.sum(np.abs(y_w - p_w)) / max(1e-6, np.sum(y_w)))
            fold_weekly_wapes[c].append(wape_f)

    # Compute robust CV metrics:
    # 1. Pooled WAPE across all 4 folds:
    y_all_folds = np.concatenate(fold_actuals)
    sum_actual = max(1e-6, np.sum(y_all_folds))
    cv_pooled_wapes = {c: float(np.sum(np.concatenate(fold_errors[c])) / sum_actual) for c in candidate_names}
    cv_median_wapes = {c: float(np.median(fold_weekly_wapes[c])) for c in candidate_names}

    # Selection:
    # Choice A: Pooled across folds
    winner_pooled = min(candidate_names, key=lambda c: cv_pooled_wapes[c])
    # Choice B: Median across folds
    winner_median = min(candidate_names, key=lambda c: cv_median_wapes[c])

    # Now evaluate ALL candidates on the HELD-OUT TEST SET (84 days)
    test_input = pd.DataFrame({"ds": df_test["date"], "is_promotion": df_test["is_promotion"]})
    y_test = df_test["quantity"].values
    y_test_w = y_test.reshape(-1, 7).sum(axis=1)

    t_wm = WeekdayMean8WModel().fit(df_train_full, target_col="quantity", date_col="date").predict(test_input, date_col="ds")["yhat"].values
    t_ma = MovingAverage91DModel().fit(df_train_full, target_col="quantity").predict(test_input)["yhat"].values
    t_cs = CrostonSBAModel().fit(df_train_full, target_col="quantity").predict(test_input)["yhat"].values
    t_sn = SeasonalNaiveModel(season_length=7).fit(df_train_full, target_col="quantity").predict(test_input)["yhat"].values

    m_full = ProphetDemandModel(
        growth="linear",
        yearly_seasonality=(float(df_train_full["quantity"].mean()) >= 4.0),
        weekly_seasonality=True,
        daily_seasonality=False,
        country_holidays="US",
        changepoint_prior_scale=0.01,
        clip_lower_bound=0.0,
    )
    fit_full = df_train_full if len(df_train_full) <= 730 else df_train_full.iloc[-730:]
    m_full.fit(pd.DataFrame({"ds": fit_full["date"], "y": fit_full["quantity"], "is_promotion": fit_full["is_promotion"]}))
    t_pr_df = m_full.predict(test_input)
    t_pr = t_pr_df["yhat"].values
    t_bl = 0.5 * t_pr + 0.5 * t_wm

    test_preds_daily = {
        "weekday_mean_8w": np.clip(t_wm, 0, max_allowed),
        "moving_average_91d": np.clip(t_ma, 0, max_allowed),
        "croston_sba": np.clip(t_cs, 0, max_allowed),
        "seasonal_naive": np.clip(t_sn, 0, max_allowed),
        "prophet_tuned": np.clip(t_pr, 0, max_allowed),
        "blend_prophet_wm8w": np.clip(t_bl, 0, max_allowed),
    }

    test_preds_w = {c: test_preds_daily[c].reshape(-1, 7).sum(axis=1) for c in candidate_names}

    return {
        "material": mat,
        "area": area,
        "cv_pooled_wapes": cv_pooled_wapes,
        "cv_median_wapes": cv_median_wapes,
        "winner_pooled": winner_pooled,
        "winner_median": winner_median,
        "y_test_w": y_test_w,
        "y_test_daily": y_test,
        "test_preds_w": test_preds_w,
        "test_preds_daily": test_preds_daily,
        "residual_std": float(m_full.residual_std or 1.0),
    }

print("Running 4-fold rolling-origin CV across 75 pairs...")
cv_results = Parallel(n_jobs=10)(delayed(eval_rolling_pair)(mat, area) for mat, area in pairs)
print("Finished rolling CV.")

# Analyze results
from collections import Counter

y_test_all_w = np.concatenate([r["y_test_w"] for r in cv_results])
y_test_all_daily = np.concatenate([r["y_test_daily"] for r in cv_results])

# 1. Current Champion in production:
# From demand_leaderboard.json, current champion weekly pooled WAPE is 29.20%, mean 39.48%

# 2. Rolling CV winner (pooled per pair):
p_w_pooled = np.concatenate([r["test_preds_w"][r["winner_pooled"]] for r in cv_results])
test_pooled_wape_pooled = compute_wape(y_test_all_w, p_w_pooled)
pair_means_pooled = [compute_wape(r["y_test_w"], r["test_preds_w"][r["winner_pooled"]]) for r in cv_results]
test_mean_wape_pooled = float(np.mean(pair_means_pooled))

# 3. Rolling CV winner (median per pair):
p_w_median = np.concatenate([r["test_preds_w"][r["winner_median"]] for r in cv_results])
test_pooled_wape_median = compute_wape(y_test_all_w, p_w_median)
pair_means_median = [compute_wape(r["y_test_w"], r["test_preds_w"][r["winner_median"]]) for r in cv_results]
test_mean_wape_median = float(np.mean(pair_means_median))

# 4. Weekday Mean 8W alone:
p_w_wm = np.concatenate([r["test_preds_w"]["weekday_mean_8w"] for r in cv_results])
test_pooled_wm = compute_wape(y_test_all_w, p_w_wm)
test_mean_wm = float(np.mean([compute_wape(r["y_test_w"], r["test_preds_w"]["weekday_mean_8w"]) for r in cv_results]))

print("\n" + "="*80)
print("TEST SET EVALUATION RESULTS (84 DAYS):")
print("="*80)
print(f"Current Champion (Existing Artifact): Test Weekly Pooled = 29.20%, Mean = 39.48%")
print(f"Weekday Mean 8W Benchmark:           Test Weekly Pooled = {test_pooled_wm*100:.2f}%, Mean = {test_mean_wm*100:.2f}%")
print(f"Rolling CV (4x21d Pooled Per-Pair):   Test Weekly Pooled = {test_pooled_wape_pooled*100:.2f}%, Mean = {test_mean_wape_pooled*100:.2f}%")
print(f"  Breakdown: {Counter([r['winner_pooled'] for r in cv_results])}")
print(f"Rolling CV (4x21d Median Per-Pair):   Test Weekly Pooled = {test_pooled_wape_median*100:.2f}%, Mean = {test_mean_wape_median*100:.2f}%")
print(f"  Breakdown: {Counter([r['winner_median'] for r in cv_results])}")
print("="*80)
