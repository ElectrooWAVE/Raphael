# prompt.md: RAPHAEL — Materials Demand Forecasting, Lead-Time Prediction & Reorder Platform

FIRST: read `rules.md` fully and obey it. Then work phase by phase. Stop after each phase and wait for my confirmation.

## 1. Product
The product name is **Raphael** (logo, page titles, metadata, README, API title, footer).
Raphael is a **single-dataset** decision tool (one dataset, no multi-dataset switching, no adapter framework). For each (material, area) pair it answers:
1. **Planning:** how much will we need? (demand forecast + confidence interval)
2. **Procurement:** how long will an order take, and how uncertain is that? (lead-time prediction + variability)
3. **Inventory:** when must we reorder, and are we already late? (reorder point, safety stock, days of stock left, alerts)
Two ML models predict; the decision layer is plain arithmetic and the UI and docs say so. College project, important: honest, reproducible, visually impressive.

## 2. My environment
- Windows PC, 32 GB DDR5, NVIDIA RTX 5060 Ti 16 GB, Python 3.11 venv, Node 20+. Everything free. Training runs locally via scripts in my terminal, never inside the agent.
- Honest compute note: Prophet and scikit-learn Random Forest are CPU work (no GPU mode). 75 series trains in minutes using all CPU cores (joblib, progress bars). Do not claim GPU acceleration for them. The GPU is optional (Phase 9 only).
- Prophet on Windows depends on cmdstanpy/CmdStan; `00_check_env.py` must fit a toy Prophet model and print the exact fix if it fails.

## 3. The dataset (provided by me; this is the ONLY dataset)
Files to place in `data/raw/` (rename from my downloads; strip any `__1_` suffix):
1. `demand_history.csv`: `date, material, area, quantity, is_promotion`
2. `lead_time_history.csv`: `material, area, order_date, order_quantity, lead_time_days`
3. `current_inventory.csv`: `material, area, current_stock, last_updated, stock_status_simulated`
4. `calendar_events_reference.csv`: `date, event_name_1, event_type_1, event_name_2, event_type_2` (reference only)

**Verified facts about these files (re-verify in `02_validate_prepare_data.py`, never assume):**
- 75 (material, area) pairs = 25 materials x 3 areas (`California - CA_1`, `Texas - TX_1`, `Wisconsin - WI_1`). Demand: 1,913 daily rows per pair, 2011-01-29 to 2016-04-24, no gaps, no missing values, no duplicates, no negatives.
- Provenance (disclose everywhere): the demand series are retail product demand from the public Walmart **M5** benchmark, relabelled as "materials" (IDs like `FOODS_3_587`, `HOBBIES_1_008`, `HOUSEHOLD_1_303`). Lead times and current inventory are **synthetic** (generated), not observed. Never call the products real raw materials or the areas Indian locations.
- Demand is intermittent: about 26% of days are zero; 29 pairs have over 30% zeros; 6 over 50%; mean about 0.6-36 units/day per pair.
- `is_promotion` has the same share (about 32.9%) for every pair and a weak average lift (about 1.06, range about 0.93-1.43). It behaves like a state-level event flag, not an item-level promotion. Describe it honestly in the UI as an "event/promotion flag" and let the measured effect speak.
- Lead time: 274 orders per pair, 2011-01-29 to 2016-04-23, mean about 5.2 days, strongly increasing with `order_quantity` within each pair (correlation about 0.89), higher in Nov-Dec (about +1.3 days), differs by area (CA about 4.2, TX about 5.2, WI about 6.3 days).
- Inventory snapshot is stamped 2016-04-24, the same day demand ends, and has a deliberate spread from critical to well-stocked.
- **`stock_status_simulated` is a label from whoever made the file. NEVER use it in any calculation, feature, or alert.** Raphael computes status itself. It may be shown only as a small "demo seed label" in a debug/methodology view.
- `calendar_events_reference.csv` contains US events (Super Bowl, Halloween, etc.). The demand data is US-based, so holiday effects use the **US** calendar, not India. No Indian-holiday claims anywhere.

**Dataset time:** all dates are in 2016. Define `as_of_date = last demand date = 2016-04-24` in `configs/raphael.yaml`. Forecasts start 2016-04-25. The UI always shows an "As of 2016-04-24 (dataset snapshot)" chip so judges are not confused by old dates. Never relabel dates to look current.

