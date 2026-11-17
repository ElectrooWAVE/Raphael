---
description: Run all checks (tests, GPU, real Chronos-2 inference) and report real output
---
1. Run `python -c "import torch;print(torch.__version__, torch.cuda.is_available())"` and report the output.
2. Run `pytest -q` and report the output.
3. Run `python scripts/smoke_test.py` and paste the full real output (device, MAE for Chronos-2 vs baseline).
4. If anything fails, diagnose the root cause. Do not replace the model or fake a forecast.
5. Summarise: what passed, what failed, what you changed.
