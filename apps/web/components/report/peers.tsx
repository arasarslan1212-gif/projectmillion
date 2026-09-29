"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { axisStyle, baseOption, EChart } from "@/components/charts/echart";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { formatValue } from "@/lib/format";
import type { ThemeColors } from "@/lib/theme";
import { withAlpha } from "@/lib/theme";
import type { AnySection, Unit } from "@/lib/types";
import { CAN_COMPUTE } from "@/lib/static";

function PeerScatter({ p }: { p: AnySection }) {
  const pts: AnySection[] = p.scatter.points;
  const build = useCallback(
    (c: ThemeColors) => {
      const maxCap = Math.max(...pts.map((x) => x.size ?? 0), 1);
      const size = (v: number | null) => 8 + 30 * Math.sqrt((v ?? 0) / maxCap);
      const mk = (subject: boolean) =>
        pts
          .filter((x) => x.is_subject === subject)
          .map((x) => ({ value: [x.x, x.y], name: x.ticker, symbolSize: size(x.size), cap: x.size }));
      return {
        ...baseOption(c),
        tooltip: {
          trigger: "item",
          backgroundColor: c.surface,
          borderColor: c.grid,
          textStyle: { color: c.ink, fontSize: 12 },
          formatter: (d: { data: { name: string; value: number[]; cap: number } }) =>
            `<b>${formatValue(d.data.value[1], "x")}</b> EV/Sales · <b>${formatValue(d.data.value[0], "pct")}</b> growth<br/>${d.data.name} · ${formatValue(d.data.cap, "usd")} market cap`,
        },
        legend: { ...(baseOption(c).legend as object), left: "auto", right: 0 },
        grid: { left: 8, right: 16, top: 36, bottom: 24, containLabel: true },
        xAxis: {
          type: "value",
          name: "Revenue growth",
          nameLocation: "middle",
          nameGap: 26,
          nameTextStyle: { color: c.muted },
          ...axisStyle(c),
          axisLabel: { color: c.muted, formatter: (v: number) => formatValue(v, "pct", { digits: 0 }) },
        },
        yAxis: {
          type: "value",
          name: "EV / Sales",
          nameTextStyle: { color: c.muted },
          ...axisStyle(c),
          axisLabel: { color: c.muted, formatter: (v: number) => formatValue(v, "x", { digits: 0 }) },
        },
        series: [
          {
            name: "Peers",
            type: "scatter",
            data: mk(false),
            itemStyle: { color: withAlpha(c.muted, 0.55), borderColor: c.surface, borderWidth: 2 },
            label: { show: true, formatter: "{b}", position: "right", color: c.muted, fontSize: 10 },
          },
          {
            name: p.rows[0].ticker,
            type: "scatter",
            data: mk(true),
            itemStyle: { color: c.series[0], borderColor: c.surface, borderWidth: 2 },
            label: {
              show: true,
              formatter: "{b}",
              position: "right",
              color: c.ink,
              fontWeight: "bold",
              fontSize: 11,
            },
          },
        ],
      };
    },
    [pts, p.rows],
  );
  if (pts.length < 3)
    return (
      <p className="text-xs text-muted">Not enough peers with growth and EV/Sales data for a scatter plot.</p>
    );
  return (
    <div>
      <div className="text-xs font-semibold text-ink-2">Growth vs. valuation (bubble size = market cap)</div>
      <EChart
        height={300}
        ariaLabel="Scatter of peers: revenue growth against EV to sales"
        build={build}
        table={{
          caption: "Peer growth and EV/Sales",
          columns: ["Ticker", "Revenue growth", "EV/Sales", "Market cap"],
          rows: pts.map((x) => [
            String(x.ticker),
            formatValue(x.x, "pct"),
            formatValue(x.y, "x"),
            formatValue(x.size, "usd"),
          ]),
        }}
      />
    </div>
  );
}

export function PeersSection({ p, onPeers }: { p: AnySection; onPeers: (peers: string[] | null) => void }) {
  const cols: { key: string; label: string; unit: Unit; higher_is_better: boolean }[] = p.columns;
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(() =>
    p.rows
      .filter((r: AnySection) => !r.is_subject)
      .map((r: AnySection) => r.ticker)
      .join(", "),
  );
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <span>{p.selection_note}</span>
        {CAN_COMPUTE && (
          <Button onClick={() => setEditing(!editing)} aria-expanded={editing}>
            Edit peers
          </Button>
        )}
      </div>
      {editing && (
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            const list = text
              .split(/[\s,]+/)
              .map((t: string) => t.trim().toUpperCase())
              .filter(Boolean);
            onPeers(list.length ? list : null);
            setEditing(false);
          }}
        >
          <label htmlFor="peer-input" className="sr-only">
            Peer tickers, comma separated
          </label>
          <input
            id="peer-input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="h-8 min-w-72 flex-1 rounded-md border border-line bg-surface px-2 text-sm"
          />
          <Button type="submit" variant="default">
            Apply
          </Button>
          <Button
            onClick={() => {
              onPeers(null);
              setEditing(false);
            }}
          >
            Reset to automatic
          </Button>
        </form>
      )}
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="tabular w-full min-w-[900px] text-right text-xs">
          <caption className="sr-only">Peer comparison</caption>
          <thead className="bg-surface-2 text-muted">
            <tr>
              <th className="sticky left-0 bg-surface-2 px-2 py-1.5 text-left font-medium">Company</th>
              {cols.map((c) => (
                <th
                  key={c.key}
                  className="px-2 py-1.5 font-medium whitespace-nowrap"
                  title={c.higher_is_better ? "Higher ranks better" : "Lower ranks better"}
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {p.rows.map((r: AnySection) => (
              <tr
                key={r.ticker}
                className={cn("border-t border-line", r.is_subject && "bg-accent-wash font-medium")}
              >
                <th
                  scope="row"
                  className={cn(
                    "sticky left-0 px-2 py-1 text-left font-normal whitespace-nowrap",
                    r.is_subject ? "bg-accent-wash font-semibold" : "bg-surface",
                  )}
                >
                  {r.is_subject ? (
                    r.ticker
                  ) : (
                    <Link href={`/stock/${r.ticker}`} className="text-accent-ink underline" title={r.name}>
                      {r.ticker}
                    </Link>
                  )}
                </th>
                {cols.map((c) => (
                  <td key={c.key} className="px-2 py-1">
                    {formatValue(r.metrics[c.key], c.unit)}
                  </td>
                ))}
              </tr>
            ))}
            <tr className="border-t-2 border-line bg-surface-2 text-ink-2">
              <th scope="row" className="sticky left-0 bg-surface-2 px-2 py-1 text-left font-medium">
                Peer median
              </th>
              {cols.map((c) => (
                <td key={c.key} className="px-2 py-1">
                  {formatValue(p.medians[c.key], c.unit)}
                </td>
              ))}
            </tr>
            <tr className="border-t border-line text-muted">
              <th scope="row" className="sticky left-0 bg-surface px-2 py-1 text-left font-normal">
                Rank
              </th>
              {cols.map((c) => (
                <td key={c.key} className="px-2 py-1">
                  {p.ranks[c.key] ? `${p.ranks[c.key].rank} of ${p.ranks[c.key].of}` : "—"}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted">
        {p.basis_note} {p.universe_note}
      </p>
      <PeerScatter p={p} />
    </div>
  );
}
