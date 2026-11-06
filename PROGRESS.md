# Raphael Project Progress

## Current Status: Phase 6 (FastAPI Backend API) Complete

### Phase Tracking

| Phase | Description | Status | Output / Artifacts |
|---|---|---|---|
| **Phase 0** | Scaffold structure, configs, dependencies, utilities, env check | **DONE** | Scaffolding, `requirements.txt`, `configs/`, `src/utils/`, `scripts/00_check_env.py` |
| **Phase 1** | Data validation & preparation (`01_validate_prepare_data.py`) | **DONE** | Parquet files in `data/processed/`, `artifacts/data_validation_report.json` |
| **Phase 2** | Model 1: Initial Prophet baseline | **DONE** | Initial Prophet fit (`artifacts/forecasts/demand_forecasts.parquet`) |
| **Phase 2b** | Model 1: Advanced Champion Forecasting & Guardrails | **DONE** | Fleet Weekly Pooled WAPE 29.20%, `artifacts/metrics/demand_leaderboard.json` |
| **Phase 3** | Model 2: Lead-time prediction (Random Forest + calibration) | **DONE** | `artifacts/lead_time/lead_time_rf_model.pkl`, `lead_time_pair_predictions.parquet` |
| **Phase 4** | Decision layer (ROP, SS, days remaining, urgency rank) | **DONE** | `src/inventory/engine.py`, `artifacts/inventory/reorder_table.parquet` |
| **Phase 5** | Recommendations & promo scenario precomputations | **DONE** | `artifacts/recommendations.parquet`, `artifacts/promo_scenarios.parquet`, `meta.json` |
| **Phase 5b**| Empirical Interval Calibration on Validation Windows | **DONE** | 80%/95% bands for all 75 pairs; Fleet test coverage 81.19% / 94.03% |
| **Phase 6** | Backend API (FastAPI, title "Raphael API") | **DONE** | `backend/main.py`, `backend/schemas.py`, `backend/data_store.py`, `scripts/serve.ps1` |
| **Phase 7** | Frontend (Next.js 16, React 19, Tailwind v4, 3D Ribbon, Motion, Hero, Forecast Studio) | **IN PROGRESS** (Steps 1–5 Complete) | Step 1 Design Tokens, Step 2 3D Ribbon & /lab/3d, Step 3 Motion System & Shell, Step 4a Hero & Peek Cards, Step 5 Forecast Dashboard |
| **Phase 8** | Deployment scripts, local serving, README guide | **IN PROGRESS** | `scripts/serve.ps1`, `README.md` root documentation |
| **Phase 9** | (Optional) XGBoost GPU challenger model | *PENDING* | Benchmark & challenger comparison |

---

### Phase 6 Backend API Summary
1. **Architecture & Performance**:
   - Title: **Raphael API** (FastAPI 0.142.2 + Uvicorn + Pydantic v2).
   - In-memory data store (`backend/data_store.py`) loaded once at lifespan startup (< 200 KB RAM).
   - Sub-millisecond to low single-digit latency (**2.26 ms** average across all endpoints).
   - GZip response compression and configurable CORS middleware.
   - Read-only on `artifacts/` (no training, no GPU required).
2. **Endpoints Implemented & Tested**:
   - `GET /health`: Health status and artifact readiness.
   - `GET /meta`: Dataset provenance, dates, fleet dimensions, model architecture, policy assumptions.
   - `GET /materials`: List of 25 materials.
   - `GET /areas`: List of 3 areas (supports optional `?material=` filter).
   - `GET /forecast/{material}/{area}`: 60-day historical tail, 90-day future champion forecast with dual 80%/95% empirical bands, model used, accuracy, low-confidence flag, empirical promotion lift with bootstrap 95% CI.
   - `GET /reorder/{material}/{area}`: Complete decision metrics (ROP, SS, $L$, dual $\sigma_L$, planned qty, days remaining, status, assumption flags).
   - `GET /urgency`: Full 75-pair ranked table (status severity first, then days remaining); supports `?status=`, `?material=`, `?area=` filters.
   - `GET /accuracy`: Fleet competition leaderboard and per-pair accuracy metrics with explicit aggregation levels.
   - `GET /leadtime/{material}/{area}`: Random Forest lead-time predictions, dual spreads, seasonal surge (+1.34d Nov-Dec), and historical bounds.
   - `POST /whatif`: Pure arithmetic decision simulator reproducing `tests/inventory_fixtures.json` (SS, ROP, EOQ, days remaining, status, stockout probability via normal LTD model).
   - `GET /export/recommendations.csv`: Streaming CSV export with full assumption flags.
   - `GET /benchmarks`: Explicit placeholder returning `"not computed yet"` until Phase 7 benchmark script runs.
