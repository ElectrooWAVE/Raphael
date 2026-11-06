"use client";

import React, { useEffect, useRef } from "react";
import Lenis from "lenis";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

export interface SmoothScrollProviderProps {
  children: React.ReactNode;
}

export function SmoothScrollProvider({ children }: SmoothScrollProviderProps) {
  const lenisRef = useRef<Lenis | null>(null);

  useEffect(() => {
    // 1. Respect prefers-reduced-motion: if enabled, skip smooth scrolling
    const prefersReducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    if (prefersReducedMotion) {
      return;
    }

    // 2. Register GSAP plugin
    gsap.registerPlugin(ScrollTrigger);

    // 3. Initialize Lenis instance
    const lenis = new Lenis({
      duration: 1.1,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      orientation: "vertical",
      gestureOrientation: "vertical",
      smoothWheel: true,
      wheelMultiplier: 0.9,
      touchMultiplier: 1.5,
    });
    lenisRef.current = lenis;
    if (typeof window !== "undefined") {
      (window as unknown as { __lenis?: Lenis }).__lenis = lenis;
    }

    // 4. Connect Lenis scroll events directly to ScrollTrigger update
    lenis.on("scroll", ScrollTrigger.update);

    // 5. Connect Lenis RAF loop to GSAP's central ticker (Single ticker, NO duplicate listeners)
    const updateGsapTicker = (time: number) => {
      lenis.raf(time * 1000);
    };
    gsap.ticker.add(updateGsapTicker);
    gsap.ticker.lagSmoothing(0);

    // 6. Clean teardown on unmount
    return () => {
      gsap.ticker.remove(updateGsapTicker);
      lenis.destroy();
      lenisRef.current = null;
      ScrollTrigger.clearMatchMedia();
    };
  }, []);

  return <>{children}</>;
}
