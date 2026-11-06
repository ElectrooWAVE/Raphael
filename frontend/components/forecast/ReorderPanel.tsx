"use client";

import React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  HelpCircle,
  Package,
  ShieldCheck,
  TrendingDown,
  Info,
} from "lucide-react";

interface ReorderPanelProps {
  currentStock: number;
  rop: number;
  safetyStock: number;
  predictedLeadTime: number;
  calibratedLeadTimeStd?: number;
  treeSpreadLeadTimeStd?: number;
  plannedOrderQty: number;
  isExtrapolation?: boolean;
  daysRemaining: number;
  daysRemainingLabel?: string;
  beyondHorizon?: boolean;
  status: "OK" | "REORDER" | "CRITICAL";
  isSimulated?: boolean;
}

export const ReorderPanel: React.FC<ReorderPanelProps> = ({
  currentStock,
  rop,
  safetyStock,
  predictedLeadTime,
  calibratedLeadTimeStd = 0.904,
  treeSpreadLeadTimeStd = 0.465,
  plannedOrderQty,
  isExtrapolation = false,
  daysRemaining,
  daysRemainingLabel = "within horizon",
  beyondHorizon = false,
  status,
  isSimulated = false,
}) => {
  // Determine Banner Styling and Copy based on exact status
  const isCritical = status === "CRITICAL";
  const isReorder = status === "REORDER";
  const isOk = status === "OK";

  return (
    <div className="space-y-4">
      {/* Alert Banner */}
      {isCritical && (
        <div className="rounded-2xl border border-red-500/40 bg-gradient-to-r from-red-950/60 via-red-900/30 to-white/[0.02] p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.12),0_0_30px_rgba(239,68,68,0.2)]">
          <div className="flex items-start gap-4">
            <div className="h-10 w-10 rounded-xl bg-red-500/20 border border-red-500/40 flex items-center justify-center text-red-400 shrink-0 animate-pulse">
              <AlertTriangle className="h-5 w-5" />
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase tracking-wider bg-red-500 text-white shadow-[0_0_10px_rgba(239,68,68,0.6)]">
                  Critical Expedite
                </span>
                {isSimulated && (
                  <span className="text-[10px] font-mono text-zinc-400">
                    (Under Promotional Simulation)
                  </span>
                )}
              </div>
              <h3 className="text-base sm:text-lg font-semibold text-white">
                Stock runs out in {daysRemaining.toFixed(1)} days &mdash; before supplier delivery ({predictedLeadTime.toFixed(1)} days)
              </h3>
              <p className="text-xs text-red-200/80 leading-relaxed max-w-3xl">
                On-hand stock is insufficient to buffer standard replenishment lead time. A stockout is imminent unless emergency expedited freight or multi-area reallocation is triggered immediately.
              </p>
            </div>
          </div>
        </div>
      )}

      {isReorder && (
        <div className="rounded-2xl border border-amber-500/35 bg-gradient-to-r from-amber-950/40 via-amber-900/20 to-white/[0.02] p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.12),0_0_24px_rgba(245,158,11,0.15)]">
          <div className="flex items-start gap-4">
            <div className="h-10 w-10 rounded-xl bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-400 shrink-0">
              <TrendingDown className="h-5 w-5" />
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase tracking-wider bg-amber-500/20 text-amber-300 border border-amber-500/40">
                  Reorder Recommended
                </span>
                {isSimulated && (
                  <span className="text-[10px] font-mono text-zinc-400">
                    (Under Promotional Simulation)
                  </span>
                )}
              </div>
              <h3 className="text-base sm:text-lg font-semibold text-white">
                Reorder now: {daysRemaining.toFixed(1)} days of stock left
              </h3>
              <p className="text-xs text-zinc-300 leading-relaxed max-w-3xl">
                Current inventory ({currentStock.toFixed(0)} units) has reached or fallen below the calculated Reorder Point ({rop.toFixed(0)} units). Place standard replenishment of {plannedOrderQty.toFixed(0)} units to maintain the assumed 95% service level.
              </p>
            </div>
          </div>
        </div>
      )}

      {isOk && (
        <div className="rounded-2xl border border-emerald-500/25 bg-gradient-to-r from-emerald-950/30 via-emerald-900/15 to-white/[0.02] p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)]">
          <div className="flex items-start gap-4">
            <div className="h-10 w-10 rounded-xl bg-emerald-500/20 border border-emerald-500/35 flex items-center justify-center text-emerald-400 shrink-0">
              <CheckCircle2 className="h-5 w-5" />
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase tracking-wider bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                  Inventory Healthy
                </span>
                {isSimulated && (
                  <span className="text-[10px] font-mono text-zinc-400">
                    (Under Promotional Simulation)
                  </span>
                )}
              </div>
              <h3 className="text-base sm:text-lg font-semibold text-white">
                {daysRemainingLabel === "no demand expected"
                  ? "No demand expected \u2014 stock remains intact"
                  : beyondHorizon
                  ? "Over 90 days of stock cover \u2014 buffer healthy"
                  : `${daysRemaining.toFixed(1)} days of stock remaining`}
              </h3>
              <p className="text-xs text-zinc-400 leading-relaxed max-w-3xl">
                On-hand inventory ({currentStock.toFixed(0)} units) comfortably exceeds the Reorder Point ({rop.toFixed(0)} units) with {safetyStock.toFixed(0)} units of dedicated safety buffer. No purchase order required at this review.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Six Metric Tiles Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {/* Metric 1: Current Stock */}
        <div className="glass-surface rounded-2xl p-4 space-y-1 border border-white/[0.08]">
          <span className="text-[11px] font-mono uppercase text-zinc-400 tracking-wider flex items-center gap-1.5">
            <Package className="h-3 w-3 text-zinc-400" />
            Stock On-Hand
          </span>
          <div className="text-2xl font-bold font-mono tabular-nums text-white">
            {currentStock.toFixed(0)}
          </div>
          <span className="text-[10px] text-zinc-500 font-mono">physical inventory</span>
        </div>

        {/* Metric 2: Days Remaining */}
        <div className={`glass-surface rounded-2xl p-4 space-y-1 border ${
          isCritical
            ? "border-red-500/30 bg-red-950/10"
            : isReorder
            ? "border-amber-500/30 bg-amber-950/10"
            : "border-white/[0.08]"
        }`}>
          <span className="text-[11px] font-mono uppercase text-zinc-400 tracking-wider flex items-center gap-1.5">
            <Clock className="h-3 w-3 text-zinc-400" />
            Cover Days
          </span>
          <div className="text-2xl font-bold font-mono tabular-nums">
            {beyondHorizon ? (
              <span className="text-[#00F2FE]">&gt; 90d</span>
            ) : daysRemainingLabel === "no demand expected" ? (
              <span className="text-zinc-400">&infin;</span>
            ) : (
              <span className={isCritical ? "text-red-400" : isReorder ? "text-amber-400" : "text-[#00F2FE]"}>
                {daysRemaining.toFixed(1)}d
              </span>
            )}
          </div>
          <span className="text-[10px] text-zinc-500 font-mono capitalize">{daysRemainingLabel}</span>
        </div>

        {/* Metric 3: Reorder Point (ROP) */}
        <div className="glass-surface rounded-2xl p-4 space-y-1 border border-white/[0.08]">
          <span className="text-[11px] font-mono uppercase text-zinc-400 tracking-wider flex items-center gap-1.5">
            <TrendingDown className="h-3 w-3 text-zinc-400" />
            Reorder Point (ROP)
          </span>
          <div className="text-2xl font-bold font-mono tabular-nums text-white">
            {rop.toFixed(1)}
          </div>
          <span className="text-[10px] text-zinc-500 font-mono">D &times; L + SS</span>
        </div>

        {/* Metric 4: Safety Stock (SS) */}
        <div className="glass-surface rounded-2xl p-4 space-y-1 border border-white/[0.08]">
          <span className="text-[11px] font-mono uppercase text-zinc-400 tracking-wider flex items-center gap-1.5">
            <ShieldCheck className="h-3 w-3 text-zinc-400" />
            Safety Stock
          </span>
          <div className="text-2xl font-bold font-mono tabular-nums text-white">
            {safetyStock.toFixed(1)}
          </div>
          <span className="text-[10px] text-zinc-500 font-mono">dual variance buffer</span>
        </div>

        {/* Metric 5: Predicted Lead Time (with calibrated & tree spread tooltips) */}
        <div className="glass-surface rounded-2xl p-4 space-y-1 border border-white/[0.08] relative group">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-mono uppercase text-zinc-400 tracking-wider flex items-center gap-1.5">
              <Clock className="h-3 w-3 text-zinc-400" />
              Lead Time
            </span>
            <div className="cursor-help text-zinc-500 hover:text-zinc-300">
              <HelpCircle className="h-3 w-3" />
            </div>
          </div>
          <div className="text-2xl font-bold font-mono tabular-nums text-white">
            {predictedLeadTime.toFixed(1)}d
          </div>
          <span className="text-[10px] text-zinc-500 font-mono">
            &plusmn;{calibratedLeadTimeStd.toFixed(2)}d std
          </span>

          {/* Hover Tooltip explaining calibrated vs tree spread - opens downward to never cover navbar */}
          <div className="absolute top-full left-0 mt-2 hidden group-hover:block z-30 w-64 p-3 rounded-xl glass-popover text-[11px] font-mono text-zinc-300 space-y-1.5 pointer-events-none">
            <div className="font-semibold text-white border-b border-white/[0.1] pb-1">
              Lead Time Uncertainty
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-400">Predicted Lead Time:</span>
              <span className="text-white font-bold">{predictedLeadTime.toFixed(2)} days</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-400">Calibrated Std (&sigma;L):</span>
              <span className="text-emerald-400 font-bold">{calibratedLeadTimeStd.toFixed(3)} days</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-400">Tree-Spread Std:</span>
              <span className="text-amber-400 font-bold">{treeSpreadLeadTimeStd.toFixed(3)} days</span>
            </div>
            <p className="text-[10px] text-zinc-400 pt-1 font-sans leading-tight">
              Safety stock uses the calibrated standard deviation from empirical out-of-fold residuals, avoiding ensemble under-dispersion.
            </p>
          </div>
        </div>

        {/* Metric 6: Planned Order Quantity */}
        <div className="glass-surface rounded-2xl p-4 space-y-1 border border-white/[0.08]">
          <span className="text-[11px] font-mono uppercase text-zinc-400 tracking-wider flex items-center gap-1.5">
            <Package className="h-3 w-3 text-zinc-400" />
            Order Sizing
          </span>
          <div className="text-2xl font-bold font-mono tabular-nums text-white">
            {plannedOrderQty.toFixed(0)}
          </div>
          <div className="flex items-center gap-1">
            <span className="text-[10px] text-zinc-500 font-mono">14d cover target</span>
            {isExtrapolation && (
              <span
                className="text-[9px] font-mono text-purple-300 px-1 py-0.2 rounded-xs bg-purple-500/15 border border-purple-500/30 cursor-help"
                title="Lead time estimated at the largest historical order size; bigger orders may take longer"
              >
                Extrap
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};


