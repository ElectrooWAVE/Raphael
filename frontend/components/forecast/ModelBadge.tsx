"use client";

import React from "react";
import { AlertCircle, CheckCircle2, ShieldAlert, Cpu, Sparkles } from "lucide-react";

interface ModelBadgeProps {
  modelUsed: string;
  intervalMethod: string;
  pooledResiduals?: boolean;
  lowConfidence?: boolean;
  weeklyWape?: number | null;
  dailyWape?: number | null;
  testDays?: number;
}

const MODEL_NAMES: Record<string, string> = {
  weekday_mean_8w: "Weekday Mean (8-Week Rolling)",
  moving_average_91d: "Moving Average (91-Day)",
  prophet_tuned: "Prophet (Hyperparameter Tuned)",
  blend_prophet_wm8w: "Prophet + Weekday Mean Blend",
  croston_sba: "Croston Syntetos-Boylan (Intermittent)",
  lightgbm_global: "LightGBM Global (Quantile)",
  seasonal_naive: "Seasonal Naive Baseline",
};

export const ModelBadge: React.FC<ModelBadgeProps> = ({
  modelUsed,
  intervalMethod,
  pooledResiduals = false,
  lowConfidence = false,
  weeklyWape,
  dailyWape,
  testDays = 84,
}) => {
  const humanModel = MODEL_NAMES[modelUsed] || modelUsed.replace(/_/g, " ").toUpperCase();
  const humanInterval =
    intervalMethod === "prophet_native"
      ? "Prophet MCMC Native Uncertainty"
      : pooledResiduals
      ? "Empirical Residual Quantiles (Pooled)"
      : "Empirical Residual Quantiles (Pair-Specific)";

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      {/* Champion Model Badge */}
      <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/[0.04] border border-white/[0.1] text-zinc-200">
        <Cpu className="h-3.5 w-3.5 text-[#00F2FE]" />
        <span className="text-zinc-400 font-mono text-[11px]">Production Model:</span>
        <span className="font-medium text-white">{humanModel}</span>
      </div>

      {/* Interval Method Badge */}
      <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/[0.04] border border-white/[0.1] text-zinc-300">
        <Sparkles className="h-3.5 w-3.5 text-[#A855F7]" />
        <span className="text-zinc-400 font-mono text-[11px]">Bands:</span>
        <span>{humanInterval}</span>
      </div>

      {/* Accuracy from /accuracy test window */}
      {weeklyWape !== undefined && weeklyWape !== null && (
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/25 text-emerald-300 font-mono">
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
          <span>Weekly WAPE {(weeklyWape * 100).toFixed(1)}%</span>
          <span className="text-emerald-500/70 text-[10px]">
            (last {testDays}d held-out test)
          </span>
        </div>
      )}

      {/* Daily WAPE if available */}
      {dailyWape !== undefined && dailyWape !== null && (
        <div className="hidden sm:inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-white/[0.03] border border-white/[0.08] text-zinc-400 font-mono text-[11px]">
          <span>Daily WAPE:</span>
          <span className="text-zinc-200">{(dailyWape * 100).toFixed(1)}%</span>
        </div>
      )}

      {/* Low Confidence Flag */}
      {lowConfidence && (
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/15 border border-amber-500/35 text-amber-300 font-medium">
          <ShieldAlert className="h-3.5 w-3.5 text-amber-400" />
          <span>Low Confidence Pair (High Residual Variance)</span>
        </div>
      )}
    </div>
  );
};
