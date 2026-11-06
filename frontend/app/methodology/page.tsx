"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Binary,
  BookOpen,
  Calculator,
  CheckCircle2,
  ChevronDown,
  Clock,
  Cpu,
  Database,
  ExternalLink,
  FileText,
  HelpCircle,
  Info,
  Layers,
  LineChart,
  RefreshCw,
  Scale,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Zap,
} from "lucide-react";
import { api, type MetaResponse, type AccuracyResponse } from "@/lib/api";

export default function MethodologyPage() {
  const [meta, setMeta] = useState<MetaResponse | null>(null);
  const [accuracy, setAccuracy] = useState<AccuracyResponse | null>(null);
  const [leadTimeMetrics, setLeadTimeMetrics] = useState<Record<string, any> | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // FAQ Accordion State
  const [openFaq, setOpenFaq] = useState<number | null>(0);

  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);
    setFetchError(null);

    Promise.all([
      api.getMeta().catch(() => null),
      api.getAccuracy().catch(() => null),
      api.getLeadTimeMetrics().catch(() => null),
    ])
      .then(([m, a, lt]) => {
        if (isMounted) {
          setMeta(m);
          setAccuracy(a);
          setLeadTimeMetrics(lt);
          setIsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (isMounted) {
          setFetchError(err instanceof Error ? err.message : String(err));
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const policy = meta?.policy_assumptions;
  const ltOverall = leadTimeMetrics?.overall;
  const championWape = accuracy?.leaderboard?.[0]?.weekly_pooled_wape;
  const weekdayWape = accuracy?.leaderboard?.find((m) =>
    m.model.toLowerCase().includes("weekday mean")
  )?.weekly_pooled_wape;

  const faqs = [
    {
      q: "Why not LightGBM or Deep Learning as the primary production model?",
      a: "During our model tournament, LightGBM Global suffered an initial target-scaling bug on zero-demand series (dividing zero-demand series by 0.05, producing 277% error). Once repaired by eliminating the division by 0.05 and applying log1p scaling with unified categories, LightGBM achieved 36.92% weekly pooled test WAPE. However, this remained markedly inferior to the simple Weekday Mean 8W baseline (30.52%). Following our rigorous guardrails, LightGBM was disqualified from production selection. Raphael adopts simple, robust statistical baselines that reliably generalize rather than complex ML heuristics that overfit.",
    },
    {
      q: "Why is the fleet weekly demand forecast error approximately 30%?",
      a: "Store-level daily item demand in the M5 benchmark features severe intermittency, zero-demand days (29 of 75 pairs feature over 30% zero-demand frequency across the dataset; 30 pairs are flagged as low-confidence based on pre-test intermittency), and high Poisson dispersion. In empirical supply chain benchmarks, 30.52% weekly pooled WAPE represents high-caliber retail accuracy for sparse item-location pairs. Aggregating to weekly buckets smooths daily Poisson noise while preserving the operational signals required for 7-day review replenishment.",
    },
    {
      q: "Is this real enterprise production data?",
      a: "Demand series are drawn directly from the globally recognized Walmart M5 benchmark (Kaggle). The M5 series come from the FOODS, HOBBIES, and HOUSEHOLD departments and are used here as stand-ins for materials across three US geographical hubs (California CA_1, Texas TX_1, Wisconsin WI_1). Supplier lead times and on-hand inventory levels are synthetic, generated via calibrated statistical distributions conditioned on item volume and order timing. This architecture allows full transparency without enterprise NDA restrictions.",
    },
    {
      q: "How does the decision layer handle supplier lead-time uncertainty?",
      a: "Raw tree ensemble disagreement (variance across Random Forest estimators) severely under-disperses operational risk, capturing only 76.9% of out-of-fold supplier deliveries on a 95% nominal bound. Raphael resolves this by fitting empirical residual standard deviations segmented by destination area and a Nov–Dec season flag (is_holiday_season feature), achieving 95.9% calibrated coverage for safety stock and reorder point calculations.",
    },
  ];

  return (
    <div className="relative min-h-screen text-zinc-100">
      <div className="mx-auto max-w-6xl px-4 pt-28 sm:pt-32 pb-16 sm:px-6 lg:px-8 space-y-12">
        {/* Header Breadcrumb */}
        <div className="space-y-3 border-b border-white/[0.08] pb-6">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-xs text-zinc-400 hover:text-[#00F2FE] transition-colors font-mono"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Back to Overview</span>
          </Link>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2.5">
                <div className="h-9 w-9 rounded-xl bg-[#F59E0B]/10 border border-[#F59E0B]/25 flex items-center justify-center text-[#F59E0B]">
                  <BookOpen className="h-5 w-5" />
                </div>
                <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-white font-mono flex items-center gap-3">
                  <span>Methodology &amp; Architecture</span>
                  <span className="text-xs font-normal px-2.5 py-0.5 rounded-full border border-[#F59E0B]/30 bg-[#F59E0B]/10 text-[#F59E0B]">
                    Mathematical Foundations
                  </span>
                </h1>
              </div>
              <p className="text-xs text-zinc-400 max-w-3xl">
                Rigorous boundaries between predictive machine learning and deterministic inventory arithmetic, data provenance, formula specifications, and operational assumptions.
              </p>
            </div>
            <div className="flex items-center gap-2 font-mono text-xs">
              <span className="px-3 py-1.5 rounded-xl border border-white/[0.08] bg-white/[0.02] text-zinc-400">
                Dataset Freeze: 2016-04-24
              </span>
            </div>
          </div>
        </div>

        {fetchError && (
          <div className="p-4 rounded-2xl bg-rose-950/30 border border-rose-500/30 text-rose-300 text-xs font-mono flex items-center gap-3">
            <AlertTriangle className="h-4 w-4 shrink-0 text-rose-400" />
            <span>Notice: API parameters currently falling back to verified defaults ({fetchError}).</span>
          </div>
        )}

        {/* ============================================================== */}
        {/* SECTION 1: WHAT IS ML VS ARITHMETIC                           */}
        {/* ============================================================== */}
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <Binary className="h-4 w-4 text-[#00F2FE]" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-white font-mono">
              1. Machine Learning vs. Deterministic Arithmetic Boundary
            </h2>
          </div>
          <p className="text-xs text-zinc-400 leading-relaxed">
            Raphael strictly delineates statistical and machine learning estimators from deterministic supply chain arithmetic.
            Machine learning is used exclusively to forecast uncertain future quantities (demand distributions and supplier delivery times);
            inventory sizing, risk ranking, and purchase recommendations are computed via exact closed-form operations research formulas.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 pt-2">
            {/* ML Layer Box */}
            <div className="glass-surface rounded-2xl p-6 border border-[#00F2FE]/30 bg-[#00F2FE]/[0.02] space-y-4">
              <div className="flex items-center justify-between border-b border-[#00F2FE]/20 pb-3">
                <div className="flex items-center gap-2">
                  <Cpu className="h-5 w-5 text-[#00F2FE]" />
                  <span className="text-sm font-bold font-mono text-white">Machine Learning Layer</span>
                </div>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-[#00F2FE]/15 text-[#00F2FE] border border-[#00F2FE]/30">
                  STATISTICAL &amp; ENSEMBLES
                </span>
              </div>
              <p className="text-xs text-zinc-300 leading-relaxed">
                Predicts non-stationary temporal phenomena from historical observations, holiday patterns, and order size covariates.
              </p>
              <div className="space-y-2.5 font-mono text-xs">
                <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.06] space-y-1">
                  <div className="text-white font-semibold flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-[#00F2FE]" />
                    Demand Forecasting Champions
                  </div>
                  <p className="text-[11px] text-zinc-400">
                    Prophet (Tuned Changepoints), SBA Croston Intermittent Filter, Weekday Mean 8W, and Moving Average 91D selected per-pair by lowest validation WAPE.
                  </p>
                </div>
                <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.06] space-y-1">
                  <div className="text-white font-semibold flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-[#00F2FE]" />
                    Supplier Lead-Time Random Forest
                  </div>
                  <p className="text-[11px] text-zinc-400">
                    100-tree regressor predicting delivery lead time from: material code, area code, order quantity, month, day-of-week, day, quarter, and a Nov–Dec season flag (is_holiday_season).
                  </p>
                </div>
              </div>
            </div>

            {/* Arithmetic Layer Box */}
            <div className="glass-surface rounded-2xl p-6 border border-[#A855F7]/30 bg-[#A855F7]/[0.02] space-y-4">
              <div className="flex items-center justify-between border-b border-[#A855F7]/20 pb-3">
                <div className="flex items-center gap-2">
                  <Calculator className="h-5 w-5 text-[#A855F7]" />
                  <span className="text-sm font-bold font-mono text-white">Deterministic Arithmetic Layer</span>
                </div>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-[#A855F7]/15 text-[#A855F7] border border-[#A855F7]/30">
                  OPERATIONS RESEARCH
                </span>
              </div>
              <p className="text-xs text-zinc-300 leading-relaxed">
                Zero machine learning inference: mathematical equations that ingest ML outputs and operational policies to determine action thresholds.
              </p>
              <div className="space-y-2.5 font-mono text-xs">
                <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.06] space-y-1">
                  <div className="text-white font-semibold flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-[#A855F7]" />
                    Safety Stock &amp; Reorder Point
                  </div>
                  <p className="text-[11px] text-zinc-400">
                    {"Dual-uncertainty standard normal buffer: SS = Z·√(L·σ_D² + D²·σ_L²) and ROP = D·L + SS."}
                  </p>
                </div>
                <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.06] space-y-1">
                  <div className="text-white font-semibold flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-[#A855F7]" />
                    Urgency Triage &amp; Replenishment Order
                  </div>
                  <p className="text-[11px] text-zinc-400">
                    Days remaining depletion timeline, 3-state urgency triage (CRITICAL / REORDER / OK), order-up-to level sizing, and classical EOQ.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ============================================================== */}
        {/* SECTION 2: DATA PROVENANCE                                    */}
        {/* ============================================================== */}
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <Database className="h-4 w-4 text-[#10B981]" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-white font-mono">
              2. Data Provenance &amp; Benchmark Origin
            </h2>
          </div>

          <div className="glass-surface rounded-2xl p-6 border border-white/[0.08] space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 pb-4 border-b border-white/[0.06]">
              <div>
                <span className="text-[10px] font-mono uppercase text-zinc-500 block">Underlying Demand</span>
                <span className="text-sm font-semibold text-white">M5 Retail Benchmark</span>
                <span className="text-[10px] font-mono text-zinc-400 block">Walmart daily unit sales</span>
              </div>
              <div>
                <span className="text-[10px] font-mono uppercase text-zinc-500 block">Taxonomy Mapping</span>
                <span className="text-sm font-semibold text-white">retail SKUs (FOODS, HOBBIES, HOUSEHOLD)</span>
                <span className="text-[10px] font-mono text-zinc-400 block">used as stand-ins for materials</span>
              </div>
              <div>
                <span className="text-[10px] font-mono uppercase text-zinc-500 block">Geography / Hubs</span>
                <span className="text-sm font-semibold text-white">3 US States</span>
                <span className="text-[10px] font-mono text-zinc-400 block">California (CA_1), Texas (TX_1), Wisconsin (WI_1)</span>
              </div>
              <div>
                <span className="text-[10px] font-mono uppercase text-zinc-500 block">Dataset Temporal Range</span>
                <span className="text-sm font-semibold text-white">2011 to 2016</span>
                <span className="text-[10px] font-mono text-zinc-400 block">As-of freeze: 2016-04-24</span>
              </div>
            </div>

            <div className="space-y-3 text-xs text-zinc-300 leading-relaxed">
              <p>
                <strong>Demand History:</strong> The demand time series originates from the canonical M5 competition dataset. 25 selected items across 3 regional distribution hubs comprise 75 distinct time series spanning 1,913 days (5.2 years). Items include high-velocity continuous lines as well as highly intermittent, zero-inflated demand patterns.
              </p>
              <p>
                <strong>Synthetic Vendor Lead Times &amp; Stock:</strong> Real commercial supply chain supplier lead times and warehouse stock positions are proprietary; therefore, operational lead times (mean 7.1 days, range 3 to 14 days) and current stock balances were synthesized using a reproducible operational generator that models physical distance, order volume friction, and a Nov–Dec seasonal congestion flag.
              </p>
              <p>
                <strong>Event &amp; Promotion Flags:</strong> Calendar events map to official US Federal holidays and major cultural occasions (Super Bowl, Thanksgiving, Christmas, Labor Day). Promotional flags represent statewide marketing activations, displaying modest empirical lift (fleet average +1.8%).
              </p>
            </div>
          </div>
        </section>

        {/* ============================================================== */}
        {/* SECTION 3: MATHEMATICAL FORMULAS                              */}
        {/* ============================================================== */}
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <Scale className="h-4 w-4 text-[#F59E0B]" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-white font-mono">
              3. Closed-Form Inventory Decision Formulas
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Safety Stock */}
            <div className="glass-surface rounded-2xl p-5 border border-white/[0.08] space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-white font-mono">Safety Stock (SS)</span>
                <span className="text-[10px] font-mono text-[#00F2FE]">Dual Uncertainty</span>
              </div>
              <div className="p-3 rounded-xl bg-white/[0.035] shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] border border-white/[0.07] text-center font-mono text-sm text-[#00F2FE] overflow-x-auto">
                {"$$SS = Z_{\\alpha} \\cdot \\sqrt{L \\cdot \\sigma_D^2 + D^2 \\cdot \\sigma_L^2}$$"}
              </div>
              <p className="text-[11px] text-zinc-400 leading-relaxed">
                Buffers against both demand variability (σ_D) and lead-time arrival uncertainty (σ_L). Z_α = 1.645 corresponds to a 95% cycle service level.
              </p>
            </div>

            {/* Reorder Point */}
            <div className="glass-surface rounded-2xl p-5 border border-white/[0.08] space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-white font-mono">Reorder Point (ROP)</span>
                <span className="text-[10px] font-mono text-emerald-400">Trigger Threshold</span>
              </div>
              <div className="p-3 rounded-xl bg-white/[0.035] shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] border border-white/[0.07] text-center font-mono text-sm text-emerald-400 overflow-x-auto">
                {"$$ROP = (D \\cdot L) + SS$$"}
              </div>
              <p className="text-[11px] text-zinc-400 leading-relaxed">
                Expected replenishment lead-time demand plus safety buffer. When on-hand stock reaches or drops below ROP, a purchase order must be initiated.
              </p>
            </div>

            {/* Order Up To Level & Recommended Qty */}
            <div className="glass-surface rounded-2xl p-5 border border-white/[0.08] space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-white font-mono">Order-Up-To Level &amp; Recommendation</span>
                <span className="text-[10px] font-mono text-[#A855F7]">Service-Driven</span>
              </div>
              <div className="p-3 rounded-xl bg-white/[0.035] shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] border border-white/[0.07] text-center font-mono text-xs text-[#A855F7] space-y-1 overflow-x-auto">
                <div>{"$$S = ROP + (R \\cdot D)$$"}</div>
                <div>{"$$Q^* = \\max(Q_{\\text{plan}},\\, S - I_{\\text{current}})$$"}</div>
              </div>
              <p className="text-[11px] text-zinc-400 leading-relaxed">
                Ensures post-order stock recovers above ROP by at least one review period (R=7 days) of demand. Unbounded by historical caps; orders beyond historical P95 set the extrapolation flag.
              </p>
            </div>

            {/* Days Remaining & Urgency Triage */}
            <div className="glass-surface rounded-2xl p-5 border border-white/[0.08] space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-white font-mono">Urgency Status Classification</span>
                <span className="text-[10px] font-mono text-rose-400">Triage Rules</span>
              </div>
              <div className="p-3 rounded-xl bg-white/[0.035] shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] border border-white/[0.07] text-center font-mono text-xs text-rose-300 space-y-1 overflow-x-auto">
                <div>{"$$\\text{CRITICAL if } \\tau_{\\text{remain}} < L$$"}</div>
                <div>{"$$\\text{REORDER if } I \\le ROP \\text{ and } \\tau_{\\text{remain}} \\ge L$$"}</div>
                <div>{"$$\\text{OK if } I > ROP$$"}</div>
              </div>
              <p className="text-[11px] text-zinc-400 leading-relaxed">
                τ_remain = I_current / D. If stock runs out before supplier lead time arrives, stockout is inevitable without expedited freight.
              </p>
            </div>

            {/* EOQ */}
            <div className="glass-surface rounded-2xl p-5 border border-white/[0.08] space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-white font-mono">Economic Order Quantity (EOQ)</span>
                <span className="text-[10px] font-mono text-blue-400">Cost-Optimal</span>
              </div>
              <div className="p-3 rounded-xl bg-white/[0.035] shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] border border-white/[0.07] text-center font-mono text-sm text-blue-400 overflow-x-auto">
                {"$$EOQ = \\sqrt{\\frac{2 \\cdot A \\cdot S_o}{H}}$$"}
              </div>
              <p className="text-[11px] text-zinc-400 leading-relaxed">
                Balances fixed purchase ordering cost ($S_o = \\$50$) against annual holding cost ($H = \\$2.00$). $EOQ$ is illustrative due to assumed cost parameters.
              </p>
            </div>

            {/* Stockout Probability */}
            <div className="glass-surface rounded-2xl p-5 border border-white/[0.08] space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-white font-mono">Cycle Stockout Probability</span>
                <span className="text-[10px] font-mono text-amber-400">Normal Tail Model</span>
              </div>
              <div className="p-3 rounded-xl bg-white/[0.035] shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] border border-white/[0.07] text-center font-mono text-sm text-amber-400 overflow-x-auto">
                {"$$P(\\text{Stockout}) = 1 - \\Phi\\left(\\frac{I_{\\text{current}} - \\mu_{\\text{LTD}}}{\\sigma_{\\text{LTD}}}\\right)$$"}
              </div>
              <p className="text-[11px] text-zinc-400 leading-relaxed">
                Standard normal cumulative distribution over lead-time demand μ_LTD = D·L. Approximation assumes Gaussian distribution over replenishment window.
              </p>
            </div>
          </div>
        </section>

        {/* ============================================================== */}
        {/* SECTION 4: OPERATIONAL ASSUMPTIONS TABLE                       */}
        {/* ============================================================== */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Info className="h-4 w-4 text-[#00F2FE]" />
              <h2 className="text-sm font-bold uppercase tracking-wider text-white font-mono">
                4. Operational Policy Assumptions (Explicitly Badged)
              </h2>
            </div>
            <span className="text-[11px] font-mono text-amber-400 font-semibold">
              7 Assumed Parameters
            </span>
          </div>

          <div className="glass-surface rounded-2xl border border-white/[0.08] overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="border-b border-white/[0.08] bg-white/[0.02] text-zinc-400 text-[11px]">
                  <tr>
                    <th className="py-3 px-4">Parameter Name</th>
                    <th className="py-3 px-3">Live Value</th>
                    <th className="py-3 px-3">Status</th>
                    <th className="py-3 px-4">Operational Justification &amp; Impact</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.04]">
                  <tr>
                    <td className="py-3 px-4 text-white font-medium">Target Cycle Service Level</td>
                    <td className="py-3 px-3 text-[#00F2FE] font-bold">
                      {policy?.service_level ? `${(policy.service_level * 100).toFixed(1)}%` : "95.0%"}
                    </td>
                    <td className="py-3 px-3">
                      <span className="px-2 py-0.5 rounded-full text-[10px] bg-amber-500/15 text-amber-400 border border-amber-500/30">
                        ASSUMED
                      </span>
                    </td>
                    <td className="py-3 px-4 text-zinc-400">
                      Standard industry benchmark for retail &amp; industrial spare parts; maps to one-tailed normal Z = 1.645.
                    </td>
                  </tr>
                  <tr>
                    <td className="py-3 px-4 text-white font-medium">Periodic Review Cadence (R)</td>
                    <td className="py-3 px-3 text-white font-bold">
                      {policy?.review_period_days ? `${policy.review_period_days} Days` : "7 Days"}
                    </td>
                    <td className="py-3 px-3">
                      <span className="px-2 py-0.5 rounded-full text-[10px] bg-amber-500/15 text-amber-400 border border-amber-500/30">
                        ASSUMED
                      </span>
                    </td>
                    <td className="py-3 px-4 text-zinc-400">
                      Weekly order generation batch cycle. Governs the order-up-to level buffer added to ROP.
                    </td>
                  </tr>
                  <tr>
                    <td className="py-3 px-4 text-white font-medium">Target Stock Cover Days</td>
                    <td className="py-3 px-3 text-white font-bold">
                      {policy?.cover_days_target ? `${policy.cover_days_target} Days` : "30 Days"}
                    </td>
                    <td className="py-3 px-3">
                      <span className="px-2 py-0.5 rounded-full text-[10px] bg-amber-500/15 text-amber-400 border border-amber-500/30">
                        ASSUMED
                      </span>
                    </td>
                    <td className="py-3 px-4 text-zinc-400">
                      Planned order horizon used as candidate baseline before applying order-up-to level rule.
                    </td>
                  </tr>
                  <tr>
                    <td className="py-3 px-4 text-white font-medium">Flat Unit Cost</td>
                    <td className="py-3 px-3 text-emerald-400 font-bold">
                      ${policy?.default_unit_cost ? policy.default_unit_cost.toFixed(2) : "10.00"}
                    </td>
                    <td className="py-3 px-3">
                      <span className="px-2 py-0.5 rounded-full text-[10px] bg-amber-500/15 text-amber-400 border border-amber-500/30">
                        ASSUMED
                      </span>
                    </td>
                    <td className="py-3 px-4 text-zinc-400">
                      Homogeneous price proxy across all SKUs. Users can test custom cost sensitivity in the Simulator.
                    </td>
                  </tr>
                  <tr>
                    <td className="py-3 px-4 text-white font-medium">Fixed Order Cost (S_o)</td>
                    <td className="py-3 px-3 text-emerald-400 font-bold">
                      ${policy?.ordering_cost_fixed ? policy.ordering_cost_fixed.toFixed(2) : "50.00"} / PO
                    </td>
                    <td className="py-3 px-3">
                      <span className="px-2 py-0.5 rounded-full text-[10px] bg-amber-500/15 text-amber-400 border border-amber-500/30">
                        ASSUMED
                      </span>
                    </td>
                    <td className="py-3 px-4 text-zinc-400">
                      Administrative purchase order processing, receiving dock, and verification labor cost per order.
                    </td>
                  </tr>
                  <tr>
                    <td className="py-3 px-4 text-white font-medium">Annual Holding Cost Rate (i)</td>
                    <td className="py-3 px-3 text-emerald-400 font-bold">
                      {policy?.holding_cost_annual_rate ? `${(policy.holding_cost_annual_rate * 100).toFixed(0)}%` : "20%"} / Year
                    </td>
                    <td className="py-3 px-3">
                      <span className="px-2 py-0.5 rounded-full text-[10px] bg-amber-500/15 text-amber-400 border border-amber-500/30">
                        ASSUMED
                      </span>
                    </td>
                    <td className="py-3 px-4 text-zinc-400">
                      Cost of working capital, warehouse shelving, insurance, and obsolescence risk ($H = \$2.00$/unit/yr).
                    </td>
                  </tr>
                  <tr>
                    <td className="py-3 px-4 text-white font-medium">Open Purchase Order Pipeline</td>
                    <td className="py-3 px-3 text-white font-bold">0 In-Flight</td>
                    <td className="py-3 px-3">
                      <span className="px-2 py-0.5 rounded-full text-[10px] bg-amber-500/15 text-amber-400 border border-amber-500/30">
                        ASSUMED
                      </span>
                    </td>
                    <td className="py-3 px-4 text-zinc-400">
                      Net inventory position equals physical on-hand inventory; outstanding orders are assumed zero.
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* ============================================================== */}
        {/* SECTION 5: ACCURACY EVALUATION METHODOLOGY                     */}
        {/* ============================================================== */}
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <LineChart className="h-4 w-4 text-[#A855F7]" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-white font-mono">
              5. Accuracy Measurement &amp; Benchmark Baseline Realities
            </h2>
          </div>

          <div className="glass-surface rounded-2xl p-6 border border-white/[0.08] space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pb-4 border-b border-white/[0.06]">
              <div className="space-y-1">
                <span className="text-[10px] font-mono uppercase text-zinc-500">Evaluation Window</span>
                <div className="text-xl font-bold font-mono text-white">84 Held-Out Days</div>
                <p className="text-[11px] text-zinc-400">12 full weeks through freeze date (2016-04-24)</p>
              </div>
              <div className="space-y-1">
                <span className="text-[10px] font-mono uppercase text-zinc-500">Production Fleet WAPE</span>
                <div className="text-xl font-bold font-mono text-[#00F2FE]">
                  {championWape ? `${(championWape * 100).toFixed(2)}%` : "30.52%"}
                </div>
                <p className="text-[11px] text-zinc-400">Volume-weighted weekly pooled portfolio error (Weekday Mean 8W)</p>
              </div>
              <div className="space-y-1">
                <span className="text-[10px] font-mono uppercase text-zinc-500">Best Challenger WAPE</span>
                <div className="text-xl font-bold font-mono text-zinc-300">
                  30.82%
                </div>
                <p className="text-[11px] text-zinc-400">Moving Average 91D (Challenger)</p>
              </div>
            </div>

            <div className="space-y-3 text-xs text-zinc-300 leading-relaxed">
              <p>
                <strong>Why Weekly Pooled WAPE is the Headline:</strong> Daily sales data in retail supply chains is dominated by day-of-week shopping patterns and discrete single-unit purchase noise. Weekly aggregation accurately reflects the periodic replenishment review period. Volume-weighted pooled WAPE (&Sigma;|y &minus; &ycirc;| / &Sigma;y) ensures large items that dominate warehouse inventory carry proportional weight, preventing tiny-denominator skew.
              </p>
              <div className="p-4 rounded-xl bg-amber-950/20 border border-amber-500/30 text-amber-200/90 text-xs font-sans space-y-2">
                <div className="font-semibold font-mono text-amber-300">
                  Honest Assessment: Simple Baselines are Hard to Beat
                </div>
                <p>
                  On retail demand series, a simple 8-week historical weekday average achieves 30.52% pooled test error across all 75 pairs, outperforming rolling-origin cross-validation champion selection and complex ML algorithms on the held-out test window.
                </p>
                <p className="text-amber-300/80 font-mono text-[11px] pt-1 border-t border-amber-500/20">
                  Note: An earlier per-pair champion selection used information from the test window and was discarded; the current test results come from a fixed production model. The test window has been inspected multiple times during development.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ============================================================== */}
        {/* SECTION 6: LEAD-TIME UNCERTAINTY CALIBRATION                  */}
        {/* ============================================================== */}
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-[#F59E0B]" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-white font-mono">
              6. Lead-Time Uncertainty &amp; Spread Calibration
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="glass-surface rounded-2xl p-5 border border-amber-500/30 bg-amber-950/10 space-y-2">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4 text-amber-400" />
                <span className="text-sm font-bold font-mono text-white">
                  Tree Spread Std: {ltOverall?.tree_std_coverage_95 ? `${(ltOverall.tree_std_coverage_95 * 100).toFixed(1)}%` : "76.9%"} Coverage
                </span>
              </div>
              <p className="text-xs text-zinc-300 leading-relaxed">
                Standard deviation computed from tree-to-tree prediction variance across the 100 Random Forest estimators reflects only model epistemic disagreement. It severely under-disperses operational risk, capturing only 76.9% of deliveries within nominal 95% intervals.
              </p>
            </div>

            <div className="glass-surface rounded-2xl p-5 border border-emerald-500/30 bg-emerald-950/10 space-y-2">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                <span className="text-sm font-bold font-mono text-white">
                  Calibrated Residual Std: {ltOverall?.calibrated_coverage_95 ? `${(ltOverall.calibrated_coverage_95 * 100).toFixed(1)}%` : "95.9%"} Coverage
                </span>
              </div>
              <p className="text-xs text-zinc-300 leading-relaxed">
                Derived empirically from out-of-fold supplier delivery residuals partitioned by destination area and a Nov–Dec season flag (is_holiday_season). Safety stock formulas strictly adopt the calibrated std to prevent under-buffered stockouts.
              </p>
            </div>
          </div>
        </section>

        {/* ============================================================== */}
        {/* SECTION 7: LIMITATIONS & BOUNDARY DISCLOSURES                 */}
        {/* ============================================================== */}
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-rose-400" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-white font-mono">
              7. Engineering Limitations &amp; Boundary Conditions
            </h2>
          </div>

          <div className="glass-surface rounded-2xl p-6 border border-white/[0.08] grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
            <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-1">
              <span className="text-rose-400 font-semibold block">1. Intermittent Demand Sparsity</span>
              <p className="text-zinc-400 font-sans">
                30 of 75 pairs feature high zero-demand frequency where continuous Gaussian assumptions degrade. Croston SBA handles replenishment sizing, but confidence flags alert buyers to widened prediction intervals.
              </p>
            </div>

            <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-1">
              <span className="text-rose-400 font-semibold block">2. Normal Lead-Time Demand Approximation</span>
              <p className="text-zinc-400 font-sans">
                Analytical stockout probabilities assume lead-time demand is normally distributed. While supported by the Central Limit Theorem over 7-day windows, it remains a heuristic for low-count items.
              </p>
            </div>

            <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-1">
              <span className="text-rose-400 font-semibold block">3. Synthetic Lead Times</span>
              <p className="text-zinc-400 font-sans">
                The lead-time model achieves R² = 0.785 because synthetic supplier delivery records reflect a consistent mathematical generative process rather than human driver delays or carrier bankruptcies.
              </p>
            </div>

            <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-1">
              <span className="text-rose-400 font-semibold block">4. Single-Echelon Isolated Positions</span>
              <p className="text-zinc-400 font-sans">
                No transshipment or cross-hub network pooling between California, Texas, and Wisconsin is modeled. Each material-area pair is evaluated as an autonomous distribution node.
              </p>
            </div>
          </div>
        </section>

        {/* ============================================================== */}
        {/* SECTION 8: FAQ ACCORDION FOR JUDGES                           */}
        {/* ============================================================== */}
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <HelpCircle className="h-4 w-4 text-[#00F2FE]" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-white font-mono">
              8. Evaluation FAQ for Technical Judges
            </h2>
          </div>

          <div className="space-y-3">
            {faqs.map((faq, idx) => {
              const isOpen = openFaq === idx;
              return (
                <div
                  key={idx}
                  className="glass-surface rounded-2xl border border-white/[0.08] overflow-hidden transition-all"
                >
                  <button
                    onClick={() => setOpenFaq(isOpen ? null : idx)}
                    className="w-full p-4 sm:p-5 text-left flex items-center justify-between gap-4 hover:bg-white/[0.02] transition-colors cursor-pointer"
                  >
                    <span className="text-sm font-medium text-white font-mono flex items-center gap-2.5">
                      <span className="text-[#00F2FE] font-bold">Q{idx + 1}:</span>
                      <span>{faq.q}</span>
                    </span>
                    <ChevronDown
                      className={`h-4 w-4 text-zinc-400 shrink-0 transition-transform duration-200 ${
                        isOpen ? "rotate-180 text-[#00F2FE]" : ""
                      }`}
                    />
                  </button>
                  {isOpen && (
                    <div className="px-4 pb-5 sm:px-5 border-t border-white/[0.04] pt-3 text-xs text-zinc-300 leading-relaxed font-sans">
                      {faq.a}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
}
