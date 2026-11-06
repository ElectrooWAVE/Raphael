"use client";

import React from "react";
import Link from "next/link";
import { ArrowRight, Sparkles } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";

export function FooterCta() {
  return (
    <section id="footer-cta" className="relative w-full px-[6vw] sm:px-[8vw] max-w-[1920px] mx-auto py-20 lg:py-28">
      <GlassCard className="p-8 sm:p-14 text-center relative overflow-hidden flex flex-col items-center justify-center space-y-6">
        {/* Soft cyan & violet ambient glow behind CTA */}
        <div
          className="pointer-events-none absolute -top-10 left-1/2 -translate-x-1/2 w-[600px] h-[300px] rounded-full blur-[100px] opacity-25 -z-10"
          style={{
            background:
              "radial-gradient(ellipse at center, rgba(0, 242, 254, 0.45) 0%, rgba(124, 92, 255, 0.25) 50%, transparent 75%)",
          }}
        />

        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-mono text-[#00F2FE] bg-[#00F2FE]/10 border border-[#00F2FE]/25">
          <Sparkles className="h-3.5 w-3.5 text-[#00F2FE]" />
          <span>Production Ready • 75 Material-Area Catalog</span>
        </div>

        <h2 className="text-3xl sm:text-5xl lg:text-6xl font-medium tracking-tight text-white max-w-3xl leading-[1.08]">
          Ready to eliminate material stockouts?
        </h2>

        <p className="text-zinc-400 text-base sm:text-lg max-w-2xl font-normal leading-relaxed">
          Deterministic safety stock algebra, empirical demand baselines, and calibrated lead-time uncertainty—transparent and auditable.
        </p>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center justify-center gap-4 pt-4">
          <Link
            href="/forecast"
            className="group relative px-8 py-4 rounded-full text-sm sm:text-base font-semibold text-slate-950 transition-all duration-300 hover:scale-[1.02] active:scale-95 cursor-pointer animate-glow-pulse flex items-center gap-2 overflow-hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00F2FE] focus-visible:ring-offset-2 focus-visible:ring-offset-black"
            style={{
              background:
                "linear-gradient(90deg, #7FD3D8 0%, #CFF7FA 55%, #F2FEFF 100%)",
              boxShadow:
                "inset 0 1px 0 rgba(255, 255, 255, 0.85), 0 0 40px rgba(80, 220, 230, 0.55)",
            }}
          >
            {/* Shimmer sweep */}
            <div
              className="pointer-events-none absolute -inset-full w-[200%] h-[200%] bg-gradient-to-r from-transparent via-white/50 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700 ease-out"
              style={{ transform: "skewX(-25deg)" }}
            />
            <span className="relative z-10">Launch Studio</span>
            <ArrowRight className="relative z-10 h-4.5 w-4.5 text-slate-900 group-hover:translate-x-1 transition-transform" />
          </Link>

          <Link
            href="/inventory"
            className="px-8 py-4 rounded-full text-sm sm:text-base font-medium text-zinc-200 bg-black/90 hover:text-white border border-white/25 hover:border-white/55 transition-all duration-200 active:scale-95 cursor-pointer shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60 focus-visible:ring-offset-2 focus-visible:ring-offset-black"
          >
            Open Inventory
          </Link>
        </div>
      </GlassCard>
    </section>
  );
}
