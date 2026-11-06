# rules.md: Non-negotiable rules for the coding agent

Read this file before every task. If a rule conflicts with a request, follow the rule and tell me.

## 1. Honesty and data integrity
1. NEVER invent data, metrics, dataset columns, file paths, library APIs, or results. If you don't know, write `UNKNOWN` and ask me.
2. NEVER hardcode or fake model metrics (MAPE, WAPE, RMSE, etc.). Every number shown in the UI must come from a saved file in `artifacts/` produced by a real run.
3. If a dataset is missing, stop and tell me exactly where to download it. Do not substitute synthetic data silently.
4. Synthetic data is allowed ONLY when I ask for it, and every synthetic file/chart must be labelled "Synthetic" in the file name, the metadata, and the UI.
5. Lead time, unit cost, holding cost, and ordering cost are often NOT in public datasets. If they are assumed, store them in `configs/assumptions.yaml`, mark them `assumed: true`, and show an "Assumed" badge in the UI.
6. Never claim "fully accurate". Report error against a held-out test period and compare against a naive baseline and seasonal-naive baseline.
7. If a library version or API is uncertain, check the installed version (`pip show`, `npm ls`) instead of guessing.

## 2. Token and cost discipline
1. Do not paste large files or long logs into chat. Write code to files and summarize in under 10 lines.
2. Do not re-read the whole repo every task. Read only the files you need; keep `PROGRESS.md` updated so you don't have to.
3. Long-running work (data prep, training, backtests) must be a standalone script I run in my own terminal. Do not run training inside the agent session.
4. When you hand me a script, give me: the exact command, expected runtime, and expected output files. Nothing else.

## 3. Script requirements (every script in `scripts/`)
1. Show a `tqdm` progress bar for every loop over items, folds, epochs, or files, plus a clear start/finish message with elapsed time.
2. Checkpointing: save progress after each unit of work (per SKU, per fold, per epoch) to `checkpoints/<script_name>/`. On restart, resume automatically and skip finished units. Support `--force` to restart from scratch.
3. Use `argparse` with `--config` pointing to a YAML file. No hardcoded dataset names or paths in code.
4. Seed everything (`--seed`, default 42) for reproducibility.
5. Log to console and to `logs/<script_name>_<timestamp>.log`.
6. Fail loudly with a clear message on missing files or schema mismatch. Never swallow exceptions.
7. Use the GPU when it genuinely helps (XGBoost `device="cuda"`, PyTorch models). Auto-detect and fall back to CPU with a printed warning. Never assume GPU is present.
8. Process data in vectorized pandas/polars, in chunks if memory is a concern. Use parquet, not CSV, for intermediate data.

## 4. Architecture and scalability
1. Raphael is a single-dataset project: no adapter framework, no dataset switcher. File paths, column names, `as_of_date`, and settings live in `configs/raphael.yaml`, never hardcoded. Code assumes the Raphael schema: demand (`date, material, area, quantity, is_promotion`), lead times (`material, area, order_date, order_quantity, lead_time_days`), inventory (`material, area, current_stock, last_updated`).
2. Validate the schema on every load and fail loudly on mismatch.
3. Models are pluggable via a registry (`src/models/registry.py`). Each model implements `fit`, `predict`, `save`, `load`.
4. Keep strict separation: `data/` (raw, never edited), `artifacts/` (generated), `src/` (library code), `scripts/` (entry points), `backend/` (API), `frontend/` (website).
5. Type hints and short docstrings on all public functions. No dead code, no giant files (split above ~300 lines).
6. Never commit raw data, model weights, `.env`, or secrets. Keep `.gitignore` current.

## 5. Modeling rules
1. Split by time only. Never random-split time series. No leakage: lag/rolling features must use only past data.
2. Always report baselines (naive, seasonal naive) next to every model.
3. Use rolling-origin backtesting for the final comparison.
4. Provide prediction intervals (quantile models or conformal) and report their empirical coverage.
5. Choose the best model per item or item cluster from backtest results, not by assumption.
6. Inventory formulas must cite their definitions in code comments. Safety stock uses forecast error std (not raw demand std) where possible.

## 6. Frontend rules
1. Stack: Next.js (App Router) + TypeScript + Tailwind. Animations: GSAP ScrollTrigger and/or Framer Motion, Lenis for smooth scroll.
2. Glassmorphism design system defined once as tokens (CSS variables / Tailwind theme). No one-off styles.
3. Spline 3D scenes are lazy-loaded, never block first paint, and have a static fallback image. Respect `prefers-reduced-motion`.
4. Target: Lighthouse performance 80+ on desktop, no layout shift, 60fps scroll on a mid-range laptop.
5. The UI reads only from the API. Empty or loading states must be explicit. Never show placeholder numbers that look real.
6. Accessible: keyboard navigable, sufficient contrast on glass surfaces, alt text.

## 7. Workflow
1. Work in small phases from `prompt.md`. After each phase: update `PROGRESS.md` (done / next / blockers), then stop and wait for me.
2. Before large changes, state the plan in 5 lines or fewer and wait for my OK.
3. If something is ambiguous, ask ONE concise question instead of guessing.
4. When a task fails, report the real error message. Do not claim success without evidence (output file exists, test passes).

## 8. Raphael-specific rules
1. The product name is **Raphael** in all UI text, titles, README, and API metadata.
2. Provenance disclosure everywhere (UI badge, `/meta`, methodology): demand is public M5 retail benchmark data relabelled as "materials"; lead times and current inventory are synthetic. Never call the items real raw materials, the areas Indian locations, or synthetic results real-world performance.
3. `stock_status_simulated` is NEVER used in calculations, features, alerts, or ranking. Raphael computes status itself.
4. Prophet and Random Forest do the predicting. Safety stock, reorder point, days remaining, and alerts are arithmetic. Say so in code comments and the methodology page.
5. Holiday effects use the US calendar (`holidays` / Prophet country holidays), matching the US-based demand data. Never hand-type holiday dates, never claim Indian-holiday effects, and report which horizon dates lack event coverage.
6. The Random Forest tree-spread std is reported, but safety-stock math uses the calibrated lead-time uncertainty; show both with an explanation.
7. The promotion/event simulator is labelled "Simulated" and uses precomputed uplift scenarios; never imply Prophet re-ran live if it did not. The event flag's measured effect is small; do not exaggerate it.
8. Accuracy figures in the UI come only from saved evaluation files and must name their aggregation level (daily, weekly, lead-time window). Intermittent pairs where Prophet loses to a baseline are flagged, not hidden. Forecasts and bounds are clipped at 0.
9. All dates are in the dataset's own time (as_of_date 2016-04-24). Always show the "As of" chip; never shift dates to look current.
10. The hero image in `docs/reference/` is a visual reference only: never copy its garbled text or watermark, and never ship it as an asset.
