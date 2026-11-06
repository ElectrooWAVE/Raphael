"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { api, type MetaResponse } from "@/lib/api";
import { Reveal } from "@/components/motion/Reveal";
import { CountUp } from "@/components/motion/CountUp";
import { TiltCard } from "@/components/motion/TiltCard";
import {
  Activity,
  ArrowLeft,
  Box,
  Compass,
  Database,
  Layers,
  MousePointer,
  RefreshCw,
  Sparkles,
  Zap,
} from "lucide-react";

export default function MotionLabPage() {
  const [meta, setMeta] = useState<MetaResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [retriggerKey, setRetriggerKey] = useState<number>(0);
  const [isReduced, setIsReduced] = useState<boolean>(false);

  useEffect(() => {
    let isMounted = true;
    api
      .getMeta()
      .then((data) => {
        if (isMounted) {
          setMeta(data);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof Error ? err.message : String(err));
          setIsLoading(false);
        }
      });

    const q = window.matchMedia("(prefers-reduced-motion: reduce)");
    setIsReduced(q.matches);
    const handler = (e: MediaQueryListEvent) => setIsReduced(e.matches);
    q.addEventListener("change", handler);

    return () => {
      isMounted = false;
      q.removeEventListener("change", handler);
    };
  }, []);

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8 space-y-10">
      {/* Header & Navigation */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/[0.08] pb-6">
        <div className="space-y-1">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-xs text-zinc-400 hover:text-[#00F2FE] transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Back to Overview</span>
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-white flex items-center gap-3">
              <span>Raphael Motion Primitives Lab</span>
            </h1>
          </div>
          <p className="text-xs text-zinc-400">
            Interactive test ground verifying <code>Reveal</code>, <code>CountUp</code>, and <code>TiltCard</code> using real data fetched from <code>/meta</code>.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-[11px] font-mono px-3 py-1.5 rounded-full bg-white/[0.04] border border-white/[0.08] text-zinc-300">
            <span
              className={`h-2 w-2 rounded-full ${
                isReduced ? "bg-amber-400" : "bg-[#10B981]"
              }`}
            />
            <span>
              {isReduced ? "Reduced Motion Active" : "Full Motion Active"}
            </span>
          </div>

          <button
            onClick={() => setRetriggerKey((k) => k + 1)}
            className="glow-cyan-btn px-4 py-2 rounded-full text-xs font-medium flex items-center gap-1.5 cursor-pointer shadow-md"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Re-trigger CountUp</span>
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="py-20 flex flex-col items-center justify-center space-y-3">
          <div className="h-8 w-8 rounded-full border-2 border-[#00F2FE] border-t-transparent animate-spin" />
          <p className="text-xs font-mono text-zinc-400">
            Retrieving real data values from /meta...
          </p>
        </div>
      ) : error ? (
        <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-6 text-xs text-amber-200">
          Failed to load metadata from /meta: {error}
        </div>
      ) : meta ? (
        <div className="space-y-12" key={retriggerKey}>
          {/* PRIMITIVE 1: CountUp (Animated Number Counters from 0 to Real Props) */}
          <section className="space-y-4">
            <div className="flex items-center justify-between border-b border-white/[0.06] pb-2">
              <div className="flex items-center gap-2 text-sm font-semibold text-white">
                <Zap className="h-4 w-4 text-[#00F2FE]" />
                <span>1. CountUp Primitive — Real Values from /meta</span>
              </div>
              <span className="text-[11px] font-mono text-zinc-400">
                Easing: Ease-out cubic • Respects reduced motion
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="glass-surface rounded-2xl p-5 space-y-1">
                <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-mono">
                  Total SKU Pairs
                </span>
                <div className="text-3xl font-mono font-semibold text-[#00F2FE]">
                  <CountUp value={meta.fleet_dimensions.total_pairs} duration={1.2} />
                </div>
                <p className="text-[10px] text-zinc-400">Evaluated catalog pairs</p>
              </div>

              <div className="glass-surface rounded-2xl p-5 space-y-1">
                <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-mono">
                  Materials Catalog
                </span>
                <div className="text-3xl font-mono font-semibold text-[#A855F7]">
                  <CountUp value={meta.fleet_dimensions.total_materials} duration={1.2} />
                </div>
                <p className="text-[10px] text-zinc-400">Unique material codes</p>
              </div>

              <div className="glass-surface rounded-2xl p-5 space-y-1">
                <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-mono">
                  Demand Days / Pair
                </span>
                <div className="text-3xl font-mono font-semibold text-[#EC4899]">
                  <CountUp
                    value={meta.fleet_dimensions.total_demand_days_per_pair}
                    duration={1.6}
                  />
                </div>
                <p className="text-[10px] text-zinc-400">Historical observation depth</p>
              </div>

              <div className="glass-surface rounded-2xl p-5 space-y-1">
                <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-mono">
                  Total Historical Orders
                </span>
                <div className="text-3xl font-mono font-semibold text-[#10B981]">
                  <CountUp
                    value={meta.fleet_dimensions.total_historical_orders}
                    duration={1.8}
                  />
                </div>
                <p className="text-[10px] text-zinc-400">Supplier order history</p>
              </div>
            </div>
          </section>

          {/* PRIMITIVE 2: TiltCard (Cursor-Tracking 3D Spring Physics) */}
          <section className="space-y-4">
            <div className="flex items-center justify-between border-b border-white/[0.06] pb-2">
              <div className="flex items-center gap-2 text-sm font-semibold text-white">
                <MousePointer className="h-4 w-4 text-[#A855F7]" />
                <span>2. TiltCard Primitive — Cursor-Tracking 3D Springs</span>
              </div>
              <span className="text-[11px] font-mono text-zinc-400">
                Spring physics: stiffness 240, damping 20 • Dynamic glare
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <TiltCard className="h-full">
                <div className="glass-surface h-full rounded-2xl p-6 space-y-3 border border-white/[0.1] hover:border-[#00F2FE]/40 transition-colors">
                  <div className="h-9 w-9 rounded-xl bg-[#00F2FE]/10 border border-[#00F2FE]/25 flex items-center justify-center text-[#00F2FE]">
                    <Activity className="h-4 w-4" />
                  </div>
                  <div className="space-y-1">
                    <span className="text-[10px] font-mono uppercase tracking-wider text-[#00F2FE]">
                      Demand Engine
                    </span>
                    <h3 className="text-sm font-semibold text-white">
                      Champion Forecasting
                    </h3>
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    {meta.model_architecture.demand_models}
                  </p>
                </div>
              </TiltCard>

              <TiltCard className="h-full">
                <div className="glass-surface h-full rounded-2xl p-6 space-y-3 border border-white/[0.1] hover:border-[#A855F7]/40 transition-colors">
                  <div className="h-9 w-9 rounded-xl bg-[#A855F7]/10 border border-[#A855F7]/25 flex items-center justify-center text-[#A855F7]">
                    <Compass className="h-4 w-4" />
                  </div>
                  <div className="space-y-1">
                    <span className="text-[10px] font-mono uppercase tracking-wider text-[#A855F7]">
                      Lead-Time Engine
                    </span>
                    <h3 className="text-sm font-semibold text-white">
                      Uncertainty Calibration
                    </h3>
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    {meta.model_architecture.lead_time_model}
                  </p>
                </div>
              </TiltCard>

              <TiltCard className="h-full">
                <div className="glass-surface h-full rounded-2xl p-6 space-y-3 border border-white/[0.1] hover:border-[#EC4899]/40 transition-colors">
                  <div className="h-9 w-9 rounded-xl bg-[#EC4899]/10 border border-[#EC4899]/25 flex items-center justify-center text-[#EC4899]">
                    <Box className="h-4 w-4" />
                  </div>
                  <div className="space-y-1">
                    <span className="text-[10px] font-mono uppercase tracking-wider text-[#EC4899]">
                      Decision Layer
                    </span>
                    <h3 className="text-sm font-semibold text-white">
                      Pure Arithmetic Policy
                    </h3>
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    {meta.model_architecture.decision_engine}
                  </p>
                </div>
              </TiltCard>
            </div>
          </section>

          {/* PRIMITIVE 3: Reveal (Scroll-Triggered Staggered Animations) */}
          <section className="space-y-4">
            <div className="flex items-center justify-between border-b border-white/[0.06] pb-2">
              <div className="flex items-center gap-2 text-sm font-semibold text-white">
                <Sparkles className="h-4 w-4 text-[#EC4899]" />
                <span>3. Reveal Primitive — Scroll-Triggered Staggered Entry</span>
              </div>
              <span className="text-[11px] font-mono text-zinc-400">
                Staggered cubic curves • Directional entry
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Reveal direction="up" staggerIndex={0}>
                <div className="glass-surface rounded-2xl p-5 space-y-2 border border-white/[0.08]">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-[#00F2FE]">
                    Policy Parameter
                  </span>
                  <div className="text-base font-semibold text-white">
                    Target Service Level: {(meta.policy_assumptions.service_level * 100).toFixed(1)}%
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    Standard normal quantile Z = {meta.policy_assumptions.z_score.toFixed(3)} ensuring 95% cycle-service level during lead times.
                  </p>
                </div>
              </Reveal>

              <Reveal direction="up" staggerIndex={1}>
                <div className="glass-surface rounded-2xl p-5 space-y-2 border border-white/[0.08]">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-[#10B981]">
                    Review Cycle
                  </span>
                  <div className="text-base font-semibold text-white">
                    Review Period: {meta.policy_assumptions.review_period_days} Days (Weekly)
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    Target cover duration of {meta.policy_assumptions.cover_days_target} days with fixed ordering cost of ${meta.policy_assumptions.ordering_cost_fixed.toFixed(2)}.
                  </p>
                </div>
              </Reveal>

              <Reveal direction="up" staggerIndex={2}>
                <div className="glass-surface rounded-2xl p-5 space-y-2 border border-white/[0.08]">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-[#A855F7]">
                    Triage Distribution
                  </span>
                  <div className="text-base font-semibold text-white">
                    OK: {meta.status_summary.OK} • REORDER: {meta.status_summary.REORDER} • CRITICAL: {meta.status_summary.CRITICAL}
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    Categorization across all 75 pairs based on days of stock remaining relative to lead time.
                  </p>
                </div>
              </Reveal>

              <Reveal direction="up" staggerIndex={3}>
                <div className="glass-surface rounded-2xl p-5 space-y-2 border border-white/[0.08]">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-[#F59E0B]">
                    Holding Economics
                  </span>
                  <div className="text-base font-semibold text-white">
                    Annual Holding Cost: {(meta.policy_assumptions.holding_cost_annual_rate * 100).toFixed(0)}%
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    Default unit cost ${meta.policy_assumptions.default_unit_cost.toFixed(2)} based on verified assumptions in <code>configs/assumptions.yaml</code>.
                  </p>
                </div>
              </Reveal>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
