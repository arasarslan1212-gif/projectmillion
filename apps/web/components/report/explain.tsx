"use client";

import { ArrowDownRight, ArrowUpRight, CircleAlert, Crosshair, Minus } from "lucide-react";
import { createContext, useContext, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { formatDate, formatValue } from "@/lib/format";
import { DISCLAIMER_SHORT } from "@/lib/legal";
import { MODE_OPTIONS, type ReadingMode, useReadingMode } from "@/lib/mode";
import type { AnySection, Unit } from "@/lib/types";

interface Sent {
  text: string;
  facts: string[];
}

interface Fact {
  id: string;
  label: string;
  value: number | string | null;
  unit: string;
  group: string;
  source: string | null;
  as_of: string | null;
  display: string | null;
}

interface Active {
  key: string;
  block: string;
  facts: string[];
}

interface Ctx {
  mode: ReadingMode;
  active: Active | null;
  setActive: (a: Active) => void;
  facts: Map<string, Fact>;
}

const ExplainCtx = createContext<Ctx | null>(null);

function useExplain(): Ctx {
  const c = useContext(ExplainCtx);
  if (!c) throw new Error("ExplainCtx missing");
  return c;
}

/** Where each fact group lives in the report, so a fact can link back to the section that computed it. */
const GROUP_HOME: Record<string, [string, string]> = {
  company: ["snapshot", "Snapshot"],
  trust: ["trust", "Trust Rating"],
  metrics: ["trust", "Trust Rating"],
  risk: ["risk", "Risk & red flags"],
  valuation: ["valuation", "Price target"],
  confidence: ["valuation", "Price target"],
  analysts: ["analysts", "Analysts"],
  news: ["news", "News"],
  earnings: ["earnings", "Earnings"],
  dividends: ["dividends", "Dividends"],
  ownership: ["ownership", "Ownership"],
  gaps: ["explain-gaps", "Data gaps"],
  triggers: ["explain-triggers", "Triggers (computed for this section)"],
  premortem: ["explain-premortem", "Pre-mortem"],
};

const METHOD_BADGE: Record<string, { label: string; tone: "neutral" | "accent" | "warning" }> = {
  template: { label: "Template text", tone: "neutral" },
  llm: { label: "Model-written · fact-checked", tone: "accent" },
  mixed: { label: "Model-written · partly template", tone: "warning" },
};

/** One sentence that reveals the facts behind it on hover, focus or tap. */
function Sentence({ block, i, s }: { block: string; i: number; s: Sent }) {
  const { active, setActive } = useExplain();
  const key = `${block}:${i}`;
  const set = () => setActive({ key, block, facts: s.facts });
  return (
    <span
      tabIndex={0}
      onMouseEnter={set}
      onFocus={set}
      onClick={set}
      onKeyDown={(e) => e.key === "Enter" && set()}
      className={cn(
        "cursor-help rounded-sm decoration-dotted underline-offset-4 transition-colors hover:underline focus-visible:underline focus-visible:outline-none",
        active?.key === key && "bg-accent-wash underline",
      )}
    >
      {s.text}
    </span>
  );
}

function Sentences({ block, sents, className }: { block: string; sents?: Sent[]; className?: string }) {
  if (!sents?.length) return <p className="text-sm text-muted">Not enough data for this part.</p>;
  return (
    <p className={cn("text-sm leading-relaxed text-ink", className)}>
      {sents.map((s, i) => (
        <span key={i}>
          <Sentence block={block} i={i} s={s} />{" "}
        </span>
      ))}
    </p>
  );
}

/** An introduction, a list of points, and closing context ("For scale: …"), each sentence traceable. */
function SentenceList({ block, sents }: { block: string; sents?: Sent[] }) {
  if (!sents?.length) return <p className="text-sm text-muted">Not enough data for this part.</p>;
  const items = sents.map((s, i) => ({ s, i }));
  const [intro, ...rest] = items;
  const tail = rest.filter((x) => x.s.text.startsWith("For scale"));
  const points = rest.filter((x) => !x.s.text.startsWith("For scale"));
  return (
    <div className="space-y-1.5 text-sm leading-relaxed text-ink">
      <p>
        <Sentence block={block} i={intro.i} s={intro.s} />
      </p>
      {points.length > 0 && (
        <ul className="list-disc space-y-1 pl-5">
          {points.map((x) => (
            <li key={x.i}>
              <Sentence block={block} i={x.i} s={x.s} />
            </li>
          ))}
        </ul>
      )}
      {tail.map((x) => (
        <p key={x.i} className="text-ink-2">
          <Sentence block={block} i={x.i} s={x.s} />
        </p>
      ))}
    </div>
  );
}

function FactValue({ f }: { f: Fact }) {
  if (typeof f.value === "string") return <span className="text-ink-2">{f.value}</span>;
  const unit = (f.unit === "x" ? "x" : f.unit) as Unit;
  const known = ["usd", "usd_per_share", "pct", "prob", "ratio", "x", "score", "count", "days", "years"];
  return (
    <span className="tabular font-semibold">
      {known.includes(f.unit) ? formatValue(f.value, unit) : (f.display ?? String(f.value))}
    </span>
  );
}

function FactRow({ f, mode }: { f: Fact; mode: ReadingMode }) {
  const home = GROUP_HOME[f.group];
  return (
    <li className="border-b border-line py-2 last:border-b-0">
      <div className="text-xs text-muted">{f.label}</div>
      <div className="mt-0.5 text-sm">
        <FactValue f={f} />
      </div>
      <div className="mt-0.5 flex flex-wrap gap-x-2 text-[11px] text-muted">
        {home && (
          <a href={`#${home[0]}`} className="underline decoration-dotted underline-offset-2 hover:text-ink-2">
            {home[1]}
          </a>
        )}
        {f.source && <span>source: {f.source}</span>}
        {f.as_of && <span>as of {formatDate(f.as_of)}</span>}
        {mode === "analyst" && <span className="font-mono">{f.id}</span>}
      </div>
    </li>
  );
}

function FactsPanel({ className }: { className?: string }) {
  const { active, facts, mode } = useExplain();
  const list = (active?.facts ?? []).map((id) => facts.get(id)).filter((f): f is Fact => !!f);
  return (
    <div className={cn("rounded-lg border border-line bg-surface-2 p-3", className)} aria-live="polite">
      <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted">
        <Crosshair className="size-3.5" aria-hidden /> Facts behind the sentence
      </div>
      {!active ? (
        <p className="mt-2 text-xs text-ink-2">
          Hover, tap or tab to any sentence to see the numbers it uses, where each was computed and how
          current it is. The text may only state numbers from these facts.
        </p>
      ) : list.length === 0 ? (
        <p className="mt-2 text-xs text-ink-2">This sentence states no numbers of its own.</p>
      ) : (
        <ul className="mt-1">
          {list.map((f) => (
            <FactRow key={f.id} f={f} mode={mode} />
          ))}
        </ul>
      )}
    </div>
  );
}

function Block({
  id,
  title,
  children,
  hint,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
  hint?: React.ReactNode;
}) {
  const { active } = useExplain();
  return (
    <div id={`explain-${id}`} className="scroll-mt-40 border-t border-line pt-4 first:border-t-0 first:pt-0">
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
      <div className="mt-2 space-y-3">{children}</div>
      {active?.block === id && <FactsPanel className="mt-3 lg:hidden" />}
    </div>
  );
}

function Row({
  block,
  rowKey,
  facts,
  children,
}: {
  block: string;
  rowKey: string;
  facts: string[];
  children: React.ReactNode;
}) {
  const { active, setActive } = useExplain();
  const key = `${block}:row:${rowKey}`;
  const set = () => setActive({ key, block, facts });
  return (
    <tr
      tabIndex={0}
      onMouseEnter={set}
      onFocus={set}
      onClick={set}
      className={cn(
        "cursor-help border-b border-line last:border-b-0 focus-visible:outline-none",
        active?.key === key ? "bg-accent-wash" : "hover:bg-surface-2",
      )}
    >
      {children}
    </tr>
  );
}

function PillarTable({
  rows,
  totals,
}: {
  rows: AnySection[];
  totals: { raw?: number; ded?: number; score?: number };
}) {
  if (!rows?.length) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[26rem] text-sm">
        <caption className="sr-only">Pillar scores, weights and contributions to the Trust Rating</caption>
        <thead>
          <tr className="border-b border-line text-left text-xs text-muted">
            <th className="py-1.5 pr-2 font-medium">Pillar</th>
            <th className="py-1.5 pr-2 text-right font-medium">Score</th>
            <th className="py-1.5 pr-2 text-right font-medium">Weight</th>
            <th className="py-1.5 text-right font-medium">Points</th>
          </tr>
        </thead>
        <tbody>
          {[...rows]
            .sort((a, b) => b.points - a.points)
            .map((r) => (
              <Row key={r.id} block="trust_path" rowKey={r.id} facts={r.facts}>
                <td className="py-1.5 pr-2">{r.label}</td>
                <td className="tabular py-1.5 pr-2 text-right">{formatValue(r.score, "score")}</td>
                <td className="tabular py-1.5 pr-2 text-right text-ink-2">
                  {formatValue(r.weight, "pct", { digits: 0 })}
                </td>
                <td className="tabular py-1.5 text-right font-medium">
                  {formatValue(r.points, "score", { digits: 1 })}
                </td>
              </Row>
            ))}
        </tbody>
        <tfoot className="text-xs">
          <tr>
            <td className="pt-2 pr-2 text-muted" colSpan={3}>
              Weighted total
            </td>
            <td className="tabular pt-2 text-right">
              {formatValue(totals.raw ?? null, "score", { digits: 1 })}
            </td>
          </tr>
          {!!totals.ded && (
            <tr>
              <td className="pr-2 text-muted" colSpan={3}>
                Red-flag deductions
              </td>
              <td className="tabular text-right text-critical-ink">−{formatValue(totals.ded, "score")}</td>
            </tr>
          )}
          <tr className="font-semibold">
            <td className="pr-2" colSpan={3}>
              Trust Rating
            </td>
            <td className="tabular text-right">{formatValue(totals.score ?? null, "score")}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function MethodTable({ rows, p50 }: { rows: AnySection[]; p50?: number }) {
  if (!rows?.length) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[30rem] text-sm">
        <caption className="sr-only">Valuation methods, their weights and 12-month figures</caption>
        <thead>
          <tr className="border-b border-line text-left text-xs text-muted">
            <th className="py-1.5 pr-2 font-medium">Method</th>
            <th className="py-1.5 pr-2 text-right font-medium">Long-term value</th>
            <th className="py-1.5 pr-2 text-right font-medium">12-month figure</th>
            <th className="py-1.5 text-right font-medium">Weight</th>
          </tr>
        </thead>
        <tbody>
          {[...rows]
            .sort((a, b) => b.weight - a.weight)
            .map((r) => (
              <Row key={r.id} block="target_path" rowKey={r.id} facts={r.facts}>
                <td className="py-1.5 pr-2">{r.label}</td>
                <td className="tabular py-1.5 pr-2 text-right text-ink-2">
                  {formatValue(r.value, "usd_per_share")}
                </td>
                <td className="tabular py-1.5 pr-2 text-right">
                  {formatValue(r.target_12m, "usd_per_share")}
                </td>
                <td className="tabular py-1.5 text-right font-medium">
                  {formatValue(r.weight, "pct", { digits: 0 })}
                </td>
              </Row>
            ))}
        </tbody>
        <tfoot className="text-xs font-semibold">
          <tr>
            <td className="pt-2 pr-2" colSpan={2}>
              Weighted blend (P50)
            </td>
            <td className="tabular pt-2 pr-2 text-right">{formatValue(p50 ?? null, "usd_per_share")}</td>
            <td className="tabular pt-2 text-right">100%</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

const CASE_STYLE: Record<string, { title: string; ink: string; Icon: typeof ArrowUpRight }> = {
  bear: { title: "Bear case", ink: "text-critical-ink", Icon: ArrowDownRight },
  base: { title: "Base case", ink: "text-ink", Icon: Minus },
  bull: { title: "Bull case", ink: "text-good-ink", Icon: ArrowUpRight },
};

function Cases({ cases }: { cases: AnySection[] }) {
  const { mode, active, setActive } = useExplain();
  if (!cases?.length) return <p className="text-sm text-muted">No scenario model applies to this company.</p>;
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {cases.map((c) => {
        const st = CASE_STYLE[c.name] ?? CASE_STYLE.base;
        const key = `cases:${c.name}`;
        const set = () => setActive({ key, block: "cases", facts: c.facts });
        return (
          <div
            key={c.name}
            tabIndex={0}
            onMouseEnter={set}
            onFocus={set}
            onClick={set}
            className={cn(
              "cursor-help rounded-lg border border-line p-3 focus-visible:outline-none",
              active?.key === key && "border-accent bg-accent-wash",
            )}
          >
            <div className={cn("flex items-center gap-1 text-xs font-semibold", st.ink)}>
              <st.Icon className="size-3.5" aria-hidden /> {st.title}
            </div>
            <div className="tabular mt-1 text-lg font-semibold">{formatValue(c.value, "usd_per_share")}</div>
            <div className="text-xs text-muted">
              long-term value · {formatValue(c.probability, "pct", { digits: 0 })} weight
            </div>
            {mode === "analyst" ? (
              <dl className="mt-2 space-y-0.5 text-xs">
                {c.assumptions.map((a: AnySection) => (
                  <div key={a.id} className="flex justify-between gap-2">
                    <dt className="text-ink-2">{a.label}</dt>
                    <dd className="tabular">{formatValue(a.value, "pct")}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="mt-2 text-xs text-ink-2">{c.plain?.[0]?.text}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Triggers({ triggers }: { triggers: AnySection[] }) {
  const { mode, active, setActive } = useExplain();
  if (!triggers?.length)
    return <p className="text-sm text-muted">No measurable triggers could be computed.</p>;
  return (
    <ul className="space-y-2">
      {triggers.map((t) => {
        const key = `triggers:${t.id}`;
        const set = () => setActive({ key, block: "triggers", facts: t.facts });
        return (
          <li
            key={t.id}
            tabIndex={0}
            onMouseEnter={set}
            onFocus={set}
            onClick={set}
            className={cn(
              "cursor-help rounded-lg border border-line px-3 py-2 focus-visible:outline-none",
              active?.key === key && "border-accent bg-accent-wash",
            )}
          >
            <p className="text-sm">{mode === "plain" ? t.plain : t.analyst}</p>
            <p className="mt-0.5 text-xs text-muted">Effect: {t.effect}</p>
          </li>
        );
      })}
    </ul>
  );
}

function AllFacts() {
  const { facts, active, mode } = useExplain();
  const on = new Set(active?.facts ?? []);
  const groups = useMemo(() => {
    const g = new Map<string, Fact[]>();
    for (const f of facts.values()) {
      if (!g.has(f.group)) g.set(f.group, []);
      g.get(f.group)?.push(f);
    }
    return [...g.entries()];
  }, [facts]);
  return (
    <details className="group rounded-lg border border-line">
      <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-ink-2 hover:text-ink">
        All {facts.size} facts the explanation may use
      </summary>
      <div className="max-h-[28rem] overflow-auto border-t border-line px-3 pb-3">
        {groups.map(([g, fs]) => (
          <div key={g} className="mt-3">
            <div className="text-[11px] font-medium uppercase tracking-wide text-muted">
              {GROUP_HOME[g]?.[1] ?? g}
            </div>
            <table className="mt-1 w-full text-xs">
              <tbody>
                {fs.map((f) => (
                  <tr
                    key={f.id}
                    className={cn("border-b border-line last:border-b-0", on.has(f.id) && "bg-accent-wash")}
                  >
                    <td className="py-1 pr-2 text-ink-2">
                      {f.label}
                      {mode === "analyst" && (
                        <span className="ml-1 font-mono text-[10px] text-muted">{f.id}</span>
                      )}
                    </td>
                    <td className="max-w-[20rem] py-1 text-right">
                      <FactValue f={f} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </details>
  );
}

export function ModeToggle() {
  const [mode, setMode] = useReadingMode();
  return <Segmented label="Reading mode" value={mode} options={MODE_OPTIONS} onChange={setMode} />;
}

export function ExplainSection({ e }: { e: AnySection }) {
  const [mode] = useReadingMode();
  const [active, setActive] = useState<Active | null>(null);
  const facts = useMemo(() => new Map<string, Fact>((e.facts as Fact[]).map((f) => [f.id, f])), [e.facts]);
  const ctx = useMemo(() => ({ mode, active, setActive, facts }), [mode, active, facts]);
  const p = e.parts as Record<string, AnySection>;
  const badge = METHOD_BADGE[e.method] ?? METHOD_BADGE.template;
  const num = (id: string) => {
    const v = facts.get(id)?.value;
    return typeof v === "number" ? v : undefined;
  };
  const s = (name: string) => p[name]?.[mode] as Sent[] | undefined;
  const v = e.validation ?? {};

  return (
    <ExplainCtx.Provider value={ctx}>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <Badge tone={badge.tone}>{badge.label}</Badge>
        <span className="min-w-0 flex-1">{e.method_note}</span>
      </div>
      {mode === "analyst" && e.method !== "template" && (
        <p className="mt-1 text-xs text-muted">
          Fact check: {v.checked} sentences checked
          {v.regenerated?.length ? `; regenerated ${v.regenerated.join(", ")}` : ""}
          {v.fallback?.length ? `; template fallback for ${v.fallback.join(", ")}` : ""}.
        </p>
      )}

      <div className="mt-4 grid gap-6 lg:grid-cols-[minmax(0,1fr)_17rem]">
        <div className="min-w-0 space-y-4">
          <Block id="view" title="The view in three sentences">
            <Sentences block="view" sents={s("view")} className="text-[15px]" />
          </Block>
          <Block
            id="trust_path"
            title="From inputs to the Trust Rating"
            hint="Metrics are scored against the sector, averaged into pillars, and the pillars weighted into one score."
          >
            <Sentences block="trust_path" sents={s("trust_path")} />
            <PillarTable
              rows={p.trust_path?.table ?? []}
              totals={{ raw: num("trust.raw"), ded: num("trust.deductions"), score: num("trust.score") }}
            />
          </Block>
          <Block
            id="target_path"
            title="From valuation methods to the price target"
            hint="Each method's value becomes a 12-month figure; the weighted blend is the app's P50 estimate."
          >
            <Sentences block="target_path" sents={s("target_path")} />
            <MethodTable rows={p.target_path?.table ?? []} p50={num("val.p50")} />
          </Block>
          <Block
            id="cases"
            title="Bear, base and bull cases"
            hint="Long-term values under each set of assumptions, and how much weight the app gives each."
          >
            <Cases cases={e.cases} />
          </Block>
          <Block id="pricing_in" title="What the market is pricing in">
            <Sentences block="pricing_in" sents={s("pricing_in")} />
          </Block>
          <Block id="drivers" title="Key drivers">
            <Sentences block="drivers" sents={s("drivers")} />
          </Block>
          <Block
            id="against"
            title="The case against the app's view"
            hint="The strongest argument for the opposite outcome, built from the same facts."
          >
            <Sentences block="against" sents={s("against")} />
          </Block>
          <Block
            id="premortem"
            title="Pre-mortem: if the stock fell 40% in a year"
            hint="A thought exercise, not a forecast: each reason is a weakness already visible in today's data."
          >
            <SentenceList block="premortem" sents={s("premortem")} />
          </Block>
          <Block
            id="triggers"
            title="What would change the view"
            hint="Specific thresholds computed from the company's own history and the app's range."
          >
            <Triggers triggers={e.triggers} />
          </Block>
          <Block id="confidence" title="Why confidence is what it is">
            <Sentences block="confidence" sents={s("confidence")} />
          </Block>
          <Block id="gaps" title="Data gaps and caveats">
            {e.gaps?.length ? (
              <ul className="space-y-1 text-sm">
                {e.gaps.map((g: AnySection) => (
                  <li key={g.id} className="flex gap-2">
                    <CircleAlert className="mt-0.5 size-3.5 shrink-0 text-warning-ink" aria-hidden />
                    <span>
                      <span className="font-medium">{g.label}:</span>{" "}
                      <span className="text-ink-2">{g.text}</span>
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-ink-2">No data gaps affected this report.</p>
            )}
          </Block>
          <AllFacts />
          <p className="text-xs text-muted">{e.disclaimer ?? DISCLAIMER_SHORT}</p>
        </div>
        <div className="hidden lg:block">
          <FactsPanel className="sticky top-40" />
        </div>
      </div>
    </ExplainCtx.Provider>
  );
}

/** The header Verdict: 3–4 sentences, each checked against the report's facts. */
export function VerdictCard({
  e,
  loading,
  error,
}: {
  e: AnySection | null;
  loading: boolean;
  error: string | null;
}) {
  const [mode] = useReadingMode();
  if (!e && loading) {
    return (
      <div
        className="rounded-2xl border border-line bg-surface px-4 py-4 shadow-card sm:px-6"
        aria-busy="true"
      >
        <div className="text-[11px] font-medium uppercase tracking-wide text-muted">Verdict</div>
        <Skeleton className="mt-2 h-4 w-full" />
        <Skeleton className="mt-1.5 h-4 w-4/5" />
      </div>
    );
  }
  if (!e || (e.status !== "ok" && e.status !== "partial")) {
    if (!error && !e) return null;
    return (
      <div className="rounded-2xl border border-line bg-surface px-4 py-4 text-sm text-ink-2 shadow-card sm:px-6">
        The verdict is not available: {e?.reason ?? error}
      </div>
    );
  }
  const sents = (e.verdict?.[mode] ?? []) as Sent[];
  const badge = METHOD_BADGE[e.method] ?? METHOD_BADGE.template;
  return (
    <div className="rounded-2xl border border-line bg-surface px-4 py-4 shadow-card sm:px-6">
      <div className="flex flex-wrap items-center gap-2">
        <div className="text-[11px] font-medium uppercase tracking-wide text-muted">Verdict</div>
        <Badge tone={badge.tone} className="text-[10px]">
          {badge.label}
        </Badge>
        <a href="#explain" className="ml-auto text-xs text-accent-ink underline underline-offset-2">
          How the app got here
        </a>
      </div>
      <p className="mt-1.5 text-sm leading-relaxed text-ink">{sents.map((x) => x.text).join(" ")}</p>
      <p className="mt-1.5 text-[11px] text-muted">{DISCLAIMER_SHORT}</p>
    </div>
  );
}
