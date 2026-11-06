"use client";

import React from "react";
import { Sliders, Sparkles, Tag, TrendingUp, AlertCircle } from "lucide-react";

interface PromotionSimulatorProps {
  isActive: boolean;
  onToggle: (active: boolean) => void;
  startOffsetDays: number;
  onStartOffsetChange: (val: number) => void;
  durationDays: number;
  onDurationChange: (val: number) => void;
  empiricalLift: number;
  hasMeasurableEffect: boolean;
  effectDescription?: string;
  liftCiLower?: number;
  liftCiUpper?: number;
  originalRop: number;
  simulatedRop: number;
  originalSs: number;
  simulatedSs: number;
  originalDaysRemaining: number;
  simulatedDaysRemaining: number;
  originalStatus: "OK" | "REORDER" | "CRITICAL";
  simulatedStatus: "OK" | "REORDER" | "CRITICAL";
  originalForecastTotal: number;
  simulatedForecastTotal: number;
}

export const PromotionSimulator: React.FC<PromotionSimulatorProps> = ({
  isActive,
  onToggle,
  startOffsetDays,
  onStartOffsetChange,
  durationDays,
  onDurationChange,
  empiricalLift,
  hasMeasurableEffect,
  effectDescription,
  liftCiLower,
  liftCiUpper,
  originalRop,
  simulatedRop,
  originalSs,
  simulatedSs,
  originalDaysRemaining,
  simulatedDaysRemaining,
  originalStatus,
  simulatedStatus,
  originalForecastTotal,
  simulatedForecastTotal,
}) => {
  const forecastDelta = simulatedForecastTotal - originalForecastTotal;
  const ropDelta = simulatedRop - originalRop;
  const ssDelta = simulatedSs - originalSs;
  const daysDelta = simulatedDaysRemaining - originalDaysRemaining;
  const statusChanged = originalStatus !== simulatedStatus;

  return (
    <div className="glass-surface rounded-2xl p-6 border border-white/[0.08] space-y-6">
      {/* Simulator Header & Toggle */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/[0.08] pb-5">
        <div className="flex items-center gap-3">
          <div className={`h-10 w-10 rounded-2xl flex items-center justify-center transition-colors ${
            isActive
              ? "bg-[#EC4899]/20 border border-[#EC4899]/40 text-[#EC4899]"
              : "bg-white/[0.05] border border-white/[0.1] text-zinc-400"
          }`}>
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-semibold text-white">
                Promotion &amp; Uplift Simulator
              </h3>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono uppercase tracking-wider bg-white/[0.06] text-zinc-300 border border-white/[0.1]">
                Simulated, empirical lift
              </span>
            </div>
            <p className="text-xs text-zinc-400">
              Apply empirically measured promotional uplift to project dynamic ROP surges and inventory depletion in-browser.
            </p>
          </div>
        </div>

        {/* Toggle Switch */}
        <label className="relative inline-flex items-center cursor-pointer select-none">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(e) => onToggle(e.target.checked)}
            className="sr-only peer"
          />
          <div className="w-11 h-6 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[#EC4899]"></div>
          <span className="ml-3 text-xs font-mono font-medium text-zinc-300">
            {isActive ? "Simulation Active" : "Disabled"}
          </span>
        </label>
      </div>

      {/* Measurable Effect Banner */}
      {!hasMeasurableEffect ? (
        <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/25 flex items-start gap-3 text-xs text-amber-300">
          <AlertCircle className="h-4 w-4 shrink-0 text-amber-400 mt-0.5" />
          <div>
            <span className="font-semibold">No measurable promo effect: </span>
            This material/area pair showed no statistically significant empirical sales uplift during past promotional campaigns. Empirical lift multiplier is locked at 1.00x.
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-4 p-3.5 rounded-xl bg-white/[0.03] border border-white/[0.06] text-xs font-mono">
          <div className="flex items-center gap-2 text-zinc-300">
            <TrendingUp className="h-4 w-4 text-[#EC4899]" />
            <span>Empirical Lift:</span>
            <span className="text-[#EC4899] font-bold text-sm">
              +{((empiricalLift - 1.0) * 100).toFixed(1)}% ({empiricalLift.toFixed(3)}&times;)
            </span>
            {liftCiLower !== undefined && liftCiUpper !== undefined && (
              <span className="text-zinc-500 text-[11px]">
                [95% CI: {liftCiLower.toFixed(3)} &mdash; {liftCiUpper.toFixed(3)}]
              </span>
            )}
          </div>
          {effectDescription && (
            <div className="text-[11px] text-zinc-400 font-sans italic">
              {effectDescription}
            </div>
          )}
        </div>
      )}

      {/* Simulator Interactive Sliders (always visible; disabled until toggle is ON) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Slider 1: Start Offset */}
        <div className="space-y-2">
          <div className="flex justify-between items-center text-xs">
            <span className="text-zinc-300 font-mono flex items-center gap-1.5">
              <Sliders className="h-3.5 w-3.5 text-[#00F2FE]" />
              Event Starts In:
            </span>
            <span className="text-white font-mono font-bold bg-white/[0.08] px-2 py-0.5 rounded-md tabular-nums">
              +{startOffsetDays} days
            </span>
          </div>
          <input
            type="range"
            id="promo-start-slider"
            aria-label="Promotion start offset in days"
            min="1"
            max="30"
            step="1"
            value={startOffsetDays}
            disabled={!isActive}
            onChange={(e) => onStartOffsetChange(Number(e.target.value))}
            className="raphael-range"
            style={{ ["--range-color" as string]: "#00F2FE", ["--fill" as string]: `${((startOffsetDays - 1) / 29) * 100}%` } as React.CSSProperties}
          />
          <div className="flex justify-between text-[10px] text-zinc-500 font-mono">
            <span>+1 day</span>
            <span>+15 days</span>
            <span>+30 days</span>
          </div>
        </div>

        {/* Slider 2: Event Duration */}
        <div className="space-y-2">
          <div className="flex justify-between items-center text-xs">
            <span className="text-zinc-300 font-mono flex items-center gap-1.5">
              <Tag className="h-3.5 w-3.5 text-[#EC4899]" />
              Promotion Duration:
            </span>
            <span className="text-white font-mono font-bold bg-white/[0.08] px-2 py-0.5 rounded-md tabular-nums">
              {durationDays} days
            </span>
          </div>
          <input
            type="range"
            id="promo-duration-slider"
            aria-label="Promotion duration in days"
            min="1"
            max="21"
            step="1"
            value={durationDays}
            disabled={!isActive}
            onChange={(e) => onDurationChange(Number(e.target.value))}
            className="raphael-range"
            style={{ ["--range-color" as string]: "#EC4899", ["--fill" as string]: `${((durationDays - 1) / 20) * 100}%` } as React.CSSProperties}
          />
          <div className="flex justify-between text-[10px] text-zinc-500 font-mono">
            <span>1 day</span>
            <span>7 days</span>
            <span>21 days</span>
          </div>
        </div>
      </div>

      {/* Live Arithmetic Decision Recomputation Results (fixed height: no layout shift on toggle) */}
      <div className="pt-4 border-t border-white/[0.08] space-y-3 min-h-[190px]">
        <div className="text-xs font-mono uppercase text-zinc-400 tracking-wider">
          {isActive ? "Live Recomputed Inventory Decision Impact" : "Turn the simulator on to recompute the decision"}
        </div>

        {isActive && (
          <>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 font-mono text-xs" id="promo-impact-grid">
              {/* Impact 0: Forecast total */}
              <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.08] space-y-1">
                <span className="text-zinc-400 text-[11px]">Forecast, next 30d</span>
                <div className="flex items-baseline gap-2">
                  <span className="text-white text-base font-bold tabular-nums" data-testid="sim-forecast">{simulatedForecastTotal.toFixed(0)}</span>
                  <span className={`text-[11px] ${forecastDelta > 0 ? "text-[#EC4899]" : "text-zinc-500"}`}>
                    {forecastDelta > 0 ? `+${forecastDelta.toFixed(0)}` : "0"} units
                  </span>
                </div>
                <span className="text-[10px] text-zinc-500">Base: {originalForecastTotal.toFixed(0)}</span>
              </div>

              {/* Impact 1: Reorder Point Surge */}
              <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.08] space-y-1">
                <span className="text-zinc-400 text-[11px]">Reorder Point (ROP)</span>
                <div className="flex items-baseline gap-2">
                  <span className="text-white text-base font-bold tabular-nums" data-testid="sim-rop">{simulatedRop.toFixed(1)}</span>
                  <span className={`text-[11px] ${ropDelta > 0 ? "text-amber-400" : "text-zinc-500"}`}>
                    {ropDelta > 0 ? `+${ropDelta.toFixed(1)}` : "0.0"} units
                  </span>
                </div>
                <span className="text-[10px] text-zinc-500">Base: {originalRop.toFixed(1)}</span>
              </div>

              {/* Impact 2: Safety Stock Surge */}
              <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.08] space-y-1">
                <span className="text-zinc-400 text-[11px]">Safety Stock (SS)</span>
                <div className="flex items-baseline gap-2">
                  <span className="text-white text-base font-bold tabular-nums" data-testid="sim-ss">{simulatedSs.toFixed(1)}</span>
                  <span className={`text-[11px] ${ssDelta > 0 ? "text-amber-400" : "text-zinc-500"}`}>
                    {ssDelta > 0 ? `+${ssDelta.toFixed(1)}` : "0.0"} units
                  </span>
                </div>
                <span className="text-[10px] text-zinc-500">Base: {originalSs.toFixed(1)}</span>
              </div>

              {/* Impact 3: Accelerated Depletion */}
              <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.08] space-y-1">
                <span className="text-zinc-400 text-[11px]">Days Remaining</span>
                <div className="flex items-baseline gap-2">
                  <span className="text-white text-base font-bold tabular-nums" data-testid="sim-days">{simulatedDaysRemaining.toFixed(1)}d</span>
                  <span className={`text-[11px] ${daysDelta < 0 ? "text-red-400" : "text-zinc-500"}`}>
                    {daysDelta < 0 ? `${daysDelta.toFixed(1)}d` : "0.0d"}
                  </span>
                </div>
                <span className="text-[10px] text-zinc-500">Base: {originalDaysRemaining.toFixed(1)}d</span>
              </div>
            </div>

            <div className={`p-2.5 rounded-lg border text-xs font-mono flex items-center justify-between ${statusChanged ? "bg-red-500/15 border-red-500/30 text-red-300" : "bg-white/[0.03] border-white/[0.08] text-zinc-300"}`}>
              <span>{statusChanged ? "Status Escalation:" : "Status (unchanged):"}</span>
              <div className="flex items-center gap-2" data-testid="sim-status">
                {statusChanged ? (
                  <>
                    <span className="line-through text-zinc-400">{originalStatus}</span>
                    <span>&rarr;</span>
                    <span className="font-bold text-red-400">{simulatedStatus}</span>
                  </>
                ) : (
                  <span className="font-bold">{simulatedStatus}</span>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
