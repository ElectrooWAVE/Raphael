"use client";

import React, { useEffect, useState, useMemo, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  api,
  type UrgencyResponse,
  type ReorderResponse,
} from "@/lib/api";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Box,
  Check,
  Download,
  ExternalLink,
  Filter,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  Truck,
  X,
} from "lucide-react";

type SortField =
  | "urgency_rank"
  | "material"
  | "area"
  | "status"
  | "current_stock"
  | "days_remaining"
  | "reorder_point_rop"
  | "safety_stock_ss"
  | "predicted_lead_time_days"
  | "recommended_order_quantity";

type SortDirection = "asc" | "desc";

export default function InventoryPage() {
  const router = useRouter();

  // Data state
  const [data, setData] = useState<UrgencyResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters state
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [areaFilter, setAreaFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Sorting state
  const [sortField, setSortField] = useState<SortField>("urgency_rank");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

  // Export state
  const [isExporting, setIsExporting] = useState<boolean>(false);
  const [exportFeedback, setExportFeedback] = useState<string | null>(null);

  // Fetch urgency data from API
  const loadUrgencyData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.getUrgency();
      setData(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUrgencyData();
  }, [loadUrgencyData]);

  // Extract distinct areas for filter dropdown
  const distinctAreas = useMemo(() => {
    if (!data?.items) return [];
    const set = new Set<string>();
    data.items.forEach((item) => set.add(item.area));
    return Array.from(set).sort();
  }, [data?.items]);

  // Filter and sort items
  const filteredAndSortedItems = useMemo(() => {
    if (!data?.items) return [];

    let items = [...data.items];

    // Status filter
    if (statusFilter) {
      items = items.filter(
        (it) => it.status.toUpperCase() === statusFilter.toUpperCase()
      );
    }

    // Area filter
    if (areaFilter !== "ALL") {
      items = items.filter((it) => it.area === areaFilter);
    }

    // Search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      items = items.filter(
        (it) =>
          it.material.toLowerCase().includes(q) ||
          it.area.toLowerCase().includes(q) ||
          it.champion_model.toLowerCase().includes(q)
      );
    }

    // Sorting
    items.sort((a, b) => {
      let valA = a[sortField];
      let valB = b[sortField];

      // Severity ordering for status
      if (sortField === "status") {
        const severityMap: Record<string, number> = {
          CRITICAL: 1,
          REORDER: 2,
          OK: 3,
        };
        valA = severityMap[a.status] || 99;
        valB = severityMap[b.status] || 99;
      }

      if (typeof valA === "string" && typeof valB === "string") {
        return sortDirection === "asc"
          ? valA.localeCompare(valB)
          : valB.localeCompare(valA);
      }

      const numA = Number(valA);
      const numB = Number(valB);
      return sortDirection === "asc" ? numA - numB : numB - numA;
    });

    return items;
  }, [data?.items, statusFilter, areaFilter, searchQuery, sortField, sortDirection]);

  // Handle column header sorting
  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDirection("asc");
    }
  };

  // Handle CSV export with user feedback (supports client-side offline export)
  const handleExportCsv = async () => {
    setIsExporting(true);
    setExportFeedback(null);
    try {
      const params: { status?: string; area?: string } = {};
      if (statusFilter) params.status = statusFilter.toLowerCase();
      if (areaFilter !== "ALL") params.area = areaFilter;

      let csvBlob: Blob | null = null;

      // Try server export if not in offline mode
      if (!api.getApiStatus().isOffline) {
        try {
          const url = api.getExportRecommendationsUrl(params);
          const res = await fetch(url);
          if (res.ok) {
            csvBlob = await res.blob();
          }
        } catch {
          // Fall through to client-side CSV generation
        }
      }

      // Offline snapshot fallback: build CSV client-side from cached items
      if (!csvBlob) {
        const itemsToExport =
          filteredAndSortedItems.length > 0
            ? filteredAndSortedItems
            : data?.items || [];
        if (itemsToExport.length === 0) {
          throw new Error("No inventory recommendations available to export");
        }

        const headers = [
          "material",
          "area",
          "urgency_rank",
          "status",
          "days_remaining",
          "current_stock",
          "reorder_point_rop",
          "safety_stock_ss",
          "recommended_order_quantity",
          "eoq_quantity",
          "order_up_to_level",
          "predicted_lead_time_days",
          "demand_rate_d",
          "demand_error_std_sigma_d",
          "calibrated_lead_time_std_sigma_l",
          "low_confidence",
          "weak_normal_assumption",
          "is_quantity_extrapolation",
          "as_of_date",
        ];

        const rows = [headers.join(",")];
        for (const item of itemsToExport) {
          const row = headers.map((h) => {
            const val = (item as any)[h];
            if (val === undefined || val === null) return "";
            if (typeof val === "string") return `"${val.replace(/"/g, '""')}"`;
            return val;
          });
          rows.push(row.join(","));
        }
        csvBlob = new Blob([rows.join("\n")], { type: "text/csv;charset=utf-8;" });
      }

      const downloadUrl = window.URL.createObjectURL(csvBlob);
      const a = document.createElement("a");
      a.href = downloadUrl;
      const dateTag = data?.as_of_date || "2016-04-24";
      a.download = `raphael_recommendations_${statusFilter ? `${statusFilter.toLowerCase()}_` : ""}${dateTag}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(downloadUrl);

      setExportFeedback(`Exported ${filteredAndSortedItems.length} rows`);
      setTimeout(() => setExportFeedback(null), 4000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setExportFeedback(`Export failed: ${msg}`);
      setTimeout(() => setExportFeedback(null), 5000);
    } finally {
      setIsExporting(false);
    }
  };

  // Navigate to forecast studio for pair
  const handleRowClick = (material: string, area: string) => {
    router.push(
      `/forecast?material=${encodeURIComponent(material)}&area=${encodeURIComponent(area)}`
    );
  };

  const statusBreakdown = data?.status_breakdown || {
    CRITICAL: 0,
    REORDER: 0,
    OK: 0,
  };
  const criticalCount = statusBreakdown.CRITICAL || 0;
  const reorderCount = statusBreakdown.REORDER || 0;
  const okCount = statusBreakdown.OK || 0;
  const totalCount = data?.total_pairs || 0;

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 space-y-6">
      {/* Top Header & Breadcrumbs */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/[0.08] pb-5">
        <div className="space-y-1.5">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-xs text-zinc-400 hover:text-[#00F2FE] transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Back to Overview</span>
          </Link>
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-2xl bg-[#00F2FE]/10 border border-[#00F2FE]/25 flex items-center justify-center text-[#00F2FE]">
              <Box className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-white">
                  Inventory Replenishment &amp; Urgency
                </h1>
                {process.env.NODE_ENV === "development" && (
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-white/[0.05] text-zinc-400 border border-white/[0.1]">
                    Phase 7 Step 6
                  </span>
                )}
              </div>
              <p className="text-xs text-zinc-400">
                Fleet-wide ranking by days remaining, stockout risk triage, and automated order sizing across all 75 pairs.
              </p>
            </div>
          </div>
        </div>

        {/* Global CSV Export Action */}
        <div className="flex items-center gap-3">
          <button
            onClick={loadUrgencyData}
            disabled={isLoading}
            title="Refresh Table Data"
            className="glass-pill p-2 text-zinc-400 hover:text-white border border-white/[0.1] hover:bg-white/[0.06] transition-colors disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
          </button>

          <button
            onClick={handleExportCsv}
            disabled={isExporting || isLoading || filteredAndSortedItems.length === 0}
            className="glow-cyan-btn px-4 py-2 rounded-xl text-xs font-mono font-medium flex items-center gap-2 group transition-all disabled:opacity-50 cursor-pointer"
          >
            {isExporting ? (
              <RefreshCw className="h-3.5 w-3.5 animate-spin" />
            ) : exportFeedback ? (
              <Check className="h-3.5 w-3.5 text-black" />
            ) : (
              <Download className="h-3.5 w-3.5" />
            )}
            <span>
              {isExporting
                ? "Exporting..."
                : exportFeedback || "Export CSV"}
            </span>
          </button>
        </div>
      </div>

      {/* Global CRITICAL Alert Banner: Triggered whenever critical items exist */}
      {criticalCount > 0 && (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          className="relative overflow-hidden rounded-2xl border border-rose-500/30 bg-rose-950/20 bg-[linear-gradient(135deg,rgba(255,255,255,0.05),rgba(255,255,255,0.01))] p-4 sm:p-5 shadow-[0_0_30px_rgba(244,63,94,0.12)]"
        >
          <div className="flex items-start sm:items-center justify-between gap-4">
            <div className="flex items-start sm:items-center gap-3.5">
              <div className="h-10 w-10 shrink-0 rounded-xl bg-rose-500/15 border border-rose-500/30 flex items-center justify-center text-rose-400 shadow-[0_0_12px_rgba(244,63,94,0.3)]">
                <ShieldAlert className="h-5 w-5" />
              </div>
              <div className="space-y-0.5">
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold text-rose-200">
                    {criticalCount} items will run out before an order can arrive
                  </h3>
                  <span className="h-2 w-2 rounded-full bg-rose-500 animate-ping" />
                </div>
                <p className="text-xs text-rose-300/80 leading-relaxed">
                  On-hand stock cover is shorter than supplier lead time. Immediate purchase orders or expedited shipment required to prevent stockouts.
                </p>
              </div>
            </div>

            <button
              onClick={() => setStatusFilter(statusFilter === "CRITICAL" ? null : "CRITICAL")}
              className={`shrink-0 px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-all cursor-pointer ${
                statusFilter === "CRITICAL"
                  ? "bg-rose-500 text-white shadow-[0_0_12px_rgba(244,63,94,0.5)]"
                  : "bg-rose-500/20 text-rose-300 border border-rose-500/30 hover:bg-rose-500/30"
              }`}
            >
              {statusFilter === "CRITICAL" ? "Show All" : "Filter Critical"}
            </button>
          </div>
        </motion.div>
      )}

      {/* Summary Strip: 3 Clickable Triage Counters from API */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
        {/* CRITICAL Card */}
        <button
          onClick={() => setStatusFilter(statusFilter === "CRITICAL" ? null : "CRITICAL")}
          className={`relative text-left rounded-2xl p-4 sm:p-5 transition-all border cursor-pointer ${
            statusFilter === "CRITICAL"
              ? "border-rose-500/60 bg-rose-950/30 shadow-[0_0_24px_rgba(244,63,94,0.25)] ring-1 ring-rose-500/50"
              : "border-rose-500/20 bg-rose-950/10 hover:border-rose-500/40 hover:bg-rose-950/20"
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-mono uppercase tracking-wider text-rose-400 font-medium">
              Stockout Risk &lt; Lead Time
            </span>
            <span className="h-2.5 w-2.5 rounded-full bg-rose-500 shadow-[0_0_8px_#f43f5e] animate-pulse" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl sm:text-4xl font-mono font-bold text-white tabular-nums">
              {isLoading ? "—" : criticalCount}
            </span>
            <span className="text-xs font-mono text-rose-400">CRITICAL</span>
          </div>
          <p className="mt-1 text-[11px] text-zinc-400">
            Stock depletes before lead time expires. Expedited PO required.
          </p>
        </button>

        {/* REORDER Card */}
        <button
          onClick={() => setStatusFilter(statusFilter === "REORDER" ? null : "REORDER")}
          className={`relative text-left rounded-2xl p-4 sm:p-5 transition-all border cursor-pointer ${
            statusFilter === "REORDER"
              ? "border-amber-500/60 bg-amber-950/30 shadow-[0_0_24px_rgba(245,158,11,0.25)] ring-1 ring-amber-500/50"
              : "border-amber-500/20 bg-amber-950/10 hover:border-amber-500/40 hover:bg-amber-950/20"
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-mono uppercase tracking-wider text-amber-400 font-medium">
              At or Below Reorder Point
            </span>
            <span className="h-2.5 w-2.5 rounded-full bg-amber-400 shadow-[0_0_8px_#f59e0b]" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl sm:text-4xl font-mono font-bold text-white tabular-nums">
              {isLoading ? "—" : reorderCount}
            </span>
            <span className="text-xs font-mono text-amber-400">REORDER</span>
          </div>
          <p className="mt-1 text-[11px] text-zinc-400">
            Stock is within reorder buffer. Place regular replenishment order.
          </p>
        </button>

        {/* OK Card */}
        <button
          onClick={() => setStatusFilter(statusFilter === "OK" ? null : "OK")}
          className={`relative text-left rounded-2xl p-4 sm:p-5 transition-all border cursor-pointer ${
            statusFilter === "OK"
              ? "border-emerald-500/60 bg-emerald-950/30 shadow-[0_0_24px_rgba(16,185,129,0.25)] ring-1 ring-emerald-500/50"
              : "border-emerald-500/20 bg-emerald-950/10 hover:border-emerald-500/40 hover:bg-emerald-950/20"
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-mono uppercase tracking-wider text-emerald-400 font-medium">
              Healthy Stock Cover
            </span>
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-400 shadow-[0_0_8px_#10b981]" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl sm:text-4xl font-mono font-bold text-white tabular-nums">
              {isLoading ? "—" : okCount}
            </span>
            <span className="text-xs font-mono text-emerald-400">HEALTHY</span>
          </div>
          <p className="mt-1 text-[11px] text-zinc-400">
            Comfortably above ROP. No purchase order required at this review.
          </p>
        </button>
      </div>

      {/* Filter and Search Toolbar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pt-2">
        <div className="flex flex-wrap items-center gap-2.5 flex-1">
          {/* Search Box */}
          <div className="relative min-w-[240px] flex-1 max-w-sm">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
            <input
              type="text"
              placeholder="Search material or area..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-8 py-2 rounded-xl bg-white/[0.03] border border-white/[0.1] text-xs text-white placeholder-zinc-500 focus:outline-none focus:border-[#00F2FE]/50 focus:ring-1 focus:ring-[#00F2FE]/30 transition-all font-mono"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-white cursor-pointer"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          {/* Area Filter Dropdown */}
          <div className="relative">
            <select
              value={areaFilter}
              onChange={(e) => setAreaFilter(e.target.value)}
              className="appearance-none pl-3 pr-8 py-2 rounded-xl bg-white/[0.045] shadow-[inset_0_1px_0_rgba(255,255,255,0.1)] border border-white/[0.1] text-xs font-mono text-zinc-200 focus:outline-none focus:border-[#00F2FE]/50 transition-all cursor-pointer"
            >
              <option value="ALL">
                All Areas ({totalCount} pairs)
              </option>
              {distinctAreas.map((area) => (
                <option key={area} value={area}>
                  {area}
                </option>
              ))}
            </select>
            <Filter className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500 pointer-events-none" />
          </div>

          {/* Status Filter Badges */}
          <div className="inline-flex items-center gap-1 p-1 rounded-xl bg-white/[0.02] border border-white/[0.08]">
            <button
              onClick={() => setStatusFilter(null)}
              className={`px-2.5 py-1 rounded-lg text-xs font-mono transition-all cursor-pointer ${
                statusFilter === null
                  ? "bg-white/[0.1] text-white font-medium"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              All ({totalCount})
            </button>
            <button
              onClick={() => setStatusFilter("CRITICAL")}
              className={`px-2.5 py-1 rounded-lg text-xs font-mono transition-all cursor-pointer ${
                statusFilter === "CRITICAL"
                  ? "bg-rose-500/25 text-rose-300 font-medium border border-rose-500/40"
                  : "text-rose-400/80 hover:text-rose-300"
              }`}
            >
              Critical ({criticalCount})
            </button>
            <button
              onClick={() => setStatusFilter("REORDER")}
              className={`px-2.5 py-1 rounded-lg text-xs font-mono transition-all cursor-pointer ${
                statusFilter === "REORDER"
                  ? "bg-amber-500/25 text-amber-300 font-medium border border-amber-500/40"
                  : "text-amber-400/80 hover:text-amber-300"
              }`}
            >
              Reorder ({reorderCount})
            </button>
            <button
              onClick={() => setStatusFilter("OK")}
              className={`px-2.5 py-1 rounded-lg text-xs font-mono transition-all cursor-pointer ${
                statusFilter === "OK"
                  ? "bg-emerald-500/25 text-emerald-300 font-medium border border-emerald-500/40"
                  : "text-emerald-400/80 hover:text-emerald-300"
              }`}
            >
              Healthy ({okCount})
            </button>
          </div>
        </div>

        {/* Counter Summary */}
        <div className="text-xs font-mono text-zinc-400 flex items-center gap-2">
          <span>Showing</span>
          <span className="text-[#00F2FE] font-bold">{filteredAndSortedItems.length}</span>
          <span>of {totalCount} pairs</span>
          {(statusFilter || areaFilter !== "ALL" || searchQuery) && (
            <button
              onClick={() => {
                setStatusFilter(null);
                setAreaFilter("ALL");
                setSearchQuery("");
              }}
              className="text-xs text-zinc-500 hover:text-zinc-300 underline ml-2 cursor-pointer"
            >
              Reset filters
            </button>
          )}
        </div>
      </div>

      {/* Main Urgency Table Container */}
      <div className="rounded-2xl border border-white/[0.08] bg-white/[0.015] shadow-[0_8px_32px_rgba(0,0,0,0.4)] overflow-hidden">
        <div className="overflow-x-auto min-h-[420px]">
          <table className="w-full text-left border-collapse font-sans text-xs">
            {/* Table Header: Sticky */}
            <thead>
              <tr className="sticky top-0 glass-table-head z-10 border-b border-white/[0.08] text-[11px] font-mono text-zinc-400 tracking-wider uppercase select-none">
                <th
                  onClick={() => handleSort("urgency_rank")}
                  className="py-3 px-3.5 cursor-pointer hover:text-white transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Rank</span>
                    <SortIcon field="urgency_rank" current={sortField} dir={sortDirection} />
                  </div>
                </th>
                <th
                  onClick={() => handleSort("material")}
                  className="py-3 px-4 cursor-pointer hover:text-white transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Material &amp; Area</span>
                    <SortIcon field="material" current={sortField} dir={sortDirection} />
                  </div>
                </th>
                <th
                  onClick={() => handleSort("status")}
                  className="py-3 px-3 cursor-pointer hover:text-white transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Status</span>
                    <SortIcon field="status" current={sortField} dir={sortDirection} />
                  </div>
                </th>
                <th
                  onClick={() => handleSort("current_stock")}
                  className="py-3 px-3 cursor-pointer hover:text-white transition-colors text-right"
                >
                  <div className="flex items-center justify-end gap-1.5">
                    <span>Stock</span>
                    <SortIcon field="current_stock" current={sortField} dir={sortDirection} />
                  </div>
                </th>
                <th
                  onClick={() => handleSort("days_remaining")}
                  className="py-3 px-3 cursor-pointer hover:text-white transition-colors text-right"
                >
                  <div className="flex items-center justify-end gap-1.5">
                    <span>Cover Days</span>
                    <SortIcon field="days_remaining" current={sortField} dir={sortDirection} />
                  </div>
                </th>
                <th
                  onClick={() => handleSort("reorder_point_rop")}
                  className="py-3 px-3 cursor-pointer hover:text-white transition-colors text-right"
                >
                  <div className="flex items-center justify-end gap-1.5">
                    <span>ROP</span>
                    <SortIcon field="reorder_point_rop" current={sortField} dir={sortDirection} />
                  </div>
                </th>
                <th
                  onClick={() => handleSort("safety_stock_ss")}
                  className="py-3 px-3 cursor-pointer hover:text-white transition-colors text-right"
                >
                  <div className="flex items-center justify-end gap-1.5">
                    <span>SS</span>
                    <SortIcon field="safety_stock_ss" current={sortField} dir={sortDirection} />
                  </div>
                </th>
                <th
                  onClick={() => handleSort("predicted_lead_time_days")}
                  className="py-3 px-3 cursor-pointer hover:text-white transition-colors text-right"
                >
                  <div className="flex items-center justify-end gap-1.5">
                    <span>Lead Time</span>
                    <SortIcon field="predicted_lead_time_days" current={sortField} dir={sortDirection} />
                  </div>
                </th>
                <th
                  onClick={() => handleSort("recommended_order_quantity")}
                  className="py-3 px-3 cursor-pointer hover:text-white transition-colors text-right"
                >
                  <div className="flex items-center justify-end gap-1.5">
                    <span>Order Qty</span>
                    <SortIcon field="recommended_order_quantity" current={sortField} dir={sortDirection} />
                  </div>
                </th>
                <th className="py-3 px-3 text-center">Signals</th>
              </tr>
            </thead>

            {/* Table Body */}
            <tbody className="divide-y divide-white/[0.04]">
              {isLoading ? (
                // Skeletons during load - zero layout shift
                Array.from({ length: 12 }).map((_, idx) => (
                  <tr key={idx} className="animate-pulse">
                    <td className="py-3.5 px-3.5">
                      <div className="h-4 w-6 rounded bg-white/[0.05]" />
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="space-y-1.5">
                        <div className="h-4 w-28 rounded bg-white/[0.05]" />
                        <div className="h-3 w-16 rounded bg-white/[0.03]" />
                      </div>
                    </td>
                    <td className="py-3.5 px-3">
                      <div className="h-5 w-20 rounded-full bg-white/[0.05]" />
                    </td>
                    <td className="py-3.5 px-3 text-right">
                      <div className="h-4 w-12 rounded bg-white/[0.05] ml-auto" />
                    </td>
                    <td className="py-3.5 px-3 text-right">
                      <div className="h-4 w-14 rounded bg-white/[0.05] ml-auto" />
                    </td>
                    <td className="py-3.5 px-3 text-right">
                      <div className="h-4 w-12 rounded bg-white/[0.05] ml-auto" />
                    </td>
                    <td className="py-3.5 px-3 text-right">
                      <div className="h-4 w-12 rounded bg-white/[0.05] ml-auto" />
                    </td>
                    <td className="py-3.5 px-3 text-right">
                      <div className="h-4 w-14 rounded bg-white/[0.05] ml-auto" />
                    </td>
                    <td className="py-3.5 px-3 text-right">
                      <div className="h-4 w-14 rounded bg-white/[0.05] ml-auto" />
                    </td>
                    <td className="py-3.5 px-3 text-center">
                      <div className="h-4 w-16 rounded bg-white/[0.05] mx-auto" />
                    </td>
                  </tr>
                ))
              ) : error ? (
                <tr>
                  <td colSpan={10} className="py-12 text-center">
                    <div className="inline-flex flex-col items-center gap-3">
                      <AlertTriangle className="h-6 w-6 text-rose-400" />
                      <div className="text-sm font-medium text-white">Failed to load urgency data</div>
                      <p className="text-xs text-zinc-400 max-w-sm">{error}</p>
                      <button
                        onClick={loadUrgencyData}
                        className="mt-2 px-4 py-1.5 rounded-xl bg-white/[0.08] hover:bg-white/[0.12] text-xs font-mono text-white transition-colors cursor-pointer"
                      >
                        Retry
                      </button>
                    </div>
                  </td>
                </tr>
              ) : filteredAndSortedItems.length === 0 ? (
                <tr>
                  <td colSpan={10} className="py-12 text-center text-zinc-400">
                    <p className="text-sm font-medium">No items match your active filters.</p>
                    <button
                      onClick={() => {
                        setStatusFilter(null);
                        setAreaFilter("ALL");
                        setSearchQuery("");
                      }}
                      className="mt-2 text-xs text-[#00F2FE] hover:underline font-mono cursor-pointer"
                    >
                      Clear all filters
                    </button>
                  </td>
                </tr>
              ) : (
                filteredAndSortedItems.map((item, idx) => {
                  const isCritical = item.status.toUpperCase() === "CRITICAL";
                  const isReorder = item.status.toUpperCase() === "REORDER";
                  const isOk = item.status.toUpperCase() === "OK";
                  const stockoutBeforeLeadTime =
                    item.days_remaining <= item.predicted_lead_time_days;

                  return (
                    <motion.tr
                      key={`${item.material}-${item.area}`}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{
                        duration: 0.2,
                        delay: Math.min(idx, 15) * 0.02,
                        ease: "easeOut",
                      }}
                      onClick={() => handleRowClick(item.material, item.area)}
                      className="group cursor-pointer hover:bg-white/[0.035] transition-colors relative"
                    >
                      {/* Rank */}
                      <td className="py-3 px-3.5 font-mono text-zinc-400 text-xs">
                        <span
                          className={`font-semibold ${
                            item.urgency_rank <= 5
                              ? "text-rose-400"
                              : item.urgency_rank <= 25
                              ? "text-amber-400"
                              : "text-zinc-500"
                          }`}
                        >
                          #{item.urgency_rank}
                        </span>
                      </td>

                      {/* Material & Area */}
                      <td className="py-3 px-4">
                        <div className="flex flex-col gap-0.5">
                          <div className="flex items-center gap-1.5">
                            <span className="font-mono font-medium text-white group-hover:text-[#00F2FE] transition-colors">
                              {item.material}
                            </span>
                            <ExternalLink className="h-3 w-3 text-zinc-600 group-hover:text-[#00F2FE] transition-colors opacity-0 group-hover:opacity-100" />
                          </div>
                          <div className="flex items-center gap-2 text-[11px] font-mono text-zinc-400">
                            <span>{item.area}</span>
                            <span className="text-zinc-600">•</span>
                            <span className="text-zinc-500 text-[10px]">
                              {item.champion_model.replace(/_/g, " ")}
                            </span>
                          </div>
                        </div>
                      </td>

                      {/* Status Chip */}
                      <td className="py-3 px-3 whitespace-nowrap">
                        {isCritical ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-medium bg-rose-500/15 text-rose-300 border border-rose-500/30 shadow-[0_0_8px_rgba(244,63,94,0.2)]">
                            <span className="h-1.5 w-1.5 rounded-full bg-rose-500 animate-pulse" />
                            CRITICAL
                          </span>
                        ) : isReorder ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-medium bg-amber-500/15 text-amber-300 border border-amber-500/30">
                            <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                            REORDER
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-medium bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                            HEALTHY
                          </span>
                        )}
                      </td>

                      {/* Stock On-Hand */}
                      <td className="py-3 px-3 text-right font-mono tabular-nums text-zinc-200">
                        {item.current_stock.toFixed(0)}
                      </td>

                      {/* Cover Days */}
                      <td className="py-3 px-3 text-right font-mono tabular-nums">
                        {item.beyond_horizon ? (
                          <span className="text-emerald-400 font-medium">&gt;90d</span>
                        ) : (
                          <span
                            className={`font-semibold ${
                              item.days_remaining <= item.predicted_lead_time_days
                                ? "text-rose-400"
                                : item.days_remaining < 14
                                ? "text-amber-400"
                                : "text-emerald-400"
                            }`}
                          >
                            {item.days_remaining.toFixed(1)}d
                          </span>
                        )}
                      </td>

                      {/* ROP */}
                      <td className="py-3 px-3 text-right font-mono tabular-nums text-zinc-300">
                        {item.reorder_point_rop.toFixed(1)}
                      </td>

                      {/* Safety Stock */}
                      <td className="py-3 px-3 text-right font-mono tabular-nums text-zinc-400">
                        {item.safety_stock_ss.toFixed(1)}
                      </td>

                      {/* Predicted Lead Time */}
                      <td className="py-3 px-3 text-right font-mono tabular-nums text-zinc-300 whitespace-nowrap">
                        <span>{item.predicted_lead_time_days.toFixed(1)}d</span>
                        <span className="text-[10px] text-zinc-500 ml-1">
                          ±{item.calibrated_lead_time_std_sigma_l.toFixed(1)}
                        </span>
                      </td>

                      {/* Recommended Order Qty */}
                      <td className="py-3 px-3 text-right font-mono tabular-nums">
                        {item.recommended_order_quantity > 0 ? (
                          <span className="inline-block px-2 py-0.5 rounded-lg bg-[#00F2FE]/10 text-[#00F2FE] border border-[#00F2FE]/25 font-bold shadow-[0_0_8px_rgba(0,242,254,0.15)]">
                            {item.recommended_order_quantity.toFixed(0)}
                          </span>
                        ) : (
                          <span className="text-zinc-600">—</span>
                        )}
                      </td>

                      {/* Badges / Signals */}
                      <td className="py-3 px-3 text-center whitespace-nowrap">
                        <div className="flex items-center justify-center gap-1.5">
                          {stockoutBeforeLeadTime && (
                            <span
                              title="Stock exhausts before supplier lead time! Immediate purchase order required."
                              className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-rose-500/20 text-rose-300 border border-rose-500/30"
                            >
                              PO NOW
                            </span>
                          )}
                          {item.low_confidence && (
                            <span
                              title="High error variance on historical holdout (>0.45 WAPE)"
                              className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-amber-500/20 text-amber-300 border border-amber-500/30"
                            >
                              Low Conf
                            </span>
                          )}
                          {item.is_quantity_extrapolation && (
                            <span
                              title="Lead time estimated at the largest historical order size; bigger orders may take longer"
                              className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-purple-500/20 text-purple-300 border border-purple-500/30 cursor-help"
                            >
                              Extrap
                            </span>
                          )}
                          {!stockoutBeforeLeadTime && !item.low_confidence && !item.is_quantity_extrapolation && (
                            <span className="text-zinc-700 text-[10px]">—</span>
                          )}
                        </div>
                      </td>
                    </motion.tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Table Footer Strip */}
        <div className="p-3.5 bg-white/[0.025] border-t border-white/[0.06] flex flex-col sm:flex-row items-center justify-between text-[11px] font-mono text-zinc-500 gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span>Deterministic Policy:</span>
            <code className="text-zinc-300">ROP = D × L + z × σ_LTD</code>
            <span className="text-zinc-600">•</span>
            <span>z = 1.645 (95% SL)</span>
            <span className="text-zinc-600">•</span>
            <span className="text-zinc-400">No open purchase orders are modeled; stock position equals on-hand stock.</span>
          </div>
          <div>
            Click any row to open full Demand Studio with 90-day trajectory.
          </div>
        </div>
      </div>
    </div>
  );
}

// Small helper for sort arrow indicator
function SortIcon({
  field,
  current,
  dir,
}: {
  field: SortField;
  current: SortField;
  dir: SortDirection;
}) {
  if (current !== field) {
    return <ArrowUpDown className="h-3 w-3 text-zinc-600" />;
  }
  return dir === "asc" ? (
    <ArrowUp className="h-3 w-3 text-[#00F2FE]" />
  ) : (
    <ArrowDown className="h-3 w-3 text-[#00F2FE]" />
  );
}
