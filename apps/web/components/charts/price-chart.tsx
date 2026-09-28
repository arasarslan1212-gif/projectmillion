"use client";

import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  CrosshairMode,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  LineSeries,
  LineStyle,
  type MouseEventParams,
  PriceScaleMode,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { Table2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { formatDate, formatValue } from "@/lib/format";
import { type ThemeColors, useThemeColors, withAlpha } from "@/lib/theme";
import type { AnySection } from "@/lib/types";

type ChartType = "candles" | "line" | "area";
type Range = "1D" | "5D" | "1M" | "3M" | "6M" | "YTD" | "1Y" | "5Y" | "MAX";
const RANGES: Range[] = ["1D", "5D", "1M", "3M", "6M", "YTD", "1Y", "5Y", "MAX"];

export interface ChartEvent {
  date: string;
  kind: "earnings" | "news" | "insider_buy" | "insider_sell" | "analyst" | "filing";
  label: string;
  detail?: string;
  url?: string | null;
  tone?: "good" | "bad" | "neutral";
}

export interface ChartOverlays {
  cone?: { dates: string[]; p10: number[]; p50: number[]; p90: number[] } | null;
  consensus?: { all?: number | null; trusted?: number | null } | null;
  analystTargets?: { date: string; target: number; label: string }[];
  events?: ChartEvent[];
  high52?: number | null;
  low52?: number | null;
}

interface Toggles {
  volume: boolean;
  sma20: boolean;
  sma50: boolean;
  sma200: boolean;
  ema20: boolean;
  bb: boolean;
  rsi: boolean;
  macd: boolean;
  cone: boolean;
  consensus: boolean;
  targets: boolean;
  earnings: boolean;
  news: boolean;
  insiders: boolean;
  dividends: boolean;
  range52: boolean;
  compare: boolean;
}

const DEFAULT_TOGGLES: Toggles = {
  volume: true,
  sma20: false,
  sma50: true,
  sma200: true,
  ema20: false,
  bb: false,
  rsi: false,
  macd: false,
  cone: true,
  consensus: true,
  targets: false,
  earnings: true,
  news: false,
  insiders: false,
  dividends: false,
  range52: false,
  compare: false,
};

const toTime = (d: string) => (Date.parse(`${d}T00:00:00Z`) / 1000) as UTCTimestamp;

function lineData(dates: string[], vals: (number | null)[]) {
  const out: { time: UTCTimestamp; value: number }[] = [];
  for (let i = 0; i < dates.length; i++) {
    const v = vals[i];
    if (v !== null && v !== undefined && Number.isFinite(v)) out.push({ time: toTime(dates[i]), value: v });
  }
  return out;
}

function rangeStart(range: Range, last: Date): Date | null {
  const d = new Date(last);
  switch (range) {
    case "1D":
    case "5D":
      d.setUTCDate(d.getUTCDate() - 7);
      return d;
    case "1M":
      d.setUTCMonth(d.getUTCMonth() - 1);
      return d;
    case "3M":
      d.setUTCMonth(d.getUTCMonth() - 3);
      return d;
    case "6M":
      d.setUTCMonth(d.getUTCMonth() - 6);
      return d;
    case "YTD":
      return new Date(Date.UTC(last.getUTCFullYear(), 0, 1));
    case "1Y":
      d.setUTCFullYear(d.getUTCFullYear() - 1);
      return d;
    case "5Y":
      d.setUTCFullYear(d.getUTCFullYear() - 5);
      return d;
    default:
      return null;
  }
}

function Toggle({
  on,
  onClick,
  children,
  disabled,
  title,
}: {
  on: boolean;
  onClick: () => void;
  children: React.ReactNode;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      title={title}
      onClick={onClick}
      aria-pressed={on}
      className={cn(
        "rounded-md border px-2 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40",
        on ? "border-accent/40 bg-accent-wash text-accent-ink" : "border-line text-ink-2 hover:bg-surface-2",
      )}
    >
      {children}
    </button>
  );
}

interface Readout {
  date: string;
  o?: number;
  h?: number;
  l?: number;
  c?: number;
  v?: number;
  extra: { label: string; value: string; color: string }[];
}

export function PriceChart({
  chart,
  overlays,
  ticker,
}: {
  chart: AnySection;
  overlays?: ChartOverlays;
  ticker: string;
}) {
  const colors = useThemeColors();
  const box = useRef<HTMLDivElement>(null);
  const api = useRef<IChartApi | null>(null);
  const [type, setType] = useState<ChartType>("candles");
  const [range, setRange] = useState<Range>("1Y");
  const [log, setLog] = useState(false);
  const [t, setT] = useState<Toggles>(DEFAULT_TOGGLES);
  const [readout, setReadout] = useState<Readout | null>(null);
  const [showTable, setShowTable] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<ChartEvent | null>(null);
  const flip = (k: keyof Toggles) => setT((s) => ({ ...s, [k]: !s[k] }));

  const dates: string[] = chart.dates;
  const o = chart.ohlc;
  const ind = chart.indicators;
  const lastDate = dates[dates.length - 1];
  const events = useMemo(() => overlays?.events ?? [], [overlays]);
  const eventsByDate = useMemo(() => {
    const m = new Map<string, ChartEvent[]>();
    for (const e of events) m.set(e.date, [...(m.get(e.date) ?? []), e]);
    return m;
  }, [events]);

  useEffect(() => {
    if (!box.current || !colors) return;
    const c: ThemeColors = colors;
    const el = box.current;
    const ch = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: c.surface },
        textColor: c.muted,
        fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif",
        fontSize: 11,
        attributionLogo: true,
        panes: { separatorColor: c.grid, separatorHoverColor: c.axis },
      },
      grid: { vertLines: { visible: false }, horzLines: { color: c.grid } },
      rightPriceScale: {
        borderColor: c.axis,
        mode: t.compare
          ? PriceScaleMode.Percentage
          : log
            ? PriceScaleMode.Logarithmic
            : PriceScaleMode.Normal,
      },
      timeScale: { borderColor: c.axis, rightOffset: 4, fixLeftEdge: true },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: c.axis, labelBackgroundColor: c.ink2 },
        horzLine: { color: c.axis, labelBackgroundColor: c.ink2 },
      },
      localization: {
        priceFormatter: (p: number) => (t.compare ? `${p.toFixed(1)}%` : formatValue(p, "usd_per_share")),
      },
    });
    api.current = ch;
    const up = c.good;
    const down = c.critical;
    let main: ISeriesApi<"Candlestick"> | ISeriesApi<"Line"> | ISeriesApi<"Area">;
    const extraSeries: { s: ISeriesApi<"Line">; label: string; color: string }[] = [];

    if (t.compare) {
      main = ch.addSeries(LineSeries, {
        color: c.series[0],
        lineWidth: 2,
        priceLineVisible: false,
        title: ticker,
      });
      main.setData(lineData(dates, o.adj_close));
      const compColors = [c.series[1], c.series[2]];
      Object.values(chart.comparisons ?? {}).forEach((cmp, i) => {
        const cc = cmp as { ticker: string; label: string; adj_close: (number | null)[] };
        const s = ch.addSeries(LineSeries, {
          color: compColors[i],
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: true,
          title: cc.ticker,
        });
        s.setData(lineData(dates, cc.adj_close));
        extraSeries.push({ s, label: cc.label, color: compColors[i] });
      });
    } else if (type === "candles") {
      const s = ch.addSeries(CandlestickSeries, {
        upColor: up,
        downColor: down,
        borderVisible: false,
        wickUpColor: up,
        wickDownColor: down,
        priceLineColor: c.axis,
      });
      const data = [];
      for (let i = 0; i < dates.length; i++) {
        const cl = o.close[i];
        if (cl === null) continue;
        data.push({
          time: toTime(dates[i]),
          open: o.open[i] ?? cl,
          high: o.high[i] ?? cl,
          low: o.low[i] ?? cl,
          close: cl,
        });
      }
      s.setData(data);
      main = s;
    } else if (type === "area") {
      const s = ch.addSeries(AreaSeries, {
        lineColor: c.series[0],
        topColor: withAlpha(c.series[0], 0.18),
        bottomColor: withAlpha(c.series[0], 0.0),
        lineWidth: 2,
        priceLineColor: c.axis,
      });
      s.setData(lineData(dates, o.close));
      main = s;
    } else {
      const s = ch.addSeries(LineSeries, { color: c.series[0], lineWidth: 2, priceLineColor: c.axis });
      s.setData(lineData(dates, o.close));
      main = s;
    }

    if (!t.compare) {
      const addLine = (
        key: string,
        label: string,
        color: string,
        style: LineStyle = LineStyle.Solid,
        width: 1 | 2 = 1,
      ) => {
        const s = ch.addSeries(LineSeries, {
          color,
          lineWidth: width,
          lineStyle: style,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        s.setData(lineData(dates, ind[key]));
        extraSeries.push({ s, label, color });
      };
      if (t.sma20) addLine("sma20", "SMA 20", c.series[3]);
      if (t.sma50) addLine("sma50", "SMA 50", c.series[1]);
      if (t.sma200) addLine("sma200", "SMA 200", c.series[6]);
      if (t.ema20) addLine("ema20", "EMA 20", c.series[4]);
      if (t.bb) {
        addLine("bb_upper", "Bollinger upper", c.muted);
        addLine("bb_lower", "Bollinger lower", c.muted);
      }
      if (t.range52 && overlays?.high52 && overlays?.low52) {
        main.createPriceLine({
          price: overlays.high52,
          color: c.muted,
          lineWidth: 1,
          lineStyle: LineStyle.Dotted,
          axisLabelVisible: true,
          title: "52w high",
        });
        main.createPriceLine({
          price: overlays.low52,
          color: c.muted,
          lineWidth: 1,
          lineStyle: LineStyle.Dotted,
          axisLabelVisible: true,
          title: "52w low",
        });
      }
      if (t.consensus && overlays?.consensus) {
        if (overlays.consensus.all)
          main.createPriceLine({
            price: overlays.consensus.all,
            color: c.series[1],
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: "All-analyst consensus",
          });
        if (overlays.consensus.trusted)
          main.createPriceLine({
            price: overlays.consensus.trusted,
            color: c.series[2],
            lineWidth: 2,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: "Trusted consensus",
          });
      }
      if (t.cone && overlays?.cone) {
        const cone = overlays.cone;
        const mk = (vals: number[], color: string, label: string, width: 1 | 2) => {
          const s = ch.addSeries(LineSeries, {
            color,
            lineWidth: width,
            lineStyle: LineStyle.Dashed,
            priceLineVisible: false,
            lastValueVisible: true,
            title: label,
            crosshairMarkerVisible: false,
          });
          s.setData(cone.dates.map((d, i) => ({ time: toTime(d), value: vals[i] })));
          extraSeries.push({ s, label: `App ${label}`, color });
        };
        mk(cone.p90, c.series[0], "P90", 1);
        mk(cone.p50, c.series[0], "P50", 2);
        mk(cone.p10, c.series[0], "P10", 1);
      }
      if (t.targets && overlays?.analystTargets?.length) {
        const s = ch.addSeries(LineSeries, {
          color: "transparent",
          lineVisible: false,
          pointMarkersVisible: true,
          pointMarkersRadius: 3,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        const pts = [...overlays.analystTargets].sort((a, b) => a.date.localeCompare(b.date));
        const seen = new Set<number>();
        s.setData(
          pts
            .map((p) => ({ time: toTime(p.date), value: p.target, color: withAlpha(c.series[1], 0.8) }))
            .filter((p) => (seen.has(p.time) ? false : (seen.add(p.time), true))),
        );
      }
      if (t.volume) {
        const v = ch.addSeries(HistogramSeries, {
          priceScaleId: "vol",
          priceFormat: { type: "volume" },
          lastValueVisible: false,
          priceLineVisible: false,
        });
        ch.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
        v.setData(
          dates
            .map((d, i) => ({
              time: toTime(d),
              value: o.volume[i] ?? 0,
              color: withAlpha((o.close[i] ?? 0) >= (o.open[i] ?? 0) ? up : down, 0.35),
            }))
            .filter((x) => x.value > 0),
        );
      }
    }

    // markers on the main series
    const markers: SeriesMarker<Time>[] = [];
    if (!t.compare) {
      for (const s of chart.markers?.splits ?? [])
        markers.push({
          time: toTime(s.date),
          position: "aboveBar",
          shape: "square",
          color: c.ink2,
          text: `Split ${s.ratio}:1`,
        });
      if (t.dividends)
        for (const d of chart.markers?.dividends ?? [])
          markers.push({
            time: toTime(d.date),
            position: "belowBar",
            shape: "circle",
            color: c.series[5],
            text: "D",
          });
      for (const e of events) {
        if (e.kind === "earnings" && !t.earnings) continue;
        if (e.kind === "news" && !t.news) continue;
        if ((e.kind === "insider_buy" || e.kind === "insider_sell") && !t.insiders) continue;
        if (e.kind === "analyst" || e.kind === "filing") continue;
        const tone = e.tone === "good" ? c.good : e.tone === "bad" ? c.critical : c.ink2;
        markers.push({
          time: toTime(e.date),
          position: e.kind === "insider_sell" ? "aboveBar" : "belowBar",
          shape: e.kind === "insider_buy" ? "arrowUp" : e.kind === "insider_sell" ? "arrowDown" : "circle",
          color: tone,
          text:
            e.kind === "earnings" ? "E" : e.kind === "news" ? "N" : e.kind === "insider_buy" ? "Buy" : "Sell",
          id: `${e.kind}|${e.date}`,
        });
      }
      markers.sort((a, b) => (a.time as number) - (b.time as number));
      createSeriesMarkers(main, markers);
    }

    let paneIdx = 1;
    if (t.rsi && !t.compare) {
      const r = ch.addSeries(
        LineSeries,
        { color: c.series[6], lineWidth: 2, priceLineVisible: false, title: "RSI 14" },
        paneIdx,
      );
      r.setData(lineData(dates, ind.rsi14));
      r.createPriceLine({
        price: 70,
        color: c.axis,
        lineWidth: 1,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: false,
        title: "",
      });
      r.createPriceLine({
        price: 30,
        color: c.axis,
        lineWidth: 1,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: false,
        title: "",
      });
      extraSeries.push({ s: r, label: "RSI 14", color: c.series[6] });
      ch.panes()[paneIdx]?.setStretchFactor(0.25);
      paneIdx++;
    }
    if (t.macd && !t.compare) {
      const h = ch.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, paneIdx);
      h.setData(
        dates
          .map((d, i) => ({
            time: toTime(d),
            value: ind.macd_hist[i] ?? 0,
            color: withAlpha((ind.macd_hist[i] ?? 0) >= 0 ? up : down, 0.5),
          }))
          .filter((x, i) => ind.macd_hist[i] !== null),
      );
      const m = ch.addSeries(
        LineSeries,
        { color: c.series[0], lineWidth: 2, priceLineVisible: false, title: "MACD" },
        paneIdx,
      );
      m.setData(lineData(dates, ind.macd));
      const sg = ch.addSeries(
        LineSeries,
        { color: c.series[1], lineWidth: 1, priceLineVisible: false, title: "Signal" },
        paneIdx,
      );
      sg.setData(lineData(dates, ind.macd_signal));
      extraSeries.push(
        { s: m, label: "MACD", color: c.series[0] },
        { s: sg, label: "Signal", color: c.series[1] },
      );
      ch.panes()[paneIdx]?.setStretchFactor(0.25);
    }

    const idx = new Map(dates.map((d, i) => [toTime(d) as number, i]));
    const onMove = (p: MouseEventParams<Time>) => {
      const time = (p.time as number | undefined) ?? (toTime(lastDate) as number);
      const i = idx.get(time);
      if (i === undefined) {
        setReadout(null);
        return;
      }
      const extra = extraSeries
        .map((x) => {
          const d = p.seriesData.get(x.s) as { value?: number } | undefined;
          return d?.value !== undefined
            ? {
                label: x.label,
                value: t.compare
                  ? `${d.value.toFixed(2)}`
                  : formatValue(
                      d.value,
                      x.label.startsWith("RSI") || x.label === "MACD" || x.label === "Signal"
                        ? "ratio"
                        : "usd_per_share",
                    ),
                color: x.color,
              }
            : null;
        })
        .filter(Boolean) as Readout["extra"];
      setReadout({
        date: dates[i],
        o: o.open[i] ?? undefined,
        h: o.high[i] ?? undefined,
        l: o.low[i] ?? undefined,
        c: o.close[i] ?? undefined,
        v: o.volume[i] ?? undefined,
        extra,
      });
    };
    ch.subscribeCrosshairMove(onMove);
    const onClick = (p: MouseEventParams<Time>) => {
      if (p.time === undefined) return;
      const d = new Date((p.time as number) * 1000).toISOString().slice(0, 10);
      const evs = eventsByDate.get(d);
      if (evs?.length) setSelectedEvent(evs[0]);
    };
    ch.subscribeClick(onClick);
    onMove({ seriesData: new Map() } as unknown as MouseEventParams<Time>);

    // initial visible range
    const last = new Date(`${lastDate}T00:00:00Z`);
    const start = rangeStart(range, last);
    const end =
      t.cone && overlays?.cone && !t.compare && ["1Y", "5Y", "MAX", "YTD", "6M"].includes(range)
        ? new Date(`${overlays.cone.dates[overlays.cone.dates.length - 1]}T00:00:00Z`)
        : last;
    if (start)
      ch.timeScale().setVisibleRange({
        from: (start.getTime() / 1000) as UTCTimestamp,
        to: (end.getTime() / 1000) as UTCTimestamp,
      });
    else ch.timeScale().fitContent();

    return () => {
      ch.unsubscribeCrosshairMove(onMove);
      ch.unsubscribeClick(onClick);
      ch.remove();
      api.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [colors, chart, overlays, type, log, t, range, ticker]);

  const hasCone = !!overlays?.cone;
  const hasConsensus = !!(overlays?.consensus?.all || overlays?.consensus?.trusted);
  const hasTargets = !!overlays?.analystTargets?.length;
  const has = (k: ChartEvent["kind"]) => events.some((e) => e.kind === k);
  const tableRows = useMemo(() => {
    const rows = [];
    for (let i = dates.length - 1; i >= Math.max(0, dates.length - 40); i--) rows.push(i);
    return rows;
  }, [dates]);

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Range" className="flex flex-wrap rounded-md border border-line p-0.5">
          {RANGES.map((r) => (
            <Button
              key={r}
              variant="segment"
              active={range === r}
              onClick={() => setRange(r)}
              disabled={r === "1D"}
              title={
                r === "1D" ? "Intraday bars need an intraday data feed, which is not configured" : undefined
              }
              className="min-h-7 px-2"
            >
              {r}
            </Button>
          ))}
        </div>
        <div role="group" aria-label="Chart type" className="flex rounded-md border border-line p-0.5">
          {(["candles", "line", "area"] as ChartType[]).map((ct) => (
            <Button
              key={ct}
              variant="segment"
              active={type === ct}
              onClick={() => setType(ct)}
              className="min-h-7 px-2 capitalize"
              disabled={t.compare}
            >
              {ct}
            </Button>
          ))}
        </div>
        <Toggle on={log} onClick={() => setLog(!log)} disabled={t.compare}>
          Log
        </Toggle>
        <Toggle on={t.compare} onClick={() => flip("compare")}>
          Compare vs. market &amp; sector (%)
        </Toggle>
        <Button
          variant="ghost"
          onClick={() => setShowTable(!showTable)}
          className="ml-auto"
          aria-expanded={showTable}
        >
          <Table2 className="size-3.5" /> {showTable ? "Hide" : "Show"} data table
        </Button>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Indicators and overlays">
        <Toggle on={t.volume} onClick={() => flip("volume")}>
          Volume
        </Toggle>
        <Toggle on={t.sma20} onClick={() => flip("sma20")}>
          SMA 20
        </Toggle>
        <Toggle on={t.sma50} onClick={() => flip("sma50")}>
          SMA 50
        </Toggle>
        <Toggle on={t.sma200} onClick={() => flip("sma200")}>
          SMA 200
        </Toggle>
        <Toggle on={t.ema20} onClick={() => flip("ema20")}>
          EMA 20
        </Toggle>
        <Toggle on={t.bb} onClick={() => flip("bb")}>
          Bollinger
        </Toggle>
        <Toggle on={t.rsi} onClick={() => flip("rsi")}>
          RSI
        </Toggle>
        <Toggle on={t.macd} onClick={() => flip("macd")}>
          MACD
        </Toggle>
        <Toggle on={t.range52} onClick={() => flip("range52")} disabled={!overlays?.high52}>
          52w high/low
        </Toggle>
        <Toggle
          on={t.dividends}
          onClick={() => flip("dividends")}
          disabled={!chart.markers?.dividends?.length}
        >
          Dividends
        </Toggle>
        <Toggle
          on={t.cone && hasCone}
          onClick={() => flip("cone")}
          disabled={!hasCone}
          title={hasCone ? undefined : "Available once the valuation section has loaded"}
        >
          12-mo range cone
        </Toggle>
        <Toggle on={t.consensus && hasConsensus} onClick={() => flip("consensus")} disabled={!hasConsensus}>
          Consensus lines
        </Toggle>
        <Toggle on={t.targets && hasTargets} onClick={() => flip("targets")} disabled={!hasTargets}>
          Analyst targets
        </Toggle>
        <Toggle
          on={t.earnings && has("earnings")}
          onClick={() => flip("earnings")}
          disabled={!has("earnings")}
        >
          Earnings
        </Toggle>
        <Toggle on={t.news && has("news")} onClick={() => flip("news")} disabled={!has("news")}>
          News
        </Toggle>
        <Toggle
          on={t.insiders && (has("insider_buy") || has("insider_sell"))}
          onClick={() => flip("insiders")}
          disabled={!(has("insider_buy") || has("insider_sell"))}
        >
          Insider trades
        </Toggle>
      </div>

      <div
        className="tabular mt-3 flex min-h-5 flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-2"
        aria-live="off"
      >
        {readout && (
          <>
            <span className="font-medium text-ink">{formatDate(readout.date)}</span>
            {!t.compare && (
              <>
                <span>O {formatValue(readout.o ?? null, "usd_per_share")}</span>
                <span>H {formatValue(readout.h ?? null, "usd_per_share")}</span>
                <span>L {formatValue(readout.l ?? null, "usd_per_share")}</span>
                <span className="font-medium text-ink">
                  C {formatValue(readout.c ?? null, "usd_per_share")}
                </span>
                <span>Vol {formatValue(readout.v ?? null, "shares")}</span>
              </>
            )}
            {readout.extra.map((x) => (
              <span key={x.label} className="inline-flex items-center gap-1">
                <span
                  className="inline-block h-0.5 w-3 rounded"
                  style={{ background: x.color }}
                  aria-hidden
                />
                {x.label} {x.value}
                {t.compare ? "%" : ""}
              </span>
            ))}
          </>
        )}
      </div>

      <div
        ref={box}
        className={cn("mt-1 w-full", t.rsi || t.macd ? "h-[520px]" : "h-[400px]", "max-sm:h-[340px]")}
        role="img"
        aria-label={`Price chart for ${ticker}, ${range} range. Use the data table for exact values.`}
      />

      {selectedEvent && (
        <div className="mt-3 rounded-lg border border-line bg-surface-2 p-3 text-sm" role="status">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="text-xs text-muted">
                {formatDate(selectedEvent.date)} · {selectedEvent.kind.replace("_", " ")}
              </div>
              <div className="font-medium">{selectedEvent.label}</div>
              {selectedEvent.detail && <p className="mt-1 text-ink-2">{selectedEvent.detail}</p>}
              {selectedEvent.url && (
                <a
                  href={selectedEvent.url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 inline-block text-xs text-accent-ink underline"
                >
                  Source
                </a>
              )}
            </div>
            <Button variant="ghost" onClick={() => setSelectedEvent(null)} aria-label="Close event details">
              Close
            </Button>
          </div>
        </div>
      )}

      {showTable && (
        <div className="mt-3 max-h-80 overflow-auto rounded-lg border border-line">
          <table className="tabular w-full text-right text-xs">
            <caption className="sr-only">Last 40 daily bars for {ticker}</caption>
            <thead className="sticky top-0 bg-surface-2 text-muted">
              <tr>
                <th className="px-2 py-1.5 text-left font-medium">Date</th>
                <th className="px-2 py-1.5 font-medium">Open</th>
                <th className="px-2 py-1.5 font-medium">High</th>
                <th className="px-2 py-1.5 font-medium">Low</th>
                <th className="px-2 py-1.5 font-medium">Close</th>
                <th className="px-2 py-1.5 font-medium">Volume</th>
              </tr>
            </thead>
            <tbody>
              {tableRows.map((i) => (
                <tr key={dates[i]} className="border-t border-line">
                  <td className="px-2 py-1 text-left">{dates[i]}</td>
                  <td className="px-2 py-1">{formatValue(o.open[i], "usd_per_share")}</td>
                  <td className="px-2 py-1">{formatValue(o.high[i], "usd_per_share")}</td>
                  <td className="px-2 py-1">{formatValue(o.low[i], "usd_per_share")}</td>
                  <td className="px-2 py-1">{formatValue(o.close[i], "usd_per_share")}</td>
                  <td className="px-2 py-1">{formatValue(o.volume[i], "shares")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 text-xs text-muted">
        {chart.notes?.adjustment} {chart.notes?.intraday} Click a marker&apos;s day to see its details.
      </p>
    </div>
  );
}
