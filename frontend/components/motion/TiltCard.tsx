"use client";

import React, { useRef, useState, useEffect } from "react";
import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";

export interface TiltCardProps {
  children: React.ReactNode;
  className?: string;
  maxTilt?: number; // max tilt degrees (e.g. 10)
  perspective?: number; // perspective in px (e.g. 1000)
  glare?: boolean;
}

export function TiltCard({
  children,
  className = "",
  maxTilt = 8,
  perspective = 1000,
  glare = true,
}: TiltCardProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [isHovered, setIsHovered] = useState<boolean>(false);
  const [isReduced, setIsReduced] = useState<boolean>(false);

  useEffect(() => {
    const q = window.matchMedia("(prefers-reduced-motion: reduce)");
    setIsReduced(q.matches);
  }, []);

  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  // Smooth spring physics for fluid tactile feel
  const springX = useSpring(mouseX, { stiffness: 240, damping: 20 });
  const springY = useSpring(mouseY, { stiffness: 240, damping: 20 });

  // Map normalized coordinates [-0.5, 0.5] to tilt angles
  const rotateX = useTransform(springY, [-0.5, 0.5], [maxTilt, -maxTilt]);
  const rotateY = useTransform(springX, [-0.5, 0.5], [-maxTilt, maxTilt]);

  // Glare highlight position
  const glareX = useTransform(springX, [-0.5, 0.5], ["0%", "100%"]);
  const glareY = useTransform(springY, [-0.5, 0.5], ["0%", "100%"]);

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (isReduced || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;

    const x = (e.clientX - rect.left) / rect.width - 0.5;
    const y = (e.clientY - rect.top) / rect.height - 0.5;

    mouseX.set(x);
    mouseY.set(y);
  };

  const handleMouseEnter = () => {
    if (isReduced) return;
    setIsHovered(true);
  };

  const handleMouseLeave = () => {
    if (isReduced) return;
    setIsHovered(false);
    mouseX.set(0);
    mouseY.set(0);
  };

  if (isReduced) {
    return <div className={className}>{children}</div>;
  }

  return (
    <div
      ref={ref}
      style={{ perspective: `${perspective}px` }}
      className="relative will-change-transform"
      onMouseMove={handleMouseMove}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <motion.div
        style={{
          rotateX,
          rotateY,
          transformStyle: "preserve-3d",
        }}
        className={`relative ${className}`}
      >
        {children}

        {/* Dynamic glare sweep */}
        {glare && isHovered && (
          <motion.div
            className="pointer-events-none absolute inset-0 rounded-[inherit] overflow-hidden opacity-40 transition-opacity duration-300"
            style={{
              background: `radial-gradient(circle at ${glareX} ${glareY}, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0) 65%)`,
            }}
          />
        )}
      </motion.div>
    </div>
  );
}
