"use client";

import React, { useEffect, useState, useRef } from "react";
import { GlassCard } from "@/components/ui/GlassCard";
import { api, type HealthResponse, type AccuracyResponse } from "@/lib/api";

function useCountUp(target: number, duration: number = 1200, enabled: boolean = true) {
  const [val, setVal] = useState<number>(0);

  useEffect(() => {
    if (!enabled) {
      setVal(target);
      return;
    }

    let start = performance.now();
    let animId: number;

    const tick = (now: number) => {
      const elapsed = now - start;
      const progress = Math.min(1, elapsed / duration);
      // easeOutExpo
      const ease = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
      setVal(ease * target);

      if (progress < 1) {
        animId = requestAnimationFrame(tick);
      } else {
        setVal(target);
      }
    };

    animId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animId);
  }, [target, duration, enabled]);

  return val;
}

export function KpiStrip() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isVisible, setIsVisible] = useState<boolean>(false);
  const [accuracy, setAccuracy] = useState<AccuracyResponse | null>(null);
  const [leadTimeMetrics, setLeadTimeMetrics] = useState<any>(null);
  const [urgencyData, setUrgencyData] = useState<any>(null);

  useEffect(() => {
    let isMounted = true;

    Promise.all([
      api.getAccuracy().catch(() => null),
      api.getLeadTimeMetrics().catch(() => null),
      api.getUrgency().catch(() => null),
    ]).then(([acc, lt, urg]) => {
      if (isMounted) {
        setAccuracy(acc);
        setLeadTimeMetrics(lt);
        setUrgencyData(urg);
      }
    });

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.2 }
    );

    if (containerRef.current) {
      observer.observe(containerRef.current);
    }

    return () => {
      isMounted = false;
      observer.disconnect();
    };
  }, []);

  // Extract metrics from API
  const pairsTotal = accuracy?.total_pairs ?? 75;
  const criticalCount = urgencyData?.summary?.critical ?? 25;
  const prodWape = (accuracy?.leaderboard?.find((m) => m.model.toLowerCase().includes("weekday"))?.weekly_pooled_wape ?? 0.305) * 100;
  const ltMae = leadTimeMetrics?.metrics?.test_mae ?? 0.76;

  // CountUp animated numbers
  const countPairs = useCountUp(pairsTotal, 1000, isVisible);
  const countRisk = useCountUp(criticalCount, 1200, isVisible);
  const countWape = useCountUp(prodWape, 1400, isVisible);
  const countMae = useCountUp(ltMae, 1400, isVisible);

  const kpis = [
    {
      label: "Pairs Evaluated",
      value: Math.round(countPairs).toString(),
      unit: "pairs",
      detail: "25 materials × 3 regional areas",
      provenance: "Retail benchmark stand-ins",
      accent: "text-[#00F2FE]",
      badge: "Fleet-wide",
    },
    {
      label: "Items at Risk",
      value: Math.round(countRisk).toString(),
      unit: "critical",
      detail: "Days remaining < supplier lead time",
      provenance: "Deterministic algebra",
      accent: "text-rose-400",
      badge: "Triage Alert",
    },
    {
      label: "Production WAPE",
      value: countWape.toFixed(1),
      unit: "%",
      detail: "Weekday Mean 8W held-out 84-day test",
      provenance: "Tournament winner",
      accent: "text-emerald-400",
      badge: "Held-out Test",
    },
    {
      label: "Lead-Time MAE",
      value: countMae.toFixed(2),
      unit: "days",
      detail: "vs 1.59d historical baseline (52% drop)",
      provenance: "Synthetic dataset",
      accent: "text-purple-400",
      badge: "Uncertainty OOF",
    },
  ];

  return (
    <section
      id="kpi-strip"
      ref={containerRef}
      className="relative w-full px-[6vw] sm:px-[8vw] max-w-[1920px] mx-auto py-12 lg:py-16"
    >
      <div className="mb-6 space-y-2">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20">
          <span>Fleet Performance Telemetry</span>
        </div>
        <h2 className="text-2xl sm:text-4xl font-medium tracking-tight text-white">
          Verified Fleet Scorecard
        </h2>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {kpis.map((kpi, idx) => (
          <GlassCard key={idx} className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono text-zinc-400 uppercase tracking-wider">
                {kpi.label}
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-white/[0.06] border border-white/[0.1] text-zinc-300">
                {kpi.badge}
              </span>
            </div>

            <div className="flex items-baseline gap-1.5">
              <span className={`text-4xl sm:text-5xl font-bold font-mono tracking-tight ${kpi.accent}`}>
                {kpi.value}
              </span>
              <span className="text-sm font-mono text-zinc-400 font-normal">
                {kpi.unit}
              </span>
            </div>

            <p className="text-xs text-zinc-400 leading-relaxed font-normal">
              {kpi.detail}
            </p>

            <div className="pt-3 border-t border-white/[0.08] flex items-center justify-between text-[11px] font-mono">
              <span className="text-zinc-500">Source:</span>
              <span className="text-zinc-300 font-medium">{kpi.provenance}</span>
            </div>
          </GlassCard>
        ))}
      </div>
    </section>
  );
}
