"use client";

import dynamic from "next/dynamic";
import { Sparkles } from "lucide-react";
import type { SplineSceneWrapperProps } from "./SplineSceneWrapper";

export const DynamicSplineScene = dynamic<SplineSceneWrapperProps>(
  () => import("./SplineSceneWrapper"),
  {
    ssr: false,
    loading: () => (
      <div className="relative w-full aspect-[4/3] sm:aspect-square bg-transparent flex flex-col items-center justify-center overflow-visible">
        <div className="relative flex items-center justify-center">
          <div className="h-16 w-16 rounded-full bg-[#00F2FE]/15 animate-ping" />
          <div className="absolute h-10 w-10 rounded-full bg-[#00F2FE]/30 animate-pulse border border-[#00F2FE]/40" />
          <Sparkles className="absolute h-5 w-5 text-[#00F2FE]" />
        </div>
      </div>
    ),
  }
);
