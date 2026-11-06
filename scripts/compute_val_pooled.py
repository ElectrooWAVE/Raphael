import sys
sys.path.insert(0, ".")
import json
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from src.evaluation.metrics import compute_wape
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

with open("artifacts/metrics/champion_model_selection.json", "r") as f:
    sel_data = json.load(f)

test_days = 84
val_days = 84

pairs = df_demand[["material", "area"]].drop_duplicates().values.tolist()

# Let's run a fast evaluation for each pair
def eval_pair(mat, area):
    df_sub = df_demand[(df_demand["material"] == mat) & (df_demand["area"] == area)].sort_values("date").reset_index(drop=True)
    train_full = df_sub.iloc[:-test_days]
    train_val = train_full.iloc[:-val_days]
    val_df = train_full.iloc[-val_days:]
    
    val_future_input = pd.DataFrame({"ds": val_df["date"], "is_promotion": val_df["is_promotion"]})
    
    # Baselines
    p_wm = WeekdayMean8WModel().fit(train_val, target_col="quantity", date_col="date").predict(val_future_input, date_col="ds")["yhat"].values
    p_ma = MovingAverage91DModel().fit(train_val, target_col="quantity").predict(val_future_input)["yhat"].values
    p_cs = CrostonSBAModel().fit(train_val, target_col="quantity").predict(val_future_input)["yhat"].values
    p_sn = SeasonalNaiveModel(season_length=7).fit(train_val, target_col="quantity").predict(val_future_input)["yhat"].values
    
    # Prophet (tuned)
    # Use standard prophet tuned
    mean_vol = float(train_val["quantity"].mean())
    m = ProphetDemandModel(
        growth="linear",
        yearly_seasonality=(mean_vol >= 4.0),
        weekly_seasonality=True,
        daily_seasonality=False,
        country_holidays="US",
        changepoint_prior_scale=0.01,
        clip_lower_bound=0.0,
    )
    df_fit = pd.DataFrame({"ds": train_val["date"], "y": train_val["quantity"], "is_promotion": train_val["is_promotion"]})
    if len(df_fit) > 730:
        df_fit = df_fit.iloc[-730:]
    m.fit(df_fit)
    p_pr = m.predict(val_future_input)["yhat"].values
    p_bl = 0.5 * p_pr + 0.5 * p_wm

    y_val = val_df["quantity"].values
    
    # Weekly aggregation (7 days non-overlapping, 12 weeks)
    y_w = y_val.reshape(-1, 7).sum(axis=1)
    wm_w = p_wm.reshape(-1, 7).sum(axis=1)
    ma_w = p_ma.reshape(-1, 7).sum(axis=1)
    cs_w = p_cs.reshape(-1, 7).sum(axis=1)
    sn_w = p_sn.reshape(-1, 7).sum(axis=1)
    pr_w = p_pr.reshape(-1, 7).sum(axis=1)
    bl_w = p_bl.reshape(-1, 7).sum(axis=1)
    
    return {
        "material": mat,
        "area": area,
        "y_w": y_w,
        "wm_w": wm_w,
        "ma_w": ma_w,
        "cs_w": cs_w,
        "sn_w": sn_w,
        "pr_w": pr_w,
        "bl_w": bl_w,
    }

print("Running parallel evaluation on 84-day val window across 75 pairs...")
results = Parallel(n_jobs=10)(delayed(eval_pair)(mat, area) for mat, area in pairs)

# Aggregate
all_y = np.concatenate([r["y_w"] for r in results])
candidates = {
    "Weekday Mean 8W": np.concatenate([r["wm_w"] for r in results]),
    "Moving Average 91D": np.concatenate([r["ma_w"] for r in results]),
    "Croston SBA": np.concatenate([r["cs_w"] for r in results]),
    "Seasonal Naive": np.concatenate([r["sn_w"] for r in results]),
    "Prophet (Tuned)": np.concatenate([r["pr_w"] for r in results]),
    "Prophet + Weekday Mean 8W Blend": np.concatenate([r["bl_w"] for r in results]),
}

# Current champion predictions on val
champ_preds = []
champ_pure_preds = []
champ_map = {p["material"] + "_" + p["area"]: p["champion_model"] for p in sel_data}

# Also compute pure val min choice for each pair
pair_val_wapes = {}
for r in results:
    key = r["material"] + "_" + r["area"]
    pair_wapes = {
        "weekday_mean_8w": compute_wape(r["y_w"], r["wm_w"]),
        "moving_average_91d": compute_wape(r["y_w"], r["ma_w"]),
        "croston_sba": compute_wape(r["y_w"], r["cs_w"]),
        "seasonal_naive": compute_wape(r["y_w"], r["sn_w"]),
        "prophet_tuned": compute_wape(r["y_w"], r["pr_w"]),
        "blend_prophet_wm8w": compute_wape(r["y_w"], r["bl_w"]),
    }
    pair_val_wapes[key] = pair_wapes
    
    # Current champion from artifact
    c_name = champ_map[key]
    pred_map = {
        "weekday_mean_8w": r["wm_w"],
        "moving_average_91d": r["ma_w"],
        "croston_sba": r["cs_w"],
        "seasonal_naive": r["sn_w"],
        "prophet_tuned": r["pr_w"],
        "blend_prophet_wm8w": r["bl_w"],
    }
    champ_preds.append(pred_map.get(c_name, r["wm_w"]))
    
    # Pure val min
    best_m = min(pair_wapes, key=pair_wapes.get)
    champ_pure_preds.append(pred_map[best_m])

candidates["Champion (Current Artifact)"] = np.concatenate(champ_preds)
candidates["Champion (Pure Val Min)"] = np.concatenate(champ_pure_preds)

print("\n" + "="*70)
print(f"{'Candidate':<35} | {'Val Wkly Mean':<15} | {'Val Wkly Pooled':<15}")
print("="*70)
for name, preds in candidates.items():
    pooled = compute_wape(all_y, preds)
    # pair-level means
    idx = 0
    pair_means = []
    for r in results:
        n_w = len(r["y_w"])
        p_sub = preds[idx:idx+n_w]
        pair_means.append(compute_wape(r["y_w"], p_sub))
        idx += n_w
    mean_pair = float(np.mean(pair_means))
    print(f"{name:<35} | {mean_pair*100:>13.2f}% | {pooled*100:>13.2f}%")
print("="*70)

# Check how many pairs would pick a different model if selection used pooled-per-pair WAPE
# For a single pair, its weekly WAPE is sum(|y_w - yhat_w|) / sum(y_w), which is already the pair's pooled WAPE!
# What about daily pooled vs weekly pooled?
print("\nChecking difference between weekly pooled per pair vs daily pooled per pair...")
