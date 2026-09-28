"use client";

import { BarChart, HeatmapChart, LineChart, RadarChart, ScatterChart, CustomChart } from "echarts/charts";
import {
  DatasetComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  RadarComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import type { EChartsCoreOption } from "echarts/core";
import { SVGRenderer } from "echarts/renderers";
import { Table2 } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { type ThemeColors, useThemeColors } from "@/lib/theme";

echarts.use([
  BarChart,
  LineChart,
  ScatterChart,
  RadarChart,
  HeatmapChart,
  CustomChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  MarkAreaComponent,
  MarkPointComponent,
  RadarComponent,
  VisualMapComponent,
  DatasetComponent,
  SVGRenderer,
]);

export type OptionBuilder = (c: ThemeColors) => EChartsCoreOption;

/** Shared chrome: recessive hairline grid, muted axis text, tooltip in text tokens. */
export function baseOption(c: ThemeColors): EChartsCoreOption {
  return {
    backgroundColor: "transparent",
    textStyle: { fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif", color: c.ink2, fontSize: 11 },
    animationDuration: 250,
    grid: { left: 8, right: 16, top: 28, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "axis",
      backgroundColor: c.surface,
      borderColor: c.grid,
      textStyle: { color: c.ink, fontSize: 12 },
      axisPointer: { type: "line", lineStyle: { color: c.axis } },
      confine: true,
    },
    legend: {
      top: 0,
      left: 0,
      icon: "roundRect",
      itemWidth: 12,
      itemHeight: 3,
      textStyle: { color: c.ink2 },
    },
  };
}

export function axisStyle(c: ThemeColors) {
  return {
    axisLine: { lineStyle: { color: c.axis } },
    axisTick: { show: false },
    axisLabel: { color: c.muted },
    splitLine: { lineStyle: { color: c.grid } },
  };
}

export interface TableView {
  columns: string[];
  rows: (string | number | null)[][];
  caption: string;
}

export function EChart({
  build,
  height = 260,
  ariaLabel,
  table,
  className,
  footer,
}: {
  build: OptionBuilder;
  height?: number;
  ariaLabel: string;
  table?: TableView;
  className?: string;
  footer?: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const colors = useThemeColors();
  const [showTable, setShowTable] = useState(false);

  useEffect(() => {
    if (!ref.current || !colors) return;
    const inst = echarts.init(ref.current, undefined, { renderer: "svg" });
    chart.current = inst;
    const ro = new ResizeObserver(() => inst.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      inst.dispose();
      chart.current = null;
    };
  }, [colors]);

  useEffect(() => {
    if (!chart.current || !colors) return;
    chart.current.setOption(build(colors), true);
  }, [build, colors]);

  return (
    <div className={cn("min-w-0", className)}>
      <div ref={ref} style={{ height }} role="img" aria-label={ariaLabel} className="w-full" />
      {(table || footer) && (
        <div className="mt-1 flex flex-wrap items-center gap-2">
          {footer}
          {table && (
            <button
              type="button"
              onClick={() => setShowTable(!showTable)}
              className="ml-auto inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-muted hover:bg-surface-2"
              aria-expanded={showTable}
            >
              <Table2 className="size-3" /> {showTable ? "Hide table" : "Table"}
            </button>
          )}
        </div>
      )}
      {table && showTable && (
        <div className="mt-1 max-h-64 overflow-auto rounded-md border border-line">
          <table className="tabular w-full text-right text-xs">
            <caption className="sr-only">{table.caption}</caption>
            <thead className="sticky top-0 bg-surface-2 text-muted">
              <tr>
                {table.columns.map((c, i) => (
                  <th key={c} className={cn("px-2 py-1 font-medium", i === 0 && "text-left")}>
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((r, i) => (
                <tr key={i} className="border-t border-line">
                  {r.map((v, j) => (
                    <td key={j} className={cn("px-2 py-1", j === 0 && "text-left")}>
                      {v ?? "—"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
