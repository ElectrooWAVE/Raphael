"use client";

import React, { Suspense, useEffect, useState, useMemo, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  ChevronDown,
  Layers,
  LineChart,
  MapPin,
  RefreshCw,
  SlidersHorizontal,
  Sparkles,
  AlertTriangle,
} from "lucide-react";
import {
  api,
  type ForecastResponse,
  type ReorderResponse,
  type LeadTimeResponse,
  type AccuracyResponse,
} from "../../lib/api";
import {
  computeSafetyStock,
  computeReorderPoint,
  computeDaysRemaining,
  classifyInventoryStatus,
} from "../../lib/inventoryEngine";
import { ForecastChart, type SimulatedForecastPoint } from "../../components/forecast/ForecastChart";
import { ReorderPanel } from "../../components/forecast/ReorderPanel";
import { PromotionSimulator } from "../../components/forecast/PromotionSimulator";
import { ModelBadge } from "../../components/forecast/ModelBadge";
import { HeldoutChart, type HeldoutGranularity } from "../../components/forecast/HeldoutChart";

function ForecastDashboardContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // URL Query Parameters State
  const initialMaterial = searchParams.get("material") || "FOODS_2_019";
  const initialArea = searchParams.get("area") || "California - CA_1";
  const initialInterval = (Number(searchParams.get("interval")) === 95 ? 95 : 80) as 80 | 95;

  const [selectedMaterial, setSelectedMaterial] = useState<string>(initialMaterial);
  const [selectedArea, setSelectedArea] = useState<string>(initialArea);
  const [intervalLevel, setIntervalLevel] = useState<80 | 95>(initialInterval);

  // Sync state if searchParams change (e.g. from /inventory row click)
  useEffect(() => {
    const m = searchParams.get("material");
    const a = searchParams.get("area");
    if (m && m !== selectedMaterial) setSelectedMaterial(m);
    if (a && a !== selectedArea) setSelectedArea(a);
  }, [searchParams, selectedMaterial, selectedArea]);

  // Lists for dropdown options
  const [materialsList, setMaterialsList] = useState<string[]>([]);
  const [areasList, setAreasList] = useState<string[]>([]);

  // Fetched data states
  const [forecastData, setForecastData] = useState<ForecastResponse | null>(null);
  const [reorderData, setReorderData] = useState<ReorderResponse | null>(null);
  const [leadTimeData, setLeadTimeData] = useState<LeadTimeResponse | null>(null);
  const [accuracyData, setAccuracyData] = useState<AccuracyResponse | null>(null);

  // UI state
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Promotion Simulator State
  const [isSimulatingPromo, setIsSimulatingPromo] = useState<boolean>(false);
  const [promoStartOffset, setPromoStartOffset] = useState<number>(7);
  const [promoDuration, setPromoDuration] = useState<number>(7);

  // Chart view: 90d forecast vs held-out actual-vs-predicted
  const [chartView, setChartView] = useState<"forecast" | "heldout">("forecast");
  const [heldoutGranularity, setHeldoutGranularity] = useState<HeldoutGranularity>("daily");

  // Keep URL search params in sync
  const updateUrlParams = useCallback(
    (mat: string, ar: string, intvl: 80 | 95) => {
      const params = new URLSearchParams();
      params.set("material", mat);
      params.set("area", ar);
      params.set("interval", String(intvl));
      router.replace(`/forecast?${params.toString()}`, { scroll: false });
    },
    [router]
  );

  // 1. Initial Load: Materials list and Accuracy metrics
  useEffect(() => {
    let isMounted = true;

    Promise.all([
      api.getMaterials().catch(() => ({ materials: [], total_materials: 0 })),
      api.getAccuracy().catch(() => null),
    ]).then(([matRes, accRes]) => {
      if (isMounted) {
        setMaterialsList(matRes.materials);
        setAccuracyData(accRes);
      }
    });

    return () => {
      isMounted = false;
    };
  }, []);

  // 2. Load available areas when material changes
  useEffect(() => {
    let isMounted = true;

    api
      .getAreas(selectedMaterial)
      .then((res) => {
        if (isMounted) {
          setAreasList(res.areas);
          // If current area is not in the list for this material, pick the first
          if (!res.areas.includes(selectedArea) && res.areas.length > 0) {
            setSelectedArea(res.areas[0]);
            updateUrlParams(selectedMaterial, res.areas[0], intervalLevel);
          }
        }
      })
      .catch((err) => {
        console.error("Failed to load areas:", err);
      });

    return () => {
      isMounted = false;
    };
  }, [selectedMaterial, selectedArea, intervalLevel, updateUrlParams]);

  // 3. Load full pair forecast, reorder, and lead-time data
  const loadPairData = useCallback(
    async (material: string, area: string) => {
      setIsLoading(true);
      setError(null);

      try {
        const [fRes, rRes, ltRes] = await Promise.all([
          api.getForecast(material, area),
          api.getReorder(material, area),
          api.getLeadTime(material, area),
        ]);

        setForecastData(fRes);
        setReorderData(rRes);
        setLeadTimeData(ltRes);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "Failed to load pair forecast";
        setError(message);
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    if (selectedMaterial && selectedArea) {
      loadPairData(selectedMaterial, selectedArea);
      updateUrlParams(selectedMaterial, selectedArea, intervalLevel);
    }
  }, [selectedMaterial, selectedArea, intervalLevel, loadPairData, updateUrlParams]);

  // Handle Material Change
  const handleMaterialChange = (newMat: string) => {
    setSelectedMaterial(newMat);
    setIsSimulatingPromo(false); // Reset simulation on pair switch
  };

  // Handle Area Change
  const handleAreaChange = (newArea: string) => {
    setSelectedArea(newArea);
    setIsSimulatingPromo(false);
  };

  // Handle Interval Toggle
  const handleIntervalToggle = (level: 80 | 95) => {
    setIntervalLevel(level);
    updateUrlParams(selectedMaterial, selectedArea, level);
  };

  // Extract empirical promo info from forecast response
  const empiricalPromo = forecastData?.empirical_promotion;
  const hasMeasurableEffect = empiricalPromo?.has_measurable_effect ?? false;
  const empiricalLift = hasMeasurableEffect ? empiricalPromo?.empirical_lift ?? 1.0 : 1.0;

  // Compute Simulated Forecast & Inventory Arithmetic Live
  const {
    simulatedForecastList,
    simulatedRop,
    simulatedSs,
    simulatedDaysRemaining,
    simulatedStatus,
  } = useMemo(() => {
    if (!forecastData || !reorderData) {
      return {
        simulatedForecastList: [] as SimulatedForecastPoint[],
        simulatedRop: 0,
        simulatedSs: 0,
        simulatedDaysRemaining: 0,
        simulatedStatus: "OK" as const,
      };
    }

    const baseForecast = forecastData.forecast_90d || [];
    const stock = reorderData.current_stock;
    const leadTime = reorderData.predicted_lead_time_days;
    const sigmaL = reorderData.calibrated_lead_time_std_sigma_l;
    const sigmaD = reorderData.demand_error_std_sigma_d;

    if (!isSimulatingPromo) {
      return {
        simulatedForecastList: baseForecast.map((p) => ({ ...p, simulated_yhat: p.yhat })),
        simulatedRop: reorderData.reorder_point_rop,
        simulatedSs: reorderData.safety_stock_ss,
        simulatedDaysRemaining: reorderData.days_remaining,
        simulatedStatus: reorderData.status as "OK" | "REORDER" | "CRITICAL",
      };
    }

    // Apply promo lift multiplier to forecast points within [startOffset, startOffset + duration]
    const promoStartIdx = Math.max(0, promoStartOffset - 1);
    const promoEndIdx = promoStartIdx + promoDuration;

    const modifiedForecast: SimulatedForecastPoint[] = baseForecast.map((pt, idx) => {
      const isInPromoWindow = idx >= promoStartIdx && idx < promoEndIdx;
      const simVal = isInPromoWindow ? pt.yhat * empiricalLift : pt.yhat;
      return {
        ...pt,
        simulated_yhat: Number(simVal.toFixed(2)),
      };
    });

    const simDailyVals = modifiedForecast.map((p) => p.simulated_yhat ?? p.yhat);

    // Compute updated mean demand rate D over the lead-time window
    const ltInt = Math.max(1, Math.round(leadTime));
    const ltWindowDemands = simDailyVals.slice(0, ltInt);
    const newDemandRate =
      ltWindowDemands.length > 0
        ? ltWindowDemands.reduce((a, b) => a + b, 0) / ltWindowDemands.length
        : reorderData.demand_rate_d;

    // Recompute SS, ROP, days remaining, and status via inventoryEngine.ts
    const newSs = computeSafetyStock(newDemandRate, sigmaD, leadTime, sigmaL, 0.95);
    const newRop = computeReorderPoint(newDemandRate, leadTime, newSs);
    const remResult = computeDaysRemaining(stock, simDailyVals);
    const newStatus = classifyInventoryStatus(stock, newRop, remResult.daysRemaining, leadTime);

    return {
      simulatedForecastList: modifiedForecast,
      simulatedRop: Number(newRop.toFixed(2)),
      simulatedSs: Number(newSs.toFixed(2)),
      simulatedDaysRemaining: remResult.daysRemaining,
      simulatedStatus: newStatus,
    };
  }, [forecastData, reorderData, isSimulatingPromo, promoStartOffset, promoDuration, empiricalLift]);

  // Extract test window accuracy for the selected pair from accuracyData
  const pairAccuracy = useMemo(() => {
    if (!accuracyData?.per_pair_metrics) return null;
    return accuracyData.per_pair_metrics.find(
      (p) => p.material === selectedMaterial && p.area === selectedArea
    );
  }, [accuracyData, selectedMaterial, selectedArea]);

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 space-y-6">
      {/* Top Breadcrumb & Title */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/[0.08] pb-5">
        <div className="space-y-1">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-xs text-zinc-400 hover:text-[#00F2FE] transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Back to Overview</span>
          </Link>
          <div className="flex items-center gap-3 pt-1">
            <div className="h-9 w-9 rounded-xl bg-[#00F2FE]/10 border border-[#00F2FE]/25 flex items-center justify-center text-[#00F2FE]">
              <LineChart className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-white flex items-center gap-2">
                <span>Demand Studio</span>
                {process.env.NODE_ENV === "development" && (
                  <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-white/[0.05] text-zinc-400 font-normal">
                    Phase 7 Step 6
                  </span>
                )}
              </h1>
              <p className="text-xs text-zinc-400">
                Multi-horizon forecasting with calibrated prediction intervals, inventory depletion triage, and promotion uplift.
              </p>
            </div>
          </div>
        </div>

        {/* Global Action Refresh */}
        <button
          onClick={() => loadPairData(selectedMaterial, selectedArea)}
          className="glass-pill px-3 py-1.5 rounded-full text-xs text-zinc-300 hover:text-white hover:bg-white/[0.08] border border-white/[0.12] transition-colors flex items-center gap-1.5 cursor-pointer"
          title="Refresh current pair data"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? "animate-spin text-[#00F2FE]" : ""}`} />
          <span>Sync Data</span>
        </button>
      </div>

      {/* Control Strip: Frosted Pills (Material, Area, 80/95 Interval) */}
      <div className="glass-surface rounded-2xl p-4 border border-white/[0.08] flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          {/* Material Selector Pill */}
          <div className="relative inline-flex items-center">
            <span className="absolute left-3.5 pointer-events-none text-zinc-400">
              <Layers className="h-3.5 w-3.5 text-[#00F2FE]" />
            </span>
            <select
              value={selectedMaterial}
              onChange={(e) => handleMaterialChange(e.target.value)}
              className="appearance-none glass-pill pl-9 pr-9 py-2 text-xs font-mono text-white bg-white/[0.04] border border-white/[0.14] rounded-full focus:outline-none focus:border-[#00F2FE]/60 cursor-pointer"
            >
              {materialsList.map((m) => (
                <option key={m} value={m} className="bg-zinc-950 text-white font-mono">
                  {m}
                </option>
              ))}
            </select>
            <span className="absolute right-3.5 pointer-events-none text-zinc-400">
              <ChevronDown className="h-3.5 w-3.5" />
            </span>
          </div>

          {/* Area Selector Pill (Filtered by Material) */}
          <div className="relative inline-flex items-center">
            <span className="absolute left-3.5 pointer-events-none text-zinc-400">
              <MapPin className="h-3.5 w-3.5 text-[#A855F7]" />
            </span>
            <select
              value={selectedArea}
              onChange={(e) => handleAreaChange(e.target.value)}
              className="appearance-none glass-pill pl-9 pr-9 py-2 text-xs font-mono text-white bg-white/[0.04] border border-white/[0.14] rounded-full focus:outline-none focus:border-[#A855F7]/60 cursor-pointer"
            >
              {areasList.map((a) => (
                <option key={a} value={a} className="bg-zinc-950 text-white font-mono">
                  {a}
                </option>
              ))}
            </select>
            <span className="absolute right-3.5 pointer-events-none text-zinc-400">
              <ChevronDown className="h-3.5 w-3.5" />
            </span>
          </div>
        </div>

        {/* 80% / 95% Interval Toggle Pills */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-zinc-400 flex items-center gap-1.5">
            <SlidersHorizontal className="h-3 w-3 text-zinc-400" />
            Bands:
          </span>
          <div className="inline-flex rounded-full p-1 bg-white/[0.04] border border-white/[0.08]">
            <button
              onClick={() => handleIntervalToggle(80)}
              className={`px-3 py-1 rounded-full text-xs font-mono transition-all cursor-pointer ${
                intervalLevel === 80
                  ? "bg-[#00F2FE] text-black font-semibold shadow-[0_0_12px_rgba(0,242,254,0.4)]"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              80% Band
            </button>
            <button
              onClick={() => handleIntervalToggle(95)}
              className={`px-3 py-1 rounded-full text-xs font-mono transition-all cursor-pointer ${
                intervalLevel === 95
                  ? "bg-[#00F2FE] text-black font-semibold shadow-[0_0_12px_rgba(0,242,254,0.4)]"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              95% Band
            </button>
          </div>
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div className="p-4 rounded-2xl bg-red-500/10 border border-red-500/30 flex items-center gap-3 text-red-300 text-xs font-mono">
          <AlertTriangle className="h-4 w-4 shrink-0 text-red-400" />
          <span>{error}</span>
        </div>
      )}

      {/* Model & Accuracy Metadata Badges */}
      {forecastData && (
        <ModelBadge
          modelUsed={forecastData.model_used}
          intervalMethod={forecastData.interval_method}
          pooledResiduals={forecastData.pooled_residuals}
          lowConfidence={forecastData.low_confidence}
          weeklyWape={
            typeof pairAccuracy?.test_weekly_wape === "number"
              ? (pairAccuracy.test_weekly_wape as number)
              : forecastData.accuracy?.weekly_pair_wape
          }
          dailyWape={
            typeof pairAccuracy?.test_daily_wape === "number"
              ? (pairAccuracy.test_daily_wape as number)
              : forecastData.accuracy?.daily_pair_wape
          }
          testDays={accuracyData?.test_days ?? 84}
        />
      )}

      {/* Chart view toggle: Forecast vs held-out actual-vs-predicted */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-full p-1 bg-white/[0.04] border border-white/[0.08]" role="tablist">
          <button
            id="view-forecast-btn"
            onClick={() => setChartView("forecast")}
            className={`px-3 py-1 rounded-full text-xs font-mono transition-all cursor-pointer ${chartView === "forecast" ? "bg-white text-black font-semibold" : "text-zinc-400 hover:text-white"}`}
          >
            Forecast (next 90d)
          </button>
          <button
            id="view-heldout-btn"
            onClick={() => setChartView("heldout")}
            className={`px-3 py-1 rounded-full text-xs font-mono transition-all cursor-pointer ${chartView === "heldout" ? "bg-white text-black font-semibold" : "text-zinc-400 hover:text-white"}`}
          >
            Held-out test: actual vs predicted (last {accuracyData?.test_days ?? 84}d)
          </button>
        </div>
        {chartView === "heldout" && (
          <div className="inline-flex rounded-full p-1 bg-white/[0.04] border border-white/[0.08]">
            {(["daily", "weekly"] as const).map((g) => (
              <button
                key={g}
                id={`heldout-${g}-btn`}
                onClick={() => setHeldoutGranularity(g)}
                className={`px-3 py-1 rounded-full text-xs font-mono capitalize transition-all cursor-pointer ${heldoutGranularity === g ? "bg-[#00F2FE] text-black font-semibold" : "text-zinc-400 hover:text-white"}`}
              >
                {g}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Chart area: fixed height so loading/pair switches never shift the layout */}
      <div className="relative min-h-[470px]">
        {forecastData ? (
          <div className={`transition-opacity duration-200 ${isLoading ? "opacity-40" : "opacity-100"}`}>
            {chartView === "forecast" ? (
              <ForecastChart
                history={forecastData.history_tail_60d || []}
                forecast={simulatedForecastList}
                asOfDate={forecastData.as_of_date}
                intervalLevel={intervalLevel}
                isSimulatingPromo={isSimulatingPromo}
              />
            ) : (
              <HeldoutChart
                points={forecastData.heldout_test || []}
                granularity={heldoutGranularity}
                wape={
                  heldoutGranularity === "weekly"
                    ? forecastData.accuracy?.weekly_pair_wape
                    : forecastData.accuracy?.daily_pair_wape
                }
              />
            )}
          </div>
        ) : (
          <div className="h-[440px] rounded-2xl border border-white/[0.08] bg-white/[0.02] flex flex-col items-center justify-center space-y-3">
            <div className="h-8 w-8 rounded-full border-2 border-[#00F2FE] border-t-transparent animate-spin" />
            <span className="text-xs font-mono text-zinc-400">{error ? "Forecast unavailable" : "Loading multi-horizon forecast..."}</span>
          </div>
        )}
        {isLoading && forecastData && (
          <div className="absolute top-3 right-3 text-[10px] font-mono text-[#00F2FE] flex items-center gap-1.5">
            <span className="h-3 w-3 rounded-full border-2 border-[#00F2FE] border-t-transparent animate-spin" />
            Updatingâ€¦
          </div>
        )}
      </div>

      {/* Reorder Panel (ROP, SS, Lead Time, Days Remaining, Order Quantity) */}
      <div className={`min-h-[330px] transition-opacity duration-200 ${isLoading ? "opacity-40" : "opacity-100"}`}>
        {reorderData && (
          <ReorderPanel
            currentStock={reorderData.current_stock}
            rop={simulatedRop}
            safetyStock={simulatedSs}
            predictedLeadTime={reorderData.predicted_lead_time_days}
            calibratedLeadTimeStd={reorderData.calibrated_lead_time_std_sigma_l}
            treeSpreadLeadTimeStd={reorderData.tree_spread_lead_time_std}
            plannedOrderQty={reorderData.recommended_order_quantity}
            isExtrapolation={reorderData.is_quantity_extrapolation}
            daysRemaining={simulatedDaysRemaining}
            daysRemainingLabel={reorderData.days_remaining_label}
            beyondHorizon={reorderData.beyond_horizon}
            status={simulatedStatus}
            isSimulated={isSimulatingPromo}
          />
        )}
      </div>

      {/* Promotion / Event Uplift Simulator */}
      <div className="min-h-[560px]">
        {forecastData && reorderData && (
          <PromotionSimulator
            isActive={isSimulatingPromo}
            onToggle={setIsSimulatingPromo}
            startOffsetDays={promoStartOffset}
            onStartOffsetChange={setPromoStartOffset}
            durationDays={promoDuration}
            onDurationChange={setPromoDuration}
            empiricalLift={empiricalLift}
            hasMeasurableEffect={hasMeasurableEffect}
            effectDescription={empiricalPromo?.effect_description}
            liftCiLower={empiricalPromo?.lift_ci_lower_95}
            liftCiUpper={empiricalPromo?.lift_ci_upper_95}
            originalRop={reorderData.reorder_point_rop}
            simulatedRop={simulatedRop}
            originalSs={reorderData.safety_stock_ss}
            simulatedSs={simulatedSs}
            originalDaysRemaining={reorderData.days_remaining}
            simulatedDaysRemaining={simulatedDaysRemaining}
            originalStatus={reorderData.status as "OK" | "REORDER" | "CRITICAL"}
            simulatedStatus={simulatedStatus}
            originalForecastTotal={(forecastData.forecast_90d || []).slice(0, 30).reduce((s, p) => s + p.yhat, 0)}
            simulatedForecastTotal={simulatedForecastList.slice(0, 30).reduce((s, p) => s + (p.simulated_yhat ?? p.yhat), 0)}
          />
        )}
      </div>
    </div>
  );
}

export default function ForecastPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl px-4 py-12 text-center text-xs font-mono text-zinc-400">
          Initializing Demand Studio...
        </div>
      }
    >
      <ForecastDashboardContent />
    </Suspense>
  );
}
