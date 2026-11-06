"use client";

import React, { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  api,
  type HealthResponse,
  type ApiStatus,
  subscribeApiStatus,
  getApiStatus,
} from "@/lib/api";
import { DataSourceDialog } from "./DataSourceDialog";
import { Database, Menu, X } from "lucide-react";

export function Navbar() {
  const pathname = usePathname();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isHealthOnline, setIsHealthOnline] = useState<boolean>(true);
  const [apiStatus, setApiStatus] = useState<ApiStatus>(getApiStatus());
  const [isDataDialogOpen, setIsDataDialogOpen] = useState<boolean>(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState<boolean>(false);
  const [hoveredLink, setHoveredLink] = useState<string | null>(null);
  const [scrolled, setScrolled] = useState<boolean>(false);
  const [sweepActive, setSweepActive] = useState<boolean>(false);
  const [cursorPos, setCursorPos] = useState<{ x: number; y: number; opacity: number }>({
    x: 50,
    y: 50,
    opacity: 0,
  });
  const [isReducedMotion, setIsReducedMotion] = useState<boolean>(false);
  const [isMobile, setIsMobile] = useState<boolean>(false);
  const [canLensing, setCanLensing] = useState<boolean>(false);

  const navBarRef = useRef<HTMLDivElement>(null);
  const rafRef = useRef<number | null>(null);

  // Check media queries & environment
  useEffect(() => {
    const q = window.matchMedia("(prefers-reduced-motion: reduce)");
    setIsReducedMotion(q.matches);
    const handleMotion = (e: MediaQueryListEvent) => setIsReducedMotion(e.matches);
    q.addEventListener("change", handleMotion);

    const checkMobile = () => {
      const mobile = window.innerWidth < 1000;
      setIsMobile(mobile);
      // Chromium feature check for optional SVG lensing filter
      const isChromium =
        typeof window !== "undefined" &&
        !!(window as any).chrome &&
        !mobile &&
        !q.matches;
      setCanLensing(isChromium);
    };
    checkMobile();
    window.addEventListener("resize", checkMobile, { passive: true });

    return () => {
      q.removeEventListener("change", handleMotion);
      window.removeEventListener("resize", checkMobile);
    };
  }, []);

  // Close mobile menu on route change & trigger 0.9s light sweep
  useEffect(() => {
    setIsMobileMenuOpen(false);
    setSweepActive(true);
    const timer = setTimeout(() => setSweepActive(false), 900);
    return () => clearTimeout(timer);
  }, [pathname]);

  // Subscribe to reactive API status
  useEffect(() => {
    return subscribeApiStatus((st) => setApiStatus(st));
  }, []);

  // Shrink navbar height and raise fill opacity after 40px of scroll
  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 40);
    };
    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  // Poll /health every 30s
  useEffect(() => {
    let isMounted = true;
    const checkHealth = () => {
      api
        .getHealth()
        .then((data) => {
          if (isMounted) {
            setHealth(data);
            setIsHealthOnline(data.status === "ok");
          }
        })
        .catch(() => {
          if (isMounted) {
            setIsHealthOnline(false);
          }
        });
    };

    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // Cursor light tracker on navbar (requestAnimationFrame throttled)
  const handlePointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (isReducedMotion || !navBarRef.current) return;
      const rect = navBarRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        setCursorPos({ x, y, opacity: 1 });
      });
    },
    [isReducedMotion]
  );

  const handlePointerLeave = useCallback(() => {
    setCursorPos((prev) => ({ ...prev, opacity: 0 }));
  }, []);

  const navLinks = [
    { href: "/", label: "Overview" },
    { href: "/forecast", label: "Forecast" },
    { href: "/inventory", label: "Inventory" },
    { href: "/simulator", label: "Simulator" },
    { href: "/telemetry", label: "Telemetry" },
    { href: "/methodology", label: "Methodology" },
  ];

  const activeHref =
    navLinks.find((l) =>
      l.href === "/" ? pathname === "/" : pathname.startsWith(l.href)
    )?.href || "/";

  const spotlightHref = hoveredLink || activeHref;

  const isHealthy = !apiStatus.isOffline && isHealthOnline;
  const dotColorClass = isHealthy
    ? "bg-[#00F2FE] shadow-[0_0_12px_#00F2FE]"
    : "bg-[#F59E0B] shadow-[0_0_12px_#F59E0B]";

  return (
    <>
      {/* Optional SVG displacement map for Chromium edge lensing */}
      <svg className="sr-only" aria-hidden="true">
        <filter id="liquid-glass-lens" x="-10%" y="-10%" width="120%" height="120%">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.04"
            numOctaves="2"
            result="noise"
          />
          <feDisplacementMap
            in="SourceGraphic"
            in2="noise"
            scale="4"
            xChannelSelector="R"
            yChannelSelector="G"
          />
        </filter>
      </svg>

      <motion.header
        initial={isReducedMotion ? false : { y: -24, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.65, ease: [0.16, 1, 0.3, 1] }}
        className="fixed top-5 sm:top-6 left-0 right-0 z-50 flex flex-col items-center pointer-events-none px-3 sm:px-4"
      >
        {/* Ambient light blobs behind navbar: drifting violet & teal glow */}
        <div className="pointer-events-none absolute -top-6 left-1/2 -translate-x-1/2 w-full max-w-[1280px] h-28 -z-10 overflow-visible flex items-center justify-between px-8 sm:px-16">
          <div
            className="w-[480px] h-[150px] rounded-full blur-[72px] animate-blob-1"
            style={{
              background:
                "radial-gradient(ellipse at center, rgba(124, 92, 255, 0.25) 0%, rgba(124, 92, 255, 0.08) 50%, transparent 75%)",
            }}
          />
          <div
            className="w-[420px] h-[140px] rounded-full blur-[68px] animate-blob-2"
            style={{
              background:
                "radial-gradient(ellipse at center, rgba(25, 211, 197, 0.18) 0%, rgba(25, 211, 197, 0.05) 50%, transparent 75%)",
            }}
          />
        </div>

        {/* Liquid Glass Capsule Navbar (ONE element with ONE backdrop-filter) */}
        <div
          ref={navBarRef}
          onPointerMove={handlePointerMove}
          onPointerLeave={handlePointerLeave}
          className={`pointer-events-auto relative w-full max-w-[1240px] md:w-[92vw] rounded-full px-5 sm:px-7 flex items-center justify-between transition-all duration-300 ${
            scrolled ? "h-14 shadow-[0_28px_70px_rgba(0,0,0,0.85)]" : "h-16 shadow-[0_24px_60px_rgba(0,0,0,0.65)]"
          }`}
          style={{
            backdropFilter: "blur(26px) saturate(180%) brightness(1.15)",
            WebkitBackdropFilter: "blur(26px) saturate(180%) brightness(1.15)",
            background: scrolled
              ? "linear-gradient(180deg, rgba(255, 255, 255, 0.14) 0%, rgba(255, 255, 255, 0.06) 45%, rgba(255, 255, 255, 0.04) 100%), rgba(10, 10, 16, 0.88)"
              : "linear-gradient(180deg, rgba(255, 255, 255, 0.16) 0%, rgba(255, 255, 255, 0.07) 45%, rgba(255, 255, 255, 0.05) 100%), rgba(14, 14, 20, 0.35)",
            boxShadow:
              "inset 0 1px 0 rgba(255, 255, 255, 0.55), inset 0 -1px 0 rgba(255, 255, 255, 0.20), inset 0 -12px 28px rgba(160, 140, 255, 0.10), 0 24px 60px rgba(0, 0, 0, 0.65), 0 18px 50px rgba(120, 100, 255, 0.14)",
          }}
        >
          {/* Layer 2: 1.2px Gradient Rim Border via mask-composite */}
          <div className="liquid-glass-rim" />

          {/* Layer 3: Top Specular Elliptical Highlight across upper third */}
          <div className="liquid-glass-specular" />

          {/* Layer 6: 3% Opacity SVG Noise Overlay (inline data URI) */}
          <div className="liquid-glass-grain" />

          {/* Layer 7: Cursor-driven Radial Spotlight (throttled pointermove) */}
          <div
            className="pointer-events-none absolute inset-0 rounded-full transition-opacity duration-300"
            style={{
              opacity: cursorPos.opacity,
              background: `radial-gradient(260px at ${cursorPos.x}px ${cursorPos.y}px, rgba(255, 255, 255, 0.22) 0%, rgba(125, 249, 228, 0.06) 40%, transparent 65%)`,
            }}
          />

          {/* Route Change Light Sweep (0.9s duration) */}
          {sweepActive && !isReducedMotion && (
            <div className="pointer-events-none absolute inset-0 rounded-full overflow-hidden">
              <div
                className="absolute top-0 bottom-0 w-36 bg-gradient-to-r from-transparent via-white/35 to-transparent animate-navbar-sweep"
                style={{ filter: "blur(2px)" }}
              />
            </div>
          )}

          {/* Optional Chromium edge lensing layer */}
          {canLensing && (
            <div
              className="pointer-events-none absolute inset-0 rounded-full opacity-20 -z-10"
              style={{ filter: "url(#liquid-glass-lens)" }}
            />
          )}

          {/* Content Left: "Raphael" wordmark (weight 600, tight tracking) + pulse ring dot */}
          <Link
            href="/"
            className="relative flex items-center group transition-transform active:scale-95 shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00F2FE] focus-visible:ring-offset-2 focus-visible:ring-offset-black rounded-full px-1"
          >
            <div className="relative inline-flex items-center">
              <span className="font-semibold text-base sm:text-[17.5px] tracking-tight text-white group-hover:text-[#00F2FE] transition-colors drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]">
                Raphael
              </span>

              {/* Cyan dot at top-right with slow ring pulse */}
              <div className="absolute -top-0.5 -right-3 flex items-center justify-center">
                <span
                  className={`h-2.5 w-2.5 rounded-full ${dotColorClass} transition-colors`}
                  title={
                    isHealthy
                      ? `Telemetry Online (As of ${health?.as_of_date || apiStatus.asOfDate || "2016-04-24"})`
                      : `Offline snapshot (generated ${apiStatus.snapshotTime || "Pre-packaged"})`
                  }
                />
                {!isReducedMotion && (
                  <span
                    className={`absolute -inset-1 rounded-full border ${
                      isHealthy ? "border-cyan-400/60" : "border-amber-400/60"
                    } animate-ring-pulse pointer-events-none`}
                  />
                )}
              </div>
            </div>
          </Link>

          {/* Content Center: Six links (14.5px, weight 500, soft white radial spotlight) */}
          <nav
            onMouseLeave={() => setHoveredLink(null)}
            className="hidden min-[1000px]:flex items-center gap-1 shrink-0 relative"
          >
            {navLinks.map((link) => {
              const isActive = link.href === activeHref;
              const isHovered = link.href === hoveredLink;
              const hasSpotlight = link.href === spotlightHref;

              return (
                <Link
                  key={link.href}
                  href={link.href}
                  onMouseEnter={() => setHoveredLink(link.href)}
                  className={`relative px-4 py-1.5 rounded-full text-[14.5px] font-medium tracking-normal transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00F2FE] focus-visible:ring-offset-2 focus-visible:ring-offset-black ${
                    isActive
                      ? "text-white"
                      : "text-zinc-300 hover:text-white"
                  }`}
                >
                  {/* Soft White Radial Spotlight (blurred ellipse ~110px wide, no boxed pill) */}
                  {hasSpotlight && (
                    <motion.div
                      layoutId="nav-spotlight"
                      transition={
                        isReducedMotion
                          ? { duration: 0 }
                          : { type: "spring", stiffness: 360, damping: 28 }
                      }
                      className="absolute -top-1 left-1/2 -translate-x-1/2 w-[110px] h-[48px] rounded-full pointer-events-none -z-10"
                      style={{
                        background: isActive
                          ? "radial-gradient(ellipse at center, rgba(255, 255, 255, 0.28) 0%, rgba(255, 255, 255, 0.08) 45%, transparent 72%)"
                          : "radial-gradient(ellipse at center, rgba(255, 255, 255, 0.16) 0%, rgba(255, 255, 255, 0.04) 45%, transparent 70%)",
                        filter: "blur(6px)",
                      }}
                    />
                  )}
                  <span className="relative z-10 drop-shadow-[0_1px_2px_rgba(0,0,0,0.7)]">
                    {link.label}
                  </span>
                </Link>
              );
            })}
          </nav>

          {/* Content Right: "Connect Data" raised glass pill + Mobile Menu Toggle */}
          <div className="flex items-center gap-2.5 shrink-0">
            <button
              id="connect-data-btn"
              onClick={() => setIsDataDialogOpen(true)}
              className="group relative px-5 py-2 rounded-full text-xs font-semibold text-white transition-all duration-200 active:scale-95 cursor-pointer flex items-center gap-1.5 shrink-0 overflow-hidden hover:-translate-y-[1px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00F2FE] focus-visible:ring-offset-2 focus-visible:ring-offset-black"
              style={{
                background:
                  "linear-gradient(180deg, rgba(255, 255, 255, 0.22) 0%, rgba(255, 255, 255, 0.08) 100%)",
                border: "1.2px solid rgba(255, 255, 255, 0.40)",
                boxShadow:
                  "inset 0 1px 0 rgba(255, 255, 255, 0.75), inset 0 -1px 0 rgba(255, 255, 255, 0.25), 0 4px 16px rgba(0, 0, 0, 0.4), 0 0 18px rgba(125, 249, 228, 0.25)",
              }}
            >
              {/* Diagonal sheen sweep on hover */}
              <div
                className="pointer-events-none absolute -inset-full w-[200%] h-[200%] bg-gradient-to-r from-transparent via-white/40 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700 ease-out"
                style={{ transform: "skewX(-25deg)" }}
              />

              <Database className="h-3.5 w-3.5 text-zinc-200 group-hover:text-white transition-colors" />
              <span className="relative z-10 drop-shadow-[0_1px_2px_rgba(0,0,0,0.6)]">
                Connect Data
              </span>
            </button>

            {/* Mobile Menu Toggle (< 1000px) */}
            <button
              type="button"
              id="mobile-nav-toggle"
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="min-[1000px]:hidden p-1.5 rounded-full border border-white/[0.22] bg-white/[0.08] text-zinc-300 hover:text-white hover:bg-white/[0.14] transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00F2FE]"
              aria-label="Toggle navigation menu"
            >
              {isMobileMenuOpen ? (
                <X className="h-4 w-4 text-white" />
              ) : (
                <Menu className="h-4 w-4 text-zinc-300" />
              )}
            </button>
          </div>
        </div>

        {/* Mobile Dropdown Sheet (< 1000px, matches liquid glass style) */}
        <AnimatePresence>
          {isMobileMenuOpen && (
            <motion.div
              initial={{ opacity: 0, y: -8, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -8, scale: 0.98 }}
              transition={{ duration: 0.2 }}
              className="pointer-events-auto min-[1000px]:hidden mt-2 w-full max-w-[1240px] md:w-[92vw] rounded-2xl px-4 py-3 space-y-1 shadow-[0_24px_60px_rgba(0,0,0,0.85)] relative overflow-hidden"
              style={{
                backdropFilter: "blur(26px) saturate(180%)",
                background:
                  "linear-gradient(180deg, rgba(255, 255, 255, 0.12) 0%, rgba(255, 255, 255, 0.04) 100%), rgba(10, 10, 16, 0.92)",
                border: "1.2px solid rgba(255, 255, 255, 0.24)",
                boxShadow: "inset 0 1px 0 rgba(255, 255, 255, 0.45)",
              }}
            >
              <div className="liquid-glass-grain" />
              {navLinks.map((link) => {
                const isActive =
                  link.href === "/"
                    ? pathname === "/"
                    : pathname.startsWith(link.href);

                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    onClick={() => setIsMobileMenuOpen(false)}
                    className={`block px-3.5 py-2 rounded-xl text-sm font-medium transition-all ${
                      isActive
                        ? "bg-white/[0.14] text-white font-semibold border border-white/[0.22] shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]"
                        : "text-zinc-300 hover:text-white hover:bg-white/[0.05]"
                    }`}
                  >
                    {link.label}
                  </Link>
                );
              })}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Status Chip Strip Below Navbar: Smaller, lower contrast, glass chips */}
        <div className="pointer-events-auto mt-2 sm:mt-2.5 flex flex-wrap items-center justify-center gap-1.5 sm:gap-2 text-[9.5px] sm:text-[10.5px] font-mono text-zinc-500 px-4">
          {/* 1. Offline Snapshot Badge */}
          {apiStatus.isOffline && (
            <span
              id="offline-snapshot-badge"
              className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-amber-500/10 backdrop-blur-none border border-amber-500/25 text-amber-300/90 shadow-[0_0_12px_rgba(245,158,11,0.15)] whitespace-nowrap"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
              <span>Offline snapshot (generated {apiStatus.snapshotTime || "Pre-packaged"})</span>
            </span>
          )}

          {/* 2. As of Date Chip */}
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-white/[0.03] backdrop-blur-none border border-white/[0.06] text-zinc-400 hover:text-zinc-300 hover:border-white/[0.12] transition-colors whitespace-nowrap">
            <span className="h-1.5 w-1.5 rounded-full bg-[#10B981]" />
            <span>As of {health?.as_of_date || apiStatus.asOfDate || "2016-04-24"}</span>
          </span>

          {/* 3. Provenance Chip */}
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-white/[0.03] backdrop-blur-none border border-white/[0.06] text-zinc-400 hover:text-zinc-300 hover:border-white/[0.12] transition-colors">
            <Database className="h-3 w-3 text-cyan-400/80 shrink-0" />
            <span>Retail benchmark + synthetic lead times/stock</span>
          </span>
        </div>
      </motion.header>

      {/* Real /meta Data Source Dialog */}
      <DataSourceDialog
        isOpen={isDataDialogOpen}
        onClose={() => setIsDataDialogOpen(false)}
      />
    </>
  );
}
