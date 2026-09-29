"use client";

import { useEffect } from "react";
import { CircleCheck, LoaderCircle, TriangleAlert } from "lucide-react";
import { startEngine, useEngine } from "@/lib/engine-client";
import { BROWSER_ENGINE, STATIC_DEMO } from "@/lib/static";

/** Static site only: says what runs where and, with the browser engine, how far it has got. */
export function EngineBanner() {
  const engine = useEngine();
  useEffect(() => {
    if (!BROWSER_ENGINE) return;
    // Start at once so edits are ready when needed, unless the visitor asked browsers to save data
    // (then the first request that needs the engine starts it).
    const saveData = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData;
    if (!saveData) startEngine();
  }, []);
  if (!STATIC_DEMO) return null;

  const box = "no-print border-b border-line bg-surface-2 px-4 py-1.5 text-center text-xs text-ink-2";
  if (!BROWSER_ENGINE) {
    return (
      <div role="note" className={box}>
        <span className="font-semibold text-ink">Static demo:</span> a read-only export of the app on
        synthetic data. Live features (what-if DCF, sharing, refresh, alert checks) need the engine; see the
        README to run it.
      </div>
    );
  }
  return (
    <div role="status" className={box}>
      <span className="font-semibold text-ink">Running in your browser:</span> the full analysis engine
      (Python, compiled to WebAssembly) on synthetic data. Saved results show instantly; anything you change
      is computed live. {engine.phase === "off" && <span>The engine starts when you first need it.</span>}
      {engine.phase === "loading" && (
        <span className="inline-flex items-center gap-1 font-medium text-ink">
          <LoaderCircle className="size-3 animate-spin" aria-hidden />
          Engine: {engine.stage.toLowerCase()}… (first visit downloads about 30 MB)
        </span>
      )}
      {engine.phase === "ready" && (
        <span className="inline-flex items-center gap-1 font-medium text-good-ink">
          <CircleCheck className="size-3" aria-hidden />
          Engine ready ({Math.round(engine.seconds)} s)
        </span>
      )}
      {engine.phase === "failed" && (
        <span className="inline-flex items-center gap-1 font-medium text-critical-ink">
          <TriangleAlert className="size-3" aria-hidden />
          Engine unavailable ({engine.error}); saved results still work.
        </span>
      )}
    </div>
  );
}