3. **Verification & Testing**:
   - `tests/test_api.py`: 12 automated unit tests passed in 0.46s (including full `/whatif` fixture reproduction and 404 validation).
   - `scripts/smoke_test_api.py`: Calls all 15 endpoints and verifies 100% ground-truth consistency against `artifacts/recommendations.parquet` for 5 random pairs.
   - `scripts/serve.ps1`: Automated PowerShell launcher.

---

### Phase 5b: Empirical Interval Calibration Summary
1. **Calibration Methodology**:
   - Zero test leakage: Residual distributions calibrated strictly on the 84-day **validation window** (days 1745–1828).
   - Conformal empirical quantiles applied symmetrically to point forecasts:
     $w_{80} = \text{percentile}(|e_{val}|, 80)$, $w_{95} = \text{percentile}(|e_{val}|, 95)$.
   - Lower bounds clipped at 0: $0 \le \text{lower}_{95} \le \text{lower}_{80} \le \hat{y} \le \text{upper}_{80} \le \text{upper}_{95}$.
   - Fallback pooling: 0 pairs required pooling (all 75 pairs had sufficient validation residuals).
2. **Held-out Test Window (Days 1829–1912) Coverage Results**:
   - **Fleet Overall**: **81.19%** (80% target) | **94.03%** (95% target)
   - **Baseline Pairs (68 pairs, empirical)**: **80.90%** (80% target) | **94.14%** (95% target)
   - **Prophet Pairs (7 pairs, native)**: **84.01%** (80% target) | **93.03%** (95% target)
   - **Mean Relative Band Width**: 2.59x mean forecast (80% band) | 3.74x mean forecast (95% band)
3. **Artifacts & API**:
   - `artifacts/forecasts/demand_forecasts_champion.parquet` and `.json` updated with `yhat_lower_80`, `yhat_upper_80`, `yhat_lower_95`, `yhat_upper_95`, `interval_method`, and `pooled_residuals`.
   - `/forecast/{material}/{area}` returns full band data and metadata flags.
   - `test_13_all_pairs_have_valid_ordered_nonnegative_bands` verifies valid, ordered, non-negative bands for all 75 pairs.

---

---

### Phase 7 Step 1: Next.js Scaffold & Design Tokens Summary
1. **Installed Stack & Dependency Audit**:
   - `next@16.3.8` (App Router, Turbopack)
   - `react@19.2.8` & `react-dom@19.2.8`
   - `tailwindcss@4.3.3` with `@tailwindcss/postcss@4.3.3`
   - `openapi-typescript@7.13.0` & `lucide-react@1.16.0`
2. **Tailwind v4 Configuration & Tokens (`frontend/app/globals.css`)**:
   - Configured natively via `@theme` directives and CSS properties.
   - Canvas: pure void black `#000000` base.
   - Glass utilities: `bg-white/[0.03]`, `backdrop-blur-2xl`, `border-white/[0.08]`, `shadow-[0_8px_32px_0_rgba(0,0,0,0.37)]`.
   - Semantic data colors: `#00F2FE` (Forecast/Prediction), `#10B981` (Healthy/OK), `#F59E0B` (Strain/REORDER), `#EF4444` (Critical/Stockout).
   - Chromatic gradients & glow utilities: `gradient-teal`, `glow-cyan-btn`, `glass-pill-nav`.
   - Typography: Geist & Geist Mono loaded via `next/font/google`.
3. **OpenAPI Schema & API Client (`frontend/lib/api.ts`)**:
   - Backend OpenAPI schema exported from live FastAPI app to `frontend/openapi.json`.
   - TypeScript definitions auto-generated to `frontend/lib/schema.d.ts` with zero hand-typed field names.
   - Full typed client supporting `/health`, `/meta`, `/materials`, `/areas`, `/forecast`, `/reorder`, `/urgency`, `/accuracy`, `/leadtime`, `/whatif`, and CSV export.
   - Explicit `ApiError` class, loading states, error states, and empty states.
4. **Verification Page (`frontend/app/page.tsx`)**:
   - Displays floating pill navbar, dual-tone gradient headline ("Know what to order, / and exactly when."), glowing buttons, and semantic data color cards.
   - Live telemetry card connects to `/health` and `/meta` displaying real-time system status, fleet dimensions, and policy defaults.
   - Production build verified: `npm run build` exits with code 0.

---

