"use client";

import React from "react";
import Link from "next/link";
import { GlassCard } from "@/components/ui/GlassCard";
import { ArrowRight, CheckCircle2, FileText, Info } from "lucide-react";

export function HonestyBlock() {
  const cards = [
    {
      title: "Demand: retail benchmark relabelled as materials",
      subtitle: "Data Provenance",
      description:
        "Daily demand observations are taken from M5 retail series across FOODS, HOBBIES, and HOUSEHOLD departments, serving as stand-ins for a materials catalog. We do not claim actual factory purchase logs.",
      href: "/methodology",
      linkText: "Read Data Provenance",
      badge: "Retail Benchmark",
      badgeColor: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20",
    },
    {
      title: "Lead times and stock: synthetic",
      subtitle: "Simulation Boundary",
      description:
        "Supplier delivery durations, on-hand stock quantities, unit costs, and holding expenses are synthetically simulated with realistic log-normal distributions to exercise the decision layer.",
      href: "/methodology",
      linkText: "View Synthetic Setup",
      badge: "Synthetic Data",
      badgeColor: "bg-amber-500/10 text-amber-400 border-amber-500/20",
    },
    {
      title: "Simple model won the tournament",
      subtitle: "Empirical Finding",
      description:
        "In our rolling-origin cross-validation and 84-day held-out fleet tournament, the simple Weekday Mean 8W baseline achieved 30.5% weekly pooled WAPE, beating complex seasonal and ML contenders.",
      href: "/telemetry",
      linkText: "Inspect Tournament Leaderboard",
      badge: "Held-out Truth",
      badgeColor: "bg-purple-500/10 text-purple-400 border-purple-500/20",
    },
  ];

  return (
    <section id="honesty-block" className="relative w-full px-[6vw] sm:px-[8vw] max-w-[1920px] mx-auto py-12 lg:py-16">
      <div className="mb-6 space-y-2">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-mono text-purple-400 bg-purple-500/10 border border-purple-500/20">
          <Info className="h-3 w-3" />
          <span>Scientific Transparency</span>
        </div>
        <h2 className="text-2xl sm:text-4xl font-medium tracking-tight text-white">
          Honesty &amp; Calibration Boundaries
        </h2>
        <p className="text-zinc-400 text-sm sm:text-base max-w-xl font-normal leading-relaxed">
          Clear disclosures on data provenance, synthetic components, and empirical tournament selection.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {cards.map((c, i) => (
          <GlassCard key={i} className="flex flex-col justify-between space-y-4">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-mono text-zinc-300">
                  {c.subtitle}
                </span>
                <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${c.badgeColor}`}>
                  {c.badge}
                </span>
              </div>

              <h3 className="text-lg font-semibold text-white leading-snug">
                {c.title}
              </h3>

              <p className="text-xs text-zinc-400 leading-relaxed font-normal">
                {c.description}
              </p>
            </div>

            <div className="pt-3 border-t border-white/[0.08]">
              <Link
                href={c.href}
                className="inline-flex items-center gap-1.5 text-xs font-mono text-[#00F2FE] hover:text-[#7DF9E4] transition-colors group focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#00F2FE] rounded"
              >
                <span>{c.linkText}</span>
                <ArrowRight className="h-3.5 w-3.5 group-hover:translate-x-1 transition-transform" />
              </Link>
            </div>
          </GlassCard>
        ))}
      </div>
    </section>
  );
}
