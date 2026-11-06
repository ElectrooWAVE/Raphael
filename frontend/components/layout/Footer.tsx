"use client";

import React from "react";
import Link from "next/link";
import { Sparkles, Terminal } from "lucide-react";

export function Footer() {
  const isDev = process.env.NODE_ENV === "development";

  return (
    <footer className="w-full border-t border-white/[0.08] bg-[#000000] py-10 px-4 sm:px-6 lg:px-8 mt-auto">
      <div className="mx-auto max-w-6xl flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-zinc-500">
        <div className="space-y-1 text-center sm:text-left">
          <div className="flex items-center justify-center sm:justify-start gap-2 text-zinc-300 font-medium">
            <span className="text-[#00F2FE]">Raphael</span>
            <span className="text-zinc-600">•</span>
            <span>Materials Demand Forecasting &amp; Replenishment Engine</span>
          </div>
          <p className="text-[11px] text-zinc-500">
            Demand: M5 retail benchmark relabelled as materials. Lead times and current stock: synthetic.
          </p>
        </div>

        <div className="flex items-center gap-4 text-[11px] font-mono">
          {isDev && (
            <div className="flex items-center gap-2 pr-2 border-r border-white/[0.08]">
              <Link href="/lab/3d" className="hover:text-[#00F2FE] transition-colors">
                3D Lab
              </Link>
              <Link href="/lab/motion" className="hover:text-[#A855F7] transition-colors">
                Motion Lab
              </Link>
            </div>
          )}
          {isDev && (
            <>
              <span className="text-zinc-400">Phase 7 Step 6</span>
              <span className="text-zinc-600">|</span>
            </>
          )}
          <span className="text-zinc-400">Next.js 16 • React 19 • Lenis • GSAP</span>
        </div>
      </div>
    </footer>
  );
}
