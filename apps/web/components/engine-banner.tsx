"use client";

import { useEffect } from "react";
import { CircleCheck, FlaskConical, LoaderCircle, Radio, TriangleAlert } from "lucide-react";
import { useHealth } from "@/lib/api";
import { startEngine, useEngine } from "@/lib/engine-client";
import { formatDate } from "@/lib/format";
import { BROWSER_ENGINE, STATIC_DEMO } from "@/lib/static";

/** One slim bar above the header: the synthetic-data label (always shown on synthetic data) and, on the static
 * site, what runs where and how far the in-browser engine has got. */
export function StatusBar() {
  const health = useHealth();
  const engine = useEngine();
  useEffect(() => {
    if (!BROWSER_ENGINE) return;
    // Start at once so edits are ready when needed, unless the visitor asked browsers to save data
    // (then the first request that needs the engine starts it).
    const saveData = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData;
    if (!saveData) startEngine();
  }, []);
  const synthetic = !!health?.synthetic;
  if (!synthetic && !STATIC_DEMO) return null;

  return (
    <div className="no-print border-b border-line bg-surface-2/70 text-xs">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-4 gap-y-1 px-4 py-1.5">
        {synthetic && (
          <p role="note" className="flex min-w-0 items-center gap-2 text-ink-2">
            <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-synthetic/15 px-2 py-0.5 font-semibold uppercase tracking-wide text-synthetic-ink">
              <FlaskConical className="size-3" aria-hidden />
              Synthetic data
            </span>
            <span className="truncate">
              Every company, price, analyst and headline here is generated for testing and is not real.
            </span>
          </p>
        )}
        {STATIC_DEMO && health && !synthetic && (
          <p role="note" className="flex min-w-0 items-center gap-2 text-ink-2">
            <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-good/12 px-2 py-0.5 font-semibold uppercase tracking-wide text-good-ink">
              <Radio className="size-3" aria-hidden />
              Real market data
            </span>
            <span className="truncate">
              As of the close on {formatDate(health.today)}; refreshed each weekday.
            </span>
          </p>
        )}
        {STATIC_DEMO && !BROWSER_ENGINE && (
          <p role="note" className="text-ink-2">
            <span className="font-semibold text-ink">Static demo:</span> saved answers only; the what-if DCF,
            sharing, refresh and alert checks need the engine (see the README).
          </p>
        )}
        {BROWSER_ENGINE && (
          <div role="status" className="flex items-center gap-2 text-ink-2 sm:ml-auto">
            <span className="hidden text-muted lg:inline">
              Running in your browser: the Python engine, compiled to WebAssembly. Saved results load
              instantly; changes are computed live.
            </span>
            <span className="sr-only lg:hidden">Running in your browser.</span>
            {engine.phase === "off" && <span className="text-muted">Engine starts when needed</span>}
            {engine.phase === "loading" && (
              <span className="inline-flex items-center gap-1 font-medium text-ink">
                <LoaderCircle className="size-3 animate-spin" aria-hidden />
                Engine: {engine.stage.toLowerCase()}…
                <span className="hidden font-normal text-muted sm:inline">(first visit ~30 MB)</span>
              </span>
            )}
            {engine.phase === "ready" && (
              <span className="inline-flex items-center gap-1 font-medium text-good-ink">
                <CircleCheck className="size-3" aria-hidden />
                Engine ready
                <span className="font-normal text-muted">({Math.round(engine.seconds)} s)</span>
              </span>
            )}
            {engine.phase === "failed" && (
              <span className="inline-flex items-center gap-1 font-medium text-critical-ink">
                <TriangleAlert className="size-3" aria-hidden />
                Engine unavailable ({engine.error}); saved results still work.
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
