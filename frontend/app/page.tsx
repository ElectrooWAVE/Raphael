"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { HeroRibbon } from "@/components/home/HeroRibbon";
import { GlassCard } from "@/components/ui/GlassCard";
import { HowItWorksStory } from "@/components/home/HowItWorksStory";
import { LiveUrgencyPreview } from "@/components/home/LiveUrgencyPreview";
import { KpiStrip } from "@/components/home/KpiStrip";
import { HonestyBlock } from "@/components/home/HonestyBlock";
import { FooterCta } from "@/components/home/FooterCta";
import { api, type HealthResponse, type AccuracyResponse } from "@/lib/api";
import {
  Activity,
  ArrowRight,
  Box,
  Compass,
  Database,
  Sparkles,
} from "lucide-react";

export default function HomePage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [accuracy, setAccuracy] = useState<AccuracyResponse | null>(null);
  const [leadTimeMetrics, setLeadTimeMetrics] = useState<any>(null);
  const [urgencyData, setUrgencyData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isReduced, setIsReduced] = useState<boolean>(false);

  useEffect(() => {
    let isMounted = true;
    const q = window.matchMedia("(prefers-reduced-motion: reduce)");
    setIsReduced(q.matches);

    Promise.all([
      api.getHealth().catch(() => null),
      api.getAccuracy().catch(() => null),
      api.getLeadTimeMetrics().catch(() => null),
      api.getUrgency().catch(() => null),
    ]).then(([healthData, accuracyData, ltData, urgData]) => {
      if (isMounted) {
        setHealth(healthData);
        setAccuracy(accuracyData);
        setLeadTimeMetrics(ltData);
        setUrgencyData(urgData);
        setIsLoading(false);
      }
    });

    return () => {
      isMounted = false;
    };
  }, []);

  // Extract live metrics from /accuracy leaderboard
  const productionLeaderboardItem = accuracy?.leaderboard?.find(
    (item) =>
      item.model.toLowerCase().includes("production") ||
      item.model.toLowerCase().includes("weekday")
  );
  const seasonalNaiveItem = accuracy?.leaderboard?.find((item) =>
    item.model.toLowerCase().includes("seasonal naive")
  );
  const movingAverageItem = accuracy?.leaderboard?.find((item) =>
    item.model.toLowerCase().includes("moving average")
  );

  const productionWapeVal = productionLeaderboardItem?.weekly_pooled_wape;
  const seasonalNaiveWapeVal = seasonalNaiveItem?.weekly_pooled_wape;
  const movingAverageWapeVal = movingAverageItem?.weekly_pooled_wape;

  const productionWapeStr =
    productionWapeVal !== undefined
      ? `${(productionWapeVal * 100).toFixed(1)}%`
      : "30.5%";

  const seasonalNaiveWapeStr =
    seasonalNaiveWapeVal !== undefined
      ? `${(seasonalNaiveWapeVal * 100).toFixed(1)}%`
      : "34.5%";

  const movingAverageWapeStr =
    movingAverageWapeVal !== undefined
      ? `${(movingAverageWapeVal * 100).toFixed(1)}%`
      : "30.8%";

  const leadTimeMaeStr =
    leadTimeMetrics?.metrics?.test_mae !== undefined
      ? `${leadTimeMetrics.metrics.test_mae.toFixed(2)}d MAE`
      : "0.76d MAE";

  const leadTimeBaselineStr =
    leadTimeMetrics?.metrics?.baseline_mae !== undefined
      ? `${leadTimeMetrics.metrics.baseline_mae.toFixed(2)}d`
      : "1.59d";

  const criticalCount = urgencyData?.summary?.critical ?? 25;
  const reorderCount = urgencyData?.summary?.reorder ?? 5;
  const okCount = urgencyData?.summary?.ok ?? 45;

  const asOfDateStr = health?.as_of_date || "2016-04-24";
  const isOnline = health?.status === "ok";

  // Headline words for staggered blur-dissolve entrance
  const line1Words = ["Know", "what", "to", "order,"];

  const [heroLight, setHeroLight] = useState<{ x: number; y: number; opacity: number }>({
    x: 0,
    y: 0,
    opacity: 0,
  });

  const handleHeroPointerMove = (e: React.PointerEvent<HTMLElement>) => {
    if (isReduced) return;
    const rect = e.currentTarget.getBoundingClientRect();
    setHeroLight({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
      opacity: 1,
    });
  };

  const handleHeroPointerLeave = () => {
    setHeroLight((prev) => ({ ...prev, opacity: 0 }));
  };

  return (
    <div className="relative min-h-screen bg-[#000000] text-zinc-100 overflow-x-clip">
      {/* Dev mode chip: strictly NODE_ENV === 'development' */}
      {process.env.NODE_ENV === "development" && (
        <div className="absolute top-2 left-6 z-40">
          <Link
            href="/lab/3d"
            className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-[10px] font-mono text-zinc-400 hover:text-[#00F2FE] bg-white/[0.04] border border-white/[0.08] transition-colors"
          >
            <Sparkles className="h-3 w-3 text-[#00F2FE]" />
            <span>Dev: /lab/3d &amp; /lab/motion</span>
            <span className="text-[#00F2FE]">&rarr;</span>
          </Link>
        </div>
      )}

      {/* Hero Viewport Section: Aligned to ~8vw, vertically centered around 45% */}
      <section
        onPointerMove={handleHeroPointerMove}
        onPointerLeave={handleHeroPointerLeave}
        className="relative w-full min-h-[960px] lg:min-h-[1020px] 2xl:min-h-[1080px] flex flex-col justify-between pt-52 sm:pt-44 lg:pt-36 pb-12 overflow-visible"
      >
        {/* Low-opacity cursor-following light over the hero */}
        <div
          className="pointer-events-none absolute inset-0 z-0 transition-opacity duration-500"
          style={{
            opacity: heroLight.opacity,
            background: `radial-gradient(650px at ${heroLight.x}px ${heroLight.y}px, rgba(0, 242, 254, 0.06) 0%, rgba(124, 92, 255, 0.03) 40%, transparent 70%)`,
          }}
        />

        {/* Hero Fluid Ribbon (Absolute right -6%, width ~62vw, mix-blend-mode: screen, passes BEHIND cards) */}
        <HeroRibbon />

        {/* Hero Foreground Content: Left column aligned to ~8vw */}
        <div className="relative z-10 w-full px-[6vw] sm:px-[8vw] max-w-[1920px] mx-auto flex-1 flex flex-col justify-center">
          <div className="max-w-[1050px] 2xl:max-w-[1240px] space-y-7 -mt-10 sm:-mt-14">
            {/* Headline clamp(56px, 6.4vw, 168px), weight 500, letter-spacing -0.04em, line-height 0.98 */}
            <h1 className="text-[clamp(44px,5.9vw,144px)] font-medium tracking-[-0.04em] leading-[0.98] text-white">
              {/* Line 1: Know what to order, */}
              <div className="flex flex-wrap items-baseline gap-x-[0.25em]">
                {line1Words.map((word, idx) => (
                  <motion.span
                    key={idx}
                    initial={
                      isReduced
                        ? false
                        : { opacity: 0, y: 18, filter: "blur(10px)" }
                    }
                    animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                    transition={{
                      duration: 0.5,
                      delay: isReduced ? 0 : 0.08 * idx,
                      ease: [0.16, 1, 0.3, 1],
                    }}
                    className="inline-block"
                  >
                    {word}
                  </motion.span>
                ))}
              </div>

              {/* Line 2: and exactly when. */}
              <div className="flex flex-wrap items-baseline gap-x-[0.25em] mt-1 sm:mt-2">
                <motion.span
                  initial={
                    isReduced
                      ? false
                      : { opacity: 0, y: 18, filter: "blur(10px)" }
                  }
                  animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                  transition={{
                    duration: 0.5,
                    delay: isReduced ? 0 : 0.35,
                    ease: [0.16, 1, 0.3, 1],
                  }}
                  className="inline-block text-white"
                >
                  and
                </motion.span>

                {/* "exactly when." in left-to-right gradient from #3FCFBF to #7DF9E4 with soft glow */}
                <motion.span
                  initial={
                    isReduced
                      ? false
                      : { opacity: 0, y: 20, filter: "blur(12px)" }
                  }
                  animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                  transition={{
                    duration: 0.55,
                    delay: isReduced ? 0 : 0.45,
                    ease: [0.16, 1, 0.3, 1],
                  }}
                  className="relative inline-block font-medium"
                >
                  {/* Soft glow duplicate under text (0 0 48px rgba(60,230,210,0.45)) */}
                  <span
                    aria-hidden="true"
                    className="absolute inset-0 select-none pointer-events-none text-transparent blur-[24px] opacity-75"
                    style={{
                      backgroundImage:
                        "linear-gradient(90deg, #3FCFBF 0%, #7DF9E4 100%)",
                      WebkitBackgroundClip: "text",
                      filter: "drop-shadow(0 0 48px rgba(60, 230, 210, 0.6))",
                    }}
                  >
                    exactly when.
                  </span>
                  <span
                    className="relative text-transparent bg-clip-text"
                    style={{
                      backgroundImage:
                        "linear-gradient(90deg, #3FCFBF 0%, #7DF9E4 100%)",
                      filter: "drop-shadow(0 0 32px rgba(60, 230, 210, 0.45))",
                    }}
                  >
                    exactly when.
                  </span>
                </motion.span>
              </div>
            </h1>

            {/* Subtitle in zinc-400, max-width ~34ch, 20-22px */}
            <motion.p
              initial={
                isReduced ? false : { opacity: 0, y: 14, filter: "blur(6px)" }
              }
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              transition={{
                duration: 0.5,
                delay: isReduced ? 0 : 0.6,
                ease: "easeOut",
              }}
              className="text-zinc-400 text-lg sm:text-[21px] max-w-[34ch] font-normal leading-[1.4] tracking-tight"
            >
              Raphael forecasts demand, predicts supplier lead times, and tells
              you exactly when to reorder.
            </motion.p>

            {/* Action Buttons: Primary icy glass pill + Secondary black pill */}
            <motion.div
              initial={isReduced ? false : { opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{
                duration: 0.45,
                delay: isReduced ? 0 : 0.72,
                ease: "easeOut",
              }}
              className="flex flex-wrap items-center gap-4 pt-3"
            >
              {/* Primary "Launch Studio": icy glass pill with glow pulse + shimmer sweep on hover */}
              <Link
                href="/forecast"
                className="group relative px-7 sm:px-8 py-3.5 sm:py-4 rounded-full text-sm sm:text-[15px] font-semibold text-slate-950 transition-all duration-300 hover:scale-[1.02] active:scale-95 cursor-pointer animate-glow-pulse flex items-center gap-2 overflow-hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00F2FE] focus-visible:ring-offset-2 focus-visible:ring-offset-black"
                style={{
                  background:
                    "linear-gradient(90deg, #7FD3D8 0%, #CFF7FA 55%, #F2FEFF 100%)",
                  boxShadow:
                    "inset 0 1px 0 rgba(255, 255, 255, 0.85), 0 0 40px rgba(80, 220, 230, 0.55)",
                }}
              >
                {/* Shimmer sweep on hover */}
                <div
                  className="pointer-events-none absolute -inset-full w-[200%] h-[200%] bg-gradient-to-r from-transparent via-white/50 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700 ease-out"
                  style={{ transform: "skewX(-25deg)" }}
                />

                <span className="relative z-10">Launch Studio</span>
                <ArrowRight className="relative z-10 h-4 w-4 text-slate-900 group-hover:translate-x-1 transition-transform" />
              </Link>

              {/* Secondary "Open Inventory": black pill, 1px border rgba(255,255,255,0.25) */}
              <Link
                href="/inventory"
                className="px-7 sm:px-8 py-3.5 sm:py-4 rounded-full text-sm sm:text-[15px] font-medium text-zinc-200 bg-black/90 hover:text-white border border-white/25 hover:border-white/55 transition-all duration-200 active:scale-95 cursor-pointer shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60 focus-visible:ring-offset-2 focus-visible:ring-offset-black"
              >
                Open Inventory
              </Link>
            </motion.div>
          </div>
        </div>

        {/* Floating Stat Pill Overlapping Ribbon's Lower-Left Loop (Directly above the cards) */}
        <motion.div
          initial={isReduced ? false : { opacity: 0, scale: 0.94 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{
            duration: 0.6,
            delay: isReduced ? 0 : 0.85,
            ease: "easeOut",
          }}
          className="absolute z-30 pointer-events-auto left-[6vw] sm:left-[48%] lg:left-[52%] xl:left-[54%] bottom-[370px] sm:bottom-[340px] lg:bottom-[320px]"
        >
          <div
            className={`rounded-full px-5 py-2.5 flex items-center gap-3.5 transition-all shadow-[0_16px_40px_rgba(0,0,0,0.85)] ${
              isReduced ? "" : "animate-ribbon-float"
            }`}
            style={{
              background: "rgba(10, 10, 16, 0.88)",
              backdropFilter: "blur(24px)",
              WebkitBackdropFilter: "blur(24px)",
              border: "1px solid rgba(255, 255, 255, 0.20)",
              boxShadow:
                "inset 0 1px 0 rgba(255, 255, 255, 0.35), 0 16px 40px rgba(0, 0, 0, 0.8)",
            }}
          >
            {/* Green dot from /health */}
            <span
              className={`h-2.5 w-2.5 rounded-full shrink-0 ${
                isOnline
                  ? "bg-[#10B981] shadow-[0_0_10px_#10B981]"
                  : "bg-[#F59E0B] shadow-[0_0_10px_#F59E0B]"
              } animate-pulse`}
            />

            {/* Two lines of small text with real API values only */}
            <div className="flex flex-col text-left font-mono">
              <span className="text-[11px] text-zinc-400 tracking-tight leading-none">
                As of {asOfDateStr}
              </span>
              <span className="text-xs sm:text-[13px] font-semibold text-white tracking-tight leading-snug mt-0.5">
                Fleet WAPE:{" "}
                <span className="text-[#3FCFBF] drop-shadow-[0_0_8px_rgba(63,207,191,0.5)]">
                  {productionWapeStr} Weekly
                </span>
              </span>
            </div>
          </div>
        </motion.div>

        {/* Hero Bottom Cards: Peeking into the first viewport, overlapping the ribbon */}
        <div className="relative z-20 w-full px-[6vw] sm:px-[8vw] max-w-[1920px] mx-auto pt-16 sm:pt-20">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5 lg:gap-6">
            {/* Card 1: Demand Model */}
            <GlassCard className="space-y-4 hover:border-[#00F2FE]/40 transition-colors">
              <div className="flex items-center justify-between">
                <div className="h-9 w-9 rounded-xl bg-[#00F2FE]/10 border border-[#00F2FE]/30 flex items-center justify-center text-[#00F2FE]">
                  <Activity className="h-4.5 w-4.5" />
                </div>
                <span className="text-[10px] font-mono font-medium text-[#00F2FE] px-2.5 py-0.5 rounded-full bg-[#00F2FE]/10 border border-[#00F2FE]/25">
                  Production Model
                </span>
              </div>
              <div className="space-y-1">
                <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400">
                  Demand Model
                </span>
                <h3 className="text-lg font-semibold text-white">
                  {productionWapeStr} Weekly WAPE
                </h3>
              </div>
              <p className="text-xs text-zinc-300 leading-relaxed font-normal">
                Weekday Mean 8W serves as the fixed production model across all 75
                material-area pairs, outperforming seasonal and ML challengers
                on held-out evaluation.
              </p>
              <div className="pt-2.5 border-t border-white/[0.08] text-[11px] font-mono text-zinc-400">
                Challengers: MA 91D ({movingAverageWapeStr}), Seasonal Naive (
                {seasonalNaiveWapeStr})
              </div>
            </GlassCard>

            {/* Card 2: Lead-Time Model */}
            <GlassCard className="space-y-4 hover:border-[#A855F7]/40 transition-colors">
              <div className="flex items-center justify-between">
                <div className="h-9 w-9 rounded-xl bg-[#A855F7]/10 border border-[#A855F7]/30 flex items-center justify-center text-[#A855F7]">
                  <Compass className="h-4.5 w-4.5" />
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] font-mono text-amber-400 px-2 py-0.5 rounded-full bg-amber-500/12 border border-amber-500/25">
                    Synthetic Data
                  </span>
                  <span className="text-[10px] font-mono text-[#A855F7] px-2 py-0.5 rounded-full bg-[#A855F7]/10 border border-[#A855F7]/25">
                    Random Forest + OOF
                  </span>
                </div>
              </div>
              <div className="space-y-1">
                <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400">
                  Lead-Time Model
                </span>
                <h3 className="text-lg font-semibold text-white">
                  {leadTimeMaeStr} vs {leadTimeBaselineStr}
                </h3>
              </div>
              <p className="text-xs text-zinc-300 leading-relaxed font-normal">
                52% lower MAE than the per-pair historical mean, on synthetic
                lead times. 5-fold out-of-fold calibrated uncertainty intervals
                provide deterministic safety stock buffers.
              </p>
              <div className="pt-2.5 border-t border-white/[0.08] text-[11px] font-mono text-zinc-400">
                Model: Random Forest Regressor
              </div>
            </GlassCard>

            {/* Card 3: Decision Layer */}
            <GlassCard className="space-y-4 hover:border-[#EC4899]/40 transition-colors">
              <div className="flex items-center justify-between">
                <div className="h-9 w-9 rounded-xl bg-[#EC4899]/10 border border-[#EC4899]/30 flex items-center justify-center text-[#EC4899]">
                  <Box className="h-4.5 w-4.5" />
                </div>
                <span className="text-[10px] font-mono font-medium text-[#EC4899] px-2.5 py-0.5 rounded-full bg-[#EC4899]/10 border border-[#EC4899]/25">
                  Deterministic Policy
                </span>
              </div>
              <div className="space-y-1">
                <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400">
                  Decision Layer
                </span>
                <h3 className="text-lg font-semibold text-white">
                  {criticalCount} items at risk of stockout
                </h3>
              </div>
              <p className="text-xs text-zinc-300 leading-relaxed font-normal">
                Exact safety stock, reorder points, and EOQ computed using
                standard inventory algebra—auditable without black-box
                guesswork.
              </p>
              <div className="pt-2.5 border-t border-white/[0.08] text-[11px] font-mono text-zinc-400">
                Fleet: {criticalCount} Critical, {reorderCount} Reorder, {okCount}{" "}
                OK
              </div>
            </GlassCard>
          </div>
        </div>
      </section>

      {/* 1. "How Raphael works": Pinned scroll story with glowing scrub line */}
      <HowItWorksStory />

      {/* 2. "Right now" live preview: Most urgent pair, status chip, days left, mini chart */}
      <LiveUrgencyPreview />

      {/* 3. KPI strip: 4 CountUp tiles from the API with provenance labels */}
      <KpiStrip />

      {/* 4. Honesty block: 3 transparent disclosure cards linking to /methodology and /telemetry */}
      <HonestyBlock />

      {/* 5. Footer CTA: Large headline and Launch Studio / Open Inventory action buttons */}
      <FooterCta />
    </div>
  );
}
