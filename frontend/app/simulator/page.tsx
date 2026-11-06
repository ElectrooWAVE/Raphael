"use client";

import React, { useEffect, useState, useMemo, useCallback, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Box,
  Check,
  ChevronDown,
  Compass,
  DollarSign,
  HelpCircle,
  Info,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ReferenceDot,
  CartesianGrid,
} from "recharts";
import {
  api,
  type ReorderResponse,
  type LeadTimeResponse,
} from "@/lib/api";
import {
  computeSafetyStock,
  computeReorderPoint,
  computeOrderUpToLevel,
  computeRecommendedOrderQuantity,
  computeDaysRemaining,
  classifyInventoryStatus,
  computeEoq,
  type InventoryStatus,
} from "@/lib/inventoryEngine";

function SimulatorDashboardContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Selected pair from URL or default
  const paramMaterial = searchParams.get("material") || "FOODS_2_019";
  const paramArea = searchParams.get("area") || "California - CA_1";

  const [selectedMaterial, setSelectedMaterial] = useState<string>(paramMaterial);
  const [selectedArea, setSelectedArea] = useState<string>(paramArea);

  // Metadata dropdowns
  const [materialsList, setMaterialsList] = useState<string[]>([]);
  const [areasList, setAreasList] = useState<string[]>([]);
  const [isLoadingMeta, setIsLoadingMeta] = useState<boolean>(true);

  // Fetched baseline model values
  const [baselineReorder, setBaselineReorder] = useState<ReorderResponse | null>(null);
  const [baselineLeadTime, setBaselineLeadTime] = useState<LeadTimeResponse | null>(null);
  const [isLoadingBaseline, setIsLoadingBaseline] = useState<boolean>(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Interactive Scenario Parameters (Defaults loaded from baseline)
  const [demandShockPct, setDemandShockPct] = useState<number>(0); // -30% to +30%
  const [leadTimeOverride, setLeadTimeOverride] = useState<number>(7.0);
  const [leadTimeStdOverride, setLeadTimeStdOverride] = useState<number>(0.9);
  const [serviceLevelPct, setServiceLevelPct] = useState<number>(95.0); // 85% to 99.5%
  const [currentStockInput, setCurrentStockInput] = useState<number>(555);

  // Assumed Business Cost Parameters
  const [orderingCostFixed, setOrderingCostFixed] = useState<number>(50.0); // $50 default [ASSUMED]
  const [holdingRateAnnualPct, setHoldingRateAnnualPct] = useState<number>(20.0); // 20% annual [ASSUMED]
  const [assumedUnitCost, setAssumedUnitCost] = useState<number>(10.0); // $10.00 default [ASSUMED UNIT COST]

  // Sync state if searchParams change
  useEffect(() => {
    const m = searchParams.get("material");
    const a = searchParams.get("area");
    if (m && m !== selectedMaterial) setSelectedMaterial(m);
    if (a && a !== selectedArea) setSelectedArea(a);
  }, [searchParams, selectedMaterial, selectedArea]);

  // 1. Initial Load: Materials List
  useEffect(() => {
    let isMounted = true;
    api
      .getMaterials()
      .then((res) => {
        if (isMounted) {
          setMaterialsList(res.materials || []);
          setIsLoadingMeta(false);
        }
      })
      .catch(() => {
        if (isMounted) setIsLoadingMeta(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  // 2. Load Areas for selected material
  useEffect(() => {
    let isMounted = true;
    if (!selectedMaterial) return;

    api
      .getAreas(selectedMaterial)
      .then((res) => {
        if (isMounted) {
          setAreasList(res.areas || []);
          if (res.areas && !res.areas.includes(selectedArea) && res.areas.length > 0) {
            setSelectedArea(res.areas[0]);
          }
        }
      })
      .catch(() => {});

    return () => {
      isMounted = false;
    };
  }, [selectedMaterial, selectedArea]);

  // 3. Fetch Baseline pair data from API
  const loadPairBaseline = useCallback(async () => {
    if (!selectedMaterial || !selectedArea) return;
    setIsLoadingBaseline(true);
    setFetchError(null);

    try {
      const [reorderRes, ltRes] = await Promise.all([
        api.getReorder(selectedMaterial, selectedArea),
        api.getLeadTime(selectedMaterial, selectedArea),
      ]);

      setBaselineReorder(reorderRes);
      setBaselineLeadTime(ltRes);

      // Initialize scenario sliders with model baseline (exact unrounded values)
      setDemandShockPct(0);
      setLeadTimeOverride(reorderRes.predicted_lead_time_days);
      setLeadTimeStdOverride(reorderRes.calibrated_lead_time_std_sigma_l);
      setServiceLevelPct((reorderRes.service_level_target || 0.95) * 100);
      setCurrentStockInput(reorderRes.current_stock);

      // Update URL query parameters
      const p = new URLSearchParams();
      p.set("material", selectedMaterial);
      p.set("area", selectedArea);
      router.replace(`/simulator?${p.toString()}`, { scroll: false });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setFetchError(msg);
    } finally {
      setIsLoadingBaseline(false);
    }
  }, [selectedMaterial, selectedArea, router]);

  useEffect(() => {
    loadPairBaseline();
  }, [loadPairBaseline]);

  // Reset to Model Values handler (restores exact model baseline, all deltas return to +0.0)
  const handleResetToBaseline = () => {
    if (!baselineReorder) return;
    setDemandShockPct(0);
    setLeadTimeOverride(baselineReorder.predicted_lead_time_days);
    setLeadTimeStdOverride(baselineReorder.calibrated_lead_time_std_sigma_l);
    setServiceLevelPct((baselineReorder.service_level_target || 0.95) * 100);
    setCurrentStockInput(baselineReorder.current_stock);
    setOrderingCostFixed(50.0);
    setHoldingRateAnnualPct(20.0);
    setAssumedUnitCost(10.0);
  };

  // 4. Live Client-Side Inventory Calculations (Pure Arithmetic matching engine.ts)
  const scenarioOutputs = useMemo(() => {
    if (!baselineReorder) return null;

    // Check if parameters match model baseline exactly
    const isAtBaseline =
      Math.abs(demandShockPct) < 0.0001 &&
      Math.abs(leadTimeOverride - baselineReorder.predicted_lead_time_days) < 0.0001 &&
      Math.abs(leadTimeStdOverride - baselineReorder.calibrated_lead_time_std_sigma_l) < 0.0001 &&
      Math.abs(serviceLevelPct - ((baselineReorder.service_level_target || 0.95) * 100)) < 0.0001 &&
      Math.abs(currentStockInput - baselineReorder.current_stock) < 0.0001 &&
      Math.abs(orderingCostFixed - 50.0) < 0.0001 &&
      Math.abs(holdingRateAnnualPct - 20.0) < 0.0001 &&
      Math.abs(assumedUnitCost - 10.0) < 0.0001;

    // Adjusted demand rate & daily forecast error
    const demandMultiplier = Math.max(0, 1 + demandShockPct / 100);
    const baseDemandRate = baselineReorder.demand_rate_d;
    const simDemandRate = baseDemandRate * demandMultiplier;
    const baseSigmaD = baselineReorder.demand_error_std_sigma_d;
    const simSigmaD = baseSigmaD * Math.sqrt(demandMultiplier);

    const L = Math.max(0.1, leadTimeOverride);
    const sigmaL = Math.max(0, leadTimeStdOverride);
    const slFraction = Math.min(0.999, Math.max(0.5, serviceLevelPct / 100));

    // Pure arithmetic: SS, ROP, Order-up-to, Recommended Qty, Status
    const simSs = computeSafetyStock(simDemandRate, simSigmaD, L, sigmaL, slFraction);
    const simRop = computeReorderPoint(simDemandRate, L, simSs);

    // Order-up-to level (review period = 7d per assumptions.yaml)
    const orderUpTo = computeOrderUpToLevel(simRop, simDemandRate, 7);

    // 14-day planned demand
    const rawPlanned14d = simDemandRate * 14;
    const recResult = computeRecommendedOrderQuantity(
      rawPlanned14d,
      orderUpTo,
      currentStockInput,
      baselineReorder.hist_p5_order_quantity,
      baselineReorder.hist_p95_order_quantity
    );

    // Day-by-day forecast depletion for days remaining
    const simDailyForecast = Array.from({ length: 90 }, () => simDemandRate);
    const daysRemResult = computeDaysRemaining(currentStockInput, simDailyForecast, 90);

    // Inventory status classification
    const simStatus: InventoryStatus = classifyInventoryStatus(
      currentStockInput,
      simRop,
      daysRemResult.daysRemaining,
      L
    );

    // EOQ with explicit assumed unit cost
    const annualDemand = simDemandRate * 365;
    const holdingCostAnnualUnit = (holdingRateAnnualPct / 100) * assumedUnitCost;
    const simEoq = computeEoq(annualDemand, orderingCostFixed, holdingCostAnnualUnit);

    // When at baseline, exactly preserve precomputed authoritative artifact metrics
    const finalRop = isAtBaseline ? baselineReorder.reorder_point_rop : simRop;
    const finalSs = isAtBaseline ? baselineReorder.safety_stock_ss : simSs;
    const finalRecQty = isAtBaseline ? baselineReorder.recommended_order_quantity : recResult.recommendedQty;
    const finalDaysRem = isAtBaseline ? baselineReorder.days_remaining : daysRemResult.daysRemaining;
    const finalBeyondHorizon = isAtBaseline ? baselineReorder.beyond_horizon : daysRemResult.beyondHorizon;
    const finalStatus = isAtBaseline ? (baselineReorder.status as InventoryStatus) : simStatus;
    const finalEoq = isAtBaseline ? baselineReorder.eoq_quantity : simEoq;
    const finalIsExtrap = isAtBaseline ? baselineReorder.is_quantity_extrapolation : recResult.isExtrapolation;

    // Stockout probability from normal lead-time demand model
    // LTD ~ Normal(mu_LTD = D * L, sigma_LTD = sqrt(L * sigma_D^2 + D^2 * sigma_L^2))
    const muLtd = simDemandRate * L;
    const varianceLtd = L * Math.pow(simSigmaD, 2) + Math.pow(simDemandRate, 2) * Math.pow(sigmaL, 2);
    const sigmaLtd = Math.sqrt(Math.max(0, varianceLtd));

    let stockoutProb = 0;
    if (currentStockInput <= 0) {
      stockoutProb = 1.0;
    } else if (sigmaLtd > 0) {
      const zScoreCurr = (currentStockInput - muLtd) / sigmaLtd;
      // Normal standard survival function: 1 - 0.5 * (1 + erf(z / sqrt(2)))
      const t = 1.0 / (1.0 + 0.2316419 * Math.abs(zScoreCurr));
      const poly =
        t *
        (0.31938153 +
          t *
            (-0.356563782 +
              t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
      const cdfVal =
        zScoreCurr >= 0
          ? 1.0 - (1.0 / Math.sqrt(2 * Math.PI)) * Math.exp(-0.5 * zScoreCurr * zScoreCurr) * poly
          : (1.0 / Math.sqrt(2 * Math.PI)) * Math.exp(-0.5 * zScoreCurr * zScoreCurr) * poly;
      stockoutProb = Math.max(0, Math.min(1, 1.0 - cdfVal));
    } else {
      stockoutProb = currentStockInput >= muLtd ? 0.0 : 1.0;
    }

    // Cost-vs-Service curve data points across 85% to 99.5%
    const serviceCurveData: Array<{ slPct: number; ssUnits: number; annualSsCost: number }> = [];
    const testPoints = [85, 87.5, 90, 92.5, 95, 97, 98, 99, 99.5];
    testPoints.forEach((sl) => {
      const ssAtSl = computeSafetyStock(simDemandRate, simSigmaD, L, sigmaL, sl / 100);
      const costAtSl = ssAtSl * holdingCostAnnualUnit;
      serviceCurveData.push({
        slPct: sl,
        ssUnits: Number(ssAtSl.toFixed(1)),
        annualSsCost: Number(costAtSl.toFixed(1)),
      });
    });

    return {
      simDemandRate,
      simSigmaD,
      L,
      sigmaL,
      simSs: finalSs,
      simRop: finalRop,
      orderUpTo,
      recommendedOrderQuantity: finalRecQty,
      isQuantityExtrapolation: finalIsExtrap,
      daysRemaining: finalDaysRem,
      beyondHorizon: finalBeyondHorizon,
      status: finalStatus,
      simEoq: finalEoq,
      annualDemand,
      holdingCostAnnualUnit,
      stockoutProb,
      serviceCurveData,
      isAtBaseline,
    };
  }, [
    baselineReorder,
    demandShockPct,
    leadTimeOverride,
    leadTimeStdOverride,
    serviceLevelPct,
    currentStockInput,
    orderingCostFixed,
    holdingRateAnnualPct,
    assumedUnitCost,
  ]);

  // Delta helpers for baseline comparison (identically 0.0 when at model baseline)
  const isBase = scenarioOutputs?.isAtBaseline ?? true;
  const deltaSs = scenarioOutputs && baselineReorder && !isBase ? scenarioOutputs.simSs - baselineReorder.safety_stock_ss : 0;
  const deltaRop = scenarioOutputs && baselineReorder && !isBase ? scenarioOutputs.simRop - baselineReorder.reorder_point_rop : 0;
  const deltaRecQty = scenarioOutputs && baselineReorder && !isBase ? scenarioOutputs.recommendedOrderQuantity - baselineReorder.recommended_order_quantity : 0;

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 space-y-6">
      {/* Top Header & Breadcrumb */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/[0.08] pb-5">
        <div className="space-y-1.5">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-xs text-zinc-400 hover:text-[#00F2FE] transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Back to Overview</span>
          </Link>
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-2xl bg-[#A855F7]/10 border border-[#A855F7]/25 flex items-center justify-center text-[#A855F7]">
              <Sliders className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-white">
                  Inventory Scenario Simulator
                </h1>
                {process.env.NODE_ENV === "development" && (
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-white/[0.05] text-zinc-400 border border-white/[0.1]">
                    Phase 7 Step 7a
                  </span>
                )}
              </div>
              <p className="text-xs text-zinc-400">
                Stress-test inventory policies with demand shocks, lead-time delays, cost overrides, and live trade-off curves.
              </p>
            </div>
          </div>
        </div>

        {/* Pair Selector Toolbar */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Material Select */}
          <div className="relative">
            <select
              value={selectedMaterial}
              onChange={(e) => setSelectedMaterial(e.target.value)}
              disabled={isLoadingMeta}
              className="appearance-none pl-3 pr-8 py-2 rounded-xl bg-white/[0.045] shadow-[inset_0_1px_0_rgba(255,255,255,0.1)] border border-white/[0.1] text-xs font-mono text-zinc-200 focus:outline-none focus:border-[#00F2FE]/50 transition-all cursor-pointer disabled:opacity-50"
            >
              {materialsList.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500 pointer-events-none" />
          </div>

          {/* Area Select */}
          <div className="relative">
            <select
              value={selectedArea}
              onChange={(e) => setSelectedArea(e.target.value)}
              disabled={isLoadingMeta || areasList.length === 0}
              className="appearance-none pl-3 pr-8 py-2 rounded-xl bg-white/[0.045] shadow-[inset_0_1px_0_rgba(255,255,255,0.1)] border border-white/[0.1] text-xs font-mono text-zinc-200 focus:outline-none focus:border-[#00F2FE]/50 transition-all cursor-pointer disabled:opacity-50"
            >
              {areasList.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500 pointer-events-none" />
          </div>

          {/* Reset to Model Values Button */}
          <button
            onClick={handleResetToBaseline}
            title="Reset all parameters to ML model baseline"
            className="glass-pill px-3 py-2 text-xs font-mono text-zinc-300 hover:text-white hover:bg-white/[0.08] border border-white/[0.12] transition-all flex items-center gap-1.5 cursor-pointer"
          >
            <RotateCcw className="h-3.5 w-3.5 text-[#00F2FE]" />
            <span>Reset Baseline</span>
          </button>
        </div>
      </div>

      {fetchError && (
        <div className="p-4 rounded-2xl border border-rose-500/30 bg-rose-950/20 text-xs font-mono text-rose-300 flex items-center gap-3">
          <AlertTriangle className="h-4 w-4 shrink-0 text-rose-400" />
          <span>Error loading baseline data for selected pair: {fetchError}</span>
        </div>
      )}

      {/* Main 3-Column Layout: Parameters | Risk Gauge Area | Live Outputs */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* ============================================================== */}
        {/* COLUMN 1: PARAMETER DECK (lg:col-span-4)                      */}
        {/* ============================================================== */}
        <div className="lg:col-span-4 glass-surface rounded-2xl p-5 border border-white/[0.08] space-y-6">
          <div className="flex items-center justify-between border-b border-white/[0.06] pb-3">
            <div className="flex items-center gap-2">
              <Sliders className="h-4 w-4 text-[#A855F7]" />
              <h2 className="text-sm font-semibold text-white">Parameter Deck</h2>
            </div>
            <span className="text-[10px] font-mono text-zinc-400">Live Client Math</span>
          </div>

          {/* 1. Demand Shock Slider (-30% to +30%) */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-zinc-300">Demand Shock:</span>
              <span
                className={`font-bold tabular-nums ${
                  demandShockPct > 0
                    ? "text-[#00F2FE]"
                    : demandShockPct < 0
                    ? "text-amber-400"
                    : "text-zinc-400"
                }`}
              >
                {demandShockPct > 0 ? `+${demandShockPct}%` : `${demandShockPct}%`}
              </span>
            </div>
            <input
              type="range"
              min="-30"
              max="30"
              step="1"
              value={demandShockPct}
              onChange={(e) => setDemandShockPct(Number(e.target.value))}
              className="raphael-range w-full cursor-pointer"
              style={
                {
                  "--fill": `${((demandShockPct + 30) / 60) * 100}%`,
                  "--range-color": demandShockPct >= 0 ? "#00F2FE" : "#F59E0B",
                } as React.CSSProperties
              }
            />
            <div className="flex justify-between text-[10px] font-mono text-zinc-500">
              <span>-30% Contraction</span>
              <span>Baseline</span>
              <span>+30% Surge</span>
            </div>
          </div>

          {/* 2. Lead Time Override Slider (1d to 25d) */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-zinc-300">Lead Time (L):</span>
              <span className="text-white font-bold tabular-nums">
                {leadTimeOverride.toFixed(2)} days
              </span>
            </div>
            <input
              type="range"
              min="1"
              max="25"
              step="0.01"
              value={leadTimeOverride}
              onChange={(e) => setLeadTimeOverride(Number(e.target.value))}
              className="raphael-range w-full cursor-pointer"
              style={
                {
                  "--fill": `${((leadTimeOverride - 1) / 24) * 100}%`,
                  "--range-color": "#A855F7",
                } as React.CSSProperties
              }
            />
            <div className="flex justify-between text-[10px] font-mono text-zinc-500">
              <span>1.0d Fast</span>
              <span>Model: {baselineReorder?.predicted_lead_time_days.toFixed(2) || "—"}d</span>
              <span>25.0d Stalled</span>
            </div>
          </div>

          {/* 3. Lead-Time Variability (sigma_L) Slider (0.0d to 4.0d) */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-zinc-300">Lead Time Std (σ_L):</span>
              <span className="text-white font-bold tabular-nums">
                ±{leadTimeStdOverride.toFixed(3)}d
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="4"
              step="0.001"
              value={leadTimeStdOverride}
              onChange={(e) => setLeadTimeStdOverride(Number(e.target.value))}
              className="raphael-range w-full cursor-pointer"
              style={
                {
                  "--fill": `${(leadTimeStdOverride / 4) * 100}%`,
                  "--range-color": "#EC4899",
                } as React.CSSProperties
              }
            />
            <div className="flex justify-between text-[10px] font-mono text-zinc-500">
              <span>0.0d Deterministic</span>
              <span>Calibrated: {baselineReorder?.calibrated_lead_time_std_sigma_l.toFixed(3) || "—"}d</span>
              <span>4.0d Volatile</span>
            </div>
          </div>

          {/* 4. Target Service Level (85% to 99.5%) */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-zinc-300">Cycle Service Level:</span>
              <span className="text-[#10B981] font-bold tabular-nums">
                {serviceLevelPct.toFixed(2)}%
              </span>
            </div>
            <input
              type="range"
              min="85"
              max="99.5"
              step="0.01"
              value={serviceLevelPct}
              onChange={(e) => setServiceLevelPct(Number(e.target.value))}
              className="raphael-range w-full cursor-pointer"
              style={
                {
                  "--fill": `${((serviceLevelPct - 85) / 14.5) * 100}%`,
                  "--range-color": "#10B981",
                } as React.CSSProperties
              }
            />
            <div className="flex justify-between text-[10px] font-mono text-zinc-500">
              <span>85.0% (Z=1.04)</span>
              <span>95.0% (Z=1.65)</span>
              <span>99.5% (Z=2.58)</span>
            </div>
          </div>

          {/* 5. Current Stock Input */}
          <div className="space-y-1.5 pt-2 border-t border-white/[0.06]">
            <label className="text-xs font-mono text-zinc-300 flex items-center justify-between">
              <span>Current On-Hand Stock:</span>
              <span className="text-[10px] text-zinc-500">Physical Units</span>
            </label>
            <input
              type="number"
              min="0"
              value={currentStockInput}
              onChange={(e) => setCurrentStockInput(Math.max(0, Number(e.target.value)))}
              className="w-full px-3 py-2 rounded-xl bg-white/[0.03] border border-white/[0.1] text-xs font-mono text-white focus:outline-none focus:border-[#00F2FE]/50"
            />
          </div>

          {/* 6. Assumed Cost Inputs Deck */}
          <div className="space-y-3 pt-3 border-t border-white/[0.06]">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-400 font-medium">
                Business Cost Assumptions
              </span>
              <span className="text-[9px] font-mono text-amber-400 px-1.5 py-0.5 rounded bg-amber-500/10 border border-amber-500/20">
                ASSUMED
              </span>
            </div>

            {/* Ordering Cost */}
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-zinc-400">Fixed Order Cost (S):</span>
              <div className="flex items-center gap-1">
                <span className="text-zinc-500">$</span>
                <input
                  type="number"
                  min="1"
                  step="5"
                  value={orderingCostFixed}
                  onChange={(e) => setOrderingCostFixed(Math.max(1, Number(e.target.value)))}
                  className="w-16 px-2 py-1 rounded-lg bg-white/[0.04] border border-white/[0.1] text-xs font-mono text-white text-right"
                />
              </div>
            </div>

            {/* Holding Rate Annual % */}
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-zinc-400">Annual Holding Rate (i):</span>
              <div className="flex items-center gap-1">
                <input
                  type="number"
                  min="1"
                  max="100"
                  step="1"
                  value={holdingRateAnnualPct}
                  onChange={(e) => setHoldingRateAnnualPct(Math.max(1, Number(e.target.value)))}
                  className="w-16 px-2 py-1 rounded-lg bg-white/[0.04] border border-white/[0.1] text-xs font-mono text-white text-right"
                />
                <span className="text-zinc-500">%</span>
              </div>
            </div>

            {/* User-Editable Assumed Unit Cost */}
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-zinc-300 font-medium">Assumed Unit Cost:</span>
              <div className="flex items-center gap-1">
                <span className="text-zinc-500">$</span>
                <input
                  type="number"
                  min="0.1"
                  step="1"
                  value={assumedUnitCost}
                  onChange={(e) => setAssumedUnitCost(Math.max(0.1, Number(e.target.value)))}
                  className="w-16 px-2 py-1 rounded-lg bg-[#00F2FE]/10 border border-[#00F2FE]/30 text-xs font-mono text-[#00F2FE] text-right font-bold"
                />
              </div>
            </div>
            <p className="text-[10px] text-zinc-500 leading-tight">
              Dataset provides unit quantities only. Unit cost ($10 baseline) is explicitly assumed to compute EOQ and inventory carrying valuation.
            </p>
          </div>
        </div>

        {/* ============================================================== */}
        {/* COLUMN 2: RISK GAUGE AREA (lg:col-span-4)                      */}
        {/* ============================================================== */}
        <div className="lg:col-span-4 space-y-4">
          <div className="glass-surface rounded-2xl p-5 border border-white/[0.08] flex flex-col items-center justify-center text-center space-y-5">
            {/* Header */}
            <div className="w-full flex items-center justify-between border-b border-white/[0.06] pb-3">
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-4 w-4 text-[#00F2FE]" />
                <h2 className="text-sm font-semibold text-white">Stockout Risk Gauge</h2>
              </div>
              {scenarioOutputs && (
                <span
                  className={`text-[10px] font-mono px-2 py-0.5 rounded-full uppercase tracking-wider font-semibold border ${
                    scenarioOutputs.status === "CRITICAL"
                      ? "bg-rose-500/15 text-rose-300 border-rose-500/30"
                      : scenarioOutputs.status === "REORDER"
                      ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
                      : "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                  }`}
                >
                  {scenarioOutputs.status}
                </span>
              )}
            </div>

            {/* Reserved 3D Scene Viewport / Radial Risk Gauge Display */}
            <div className="relative w-full aspect-square max-w-[280px] rounded-3xl glass-surface flex flex-col items-center justify-center p-6 overflow-hidden">
              {/* Radial Glowing Background Pulse */}
              <div
                className={`absolute inset-0 rounded-3xl blur-3xl opacity-20 pointer-events-none transition-colors duration-500 ${
                  scenarioOutputs?.status === "CRITICAL"
                    ? "bg-rose-500"
                    : scenarioOutputs?.status === "REORDER"
                    ? "bg-amber-500"
                    : "bg-emerald-500"
                }`}
              />

              {/* Animated SVG Radial Gauge */}
              <div className="relative h-44 w-44 flex items-center justify-center">
                <svg className="h-full w-full -rotate-90" viewBox="0 0 100 100">
                  {/* Background Track */}
                  <circle
                    cx="50"
                    cy="50"
                    r="40"
                    fill="transparent"
                    stroke="rgba(255,255,255,0.06)"
                    strokeWidth="8"
                  />
                  {/* Gauge Progress Arc */}
                  <circle
                    cx="50"
                    cy="50"
                    r="40"
                    fill="transparent"
                    stroke={
                      scenarioOutputs?.status === "CRITICAL"
                        ? "#F43F5E"
                        : scenarioOutputs?.status === "REORDER"
                        ? "#F59E0B"
                        : "#10B981"
                    }
                    strokeWidth="8"
                    strokeDasharray={251.2}
                    strokeDashoffset={
                      scenarioOutputs
                        ? 251.2 * (1 - Math.min(1, scenarioOutputs.stockoutProb))
                        : 251.2
                    }
                    strokeLinecap="round"
                    className="transition-all duration-500 ease-out"
                  />
                </svg>

                {/* Inner Risk Percentage Readout */}
                <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">
                    Cycle Risk
                  </span>
                  <span
                    className={`text-3xl font-mono font-bold tabular-nums tracking-tight ${
                      scenarioOutputs?.status === "CRITICAL"
                        ? "text-rose-400"
                        : scenarioOutputs?.status === "REORDER"
                        ? "text-amber-400"
                        : "text-emerald-400"
                    }`}
                  >
                    {scenarioOutputs ? `${(scenarioOutputs.stockoutProb * 100).toFixed(1)}%` : "—"}
                  </span>
                  <span className="text-[10px] font-mono text-zinc-400 mt-0.5">
                    Stockout Prob
                  </span>
                </div>
              </div>

              {/* Stage reservation tag for Step 7b */}
              <div className="mt-2 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[9px] font-mono text-zinc-400 bg-white/[0.04] border border-white/[0.08]">
                <Sparkles className="h-2.5 w-2.5 text-[#00F2FE]" />
                <span>Reserved for 3D Risk Sphere (Step 7b)</span>
              </div>
            </div>

            {/* Model & Mathematical Disclosure Note */}
            <div className="w-full text-left p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-1.5 text-[11px] font-mono text-zinc-400">
              <div className="flex items-center gap-1.5 text-zinc-300 font-medium">
                <Info className="h-3.5 w-3.5 text-[#00F2FE]" />
                <span>Normal Lead-Time Demand Model</span>
              </div>
              <p className="text-[10px] text-zinc-500 leading-relaxed">
                P(LTD &gt; stock) = 1 - Φ((stock - μ_LTD) / σ_LTD). Assumes normally distributed demand over lead time; weak approximation for intermittent items.
              </p>
            </div>
          </div>
        </div>

        {/* ============================================================== */}
        {/* COLUMN 3: LIVE OUTPUTS & CURVE (lg:col-span-4)                */}
        {/* ============================================================== */}
        <div className="lg:col-span-4 space-y-4">
          {/* Key Scenario Metrics Cards */}
          <div className="grid grid-cols-2 gap-3">
            {/* Reorder Point (ROP) */}
            <div className="glass-surface rounded-xl p-3.5 border border-white/[0.08] space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400">
                  Reorder Point
                </span>
                <span className="text-[9px] font-mono text-zinc-500">ROP</span>
              </div>
              <div className="text-xl font-mono font-bold text-white tabular-nums">
                {scenarioOutputs ? scenarioOutputs.simRop.toFixed(1) : "—"}
              </div>
              <div className="text-[10px] font-mono text-zinc-400 flex items-center gap-1">
                <span>Base: {baselineReorder?.reorder_point_rop.toFixed(1) || "—"}</span>
                {deltaRop !== 0 && (
                  <span className={deltaRop > 0 ? "text-[#00F2FE]" : "text-amber-400"}>
                    ({deltaRop > 0 ? `+${deltaRop.toFixed(1)}` : deltaRop.toFixed(1)})
                  </span>
                )}
              </div>
            </div>

            {/* Safety Stock (SS) */}
            <div className="glass-surface rounded-xl p-3.5 border border-white/[0.08] space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400">
                  Safety Stock
                </span>
                <span className="text-[9px] font-mono text-zinc-500">SS</span>
              </div>
              <div className="text-xl font-mono font-bold text-white tabular-nums">
                {scenarioOutputs ? scenarioOutputs.simSs.toFixed(1) : "—"}
              </div>
              <div className="text-[10px] font-mono text-zinc-400 flex items-center gap-1">
                <span>Base: {baselineReorder?.safety_stock_ss.toFixed(1) || "—"}</span>
                {deltaSs !== 0 && (
                  <span className={deltaSs > 0 ? "text-[#00F2FE]" : "text-amber-400"}>
                    ({deltaSs > 0 ? `+${deltaSs.toFixed(1)}` : deltaSs.toFixed(1)})
                  </span>
                )}
              </div>
            </div>

            {/* Recommended Order Quantity */}
            <div className="glass-surface rounded-xl p-3.5 border border-white/[0.08] space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400">
                  Recommended Order
                </span>
                {scenarioOutputs?.isQuantityExtrapolation && (
                  <span
                    className="text-[9px] font-mono px-1 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 cursor-help"
                    title="Lead time estimated at the largest historical order size; bigger orders may take longer"
                  >
                    Extrap
                  </span>
                )}
              </div>
              <div className="text-xl font-mono font-bold text-[#00F2FE] tabular-nums">
                {scenarioOutputs ? scenarioOutputs.recommendedOrderQuantity.toFixed(0) : "—"}
              </div>
              <div className="text-[10px] font-mono text-zinc-400">
                Rule: max(14d, S - stock)
              </div>
              {scenarioOutputs?.isQuantityExtrapolation && (
                <p className="text-[10px] font-sans text-purple-300/80 leading-tight pt-1 border-t border-white/[0.06]">
                  Lead time estimated at the largest historical order size; bigger orders may take longer
                </p>
              )}
            </div>

            {/* Days Remaining / Cover */}
            <div className="glass-surface rounded-xl p-3.5 border border-white/[0.08] space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400">
                  Days of Cover
                </span>
                <span className="text-[9px] font-mono text-zinc-500">depletion</span>
              </div>
              <div className="text-xl font-mono font-bold text-white tabular-nums">
                {scenarioOutputs
                  ? scenarioOutputs.beyondHorizon
                    ? ">90d"
                    : `${scenarioOutputs.daysRemaining.toFixed(1)}d`
                  : "—"}
              </div>
              <div className="text-[10px] font-mono text-zinc-400">
                Lead Time: {leadTimeOverride.toFixed(2)}d
              </div>
            </div>
          </div>

          {/* Economic Order Quantity (EOQ) Card */}
          <div className="glass-surface rounded-xl p-3.5 border border-white/[0.08] flex items-center justify-between text-xs font-mono">
            <div>
              <span className="text-zinc-400 block text-[10px] uppercase tracking-wider">
                Economic Order Quantity (Wilson EOQ)
              </span>
              <span className="text-base font-bold text-white">
                {scenarioOutputs ? `${scenarioOutputs.simEoq.toFixed(0)} units` : "—"}
              </span>
            </div>
            <div className="text-right text-[10px] text-zinc-500">
              <div>At Assumed ${assumedUnitCost.toFixed(2)}/unit</div>
              <div>Holding: ${(scenarioOutputs?.holdingCostAnnualUnit || 2.0).toFixed(2)}/unit/yr</div>
            </div>
          </div>

          {/* Methodology note where EOQ and recommended order both appear */}
          <div className="text-[11px] font-sans text-zinc-400 bg-white/[0.02] border border-white/[0.06] rounded-xl p-3 leading-relaxed">
            EOQ is cost-optimal under assumed costs; the recommendation is the service-driven minimum. Unit cost is assumed ($10 flat), so EOQ is illustrative.
          </div>

          {/* Cost-vs-Service Level Curve Chart */}
          <div className="glass-surface rounded-2xl p-4 border border-white/[0.08] space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-white">
                Safety Stock Cost vs Service Level
              </span>
              <span className="text-[10px] font-mono text-zinc-400">
                85% → 99.5%
              </span>
            </div>

            <div className="h-44 w-full pt-1">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={scenarioOutputs?.serviceCurveData || []} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis
                    dataKey="slPct"
                    stroke="#71717a"
                    fontSize={10}
                    tickFormatter={(v) => `${v}%`}
                  />
                  <YAxis
                    stroke="#71717a"
                    fontSize={10}
                    tickFormatter={(v) => `$${v}`}
                  />
                  <RechartsTooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const d = payload[0].payload;
                      return (
                        <div className="rounded-xl glass-popover p-2.5 text-xs font-mono text-white shadow-xl space-y-1">
                          <div className="text-[#00F2FE] font-bold">Service Level: {d.slPct}%</div>
                          <div className="text-zinc-300">Safety Stock: {d.ssUnits} units</div>
                          <div className="text-emerald-400">Annual Carrying: ${d.annualSsCost}</div>
                        </div>
                      );
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="annualSsCost"
                    stroke="#00F2FE"
                    strokeWidth={2}
                    dot={{ fill: "#00F2FE", r: 2 }}
                    activeDot={{ r: 5 }}
                  />
                  {/* Current operating point marker */}
                  <ReferenceDot
                    x={Number(serviceLevelPct.toFixed(1))}
                    y={scenarioOutputs ? Number((scenarioOutputs.simSs * scenarioOutputs.holdingCostAnnualUnit).toFixed(1)) : 0}
                    r={6}
                    fill="#10B981"
                    stroke="#ffffff"
                    strokeWidth={2}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="text-[10px] font-mono text-zinc-500 text-center">
              Green marker indicates current policy target ({serviceLevelPct.toFixed(1)}%). Exponential cost inflection beyond 98%.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function SimulatorPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl px-4 py-12 text-center text-xs font-mono text-zinc-400">
          Initializing Scenario Simulator...
        </div>
      }
    >
      <SimulatorDashboardContent />
    </Suspense>
  );
}
