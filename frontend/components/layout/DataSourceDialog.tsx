"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api, type MetaResponse } from "@/lib/api";
import {
  AlertCircle,
  Calendar,
  CheckCircle2,
  Database,
  Info,
  Layers,
  Server,
  X,
} from "lucide-react";

export interface DataSourceDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

export function DataSourceDialog({ isOpen, onClose }: DataSourceDialogProps) {
  const [meta, setMeta] = useState<MetaResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    let isMounted = true;
    setIsLoading(true);
    setError(null);

    api
      .getMeta()
      .then((data) => {
        if (isMounted) {
          setMeta(data);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof Error ? err.message : String(err));
          setIsLoading(false);
        }
      });

    // Close on Escape key
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      isMounted = false;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/80 backdrop-blur-md"
          />

          {/* Dialog Container */}
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 10 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
            className="relative w-full max-w-2xl rounded-3xl glass-popover p-6 sm:p-8 shadow-[0_25px_70px_rgba(0,0,0,0.85)] z-10 space-y-6"
          >
            {/* Header */}
            <div className="flex items-start justify-between gap-4 border-b border-white/[0.08] pb-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <Database className="h-4 w-4 text-[#00F2FE]" />
                  <h2 className="text-lg font-semibold tracking-tight text-white">
                    Data Source &amp; Fleet Provenance
                  </h2>
                </div>
                <p className="text-xs text-zinc-400">
                  Platform metadata retrieved directly from the Raphael backend <code>/meta</code> endpoint.
                </p>
              </div>

              <button
                onClick={onClose}
                className="rounded-full p-2 text-zinc-400 hover:text-white hover:bg-white/[0.06] transition-colors cursor-pointer"
                title="Close dialog"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Content Body */}
            {isLoading ? (
              <div className="py-12 flex flex-col items-center justify-center space-y-3">
                <div className="h-8 w-8 rounded-full border-2 border-[#00F2FE] border-t-transparent animate-spin" />
                <p className="text-xs font-mono text-zinc-400">
                  Retrieving metadata from /meta...
                </p>
              </div>
            ) : error ? (
              <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 space-y-2 text-xs text-amber-200">
                <div className="flex items-center gap-2 font-medium">
                  <AlertCircle className="h-4 w-4 text-amber-400" />
                  <span>Unable to fetch backend metadata</span>
                </div>
                <p className="text-[11px] text-zinc-400 font-mono">{error}</p>
              </div>
            ) : meta ? (
              <div className="space-y-5 text-xs text-zinc-300 max-h-[60vh] overflow-y-auto pr-1">
                {/* Provenance Box */}
                <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4 space-y-3">
                  <div className="text-xs font-semibold text-white flex items-center gap-2">
                    <Info className="h-3.5 w-3.5 text-[#00F2FE]" />
                    <span>Dataset Provenance &amp; Disclosures</span>
                  </div>
                  <div className="space-y-2 text-[11px] leading-relaxed">
                    <div className="flex items-start gap-2">
                      <span className="text-[#00F2FE] font-mono font-bold">•</span>
                      <span>
                        <strong className="text-zinc-100">Demand:</strong>{" "}
                        {meta.provenance.demand}
                      </span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-amber-400 font-mono font-bold">•</span>
                      <span>
                        <strong className="text-zinc-100">Lead times:</strong> synthetic.
                      </span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-amber-400 font-mono font-bold">•</span>
                      <span>
                        <strong className="text-zinc-100">Current stock:</strong> synthetic.
                      </span>
                    </div>
                    <div className="p-3 rounded-xl bg-amber-500/5 border border-amber-500/20 text-amber-300/90 text-[11px] mt-2">
                      <strong className="text-amber-200">Honest Disclaimer:</strong>{" "}
                      {meta.provenance.disclaimer}
                    </div>
                  </div>
                </div>

                {/* Fleet Counts Grid */}
                <div className="space-y-2">
                  <div className="text-xs font-semibold text-white flex items-center gap-2">
                    <Layers className="h-3.5 w-3.5 text-[#A855F7]" />
                    <span>Active Fleet Dimensions</span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 space-y-0.5">
                      <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-mono">
                        Total SKU Pairs
                      </span>
                      <div className="text-lg font-mono font-semibold text-white">
                        {meta.fleet_dimensions.total_pairs}
                      </div>
                    </div>
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 space-y-0.5">
                      <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-mono">
                        Materials
                      </span>
                      <div className="text-lg font-mono font-semibold text-white">
                        {meta.fleet_dimensions.total_materials}
                      </div>
                    </div>
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 space-y-0.5">
                      <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-mono">
                        Supply Areas
                      </span>
                      <div className="text-lg font-mono font-semibold text-white">
                        {meta.fleet_dimensions.total_areas}
                      </div>
                    </div>
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 space-y-0.5">
                      <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-mono">
                        Demand Days / Pair
                      </span>
                      <div className="text-lg font-mono font-semibold text-[#00F2FE]">
                        {meta.fleet_dimensions.total_demand_days_per_pair.toLocaleString()}
                      </div>
                    </div>
                    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 space-y-0.5 col-span-2 sm:col-span-2">
                      <span className="text-[10px] text-zinc-400 uppercase tracking-wider font-mono">
                        Total Historical Orders
                      </span>
                      <div className="text-lg font-mono font-semibold text-[#10B981]">
                        {meta.fleet_dimensions.total_historical_orders.toLocaleString()}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Date Horizons */}
                <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4 space-y-2.5">
                  <div className="text-xs font-semibold text-white flex items-center gap-2">
                    <Calendar className="h-3.5 w-3.5 text-[#10B981]" />
                    <span>Timeline &amp; Horizon Splits</span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] font-mono">
                    <div>
                      <span className="text-zinc-500 text-[10px] block">Dataset Freeze</span>
                      <span className="text-zinc-200">{meta.dates.as_of_date}</span>
                    </div>
                    <div>
                      <span className="text-zinc-500 text-[10px] block">Forecast Start</span>
                      <span className="text-[#00F2FE]">{meta.dates.forecast_start_date}</span>
                    </div>
                    <div>
                      <span className="text-zinc-500 text-[10px] block">Horizon</span>
                      <span className="text-zinc-200">{meta.dates.forecast_horizon_days} Days</span>
                    </div>
                    <div>
                      <span className="text-zinc-500 text-[10px] block">Test Window</span>
                      <span className="text-zinc-200">{meta.dates.test_days} Days</span>
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

            {/* Footer */}
            <div className="flex items-center justify-between pt-2 border-t border-white/[0.08] text-xs">
              <span className="text-[11px] text-zinc-500 font-mono">
                Single unified dataset architecture (No file upload)
              </span>
              <button
                onClick={onClose}
                className="px-4 py-2 rounded-full text-xs font-medium bg-white/[0.06] hover:bg-white/[0.1] text-white border border-white/[0.1] transition-colors cursor-pointer"
              >
                Close
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
