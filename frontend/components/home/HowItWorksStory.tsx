"use client";

import React, { useEffect, useRef, useState } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { GlassCard } from "@/components/ui/GlassCard";
import { Database, LineChart, Compass, ShieldCheck } from "lucide-react";

interface StepItem {
  num: string;
  phase: string;
  title: string;
  subtitle: string;
  description: string;
  metrics: string;
  tag: "Arithmetic" | "ML";
  syntheticTag?: string;
  badgeClass: string;
  icon: React.ElementType;
}

export function HowItWorksStory() {
  const containerRef = useRef<HTMLDivElement>(null);
  const pinSectionRef = useRef<HTMLDivElement>(null);
  const lineProgressRef = useRef<HTMLDivElement>(null);
  const [activeStep, setActiveStep] = useState<number>(0);
  const [isReduced, setIsReduced] = useState<boolean>(false);

  const steps: StepItem[] = [
    {
      num: "01",
      phase: "Data",
      title: "Data Foundation",
      subtitle: "75 Material-Area Catalog",
      description:
        "75 material-area pairs spanning 3 regional hubs (CA, TX, WI) and 25 retail SKUs from FOODS, HOBBIES, and HOUSEHOLD used as stand-ins for materials.",
      metrics: "75 Pairs • 3 Regional Hubs",
      tag: "Arithmetic",
      badgeClass: "bg-cyan-500/10 text-cyan-400 border-cyan-500/25",
      icon: Database,
    },
    {
      num: "02",
      phase: "Demand model",
      title: "Demand Model",
      subtitle: "Weekday Mean 8W Tournament Champion",
      description:
        "Fixed 8-week weekday mean baseline selected through rigorous rolling-origin validation. 30.5% weekly pooled WAPE across 84 held-out evaluation days, beating seasonal and ML challengers.",
      metrics: "30.5% Weekly WAPE • 84d Held-Out",
      tag: "Arithmetic",
      badgeClass: "bg-emerald-500/10 text-emerald-400 border-emerald-500/25",
      icon: LineChart,
    },
    {
      num: "03",
      phase: "Lead-time model",
      title: "Lead-Time Model",
      subtitle: "Calibrated Uncertainty Regressor",
      description:
        "Random Forest Regressor trained on synthetic supplier delivery logs. Achieves 0.76d MAE vs 1.59d historical baseline (52% drop), with 5-fold out-of-fold calibration for safety buffers.",
      metrics: "0.76d MAE vs 1.59d Baseline",
      tag: "ML",
      syntheticTag: "Synthetic",
      badgeClass: "bg-purple-500/10 text-purple-400 border-purple-500/25",
      icon: Compass,
    },
    {
      num: "04",
      phase: "Reorder decision",
      title: "Reorder Decision",
      subtitle: "Deterministic Replenishment Algebra",
      description:
        "Exact inventory algebra calculates safety stock, reorder point (ROP), and EOQ without black-box guesswork. Current fleet triage: 25 Critical, 5 Reorder, 45 OK.",
      metrics: "25 Critical • 5 Reorder • 45 OK",
      tag: "Arithmetic",
      badgeClass: "bg-pink-500/10 text-pink-400 border-pink-500/25",
      icon: ShieldCheck,
    },
  ];

  useEffect(() => {
    const q = window.matchMedia("(prefers-reduced-motion: reduce)");
    setIsReduced(q.matches);

    if (q.matches || window.innerWidth < 1024) {
      return;
    }

    gsap.registerPlugin(ScrollTrigger);

    const pinSection = pinSectionRef.current;
    const container = containerRef.current;
    if (!pinSection || !container) return;

    // Pin desktop container and scrub glowing progress line + step index
    const trigger = ScrollTrigger.create({
      trigger: container,
      start: "top top+=110",
      end: "+=1600",
      pin: pinSection,
      pinType: "transform",
      scrub: 0.3,
      onUpdate: (self) => {
        const p = self.progress;
        if (lineProgressRef.current) {
          lineProgressRef.current.style.height = `${Math.min(100, Math.max(0, p * 100))}%`;
        }
        const currentIdx = Math.min(3, Math.floor(p * 4));
        setActiveStep(currentIdx);
      },
    });

    return () => {
      trigger.kill();
    };
  }, []);

  const handleStepClick = (index: number) => {
    setActiveStep(index);
    if (typeof window !== "undefined" && containerRef.current && window.innerWidth >= 1024 && !isReduced) {
      const containerTop = containerRef.current.getBoundingClientRect().top + window.scrollY;
      const targetScroll = containerTop - 110 + (index / 4) * 1600 + 40;
      const lenis = (window as unknown as { __lenis?: { scrollTo: (t: number) => void } }).__lenis;
      if (lenis) {
        lenis.scrollTo(targetScroll);
      } else {
        window.scrollTo({ top: targetScroll, behavior: "smooth" });
      }
    }
  };

  return (
    <section
      id="how-it-works"
      ref={containerRef}
      className="relative w-full px-[6vw] sm:px-[8vw] max-w-[1920px] mx-auto py-16 lg:py-24"
    >
      <div ref={pinSectionRef} className="w-full">
        {/* Section Header */}
        <div className="mb-8 lg:mb-10 space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-mono text-cyan-400 bg-cyan-500/10 border border-cyan-500/25">
            <span>Deterministic Architecture</span>
          </div>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-medium tracking-tight text-white">
            How Raphael Works
          </h2>
          <p className="text-zinc-400 text-sm sm:text-base max-w-2xl font-normal leading-relaxed">
            From raw demand history to purchase order recommendations: a four-stage pipeline governed by verified algebra and empirical evaluation.
          </p>
        </div>

        {/* Story Grid: Left Scrubbed Nav Line + Right Interactive Step Cards */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-start">
          {/* Left Guide Column (Desktop Scrubbed Line) */}
          <div className="hidden lg:flex lg:col-span-4 flex-col justify-between py-2 relative pl-6 border-l border-white/[0.08] min-h-[460px]">
            {/* Glowing Drawn Progress Line */}
            <div
              ref={lineProgressRef}
              className="absolute left-[-1px] top-0 w-[2px] bg-gradient-to-b from-[#00F2FE] via-[#7C5CFF] to-[#EC4899] shadow-[0_0_12px_#00F2FE] transition-all duration-75"
              style={{ height: "0%" }}
            />

            {steps.map((st, i) => {
              const isActive = activeStep === i;
              return (
                <div
                  key={st.num}
                  className={`transition-all duration-300 py-2.5 cursor-pointer select-none ${
                    isActive
                      ? "opacity-100 translate-x-2"
                      : "opacity-40 hover:opacity-75"
                  }`}
                  onClick={() => handleStepClick(i)}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-mono tracking-wider text-[#00F2FE]">
                      STEP {st.num}
                    </span>
                    {isActive && (
                      <span className="h-1.5 w-1.5 rounded-full bg-[#00F2FE] shadow-[0_0_6px_#00F2FE]" />
                    )}
                  </div>
                  <div
                    className={`text-base lg:text-lg font-medium transition-colors ${
                      isActive ? "text-white" : "text-zinc-400"
                    }`}
                  >
                    {st.title}
                  </div>
                  <div className="text-xs text-zinc-400 font-mono mt-0.5">
                    {st.metrics}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Right Cards Column: 4 compact, interactive glass cards */}
          <div
            className="lg:col-span-8 flex flex-col gap-3.5 transition-transform duration-500 ease-out"
            style={{
              transform:
                typeof window !== "undefined" && !isReduced
                  ? `translateY(-${activeStep * 52}px)`
                  : "none",
            }}
          >
            {steps.map((st, i) => {
              const isActive = isReduced || activeStep === i;
              const Icon = st.icon;

              return (
                <div
                  key={st.num}
                  onClick={() => handleStepClick(i)}
                  className={`transition-all duration-300 cursor-pointer ${
                    isReduced
                      ? "opacity-100"
                      : isActive
                      ? "opacity-100 translate-x-1 ring-1 ring-white/20 shadow-[0_16px_36px_rgba(0,0,0,0.7)]"
                      : "opacity-40 hover:opacity-65"
                  }`}
                >
                  <GlassCard className="p-4 sm:p-5 transition-all">
                    <div className="flex flex-wrap items-center justify-between gap-2.5">
                      <div className="flex items-center gap-3">
                        <div className="h-8 w-8 sm:h-9 sm:w-9 rounded-xl bg-white/[0.06] border border-white/[0.12] flex items-center justify-center text-white shrink-0">
                          <Icon className="h-4 w-4 text-[#00F2FE]" />
                        </div>
                        <div>
                          <div className="text-[10px] font-mono text-zinc-400 uppercase tracking-wider">
                            Step {st.num} • {st.phase}
                          </div>
                          <h3 className="text-sm sm:text-base font-semibold text-white">
                            {st.title}
                          </h3>
                        </div>
                      </div>

                      {/* Honest Labels: ML / Arithmetic + Synthetic */}
                      <div className="flex items-center gap-2">
                        {st.syntheticTag && (
                          <span className="text-[10px] font-mono text-amber-400 px-2.5 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/25">
                            {st.syntheticTag}
                          </span>
                        )}
                        <span
                          className={`text-[10px] font-mono font-medium px-2.5 py-0.5 rounded-full border ${st.badgeClass}`}
                        >
                          {st.tag}
                        </span>
                      </div>
                    </div>

                    {/* Description & Real Facts */}
                    <div className="mt-2.5 pt-2.5 border-t border-white/[0.06] flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                      <p className="text-zinc-300 font-normal leading-relaxed max-w-xl">
                        {st.description}
                      </p>
                      <div className="font-mono text-[11px] text-zinc-400 shrink-0 bg-white/[0.03] px-2.5 py-1 rounded-md border border-white/[0.06]">
                        {st.metrics}
                      </div>
                    </div>
                  </GlassCard>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
