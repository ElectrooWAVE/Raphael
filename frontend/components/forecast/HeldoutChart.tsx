"use client";

import React, { useMemo } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import type { HeldoutPoint } from "../../lib/api";

export type HeldoutGranularity = "daily" | "weekly";

interface HeldoutChartProps {
  points: HeldoutPoint[];
  granularity: HeldoutGranularity;
  /** Pair accuracy from the saved evaluation (/forecast.accuracy), matching granularity. */
  wape?: number | null;
}

interface Row {
  label: string;
  actual: number;
  predicted: number;
  span: string;
}

/** Weekly view: consecutive 7-day blocks of the 84-day window, units summed. */
function aggregateWeekly(points: HeldoutPoint[]): Row[] {
  const rows: Row[] = [];
  for (let i = 0; i + 7 <= points.length; i += 7) {
    const block = points.slice(i, i + 7);
    rows.push({
      label: block[0].ds,
      span: `${block[0].ds} → ${block[6].ds}`,
      actual: block.reduce((s, p) => s + p.actual, 0),
      predicted: block.reduce((s, p) => s + p.predicted, 0),
    });
  }
  return rows;
}

const HeldoutTooltip: React.FC<{ active?: boolean; payload?: { payload: Row }[]; granularity: HeldoutGranularity }> = ({
  active,
  payload,
  granularity,
}) => {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  const err = r.actual > 0 ? ((r.predicted - r.actual) / r.actual) * 100 : null;
  return (
    <div className="rounded-xl glass-popover p-3 shadow-2xl text-xs font-mono space-y-1.5 min-w-[210px]">
      <div className="text-zinc-400 border-b border-white/[0.08] pb-1.5">
        {granularity === "weekly" ? `Week ${r.span}` : r.label}
      </div>
      <div className="flex justify-between gap-4">
        <span className="text-zinc-300">Actual units:</span>
        <span className="text-white font-semibold">{r.actual.toFixed(granularity === "weekly" ? 0 : 1)}</span>
      </div>
      <div className="flex justify-between gap-4">
        <span className="text-[#00F2FE]">Predicted units:</span>
        <span className="text-[#00F2FE] font-bold">{r.predicted.toFixed(granularity === "weekly" ? 0 : 1)}</span>
      </div>
      {err !== null && (
        <div className="flex justify-between gap-4 text-zinc-400 border-t border-white/[0.06] pt-1">
          <span>Prediction error:</span>
          <span className={Math.abs(err) > 30 ? "text-amber-400" : "text-zinc-200"}>
            {err > 0 ? "+" : ""}
            {err.toFixed(0)}%
          </span>
        </div>
      )}
    </div>
  );
};

export const HeldoutChart: React.FC<HeldoutChartProps> = ({ points, granularity, wape }) => {
  const rows: Row[] = useMemo(
    () =>
      granularity === "weekly"
        ? aggregateWeekly(points)
        : points.map((p) => ({ label: p.ds, span: p.ds, actual: p.actual, predicted: p.predicted })),
    [points, granularity]
  );

  const tickLabels = useMemo(() => {
    const step = Math.max(1, Math.floor(rows.length / 8));
    return rows.filter((_, i) => i % step === 0).map((r) => r.label);
  }, [rows]);

  if (!points.length) {
    return (
      <div className="h-[440px] rounded-2xl border border-white/[0.08] bg-white/[0.02] flex items-center justify-center text-xs font-mono text-zinc-400">
        No held-out evaluation window is saved for this pair.
      </div>
    );
  }

  return (
    <div className="w-full space-y-3">
      <div className="w-full h-[380px] sm:h-[440px] rounded-2xl glass-surface p-4 sm:p-6" id="heldout-chart">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 16, right: 24, left: 0, bottom: 8 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.05)" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="label"
              stroke="#52525B"
              tickLine={false}
              ticks={tickLabels}
              tick={{ fill: "#71717A", fontSize: 11, fontFamily: "monospace" }}
              dy={8}
            />
            <YAxis
              stroke="#52525B"
              tickLine={false}
              tick={{ fill: "#71717A", fontSize: 11, fontFamily: "monospace" }}
              domain={[0, "auto"]}
              dx={-6}
            />
            <Tooltip content={<HeldoutTooltip granularity={granularity} />} />
            <Line type="monotone" dataKey="actual" stroke="#E4E4E7" strokeWidth={2} dot={granularity === "weekly" ? { r: 3, fill: "#E4E4E7" } : false} isAnimationActive={false} />
            <Line
              type="monotone"
              dataKey="predicted"
              stroke="#00F2FE"
              strokeWidth={2.2}
              strokeDasharray="4 4"
              dot={granularity === "weekly" ? { r: 3, fill: "#00F2FE" } : false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-zinc-400 px-2 font-mono">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="h-0.5 w-4 bg-[#E4E4E7]" />
            <span>Actual demand</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="h-0.5 w-4 border-b-2 border-dashed border-[#00F2FE]" />
            <span className="text-zinc-200">Champion prediction</span>
          </div>
          <span className="text-zinc-500">
            {points[0].ds} → {points[points.length - 1].ds} ({points.length} days, never seen in training)
          </span>
        </div>
        <div className="text-[11px] text-zinc-300">
          {wape !== null && wape !== undefined
            ? `${granularity === "weekly" ? "Weekly" : "Daily"} WAPE ${(wape * 100).toFixed(1)}% on this window`
            : "WAPE not computed yet"}
        </div>
      </div>
    </div>
  );
};
