import json
import numpy as np
import pandas as pd
from collections import Counter

sel = json.load(open('artifacts/metrics/champion_model_selection.json'))
lb = json.load(open('artifacts/metrics/demand_leaderboard.json'))

print('=== LEADERBOARD VAL WAPES ===')
for row in lb['leaderboard']:
    print(f"{row['model']}: val_weekly_mean_wape = {row['val_weekly_mean_wape']*100:.2f}%, test_pooled = {row['weekly_pooled_wape']*100:.2f}%")

print('\n=== MEAN OF PER-PAIR VALIDATION WEEKLY WAPE ===')
models = list(sel[0]['val_weekly_wapes'].keys())
val_means = {m: np.mean([p['val_weekly_wapes'][m] for p in sel]) for m in models}
val_means['champion'] = np.mean([p['champion_val_wape'] for p in sel])

for k, v in val_means.items():
    print(f"  {k}: {v*100:.2f}%")

# Now let's see how many pairs were overridden by line 312:
# if test_weekly_wapes[champion_model_name] > test_weekly_wapes["weekday_mean_8w"]: champion = weekday_mean_8w
overridden = 0
pure_val_models = []
for p in sel:
    pool = ["weekday_mean_8w", "moving_average_91d", "blend_prophet_wm8w", "croston_sba", "seasonal_naive", "prophet_tuned"]
    # check stability filter
    valid = {m: p['val_weekly_wapes'][m] for m in pool if not ((p['test_weekly_wapes'][m] > 1.5 * p['val_weekly_wapes'][m]) and (p['test_weekly_wapes'][m] > 0.40))}
    if not valid:
        valid = {"weekday_mean_8w": p['val_weekly_wapes']['weekday_mean_8w']}
    v_winner = min(valid, key=valid.get)
    pure_val_models.append(v_winner)
    if v_winner != p['champion_model']:
        overridden += 1

print(f"\nPairs where test fallback changed model from pure val winner: {overridden}")
print("Pure val winner counts:", Counter(pure_val_models))
print("Actual champion counts:", Counter([p['champion_model'] for p in sel]))
