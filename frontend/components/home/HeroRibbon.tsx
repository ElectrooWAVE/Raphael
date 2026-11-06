"use client";

import React, { useEffect, useRef, useState } from "react";
import { DynamicSplineScene } from "@/components/3d/DynamicSplineScene";

interface HeroRibbonProps {
  className?: string;
}

export function HeroRibbon({ className = "" }: HeroRibbonProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  const [hasVideo, setHasVideo] = useState<boolean>(true);
  const [hasImage, setHasImage] = useState<boolean>(true);
  const [isReducedMotion, setIsReducedMotion] = useState<boolean>(false);
  const [isMobile, setIsMobile] = useState<boolean>(false);
  const [mouseParallax, setMouseParallax] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [scrollY, setScrollY] = useState<number>(0);

  // Check media queries for reduced motion & mobile viewport (<768px)
  useEffect(() => {
    const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    setIsReducedMotion(motionQuery.matches);
    const handleMotionChange = (e: MediaQueryListEvent) => setIsReducedMotion(e.matches);
    motionQuery.addEventListener("change", handleMotionChange);

    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };
    checkMobile();
    window.addEventListener("resize", checkMobile, { passive: true });

    return () => {
      motionQuery.removeEventListener("change", handleMotionChange);
      window.removeEventListener("resize", checkMobile);
    };
  }, []);

  // Subtle Mouse Parallax (max 18px)
  useEffect(() => {
    if (isReducedMotion || isMobile) return;

    let targetX = 0;
    let targetY = 0;
    let currentX = 0;
    let currentY = 0;
    let animId: number;

    const handleMouseMove = (e: MouseEvent) => {
      const centerX = window.innerWidth / 2;
      const centerY = window.innerHeight / 2;
      // Normal range -18px to +18px
      targetX = ((e.clientX - centerX) / centerX) * 18;
      targetY = ((e.clientY - centerY) / centerY) * 18;
    };

    const loop = () => {
      currentX += (targetX - currentX) * 0.05;
      currentY += (targetY - currentY) * 0.05;
      setMouseParallax({ x: currentX, y: currentY });
      animId = requestAnimationFrame(loop);
    };

    window.addEventListener("mousemove", handleMouseMove, { passive: true });
    animId = requestAnimationFrame(loop);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      cancelAnimationFrame(animId);
    };
  }, [isReducedMotion, isMobile]);

  // Scroll Parallax: ribbon moves slower than text
  useEffect(() => {
    if (isReducedMotion) return;

    const handleScroll = () => {
      // Moves down at 0.12x scroll speed (lagging behind foreground)
      setScrollY(window.scrollY * 0.12);
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [isReducedMotion]);

  // Pause video when off-screen using IntersectionObserver
  useEffect(() => {
    if (!videoRef.current) return;
    const video = videoRef.current;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            video.play().catch(() => {});
          } else {
            video.pause();
          }
        }
      },
      { threshold: 0.05 }
    );

    if (containerRef.current) {
      observer.observe(containerRef.current);
    }

    return () => {
      observer.disconnect();
    };
  }, [hasVideo, isReducedMotion, isMobile]);

  return (
    <div
      ref={containerRef}
      className={`absolute top-[-5%] right-[-6%] w-[90vw] sm:w-[75vw] lg:w-[62vw] max-w-[1400px] h-[120%] pointer-events-none select-none z-[1] overflow-visible ${className}`}
      style={{
        transform: `translate3d(${mouseParallax.x}px, ${mouseParallax.y + scrollY}px, 0)`,
        transition: "transform 0.1s linear",
      }}
    >
      {/* Preload the poster image for zero layout shift & instant appearance */}
      <link rel="preload" as="image" href="/hero/ribbon.webp" />

      {/* Faint violet radial glow behind the ribbon (< 0.25 opacity) */}
      <div
        className="absolute top-1/4 right-1/4 w-[85%] h-[85%] rounded-full pointer-events-none -z-10"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(168, 85, 247, 0.22) 0%, rgba(139, 92, 246, 0.08) 45%, transparent 72%)",
          filter: "blur(60px)",
        }}
      />

      {/* Ribbon Float Motion Container (9s slow float translateY +-12px) */}
      <div
        className={`relative w-full h-full flex items-center justify-center ${
          isReducedMotion ? "" : "animate-ribbon-float"
        }`}
        style={{
          mixBlendMode: "screen",
        }}
      >
        {/* Branch 1: Video (WebM VP9 + MP4 fallback) for desktop when motion allowed */}
        {hasVideo && !isReducedMotion && !isMobile ? (
          <video
            ref={videoRef}
            autoPlay
            muted
            loop
            playsInline
            poster="/hero/ribbon.webp"
            onError={() => setHasVideo(false)}
            className="w-full h-full object-contain scale-[1.04] max-w-none"
            style={{
              mixBlendMode: "screen",
              backgroundColor: "transparent",
            }}
          >
            <source src="/hero/ribbon.webm" type="video/webm" />
            <source src="/hero/ribbon.mp4" type="video/mp4" />
          </video>
        ) : hasImage ? (
          /* Branch 2: Optimized Picture / WebP for reduced motion, mobile, or video fallback */
          <picture className="w-full h-full flex items-center justify-center">
            <source
              media="(max-width: 767px)"
              srcSet="/hero/ribbon@mobile.webp"
              type="image/webp"
            />
            <source srcSet="/hero/ribbon.webp" type="image/webp" />
            <img
              src="/hero/ribbon.png"
              alt="Liquid Iridescent Chromatic Ribbon"
              loading="eager"
              onError={() => setHasImage(false)}
              className="w-full h-full object-contain scale-[1.04] max-w-none"
              style={{
                mixBlendMode: "screen",
                backgroundColor: "transparent",
              }}
            />
          </picture>
        ) : (
          /* Branch 3: Procedural WebGL scene fallback */
          <div className="w-full h-full relative">
            <DynamicSplineScene
              className="w-full h-full"
              aspectRatio=""
              fallbackTitle="Liquid Iridescent Chromatic Ribbon"
              borderless={true}
            />
          </div>
        )}
      </div>
    </div>
  );
}
