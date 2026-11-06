"use client";

import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";

export interface RevealProps {
  children: React.ReactNode;
  className?: string;
  direction?: "up" | "down" | "left" | "right" | "none";
  delay?: number;
  duration?: number;
  staggerIndex?: number;
  staggerDelay?: number;
  once?: boolean;
}

export function Reveal({
  children,
  className = "",
  direction = "up",
  delay = 0,
  duration = 0.5,
  staggerIndex = 0,
  staggerDelay = 0.08,
  once = true,
}: RevealProps) {
  const [isReduced, setIsReduced] = useState<boolean>(false);

  useEffect(() => {
    const q = window.matchMedia("(prefers-reduced-motion: reduce)");
    setIsReduced(q.matches);
    const handler = (e: MediaQueryListEvent) => setIsReduced(e.matches);
    q.addEventListener("change", handler);
    return () => q.removeEventListener("change", handler);
  }, []);

  const totalDelay = delay + staggerIndex * staggerDelay;

  if (isReduced) {
    return <div className={className}>{children}</div>;
  }

  const getInitialOffset = () => {
    switch (direction) {
      case "up":
        return { y: 24, x: 0 };
      case "down":
        return { y: -24, x: 0 };
      case "left":
        return { x: 24, y: 0 };
      case "right":
        return { x: -24, y: 0 };
      case "none":
      default:
        return { x: 0, y: 0 };
    }
  };

  const initialOffset = getInitialOffset();

  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, ...initialOffset }}
      whileInView={{ opacity: 1, x: 0, y: 0 }}
      viewport={{ once, margin: "-30px" }}
      transition={{
        duration,
        delay: totalDelay,
        ease: [0.21, 0.47, 0.32, 0.98],
      }}
    >
      {children}
    </motion.div>
  );
}
