"use client";

import { useMemo, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { useJSON } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import type { AnySection } from "@/lib/types";

interface Node {
  key: string;
  path: string;
  comment: string | null;
  value?: unknown;
  children?: Node[];
}

const human = (k: string) => k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString("en-US") : String(v);
  if (Array.isArray(v)) return `[${v.map(fmt).join(", ")}]`;
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

const isLeaf = (n: Node) => !n.children;

/** A dict of dicts whose children are all scalars reads best as a matrix (e.g. weights by profile). */
function matrixColumns(n: Node): string[] | null {
  const kids = n.children ?? [];
  const compact = (c: Node) => isLeaf(c) && (!Array.isArray(c.value) || c.value.length <= 2);
  if (kids.length < 2 || !kids.every((k) => k.children && k.children.length && k.children.every(compact)))
    return null;
  const cols: string[] = [];
  for (const k of kids) for (const c of k.children ?? []) if (!cols.includes(c.key)) cols.push(c.key);
  const shared = cols.filter((c) => kids.filter((k) => k.children?.some((x) => x.key === c)).length >= 2);
  return shared.length >= 2 && cols.length <= 12 ? cols : null;
}

function Matrix({ n, cols }: { n: Node; cols: string[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-line text-left text-muted">
            <th className="py-1 pr-3 font-medium" />
            {cols.map((c) => (
              <th key={c} className="py-1 pr-2 text-right font-medium">
                {human(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {n.children?.map((row) => (
            <tr key={row.key} className="border-b border-line last:border-b-0">
              <th
                scope="row"
                className="py-1 pr-3 text-left font-medium text-ink-2"
                title={row.comment ?? undefined}
              >
                {human(row.key)}
              </th>
              {cols.map((c) => {
                const cell = row.children?.find((x) => x.key === c);
                return (
                  <td key={c} className="tabular py-1 pr-2 text-right">
                    {cell ? fmt(cell.value) : ""}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Leaves({ nodes }: { nodes: Node[] }) {
  return (
    <dl className="text-sm">
      {nodes.map((n) => (
        <div
          key={n.path}
          className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-x-3 border-b border-line py-1.5 last:border-b-0 sm:grid-cols-[34%_22%_minmax(0,1fr)]"
        >
          <dt className="text-ink-2" title={n.path}>
            {human(n.key)}
          </dt>
          <dd className="tabular font-medium [overflow-wrap:anywhere]">{fmt(n.value)}</dd>
          {n.comment && <dd className="col-span-2 text-xs text-muted sm:col-span-1">{n.comment}</dd>}
        </div>
      ))}
    </dl>
  );
}

function Tree({ nodes, depth = 0 }: { nodes: Node[]; depth?: number }) {
  const out: React.ReactNode[] = [];
  let run: Node[] = [];
  const flush = () => {
    if (run.length) out.push(<Leaves key={`l-${run[0].path}`} nodes={run} />);
    run = [];
  };
  for (const n of nodes) {
    if (isLeaf(n)) {
      run.push(n);
      continue;
    }
    flush();
    const cols = matrixColumns(n);
    out.push(
      <div key={n.path} className={cn("mt-3", depth > 0 && "border-l border-line pl-3")}>
        <div className="text-sm font-semibold text-ink" title={n.path}>
          {human(n.key)}
        </div>
        {n.comment && <p className="mt-0.5 text-xs text-muted">{n.comment}</p>}
        <div className="mt-1">
          {cols ? <Matrix n={n} cols={cols} /> : <Tree nodes={n.children ?? []} depth={depth + 1} />}
        </div>
      </div>,
    );
  }
  flush();
  return <>{out}</>;
}

export function Glossary({ items }: { items: AnySection[] }) {
  const [q, setQ] = useState("");
  const shown = useMemo(() => {
    const s = q.trim().toLowerCase();
    return s
      ? items.filter((d) => `${d.label ?? ""} ${d.id} ${d.definition ?? ""}`.toLowerCase().includes(s))
      : items;
  }, [items, q]);
  return (
    <div>
      <label htmlFor="glossary-q" className="sr-only">
        Search the glossary
      </label>
      <input
        id="glossary-q"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={`Search ${items.length} terms`}
        className="h-8 w-full max-w-sm rounded-md border border-line bg-surface px-2 text-sm"
      />
      <dl className="mt-3 grid gap-3 md:grid-cols-2">
        {shown.map((d) => (
          <div key={d.id} id={`term-${d.id}`} className="rounded-lg border border-line p-3">
            <dt className="text-sm font-semibold">{d.label ?? human(d.id)}</dt>
            <dd className="mt-1 space-y-1 text-sm text-ink-2">
              {d.plain && <p>{d.plain}</p>}
              {d.definition && <p className={cn(d.plain && "text-xs")}>{d.definition}</p>}
              {d.formula && <p className="font-mono text-[11px] text-ink">{d.formula}</p>}
              {d.interpretation && <p className="text-xs text-muted">{d.interpretation}</p>}
            </dd>
          </div>
        ))}
      </dl>
      {shown.length === 0 && <p className="mt-3 text-sm text-muted">No term matches “{q}”.</p>}
    </div>
  );
}

export function MethodologyPage({ glossaryOnly = false }: { glossaryOnly?: boolean }) {
  const { data, error } = useJSON<AnySection>("/meta/methodology");
  if (error && !data)
    return <p className="mx-auto max-w-5xl px-4 py-10 text-sm text-critical-ink">{error}</p>;
  if (!data)
    return (
      <div className="mx-auto max-w-5xl space-y-3 px-4 py-8">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  const sections = data.sections as AnySection[];
  if (glossaryOnly)
    return (
      <div className="mx-auto max-w-5xl px-4 py-6">
        <h1 className="text-2xl font-semibold tracking-tight">Glossary</h1>
        <p className="mt-1 text-sm text-ink-2">
          Every metric the app shows, with its definition and formula. These are the same definitions as the
          tooltips.
        </p>
        <div className="mt-4">
          <Glossary items={data.glossary} />
        </div>
      </div>
    );
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <h1 className="text-2xl font-semibold tracking-tight">Methodology</h1>
      <p className="mt-1 text-sm text-ink-2">
        Generated from the engine&apos;s configuration: every weight, threshold and assumption below is the
        value the engine runs with, annotated from the configuration file. Engine {data.engine_version} ·
        config {data.config_hash} · generated {formatDateTime(data.generated_at)}.
      </p>
      <div className="mt-6 grid gap-8 lg:grid-cols-[13rem_minmax(0,1fr)]">
        <nav aria-label="Methodology sections" className="hidden lg:block">
          <ol className="sticky top-20 space-y-1 text-sm">
            <li>
              <a href="#principles" className="text-ink-2 hover:text-ink">
                Principles
              </a>
            </li>
            {sections.map((s) => (
              <li key={s.id}>
                <a href={`#m-${s.id}`} className="text-ink-2 hover:text-ink">
                  {s.title}
                </a>
              </li>
            ))}
            <li>
              <a href="#glossary" className="text-ink-2 hover:text-ink">
                Glossary
              </a>
            </li>
          </ol>
        </nav>
        <div className="min-w-0 space-y-6">
          <section id="principles" className="rounded-xl border border-line bg-surface p-4 sm:p-5">
            <h2 className="text-base font-semibold">Principles</h2>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-2">
              {data.principles.map((p: string) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-muted">{data.disclaimer}</p>
          </section>
          {sections.map((s) => (
            <section
              key={s.id}
              id={`m-${s.id}`}
              className="scroll-mt-20 rounded-xl border border-line bg-surface p-4 sm:p-5"
            >
              <h2 className="text-base font-semibold">{s.title}</h2>
              <p className="mt-1 text-sm text-ink-2">{s.intro}</p>
              {s.comment && <p className="mt-1 text-xs text-muted">{s.comment}</p>}
              <div className="mt-2">
                <Tree nodes={s.params} />
              </div>
            </section>
          ))}
          <section id="glossary" className="scroll-mt-20 rounded-xl border border-line bg-surface p-4 sm:p-5">
            <h2 className="text-base font-semibold">Glossary</h2>
            <div className="mt-2">
              <Glossary items={data.glossary} />
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
