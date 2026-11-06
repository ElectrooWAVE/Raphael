import json
import numpy as np
import pandas as pd
from src.evaluation.metrics import compute_wape, evaluate_forecast_multi_level

df_demand = pd.read_parquet("data/processed/demand.parquet")
df_lt = pd.read_parquet("data/processed/lead_time.parquet")
lt_means = df_lt.groupby(["material", "area"])["lead_time_days"].mean().to_dict()

with open("artifacts/metrics/champion_model_selection.json", "r") as f:
    sel_data = json.load(f)

# Extract test_eval parquet or re-run validation slice
test_eval = pd.read_parquet("artifacts/forecasts/demand_test_eval_champion.parquet")

print("Checking validation window...")
# The code used val_days = 84 ending strictly before test_days = 84:
test_days = 84
val_days = 84

# Let's inspect the actual dates in demand:
sample_pair = df_demand[(df_demand["material"] == "FOODS_2_019") & (df_demand["area"] == "California - CA_1")].sort_values("date")
total_days = len(sample_pair)
val_slice = sample_pair.iloc[-test_days-val_days : -test_days]
val_start = val_slice["date"].min()
val_end = val_slice["date"].max()
print(f"Validation Window: {val_start.strftime('%Y-%m-%d')} to {val_end.strftime('%Y-%m-%d')} ({len(val_slice)} days)")

# We have val_weekly_wapes for every pair in champion_model_selection.json!
# Let's check candidate names:
candidates = ["weekday_mean_8w", "moving_average_91d", "croston_sba", "seasonal_naive", "prophet_tuned", "blend_prophet_wm8w", "lightgbm_global"]

# (b) Mean-of-pairs validation weekly WAPE:
print("\n--- (b) Mean-of-pairs validation weekly WAPE (84-day window) ---")
for c in candidates:
    mean_val = np.mean([p["val_weekly_wapes"][c] for p in sel_data])
    print(f"  {c:<30}: {mean_val*100:.2f}%")

# Champion mean-of-pairs in current artifact:
champ_mean_val = np.mean([p["champion_val_wape"] for p in sel_data])
print(f"  {'champion (current artifact)':<30}: {champ_mean_val*100:.2f}%")

# If champion were pure minimum per pair without test fallback:
pure_min_val = np.mean([min(p["val_weekly_wapes"][c] for c in ["weekday_mean_8w", "moving_average_91d", "blend_prophet_wm8w", "croston_sba", "seasonal_naive", "prophet_tuned"]) for p in sel_data])
print(f"  {'champion (pure val min)':<30}: {pure_min_val*100:.2f}%")
