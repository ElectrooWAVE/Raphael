"use client";

import React, { useRef, useState, useEffect } from "react";

export interface GlassCardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  className?: string;
  enableBlur?: boolean;
}

export function GlassCard({
  children,
  className = "",
  enableBlur = true,
  style,
  ...props
}: GlassCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [coords, setCoords] = useState<{ x: number; y: number; isHovered: boolean }>({
    x: 50,
    y: 50,
    isHovered: false,
  });
  const [tilt, setTilt] = useState<{ rx: number; ry: number }>({ rx: 0, ry: 0 });
  const [isReducedMotion, setIsReducedMotion] = useState<boolean>(false);

  useEffect(() => {
    const q = window.matchMedia("(prefers-reduced-motion: reduce)");
    setIsReducedMotion(q.matches);
  }, []);

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (isReducedMotion || !cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    const nx = (e.clientX - rect.left) / rect.width;
    const ny = (e.clientY - rect.top) / rect.height;

    // Clamp tilt to max 3 degrees
    const rx = (ny - 0.5) * -6; // max -3 to +3
    const ry = (nx - 0.5) * 6; // max -3 to +3

    setCoords({ x: nx * 100, y: ny * 100, isHovered: true });
    setTilt({ rx, ry });
  };

  const handlePointerLeave = () => {
    setCoords((prev) => ({ ...prev, isHovered: false }));
    setTilt({ rx: 0, ry: 0 });
  };

  return (
    <div
      ref={cardRef}
      onPointerMove={handlePointerMove}
      onPointerLeave={handlePointerLeave}
      className={`group relative rounded-[28px] overflow-hidden p-6 transition-all duration-300 hover:-translate-y-[2px] ${
        enableBlur
          ? "bg-[linear-gradient(135deg,rgba(255,255,255,0.14)_0%,rgba(255,255,255,0.04)_100%)] backdrop-blur-[24px]"
          : "bg-[linear-gradient(135deg,rgba(22,22,30,0.85)_0%,rgba(14,14,22,0.92)_100%)]"
      } ${className}`}
      style={{
        boxShadow:
          "inset 0 1px 0 rgba(255, 255, 255, 0.45), inset 0 -1px 0 rgba(255, 255, 255, 0.12), 0 24px 60px rgba(0, 0, 0, 0.65)",
        transform:
          !isReducedMotion && coords.isHovered
            ? `perspective(1000px) rotateX(${tilt.rx.toFixed(2)}deg) rotateY(${tilt.ry.toFixed(2)}deg)`
            : "perspective(1000px) rotateX(0deg) rotateY(0deg)",
        transition: coords.isHovered
          ? "transform 0.12s ease-out, box-shadow 0.3s ease"
          : "transform 0.4s ease-out, box-shadow 0.3s ease",
        ...style,
      }}
      {...props}
    >
      {/* 1.2px Gradient Rim Border via mask-composite (brighter top-left) */}
      <div
        className="pointer-events-none absolute inset-0 rounded-[28px] p-[1.2px]"
        style={{
          background:
            "linear-gradient(135deg, rgba(255, 255, 255, 0.55) 0%, rgba(255, 255, 255, 0.10) 45%, rgba(255, 255, 255, 0.22) 100%)",
          WebkitMask:
            "linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)",
          WebkitMaskComposite: "xor",
          mask: "linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)",
          maskComposite: "exclude",
        }}
      />

      {/* Cursor-following Inner Highlight on hover */}
      <div
        className="pointer-events-none absolute inset-0 rounded-[28px] transition-opacity duration-300"
        style={{
          opacity: coords.isHovered ? 1 : 0,
          background: `radial-gradient(340px at ${coords.x}% ${coords.y}%, rgba(255, 255, 255, 0.12) 0%, rgba(125, 249, 228, 0.04) 40%, transparent 70%)`,
        }}
      />

      {/* Subtle Noise Texture (inline SVG, zero network) */}
      <div className="pointer-events-none absolute inset-0 rounded-[28px] liquid-glass-grain opacity-60" />

      {/* Foreground Content */}
      <div className="relative z-10">{children}</div>
    </div>
  );
}
