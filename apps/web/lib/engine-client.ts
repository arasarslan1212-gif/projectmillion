"use client";

import { useSyncExternalStore } from "react";
import { BASE_PATH } from "./static";

/**
 * The analysis engine running in this browser (static site only): a web worker that loads Pyodide and the
 * engine bundle (public/engine-worker/worker.js). Requests queue until it is ready.
 */
export type EngineState =
  | { phase: "off" }
  | { phase: "loading"; stage: string; since: number }
  | { phase: "ready"; seconds: number }
  | { phase: "failed"; error: string };

type Reply = { status: number; text: string };

let worker: Worker | null = null;
let state: EngineState = { phase: "off" };
const listeners = new Set<() => void>();
const pending = new Map<number, (r: Reply) => void>();
let nextId = 1;

function set(s: EngineState) {
  state = s;
  listeners.forEach((l) => l());
}

function fail(message: string) {
  const error = message.split("\n")[0].slice(0, 160); // a Python traceback belongs in the console, not the page
  set({ phase: "failed", error });
  const text = JSON.stringify({ detail: `The in-browser engine is unavailable: ${error}` });
  pending.forEach((resolve) => resolve({ status: 503, text }));
  pending.clear();
}

export function startEngine(): void {
  if (worker || state.phase === "failed" || typeof window === "undefined") return;
  if (typeof Worker === "undefined" || typeof WebAssembly === "undefined") {
    fail("this browser does not support WebAssembly workers");
    return;
  }
  worker = new Worker(`${BASE_PATH}/engine-worker/worker.js`, { type: "module" });
  set({ phase: "loading", stage: "Starting", since: Date.now() });
  worker.onmessage = (e: MessageEvent) => {
    const m = e.data;
    if (m.type === "status") set({ phase: "loading", stage: m.stage, since: Date.now() });
    else if (m.type === "ready") set({ phase: "ready", seconds: m.seconds });
    else if (m.type === "failed") fail(m.error);
    else if (m.type === "response") {
      pending.get(m.id)?.({ status: m.status, text: m.text });
      pending.delete(m.id);
    }
  };
  worker.onerror = (e) => fail(e.message || "the worker could not load");
  worker.postMessage({ type: "boot" });
}

export function engineRequest(method: string, path: string, body?: string): Promise<Reply> {
  startEngine();
  if (!worker)
    return Promise.resolve({ status: 503, text: JSON.stringify({ detail: "No engine available." }) });
  const id = nextId++;
  return new Promise((resolve) => {
    pending.set(id, resolve);
    worker!.postMessage({ type: "request", id, method, path, body });
  });
}

export const engineReady = () => state.phase === "ready";

export function useEngine(): EngineState {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => state,
    () => state,
  );
}
