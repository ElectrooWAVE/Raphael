"use client";

import React, { useMemo } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  CartesianGrid,
} from "recharts";
import type { HistoryDataPoint, ForecastDataPoint } from "../../lib/api";

export interface SimulatedForecastPoint extends ForecastDataPoint {
  simulated_yhat?: number;
}

interface ForecastChartProps {
  history: HistoryDataPoint[];
  forecast: SimulatedForecastPoint[];
  asOfDate?: string;
  intervalLevel: 80 | 95;
  isSimulatingPromo?: boolean;
}

interface ChartPoint {
  date: string;
  history?: number | null;
  forecast?: number | null;
  simulated?: number | null;
  lower?: number | null;
  upper?: number | null;
  band?: [number, number] | null;
  isPromotion?: number;
  isForecast: boolean;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: any[];
  label?: string;
}

const CustomTooltip: React.FC<CustomTooltipProps> = ({ active, payload, label }) => {
  if (!active || !payload || !payload.length) return null;

  const dataPoint = payload[0]?.payload as ChartPoint | undefined;
  if (!dataPoint) return null;

  return (
    <div className="rounded-xl glass-popover p-3 shadow-2xl text-xs font-mono space-y-1.5 min-w-[200px]">
      <div className="flex items-center justify-between border-b border-white/[0.08] pb-1.5 text-zinc-400">
        <span>{label}</span>
        <span className="text-[10px] uppercase tracking-wider text-zinc-500">
          {dataPoint.isForecast ? "Forecast Period" : "Historical Actual"}
        </span>
      </div>

      {dataPoint.history !== undefined && dataPoint.history !== null && (
        <div className="flex items-center justify-between gap-4">
          <span className="text-zinc-400 flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-slate-400" />
            Historical Units:
          </span>
          <span className="text-white font-semibold">{dataPoint.history.toFixed(1)}</span>
        </div>
      )}

      {dataPoint.forecast !== undefined && dataPoint.forecast !== null && (
        <div className="flex items-center justify-between gap-4">
          <span className="text-[#00F2FE] flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-[#00F2FE] shadow-[0_0_6px_#00F2FE]" />
            Predicted Units:
          </span>
          <span className="text-[#00F2FE] font-bold">{dataPoint.forecast.toFixed(1)}</span>
        </div>
      )}

      {dataPoint.simulated !== undefined && dataPoint.simulated !== null && (
        <div className="flex items-center justify-between gap-4 text-[#EC4899]">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-[#EC4899] shadow-[0_0_6px_#EC4899]" />
            Simulated Lift:
          </span>
          <span className="font-bold">{dataPoint.simulated.toFixed(1)}</span>
        </div>
      )}

      {dataPoint.lower !== undefined && dataPoint.upper !== undefined && dataPoint.lower !== null && dataPoint.upper !== null && (
        <div className="flex items-center justify-between gap-4 text-zinc-400 pt-1 border-t border-white/[0.06] text-[11px]">
          <span>Prediction Band:</span>
          <span className="text-zinc-300">
            [{dataPoint.lower.toFixed(1)} &mdash; {dataPoint.upper.toFixed(1)}]
          </span>
        </div>
      )}

      {dataPoint.isPromotion === 1 && (
        <div className="pt-1 text-[10px] text-amber-400 font-sans">
          ★ Promotional event active on this date
        </div>
      )}
    </div>
  );
};

export const ForecastChart: React.FC<ForecastChartProps> = ({
  history,
  forecast,
  asOfDate = "2016-04-24",
  intervalLevel,
  isSimulatingPromo = false,
}) => {
  // Format history and forecast points into continuous timeline
  const chartData = useMemo(() => {
    const points: ChartPoint[] = [];

    // History points
    history.forEach((h) => {
      points.push({
        date: h.date,
        history: h.quantity,
        forecast: null,
        lower: null,
        upper: null,
        band: null,
        isPromotion: h.is_promotion,
        isForecast: false,
      });
    });

    // Bridge point: Connect history last day to forecast start
    if (history.length > 0 && points.length > 0) {
      const lastHist = points[points.length - 1];
      if (lastHist.date === asOfDate) {
        lastHist.forecast = lastHist.history;
      }
    }

    // Forecast points
    forecast.forEach((f) => {
      const lower =
        intervalLevel === 80 ? f.yhat_lower_80 ?? null : f.yhat_lower_95 ?? null;
      const upper =
        intervalLevel === 80 ? f.yhat_upper_80 ?? null : f.yhat_upper_95 ?? null;
      const hasBand = lower !== null && upper !== null;

      points.push({
        date: f.ds,
        history: null,
        forecast: f.yhat,
        simulated: isSimulatingPromo && f.simulated_yhat !== undefined ? f.simulated_yhat : null,
        lower,
        upper,
        band: hasBand ? [lower, upper] : null,
        isForecast: true,
      });
    });

    return points;
  }, [history, forecast, asOfDate, intervalLevel, isSimulatingPromo]);

  // Determine tick interval for XAxis
  const tickDates = useMemo(() => {
    if (chartData.length === 0) return [];
    const step = Math.max(1, Math.floor(chartData.length / 8));
    return chartData.filter((_, idx) => idx % step === 0).map((p) => p.date);
  }, [chartData]);

  return (
    <div className="w-full space-y-3">
      {/* Chart Canvas */}
      <div className="w-full h-[380px] sm:h-[440px] rounded-2xl glass-surface p-4 sm:p-6 relative">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={chartData}
            margin={{ top: 20, right: 24, left: 0, bottom: 8 }}
          >
            <defs>
              <linearGradient id="bandGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#00F2FE" stopOpacity={0.18} />
                <stop offset="100%" stopColor="#00F2FE" stopOpacity={0.04} />
              </linearGradient>
              <filter id="cyanGlow" x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="3" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            <CartesianGrid
              stroke="rgba(255, 255, 255, 0.05)"
              strokeDasharray="3 3"
              vertical={false}
            />

            <XAxis
              dataKey="date"
              stroke="#52525B"
              tickLine={false}
              tick={{ fill: "#71717A", fontSize: 11, fontFamily: "monospace" }}
              ticks={tickDates}
              dy={8}
            />

            <YAxis
              stroke="#52525B"
              tickLine={false}
              tick={{ fill: "#71717A", fontSize: 11, fontFamily: "monospace" }}
              dx={-6}
              domain={[0, "auto"]}
            />

            <Tooltip content={<CustomTooltip />} />

            {/* Vertical Freeze Line: "As of 2016-04-24" */}
            <ReferenceLine
              x={asOfDate}
              stroke="#FFFFFF"
              strokeDasharray="3 3"
              strokeOpacity={0.45}
              label={{
                value: `As of ${asOfDate}`,
                position: "insideTopLeft",
                fill: "#E4E4E7",
                fontSize: 11,
                fontFamily: "monospace",
                offset: 8,
              }}
            />

            {/* Translucent Interval Band */}
            <Area
              type="monotone"
              dataKey="band"
              stroke="none"
              fill="url(#bandGradient)"
              isAnimationActive={false}
            />

            {/* Historical Demand Solid Line */}
            <Line
              type="monotone"
              dataKey="history"
              stroke="#94A3B8"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />

            {/* Predicted Demand Dashed Cyan Glow Line */}
            <Line
              type="monotone"
              dataKey="forecast"
              stroke="#00F2FE"
              strokeWidth={2.2}
              strokeDasharray="4 4"
              dot={false}
              isAnimationActive={false}
            />

            {/* Simulated Promotion Line (if promo simulator is toggled) */}
            {isSimulatingPromo && (
              <Line
                type="monotone"
                dataKey="simulated"
                stroke="#EC4899"
                strokeWidth={2.4}
                strokeDasharray="2 2"
                dot={false}
                isAnimationActive={false}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Chart Explanatory Legend & Policy Note */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-zinc-400 px-2 font-mono">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="h-0.5 w-4 bg-[#94A3B8]" />
            <span>History (60d)</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="h-0.5 w-4 border-b-2 border-dashed border-[#00F2FE]" />
            <span className="text-zinc-200">Forecast (90d)</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-4 rounded-xs bg-[#00F2FE]/20 border border-[#00F2FE]/40" />
            <span>{intervalLevel}% Prediction Interval</span>
          </div>
          {isSimulatingPromo && (
            <div className="flex items-center gap-2 text-[#EC4899]">
              <span className="h-0.5 w-4 border-b-2 border-dashed border-[#EC4899]" />
              <span>Simulated Uplift</span>
            </div>
          )}
        </div>

        <div className="text-[11px] text-zinc-500 italic">
          Bands reflect day-to-day demand noise for low-volume items.
        </div>
      </div>
    </div>
  );
};