### Phase 7 Step 2: 3D Scene Architecture & Teardown Summary
1. **Installed 3D Stack & Verified React 19 Compatibility**:
   - `three@0.186.1`
   - `@types/three@0.186.0`
   - `@react-three/fiber@9.8.1` (peerDependency: `react: '>=19 <19.4'`)
   - `@react-three/drei@10.7.9` (peerDependency: `react: '^19'`)
   - `@splinetool/react-spline@4.1.0` & `@splinetool/runtime@1.9.84`
2. **Components Built & Visual Tuning**:
   - `frontend/components/3d/SplineSceneWrapper.tsx`:
     - Dynamic loading with `next/dynamic` and `ssr: false`.
     - Zero CLS: fixed-size skeleton placeholder with radial pulse.
     - Offline procedural environment: compiled via `PMREMGenerator` from cyan, magenta, violet, and amber lightformers (zero external downloads).
     - Tuned `MeshPhysicalMaterial`: `transmission: 1.0`, `thickness: 1.5`, `roughness: 0.04`, `ior: 1.46`, `dispersion: 4.5`, `iridescence: 1.0`, `iridescenceIOR: 1.6`, `iridescenceThicknessRange: [200, 900]`, `clearcoat: 1.0`, `envMapIntensity: 1.55`.
     - Backlight chromatic discs & point lights behind the knot to eliminate flat black transmission.
     - Slender fluid ribbon knot geometry: `TorusKnotGeometry(2.15, 0.20, 384, 48, 2, 3)` with scale `(1.15, 1.05, 0.85)`.
     - Camera reset and expand floating utility buttons.
     - `IntersectionObserver`: pauses render loop when off-screen.
     - `prefers-reduced-motion` and mobile (<768px): CSS radial glow + static SVG wireframe fallback.
     - Full memory teardown on unmount: geometries, materials, lights, PMREM target, and WebGL renderer context loss.
   - `frontend/components/3d/DynamicSplineScene.tsx`:
     - Clean dynamic import wrapper.
   - `frontend/app/lab/3d/page.tsx`:
     - Interactive test route `/lab/3d` featuring "Mount / Unmount" toggle.
     - Live telemetry readout of `renderer.info` (`geometries`, `textures`, `programs`, `triangles`) proving numbers return to zero upon unmount.
     - Live computed leak check: `"Leak check: geometries 0 / textures 0 / programs 0 after unmount"`.
     - Stable 60 FPS counter while mounted.

3. **Step 1 Fixes Verified**:
   - Prominent fixed/sticky floating pill navbar anchored at top center as in `hero.png`.
   - Citing `configs/assumptions.yaml`: confirmed holding cost rate is 20% (0.20), not 25%.
   - "Assumed" badge rendered next to all values originating from `assumptions.yaml`.
   - $Z$-score rounded to 3 decimals ($Z=1.645$).
   - Fleet Dimensions card subtitle on its own line.
   - Headline formatted as: "Know what to order," (white) and "and " (white) with only "exactly when." in the teal glow gradient.
   - Provenance text updated: *"Demand: M5 retail benchmark relabelled as materials. Lead times and current stock: synthetic."*

---

### Phase 7 Step 3: Motion System & Global Shell Complete
- **Installed Packages**: `lenis@1.3.26`, `gsap@3.15.0`, `framer-motion@14.0.0` (React 19.2.8 & Next.js 16.3.8 verified).
- **Smooth Scroll**: `components/motion/SmoothScrollProvider.tsx` linking Lenis to GSAP ScrollTrigger via single RAF ticker with lagSmoothing(0), respecting `prefers-reduced-motion`.
- **Route Transitions**: `components/motion/PageTransition.tsx` implementing `FrozenRoute` (LayoutRouterContext) with enter (0.35s easeOut, y: 12->0, blur: 4px->0) and exit (0.25s easeIn, y: 0->-12, blur: 0->4px).
- **Global Shell**: `components/layout/Shell.tsx`, `components/layout/Navbar.tsx` (centered floating frosted pill, real `/health` telemetry dot, dataset status chip, "Connect Data" dialog from `/meta` with no upload button, dev links only when `NODE_ENV === 'development'`), `components/layout/Footer.tsx`.
- **Motion Primitives**: `Reveal` (scroll reveals with stagger), `CountUp` (animated counters from 0 to real numeric props), `TiltCard` (3D spring cursor-tilt with specular glare).
- **Demonstration**: `/lab/motion` live with real values from `/meta` (75 pairs, 25 materials, 1,913 demand days, 20,550 historical orders).
- **Empty Shell Placeholders**: `/forecast`, `/inventory`, `/simulator`, `/telemetry`, `/methodology`.

---

### What's Next
- Step 4 / Step 5 (Landing Page / Hero integration & below-the-fold sections per prompt 6.5 & 6.6).
- Stop after Step 3 as requested.

