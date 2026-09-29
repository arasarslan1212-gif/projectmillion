"use client";

import * as Switch from "@radix-ui/react-switch";
import { Activity, BellRing, CheckCheck, FileText, RefreshCw, Target, UserCheck, Users } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getJSON } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";
import { useWatchlist } from "@/lib/recent";
import type { AnySection } from "@/lib/types";

const ICONS: Record<string, typeof Target> = {
  band: Target,
  trigger: Activity,
  insider_cluster: Users,
  analyst_change: UserCheck,
  filing_8k: FileText,
};

export function AlertsPage() {
  const [list] = useWatchlist();
  const [data, setData] = useState<AnySection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await getJSON<AnySection>("/alerts"));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    let alive = true;
    getJSON<AnySection>("/alerts")
      .then((d) => alive && setData(d))
      .catch((e: Error) => alive && setError(e.message));
    const onChange = () => void load();
    window.addEventListener("alerts-changed", onChange);
    return () => {
      alive = false;
      window.removeEventListener("alerts-changed", onChange);
    };
  }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      await load();
      window.dispatchEvent(new Event("alerts-changed"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const run = () => act(() => getJSON("/alerts/run", { method: "POST" }));
  const readAll = () =>
    act(() =>
      getJSON("/alerts/read", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      }),
    );
  const toggle = (kind: string, enabled: boolean) =>
    act(() =>
      getJSON(`/alerts/rules/${kind}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      }),
    );

  const events = (data?.events ?? []) as AnySection[];
  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold tracking-tight">Alerts</h1>
          <p className="mt-1 text-sm text-ink-2">
            Changes worth a look for the stocks on your{" "}
            <Link href="/watchlist" className="text-accent-ink underline underline-offset-2">
              watchlist
            </Link>
            , checked daily. Each alert links to its evidence.
          </p>
        </div>
        <Button onClick={run} disabled={busy || !list.length}>
          <RefreshCw className={cn("size-3.5", busy && "animate-spin")} /> Check now
        </Button>
        <Button onClick={readAll} disabled={busy || !data?.unread}>
          <CheckCheck className="size-3.5" /> Mark all read
        </Button>
      </div>

      {error && <p className="mt-4 text-sm text-critical-ink">Alerts could not be loaded: {error}</p>}
      {!data && !error && <Skeleton className="mt-6 h-64 w-full" />}

      {data && (
        <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-1.5">
                <BellRing className="size-4" /> Inbox
                {data.unread > 0 && (
                  <span className="text-xs font-normal text-muted">{data.unread} unread</span>
                )}
              </CardTitle>
            </CardHeader>
            <CardBody>
              {!list.length ? (
                <p className="text-sm text-ink-2">
                  Alerts cover the stocks on your watchlist. Add some with the Watch button on a report.
                </p>
              ) : events.length === 0 ? (
                <p className="text-sm text-ink-2">
                  No alerts yet for {list.join(", ")}. When a stock is first watched, the last 60 days are
                  checked; after that, new events appear as they happen.
                </p>
              ) : (
                <ol className="divide-y divide-[var(--border)]">
                  {events.map((e) => {
                    const Icon = ICONS[e.kind] ?? BellRing;
                    return (
                      <li key={e.id} className="flex gap-3 py-2.5">
                        <Icon
                          className={cn("mt-0.5 size-4 shrink-0", e.read ? "text-muted" : "text-accent-ink")}
                          aria-hidden
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-baseline gap-x-2">
                            <Link
                              href={`/stock/${e.ticker}`}
                              className={cn("text-sm hover:underline", !e.read && "font-semibold")}
                            >
                              {e.title}
                            </Link>
                            {!e.read && <span className="sr-only">(unread)</span>}
                            <span className="text-xs text-muted">{formatDate(e.occurred_on)}</span>
                          </div>
                          <p className="text-sm text-ink-2">{e.detail}</p>
                          {e.url && (
                            <a
                              href={e.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-accent-ink underline"
                            >
                              Source
                            </a>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ol>
              )}
            </CardBody>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>What to alert on</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              {(data.rules as AnySection[]).map((r) => {
                const id = `rule-${r.kind}`;
                return (
                  <div key={r.kind} className="flex items-start justify-between gap-3">
                    <label htmlFor={id} className="text-sm text-ink-2">
                      {r.label}
                    </label>
                    <Switch.Root
                      id={id}
                      checked={r.enabled}
                      disabled={busy}
                      onCheckedChange={(v) => toggle(r.kind, v)}
                      className="relative h-5 w-9 shrink-0 rounded-full border border-line bg-surface-2 transition-colors data-[state=checked]:bg-accent-ink"
                    >
                      <Switch.Thumb className="block size-4 translate-x-0.5 rounded-full bg-surface shadow transition-transform data-[state=checked]:translate-x-4" />
                    </Switch.Root>
                  </div>
                );
              })}
              <p className="pt-1 text-xs text-muted">
                Alerts appear here only; there is no email or push delivery. They describe what changed, not
                what to do.
              </p>
            </CardBody>
          </Card>
        </div>
      )}
    </div>
  );
}
