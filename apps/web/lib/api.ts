"use client";

import { useEffect, useState } from "react";
import type { AnySection, Definition, Health, SearchResult } from "./types";

const BASE = "/api/engine";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function getJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { cache: "no-store", ...init });
  if (!r.ok) {
    let msg = `Request failed (${r.status})`;
    try {
      const body = await r.json();
      if (body?.detail) msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(r.status, msg);
  }
  return (await r.json()) as T;
}

export function search(q: string, signal?: AbortSignal): Promise<{ results: SearchResult[] }> {
  return getJSON(`/search?q=${encodeURIComponent(q)}`, { signal });
}

let healthPromise: Promise<Health> | null = null;
export function getHealth(): Promise<Health> {
  healthPromise ??= getJSON<Health>("/health").catch((e) => {
    healthPromise = null;
    throw e;
  });
  return healthPromise;
}

let defsPromise: Promise<Record<string, Definition>> | null = null;
export function getDefinitions(): Promise<Record<string, Definition>> {
  defsPromise ??= getJSON<{ definitions: Record<string, Definition> }>("/meta/definitions")
    .then((d) => d.definitions)
    .catch(() => {
      defsPromise = null;
      return {};
    });
  return defsPromise;
}

export interface SectionState<T = AnySection> {
  data: T | null;
  error: string | null;
  loading: boolean;
  notFound: boolean;
}

interface Loaded<T> {
  key: string;
  data: T | null;
  error: string | null;
  notFound: boolean;
}

/** Fetch one report section. While refetching, the previous data stays visible (no skeleton flash). */
export function useSection<T = AnySection>(
  ticker: string,
  name: string,
  version = 0,
  query = "",
): SectionState<T> {
  const key = `${ticker}|${name}|${version}|${query}`;
  const [loaded, setLoaded] = useState<Loaded<T> | null>(null);
  useEffect(() => {
    const ctrl = new AbortController();
    getJSON<T>(`/report/${encodeURIComponent(ticker)}/section/${name}${query ? `?${query}` : ""}`, {
      signal: ctrl.signal,
    })
      .then((data) => setLoaded({ key, data, error: null, notFound: false }))
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        const err = e as ApiError;
        setLoaded((prev) => ({
          key,
          data: prev?.data ?? null,
          error: err.message,
          notFound: err.status === 404,
        }));
      });
    return () => ctrl.abort();
  }, [key, ticker, name, query]);
  const sameTicker = loaded?.key.split("|")[0] === ticker && loaded?.key.split("|")[1] === name;
  return {
    data: sameTicker ? (loaded?.data ?? null) : null,
    error: loaded?.key === key ? loaded.error : null,
    loading: loaded?.key !== key,
    notFound: loaded?.key === key ? loaded.notFound : false,
  };
}

export function useHealth(): Health | null {
  const [h, setH] = useState<Health | null>(null);
  useEffect(() => {
    getHealth()
      .then(setH)
      .catch(() => setH(null));
  }, []);
  return h;
}

export function useDefinitions(): Record<string, Definition> {
  const [d, setD] = useState<Record<string, Definition>>({});
  useEffect(() => {
    getDefinitions().then(setD);
  }, []);
  return d;
}

export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Fetch any engine path; refetches when the path changes and keeps the last data while loading. */
export function useJSON<T>(path: string | null): { data: T | null; error: string | null; loading: boolean } {
  const [state, setState] = useState<{ path: string | null; data: T | null; error: string | null }>({
    path: null,
    data: null,
    error: null,
  });
  useEffect(() => {
    if (!path) return;
    const ctrl = new AbortController();
    getJSON<T>(path, { signal: ctrl.signal })
      .then((data) => setState({ path, data, error: null }))
      .catch((e: unknown) => {
        if (!ctrl.signal.aborted) setState((s) => ({ path, data: s.data, error: (e as Error).message }));
      });
    return () => ctrl.abort();
  }, [path]);
  return {
    data: state.data,
    error: state.path === path ? state.error : null,
    loading: !!path && state.path !== path,
  };
}
