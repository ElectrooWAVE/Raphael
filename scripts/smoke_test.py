"""REAL Chronos-2 test on your machine: hold out the last 28 days of a real product,
forecast them, and compare with what actually happened (and with a naive baseline).
Run:  python scripts/smoke_test.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from rdf.data_loader import get_series, load_sales
from rdf.forecaster import forecast, load_pipeline

H = 28
sales = load_sales()
for sid in ["HOUSEHOLD_1_517 | California - CA_1", "FOODS_3_080 | Texas - TX_1"]:
    s = get_series(sales, sid)
    train, actual = s.iloc[:-H], s.iloc[-H:]["sales"].to_numpy()
    pipeline, device = load_pipeline()
    f = forecast(pipeline, train, H, sid)
    assert len(f) == H and f["date"].iloc[0] == train["date"].iloc[-1] + np.timedelta64(1, "D")
    assert np.isfinite(f["median"]).all() and np.isfinite(f["expected"]).all()
    mae = np.abs(f["median"].to_numpy() - actual).mean()
    naive = np.abs(train["sales"].tail(28).mean() - actual).mean()
    print(f"[{device}] {sid}: Chronos-2 median MAE={mae:.2f}  | 28-day-mean baseline MAE={naive:.2f}  "
          f"| expected total={f['expected'].sum():.0f} vs actual={actual.sum():.0f}")
print("OK - real Chronos-2 inference works.")
