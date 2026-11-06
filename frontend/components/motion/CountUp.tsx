"use client";

import React, { useEffect, useRef, useState } from "react";
import { useInView, animate } from "framer-motion";

export interface CountUpProps {
  value: number;
  duration?: number; // seconds
  decimals?: number;
  prefix?: string;
  suffix?: string;
  className?: string;
  formatNumber?: boolean;
}

export function CountUp({
  value,
  duration = 1.2,
  decimals = 0,
  prefix = "",
  suffix = "",
  className = "",
  formatNumber = true,
}: CountUpProps) {
  const [displayValue, setDisplayValue] = useState<number>(0);
  const ref = useRef<HTMLSpanElement>(null);
  const isInView = useInView(ref, { once: true, margin: "-20px" });
  const [isReduced, setIsReduced] = useState<boolean>(false);

  useEffect(() => {
    const q = window.matchMedia("(prefers-reduced-motion: reduce)");
    setIsReduced(q.matches);
  }, []);

  useEffect(() => {
    if (isReduced) {
      setDisplayValue(value);
      return;
    }

    const startVal = 0;
    const endVal = value;
    const startTime = Date.now();
    const durationMs = duration * 1000;

    const interval = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / durationMs, 1);
      // Ease-out cubic: 1 - (1 - t)^3
      const ease = 1 - Math.pow(1 - progress, 3);
      const current = startVal + (endVal - startVal) * ease;
      setDisplayValue(current);

      if (progress >= 1) {
        setDisplayValue(endVal);
        clearInterval(interval);
      }
    }, 16);

    return () => clearInterval(interval);
  }, [value, duration, isReduced]);

  const formatted = decimals > 0 ? displayValue.toFixed(decimals) : Math.round(displayValue).toString();

  const finalFormatted = formatNumber
    ? Number(formatted).toLocaleString("en-US", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })
    : formatted;

  return (
    <span ref={ref} className={className}>
      {prefix}
      {finalFormatted}
      {suffix}
    </span>
  );
}