**Optional (stretch, lowest priority):** "Connect Data" can accept the same three-file schema and validate it; retraining after upload runs as a background job on the self-hosted backend only; on static/free hosting it is disabled with an honest tooltip.

## 4. Repository structure
```
raphael/
  rules.md  prompt.md  PROGRESS.md  README.md
  docs/reference/hero.png       # my Gemini hero image (visual reference only; see 6.1b)
  configs/
    raphael.yaml                # file paths, as_of_date, holiday_country=US, test_days, horizon, seeds
    assumptions.yaml            # service level, planned-order policy, holding/order cost (flagged assumed)
    models.yaml                 # prophet + random forest settings, quantiles
  data/raw/  data/processed/    # raw never edited
  src/
    data/                       # loading, validation, canonical frames
    models/                     # demand_prophet.py, leadtime_rf.py, baselines.py
    evaluation/                 # WAPE/MAPE/RMSE/MASE/bias, daily+weekly+lead-time-window accuracy, interval coverage
    inventory/                  # safety stock, ROP, EOQ, days_remaining, alerts, urgency rank
    utils/                      # checkpointing, logging, progress
  scripts/
    00_check_env.py
    01_validate_prepare_data.py
    02_train_demand_prophet.py        # per-pair checkpoints, parallel, tqdm
    03_train_leadtime_rf.py
    04_evaluate.py
    05_build_recommendations.py       # forecasts + ROP + SS + alerts -> artifacts/
    06_precompute_promo_scenarios.py
    07_benchmark.py                   # real timings for the telemetry page
  artifacts/  checkpoints/  logs/
  backend/                      # FastAPI
  frontend/                     # Next.js "Raphael" website
```

## 5. Phases

### Phase 0: Setup
Scaffold structure, `requirements.txt` (pandas, pyarrow, numpy, scipy, scikit-learn, prophet, holidays, joblib, pyyaml, tqdm, fastapi, uvicorn, pydantic, python-multipart), `.gitignore`, `PROGRESS.md`, `configs/raphael.yaml`. `00_check_env.py`: versions, CPU cores, RAM, disk, CUDA (informational), Prophet toy fit, `holidays` US availability. Utilities: checkpoint manager, tqdm helpers, logger.

### Phase 1: Data validation
`01_validate_prepare_data.py`: validate the four files against section 3 (column names, dtypes, 75 pairs consistent across files, no gaps/duplicates, date ranges, `as_of_date` equals last demand date, inventory date check). Print a short report: rows per pair, zero-demand share per pair, intermittency class (ADI/CV2), promo share, lead-time count per pair, stock cover distribution computed by Raphael. Save parquet. If anything differs from section 3, report it exactly and ask me.

