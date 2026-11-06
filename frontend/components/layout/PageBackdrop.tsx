"use client";

import React, { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";

/**
 * PageBackdrop: fixed, non-interactive backdrop rendered once in the Shell.
 * Pure CSS/SVG: no WebGL, no video, no network requests. Animates only
 * transform and opacity. Sits at z-0 below all page content (z-10).
 *
 * The home page ("/") keeps its original faint aurora + grain exactly as before;
 * the five app pages get the richer aurora system with a per-route tint.
 */

type TintKey = "forecast" | "inventory" | "simulator" | "telemetry" | "methodology";

const TINT_ROUTES: Record<string, TintKey> = {
  "/forecast": "forecast",
  "/inventory": "inventory",
  "/simulator": "simulator",
  "/telemetry": "telemetry",
  "/methodology": "methodology",
};

// Overall aurora intensity per route (applied as container opacity, crossfaded)
const AURORA_INTENSITY: Record<TintKey, number> = {
  forecast: 1,
  inventory: 1,
  simulator: 1,
  telemetry: 0.9,
  methodology: 0.62,
};

const TINT_KEYS: TintKey[] = ["forecast", "inventory", "simulator", "telemetry", "methodology"];

function resolveTint(pathname: string): TintKey | null {
  const match = Object.keys(TINT_ROUTES).find((r) => pathname === r || pathname.startsWith(`${r}/`));
  return match ? TINT_ROUTES[match] : null;
}

export function PageBackdrop() {
  const pathname = usePathname() || "/";
  const tint = resolveTint(pathname);
  const rootRef = useRef<HTMLDivElement>(null);
  const cursorRef = useRef<HTMLDivElement>(null);

  // Pause all backdrop animations while the tab is hidden
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const onVis = () => {
      root.dataset.paused = document.hidden ? "true" : "false";
    };
    onVis();
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, [tint !== null]); // eslint-disable-line react-hooks/exhaustive-deps

  // Cursor light: CSS variables updated on pointermove, rAF-throttled.
  // Disabled on touch / coarse pointers, under 768px and with reduced motion.
  useEffect(() => {
    const el = cursorRef.current;
    const root = rootRef.current;
    if (!el || !root || !tint) return;

    const fine = window.matchMedia("(hover: hover) and (pointer: fine)");
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (!fine.matches || reduced.matches || window.innerWidth < 768) return;

    let frame = 0;
    let x = 0;
    let y = 0;

    const apply = () => {
      frame = 0;
      root.style.setProperty("--pb-mx", `${x}px`);
      root.style.setProperty("--pb-my", `${y}px`);
    };
    const onMove = (e: PointerEvent) => {
      if (e.pointerType !== "mouse") return;
      x = e.clientX;
      y = e.clientY;
      el.style.opacity = "1";
      if (!frame) frame = requestAnimationFrame(apply);
    };
    const onLeave = (e: PointerEvent) => {
      if (!e.relatedTarget) el.style.opacity = "0";
    };
    const onBlur = () => {
      el.style.opacity = "0";
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("pointerout", onLeave);
    window.addEventListener("blur", onBlur);
    return () => {
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerout", onLeave);
      window.removeEventListener("blur", onBlur);
      el.style.opacity = "0";
    };
  }, [tint]);

  // Home and any non-app route: original faint aurora + grain (unchanged look)
  if (!tint) {
    return (
      <div className="pointer-events-none fixed inset-0 overflow-hidden z-0" aria-hidden="true">
        <div
          className="absolute -top-[10%] right-[15%] w-[650px] h-[650px] rounded-full blur-[140px] opacity-10 pointer-events-none"
          style={{ background: "radial-gradient(circle, rgba(124, 92, 255, 0.8) 0%, transparent 70%)" }}
        />
        <div
          className="absolute top-[40%] -left-[10%] w-[550px] h-[550px] rounded-full blur-[130px] opacity-8 pointer-events-none"
          style={{ background: "radial-gradient(circle, rgba(25, 211, 197, 0.7) 0%, transparent 70%)" }}
        />
        <div className="liquid-glass-grain opacity-40 pointer-events-none" />
      </div>
    );
  }

  return (
    <div
      ref={rootRef}
      className="page-backdrop pointer-events-none fixed inset-0 z-0 overflow-hidden"
      aria-hidden="true"
      data-tint={tint}
    >
      {/* b. Aurora: three soft radial blobs (gradient falloff, no filter blur) */}
      <div className="pb-aurora" style={{ opacity: AURORA_INTENSITY[tint] }}>
        <div className="pb-blob pb-blob-violet" />
        <div className="pb-blob pb-blob-blue" />
        <div className="pb-blob pb-blob-teal" />
      </div>

      {/* Per-route tint layers: all mounted, crossfaded by opacity over 0.6s */}
      {TINT_KEYS.map((key) => (
        <div key={key} className={`pb-tint pb-tint-${key}`} style={{ opacity: tint === key ? 1 : 0 }}>
          {key === "telemetry" && <div className="pb-hud-grid" />}
        </div>
      ))}

      {/* c. Top glow behind page title area, gone by ~60vh */}
      <div className="pb-top-glow" style={{ opacity: tint === "methodology" ? 0.6 : 1 }} />

      {/* g. Slow diagonal light sweep (~14s cycle) */}
      <div className="pb-sweep" />

      {/* f. Cursor light (transform driven by CSS vars) */}
      <div ref={cursorRef} className="pb-cursor" />

      {/* d. Vignette */}
      <div className="pb-vignette" />

      {/* e. Fine grain (inline SVG noise) */}
      <div className="pb-grain" />
    </div>
  );
}
