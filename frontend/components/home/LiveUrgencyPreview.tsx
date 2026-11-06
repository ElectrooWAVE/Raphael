"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { GlassCard } from "@/components/ui/GlassCard";
import { api, type UrgencyItem, type ForecastDataPoint } from "@/lib/api";
import { AlertTriangle, ArrowRight, Clock, Package, Sparkles } from "lucide-react";

export function LiveUrgencyPreview() {
  const [urgentItem, setUrgentItem] = useState<UrgencyItem | null>(null);
  const [forecastPoints, setForecastPoints] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [chartDrawn, setChartDrawn] = useState<boolean>(false);

  useEffect(() => {
    let isMounted = true;

    api
      .getUrgency()
      .then((urgRes) => {
        if (!isMounted) return;
        const topItem = urgRes.items?.[0] || null;
        setUrgentItem(topItem);

        if (topItem) {
          return api.getForecast(topItem.material, topItem.area);
        }
        return null;
      })
      .then((fRes: any) => {
        if (!isMounted || !fRes) return;
        const pts = fRes.forecast_90d || fRes.points || [];
        setForecastPoints(pts.slice(0, 28)); // Next 28 days
        setIsLoading(false);
        setTimeout(() => setChartDrawn(true), 150);
      })
      .catch((err) => {
        console.error("Live preview load failed:", err);
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  // Compute SVG coordinates for the mini chart
  const points = forecastPoints;
  const maxY = points.length > 0 ? Math.max(...points.map((p) => (p.yhat_upper_80 ?? p.yhat_upper ?? p.yhat))) * 1.15 : 10;
  const minY = 0;
  const W = 460;
  const H = 140;
  const padX = 16;
  const padY = 16;

  const getX = (idx: number) => padX + (idx / Math.max(1, points.length - 1)) * (W - 2 * padX);
  const getY = (val: number) => H - padY - ((val - minY) / (maxY - minY || 1)) * (H - 2 * padY);

  // Line path for forecast yhat
  const linePath = points.length > 0
    ? points.map((p, i) => `${i === 0 ? "M" : "L"} ${getX(i).toFixed(1)} ${getY(p.yhat).toFixed(1)}`).join(" ")
    : "";

  // Area band for [yhat_lower_80, yhat_upper_80]
  const upperPath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${getX(i).toFixed(1)} ${getY(p.yhat_upper_80 ?? p.yhat_upper ?? p.yhat).toFixed(1)}`).join(" ");
  const lowerPath = points.slice().reverse().map((p, i) => `L ${getX(points.length - 1 - i).toFixed(1)} ${getY(Math.max(0, p.yhat_lower_80 ?? p.yhat_lower ?? 0)).toFixed(1)}`).join(" ");
  const bandPath = points.length > 0 ? `${upperPath} ${lowerPath} Z` : "";

  const material = urgentItem?.material || "FOODS_3_586";
  const area = urgentItem?.area || "California - CA_1";
  const daysLeft = urgentItem?.days_remaining !== undefined ? urgentItem.days_remaining.toFixed(1) : "3.2";
  const status = urgentItem?.status || "CRITICAL";
  const stock = urgentItem?.current_stock ?? 14;
  const rop = urgentItem?.reorder_point_rop ?? 38;

  const isCritical = status === "CRITICAL";

  return (
    <section id="live-urgency" className="relative w-full px-[6vw] sm:px-[8vw] max-w-[1920px] mx-auto py-12 lg:py-16">
      <div className="mb-6 space-y-2">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-mono text-pink-400 bg-pink-500/10 border border-pink-500/20">
          <Clock className="h-3 w-3" />
          <span>Right Now: Live Catalog Triage</span>
        </div>
        <h2 className="text-2xl sm:text-4xl font-medium tracking-tight text-white">
          Active Stockout Risk
        </h2>
        <p className="text-zinc-400 text-sm sm:text-base max-w-xl font-normal leading-relaxed">
          The fleet triage engine identifies pairs with lowest days of stock remaining relative to supplier lead times.
        </p>
      </div>

      <GlassCard className="p-6 sm:p-8">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
          {/* Left Metadata & Metrics */}
          <div className="lg:col-span-6 space-y-5">
            <div className="flex flex-wrap items-center gap-3">
              {/* Status Chip */}
              <span
                className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-semibold tracking-wide ${
                  isCritical
                    ? "bg-rose-500/15 border border-rose-500/30 text-rose-400 shadow-[0_0_16px_rgba(244,63,94,0.3)]"
                    : "bg-amber-500/15 border border-amber-500/30 text-amber-400 shadow-[0_0_16px_rgba(245,158,11,0.3)]"
                }`}
              >
                <span className="h-2 w-2 rounded-full bg-rose-400 animate-pulse" />
                <span>{status}</span>
              </span>

              <span className="text-xs font-mono text-zinc-300">
                Rank #1 Priority
              </span>
            </div>

            <div>
              <h3 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
                {material}
              </h3>
              <p className="text-sm font-mono text-zinc-300 mt-0.5">
                {area}
              </p>
            </div>

            {/* Metric Pills */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-2">
              <div className="p-3 rounded-2xl bg-white/[0.04] border border-white/[0.08]">
                <div className="text-[11px] font-mono text-zinc-300">Days Left</div>
                <div className="text-lg font-bold text-rose-400 mt-0.5">
                  {daysLeft}d
                </div>
              </div>

              <div className="p-3 rounded-2xl bg-white/[0.04] border border-white/[0.08]">
                <div className="text-[11px] font-mono text-zinc-300">On Hand</div>
                <div className="text-lg font-bold text-white mt-0.5">
                  {stock} units
                </div>
              </div>

              <div className="p-3 rounded-2xl bg-white/[0.04] border border-white/[0.08] col-span-2 sm:col-span-1">
                <div className="text-[11px] font-mono text-zinc-300">Reorder Point</div>
                <div className="text-lg font-bold text-amber-300 mt-0.5">
                  {rop} units
                </div>
              </div>
            </div>

            {/* Action Link to Forecast Studio */}
            <div className="pt-2">
              <Link
                href={`/forecast?material=${encodeURIComponent(material)}&area=${encodeURIComponent(area)}`}
                className="inline-flex items-center gap-2 px-6 py-3 rounded-full text-xs sm:text-sm font-semibold text-slate-950 transition-all duration-300 hover:scale-[1.02] active:scale-95 cursor-pointer shadow-[inset_0_1px_0_rgba(255,255,255,0.8),0_0_28px_rgba(80,220,230,0.45)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00F2FE]"
                style={{
                  background:
                    "linear-gradient(90deg, #7FD3D8 0%, #CFF7FA 55%, #F2FEFF 100%)",
                }}
              >
                <span>Open in Forecast Studio</span>
                <ArrowRight className="h-4 w-4 text-slate-900" />
              </Link>
            </div>
          </div>

          {/* Right Mini Forecast SVG Chart (Draws in on entry) */}
          <div className="lg:col-span-6 p-4 rounded-2xl bg-white/[0.02] border border-white/[0.06] relative overflow-hidden">
            <div className="flex items-center justify-between text-xs font-mono text-zinc-400 mb-2 px-1">
              <span>Next 28-Day Demand Path</span>
              <span className="text-[#00F2FE]">80% Calibrated Band</span>
            </div>

            <div className="relative w-full aspect-[16/8] flex items-center justify-center">
              {isLoading ? (
                <div className="text-xs font-mono text-zinc-500 animate-pulse">
                  Loading mini trajectory...
                </div>
              ) : (
                <svg
                  viewBox={`0 0 ${W} ${H}`}
                  className="w-full h-full overflow-visible"
                >
                  <defs>
                    <linearGradient id="bandGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#00F2FE" stopOpacity="0.22" />
                      <stop offset="100%" stopColor="#00F2FE" stopOpacity="0.02" />
                    </linearGradient>
                    <linearGradient id="lineGrad" x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0%" stopColor="#00F2FE" />
                      <stop offset="100%" stopColor="#7DF9E4" />
                    </linearGradient>
                  </defs>

                  {/* Horizontal grid lines */}
                  <line x1={padX} y1={padY} x2={W - padX} y2={padY} stroke="rgba(255,255,255,0.06)" strokeDasharray="3 3" />
                  <line x1={padX} y1={H / 2} x2={W - padX} y2={H / 2} stroke="rgba(255,255,255,0.06)" strokeDasharray="3 3" />
                  <line x1={padX} y1={H - padY} x2={W - padX} y2={H - padY} stroke="rgba(255,255,255,0.10)" />

                  {/* Prediction Interval Band */}
                  {bandPath && (
                    <path
                      d={bandPath}
                      fill="url(#bandGrad)"
                      className="transition-opacity duration-700"
                      style={{ opacity: chartDrawn ? 1 : 0 }}
                    />
                  )}

                  {/* Forecast Line with Draw-In Transition */}
                  {linePath && (
                    <path
                      d={linePath}
                      fill="none"
                      stroke="url(#lineGrad)"
                      strokeWidth="2.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      style={{
                        strokeDasharray: 600,
                        strokeDashoffset: chartDrawn ? 0 : 600,
                        transition: "stroke-dashoffset 1.4s cubic-bezier(0.16, 1, 0.3, 1)",
                        filter: "drop-shadow(0 0 6px rgba(0,242,254,0.5))",
                      }}
                    />
                  )}

                  {/* First point dot */}
                  {points.length > 0 && chartDrawn && (
                    <circle
                      cx={getX(0)}
                      cy={getY(points[0].yhat)}
                      r="4"
                      fill="#00F2FE"
                      className="shadow-[0_0_8px_#00F2FE]"
                    />
                  )}
                </svg>
              )}
            </div>

            <div className="flex items-center justify-between text-[11px] font-mono text-zinc-300 mt-2 px-1">
              <span>Today (Origin)</span>
              <span>+28 Days Horizon</span>
            </div>
          </div>
        </div>
      </GlassCard>
    </section>
  );
}