### Phase 2: Model 1, Demand forecasting (Prophet) per (material, area)
- Trend, weekly + yearly seasonality, **US holiday effects** via Prophet's `add_country_holidays(country_name='US')` (do not type holiday dates by hand); optionally add the events in `calendar_events_reference.csv` as custom holidays for the history period. Report which forecast-horizon dates have no event coverage.
- `is_promotion` as an extra regressor; future frame needs a flag per day (default 0 unless a scenario says otherwise; if the flag has a deterministic pattern in the data, say so and ask me before assuming).
- Demand is count data with many zeros: clip forecasts and bounds at 0. Compare against naive and seasonal-naive baselines. If a pair is so intermittent that Prophet loses to a baseline in backtests, report it honestly and flag the pair (`model_used`, `low_confidence`); do not hide it.
- Intervals: export 80% and 95% bands.
- Held-out test: last `test_days` (config, e.g. 90) per pair. Report WAPE (primary), MAPE with zero guard, RMSE, bias, interval coverage at **three aggregation levels**: daily, weekly, and lead-time window (sum over the pair's predicted lead time), because reorder decisions use window totals. The UI headline accuracy must be computed from these files and name its level (e.g. "Weekly WAPE x% on last 90 days").
- Save per pair: future forecast with intervals, test predictions, daily residual std, regressor effect, status flags. Parallel with an overall tqdm bar; per-pair checkpoints; write `failed_pairs.json` instead of crashing.

### Phase 3: Model 2, Lead-time prediction (Random Forest)
- Features: material, area, order_quantity, month/season (Nov-Dec effect), plus calendar features derivable from `order_date`. Time-ordered train/test split.
- Output: predicted lead time (mean of trees) and variability. **Caveat:** std across trees measures tree disagreement and usually understates real variability. Report it, but calibrate the uncertainty used in decisions from held-out residuals (per area/material/season bucket or a quantile-forest approach). Show both in the telemetry page; use the calibrated one in the decision layer; explain on the methodology page.
- Evaluate with MAE, RMSE, R2, spread calibration (share of actual lead times inside mean +-1.96*calibrated std), versus a baseline of the per-pair historical mean.
- Order quantities outside the pair's historical range are extrapolations: clip or warn and show a flag in the UI.

### Phase 4: Decision layer (arithmetic, not ML; say so in code comments and UI)
Per (material, area), using `assumptions.yaml` where the data lacks inputs (flagged assumed):
- `D` = mean forecast daily demand over the lead-time window, `sigma_D` = daily forecast-error std (held-out residuals), `L` = predicted mean lead time for the planned order quantity and upcoming season, `sigma_L` = calibrated lead-time std.
- Safety stock `SS = Z * sqrt(L * sigma_D^2 + D^2 * sigma_L^2)`, `Z` = inverse normal CDF of service level (default 95%, configurable)
- Reorder point `ROP = D * L + SS`
- Planned order quantity: explicit documented policy (EOQ if costs are assumed, else cover N days of demand); handle the quantity-to-lead-time dependency without circularity (compute at the planned quantity, once).
- `days_remaining` = days until cumulative forecast demand exceeds `current_stock` (day-by-day on the forecast, not stock / average). If recent demand is zero, handle explicitly (cap at horizon, label "no demand expected").
- Status: `OK` if stock > ROP; `REORDER` if stock <= ROP; `CRITICAL` if `days_remaining` < predicted lead time. Banner text with real values ("Reorder now: X days of stock left").
- Urgency ranking: all pairs by `days_remaining` ascending (ties: status, then stock/ROP).
- Note that a normal-demand assumption is weak for low-volume intermittent pairs; flag those pairs in the UI.

### Phase 5: Artifacts and recommendations
`05_build_recommendations.py` writes forecasts, accuracy tables, lead-time predictions with both spreads, and the reorder table (ROP, SS, days_remaining, status, recommended order quantity, assumption flags, low-confidence flags) to `artifacts/`. `06_precompute_promo_scenarios.py`: per pair, forecast with the flag OFF and ON for all horizon days and store per-day uplift with intervals, so the UI can simulate a promotion over any window without running Prophet live (client composes baseline + uplift, then recomputes ROP/SS/days_remaining). Document it as an approximation, labelled "Simulated".

### Phase 6: Backend (FastAPI, title "Raphael API")
Read-only on artifacts, light compute only. Endpoints: `/materials`, `/areas?material=`, `/forecast/{material}/{area}`, `/reorder/{material}/{area}`, `/urgency`, `/accuracy`, `/leadtime/{material}/{area}`, `/whatif`, `/export/recommendations.csv`, `/meta` (dataset name, provenance, as_of_date, synthetic flags), `/benchmarks`, `/health`, and (stretch) `/upload`. CORS, pydantic models, caching.

### Phase 7: Frontend: see section 6.
### Phase 8: Deployment: see 6c. README: setup, retrain, reproduce results.
### Phase 9 (optional, only if time remains): XGBoost on GPU as a challenger model. Never replaces Prophet/RF in the reorder flow unless backtests prove it better.

## 6. Frontend specification (merged: original design brief + architecture brief)
**Role:** act as a Principal Frontend Architect and Creative Technologist. Stack: Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS, Framer Motion, GSAP ScrollTrigger, Lenis, Lucide React, Recharts (single chart library; justify in one line), `@splinetool/react-spline`, Three.js / react-three-fiber for the procedural fallback. Verify installed versions; if a Next 15 / React 19 / Tailwind API differs from what you remember, check the docs rather than guess.

### 6.1 Visual identity (merged: telemetry brief + "ultra-luxury void/chromatic glass" brief)
**Canvas:** pure black `#000000` base, minimal visual noise, so 3D lighting and glass refraction dominate. (This replaces the earlier `#08090C`. The HUD grid overlay is NOT global anymore; it appears only on `/telemetry` as a faint backdrop.)
**Glass:** floating pill-shaped nav and containers: `bg-white/[0.03]`, `backdrop-blur-2xl`, `border border-white/[0.08]`, `shadow-[0_8px_32px_0_rgba(0,0,0,0.37)]`, with hairline rim highlights. Iridescent spectral accents (violet, cyan, magenta, amber) bleeding around edges and behind hero objects.
**Semantic colors for data and status (tokens):** cyan `#00F2FE` = forecast/prediction, emerald `#10B981` = healthy/optimized, amber = strain/warning, red = stockout/critical. Chromatic gradients are for decoration and headlines, not for encoding data.
**Typography:** Inter or Geist (load with `next/font`), massive tight headlines (`tracking-[-0.03em]`, `font-medium`/`font-semibold`), dual-tone headlines (crisp white line 1, glowing teal/chromatic-gradient line 2), muted body text (`text-zinc-400`/`text-zinc-500`).
**Controls:** pill-shaped CTAs with soft interior glow and glass rim reflection; glowing HUD border pulse on the active state. Spline viewport utility buttons floating top-right of each canvas (camera reset, expand canvas); the procedural fallback must implement the same two buttons.
Everything is defined once as design tokens (CSS variables + Tailwind theme). Final palette is refined from my Spline scenes once I supply them (6b).

### 6.1b Hero visual reference (my Gemini mockup at `docs/reference/hero.png`)
View the image and match its composition and feel: pure-black void, wide floating glass pill navbar (Raphael wordmark with a small cyan dot on the left, links in the middle, "Connect Data" glass pill on the right, active link with a soft glass highlight), huge two-line headline (white line 1, teal-cyan glowing gradient on key words of line 2), muted subtitle, glowing teal-glass primary pill button next to a dark outlined secondary pill, a large iridescent liquid-glass ribbon knot on the right (violet, blue, magenta, amber refraction, cropped by the right edge), a floating glass stat pill overlapping the ribbon's lower left with a green status dot, and frosted glass cards peeking in at the bottom.
**Copy (use exactly this, not the garbled text in the image):**
- Headline: "Know what to order," / "and exactly when." (teal gradient on "exactly when.")
- Subtitle (write a real one): e.g. "Raphael forecasts demand, predicts supplier lead times, and tells you when to reorder, per material and area."
- Stat pill: live values from the API (e.g. status dot from `/health` plus the as-of date or best-model accuracy), never placeholder or invented text.
- Bottom cards: Demand model, Lead-time model, Decision layer (with real accuracy numbers from artifacts, "Not computed yet" until then).
The image has artifacts to ignore: garbled subtitle and pill text, and the small sparkle watermark at the lower right. It is a visual reference only, not an asset to ship; build everything in code with the 3D scene from 6.3/6d.

### 6.2 Motion system (roles are split to avoid conflicts)
- **Lenis** smooth scroll globally.
- **GSAP ScrollTrigger** for scroll-driven work: pinned sections, parallax layers, staggered reveals, charts that draw on viewport entry, section transitions.
- **Framer Motion** for route transitions, hover/press micro-interactions, spring-based card tilt.
- Route transitions: exit `{opacity:0, y:-12, filter:"blur(4px)", duration:0.25}`, enter `{opacity:1, y:0, filter:"blur(0px)", duration:0.35, ease:"easeOut"}`. Known caveat: `AnimatePresence mode="wait"` inside the App Router `template.tsx` often fails to play exit animations because the router swaps content immediately. Implement it with a working pattern (e.g. a frozen-router context wrapper) and test it; if it cannot be made reliable, tell me and use an enter-only transition instead of silently shipping a broken one.
- Micro-interactions: metric cards with cursor-tracking 3D tilt (springs), glowing HUD border pulse on active buttons, number counters animating from 0 to the real value on mount.
- Respect `prefers-reduced-motion` everywhere.

### 6.3 3D architecture (strict)
1. **Isolated lifecycle per route.** Each route hosts its own 3D component. No persistent canvas across routes. On unmount, dispose geometries, materials, textures, renderer, and listeners (no WebGL context or VRAM leaks). Verify by navigating between routes repeatedly and checking the context count / memory.
2. **Dynamic loading.** Every canvas is loaded with `next/dynamic` and `{ ssr: false }`, with an animated HUD skeleton / radial pulse loader at a fixed reserved size so there is zero CLS.
3. **`components/3d/SplineSceneWrapper.tsx`** accepts a Spline viewer URL via prop/env (`NEXT_PUBLIC_SPLINE_*`). If none or loading fails, it renders a procedural Three.js fallback: interactive particle cloud, rotating wireframe telemetry rings, mouse-reactive motion in the same style as my reference scenes.
4. **Performance.** `IntersectionObserver` pauses or throttles the render loop off-screen. Below 768px or with reduced motion: replace the canvas with a CSS radial glow + SVG blueprint wireframe. Cap devicePixelRatio. Lazy-load below-the-fold scenes.
5. Per-route scene theme (each is its own isolated component):
   - `/` Landing: fluid iridescent liquid-glass / chromatic wave ribbon curving through the right side, smooth organic morphing with spectral refraction.
   - `/forecast`: sweeping spectral ribbon curves suggesting multi-horizon time-series flow (can subtly react to the selected item's forecast shape, if cheap).
   - `/simulator`: dark tactile geometric sphere / lattice cluster with cyan/teal rim lighting; reacts to mouse hover AND to the live risk state (calm/green, strained/amber, critical/red) and parameter changes.
   - `/telemetry`: precision holographic silicon substrate / wireframe node cluster (also acceptable: rotating die).
   - `/methodology`: no 3D (static glow only).
6. Mobile (<768px) hides heavy canvases and shows a CSS gradient radial glow. Procedural fallbacks use chromatic fluid-style materials (e.g. custom shader or physical material with iridescence) for the ribbon scenes and dark metallic lattice for the sphere scene.

### 6.4 DATA INTEGRITY RULE FOR THE UI (overrides any example numbers)
Any number in this spec, such as an RMSSE score, "-34.2% stockout reduction", "30,490 SKUs", "1.8ms latency", "1.4ms GPU inference", or specific benchmark results, is an EXAMPLE of a slot, not a value. Never hardcode them. Every figure must come from the API / `artifacts/`. If a value does not exist yet, render an explicit "Not computed yet" state. "System: Online" reflects the real `/health` response. Event pins (Monsoon Dip, Diwali, Promo Week) come only from the holiday/event calendar or detected data, never invented. Model toggles show only models that exist in the leaderboard artifact. Latency and GPU-vs-CPU comparisons come from a real benchmark run (`scripts/08_benchmark.py`) on my actual hardware, with the detected GPU/CPU names shown, not assumed.

### 6.5 Routes (product name everywhere: **Raphael**)
**Global layout:** centered floating pill navbar (see 6.1b): "Raphael" wordmark with a pulse dot (real `/health`), links `Overview`, `Forecast`, `Inventory`, `Simulator`, `Telemetry` (+ `Methodology`), a status chip with the "As of 2016-04-24" dataset-snapshot date and a "Retail benchmark data + synthetic lead times/stock" badge, and the right glass pill **"Connect Data"**. Since there is one dataset, "Connect Data" opens a data-source dialog: dataset provenance (from `/meta`), row counts, date range, what is synthetic, and (stretch, self-hosted only) a same-schema CSV upload; no dead buttons. Route transitions per 6.2.

1. **`/` Overview.** Hero per 6.1b (split 55/45, 3D ribbon right). CTAs: "Launch Studio" (-> `/forecast`), "Open Inventory" (-> `/inventory`). Below the fold: scroll-driven "How it works" pinned story (Data -> Demand model -> Lead-time model -> Reorder decision); 3 glass cards (Demand model, Lead-time model, Decision layer, each with its real accuracy and the honest ML-vs-arithmetic label); live KPI ticker (demand weekly WAPE vs baseline, lead-time MAE, count of pairs at REORDER/CRITICAL, API latency); feature highlights; footer CTA.
2. **`/forecast` Forecast (main dashboard).** Material dropdown and Area dropdown (changing either reloads forecast and reorder calc for that pair). Interval toggle 80%/95%. Chart: history solid, forecast dashed cyan glow, translucent band, holiday/event markers from real data. Accuracy badge from saved evaluation files naming its aggregation level, plus an actual-vs-predicted toggle on the held-out window. Low-confidence flag for very intermittent pairs. **Reorder panel:** ROP, SS, predicted lead time (calibrated std and tree-spread std in a tooltip), days remaining, current stock, status. **Reorder alert banner** ("Reorder now: X days of stock left"; CRITICAL stronger). **Promotion/event simulator:** toggle + window start/length; forecast, band, ROP, SS, days remaining update live from precomputed uplift, labelled "Simulated" (and honest that the measured effect for this pair may be small). Small 3D accent.
3. **`/inventory` Inventory.** Urgency table of all 75 pairs ranked by days remaining ascending: status chip, stock, ROP, SS, lead time, recommended order qty, low-confidence flag; sort/filter by status, material, area; row click opens that pair in `/forecast`. Summary strip (counts OK/REORDER/CRITICAL). Alert banner for CRITICAL items. **Export CSV** of the current (filtered) recommendations including assumption flags.
4. **`/simulator` Scenario simulator.** Three columns: parameters (lead time override, lead-time variability, service level 85%-99.5%, demand shock -30%..+30%, holding/order cost, current stock), center 3D sphere/lattice reacting to risk state, live outputs (SS, ROP, EOQ, stockout probability via the normal lead-time-demand model with the assumption stated, working capital, days of cover, cost-vs-service curve). Client math identical to `src/inventory` (shared fixture test).
5. **`/telemetry` Model telemetry.** Demand-model accuracy table per pair (WAPE at daily/weekly/lead-time-window levels, bias, interval coverage vs baselines), worst pairs listed honestly; lead-time model metrics and spread calibration (tree-spread vs calibrated); training times and benchmarks from `07_benchmark.py` on detected hardware. HUD grid backdrop only here.
6. **`/methodology`.** What is ML (Prophet, Random Forest) vs arithmetic (SS, ROP, days remaining); formulas; assumptions with "Assumed" badges; full data provenance (M5 retail demand relabelled; synthetic lead times and stock; US holidays; weak event-flag effect); limitations (intermittent demand, RF tree-spread understates variability, normal-demand assumption, 2016 dataset dates).

### 6.6 Build order for Phase 7 (stop and wait after each step; do not dump everything in one response)
1. Design tokens: `tailwind.config.ts` (void-black base, glass utilities, chromatic text gradients, semantic data colors), globals, fonts via `next/font`, telemetry-only HUD grid utility.
2. `components/3d/SplineSceneWrapper.tsx` (dynamic loader, skeleton, fallback scene, full teardown).
3. `components/motion/PageTransition.tsx` (working route wrapper) + Lenis/GSAP provider.
4. `components/layout/Navbar.tsx` (floating frosted pill, telemetry dot from `/health`, links, status chip, "Connect Data" -> data-source dialog).
5. Landing page.
6. Inventory simulator with live math + shared test.
7. Forecast explorer.
8. Telemetry page (needs benchmark artifacts) and methodology page.
9. Offline snapshot fallback (6c), Lighthouse and 3D leak checks.
   Page order inside steps 5-8: Overview, Forecast (dashboard + promo simulator), Inventory (urgency table + CSV export), Simulator, Telemetry, Methodology.
Deliver complete working code per step, no placeholder logic. If something needs data that does not exist yet, build the real empty state instead of fake numbers.

## 6b. Spline / 3D workflow
My liked aspects of the three reference scenes: the 3D object, the colors, the motion. Community links are not directly embeddable. I will open each scene, duplicate it into my own Spline account, and export a viewer URL (or `.splinecode`). Wait for me to provide those URLs; until then use placeholders clearly marked as placeholders, and a static fallback. Do NOT guess what the scenes contain. Derive the color palette from the scenes once I describe or screenshot them.

## 6c. Hosting plan
- Default: frontend on Vercel (free), backend on Render/Hugging Face Spaces (free, cold starts).
- Preferred if possible: backend self-hosted on my PC, exposed with a free tunnel (Tailscale Funnel for a stable URL, or Cloudflare Tunnel). Provide a step-by-step guide, a `scripts/serve.ps1` that starts uvicorn, and a Windows startup option. The PC must be on for the site to work.
- Resilience: the frontend must detect API downtime and fall back to bundled static JSON snapshots (read-only mode with a visible "offline snapshot" badge), so the site never looks broken.

## 7. Output format for every phase
1. Files created/changed (list only).
2. The exact command(s) I must run, expected runtime, expected output files.
3. What to verify.
4. Updated `PROGRESS.md`. Then STOP.

Begin with Phase 0 only.
