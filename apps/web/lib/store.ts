"use client";

import { useCallback, useSyncExternalStore } from "react";

/** localStorage-backed state shared across components and tabs; never throws. */
const EVENT = "local-store-change";

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStore(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: the in-memory UI still updates below */
  }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: key }));
}

function subscribe(cb: () => void): () => void {
  window.addEventListener("storage", cb);
  window.addEventListener(EVENT, cb);
  return () => {
    window.removeEventListener("storage", cb);
    window.removeEventListener(EVENT, cb);
  };
}

export function useStored<T>(key: string, fallback: T): [T, (v: T) => void] {
  const raw = useSyncExternalStore(
    subscribe,
    () => read(key),
    () => null,
  );
  let value = fallback;
  if (raw) {
    try {
      value = JSON.parse(raw) as T;
    } catch {
      value = fallback;
    }
  }
  const set = useCallback((v: T) => writeStore(key, v), [key]);
  return [value, set];
}

/** The resolved theme ("light" | "dark") from <html data-theme>, kept in sync with toggles. */
export function useTheme(): string {
  return useSyncExternalStore(
    (cb) => {
      window.addEventListener("themechange", cb);
      return () => window.removeEventListener("themechange", cb);
    },
    () => document.documentElement.dataset.theme ?? "light",
    () => "light",
  );
}
