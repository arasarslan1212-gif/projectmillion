"use client";

import { getJSON } from "./api";
import { useStored, writeStore } from "./store";
import { CAN_COMPUTE } from "./static";

const RECENT = "recent-tickers";
const WATCH = "watchlist";

function readList(key: string): string[] {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

export function pushRecent(ticker: string): void {
  const list = readList(RECENT).filter((t) => t !== ticker);
  writeStore(RECENT, [ticker, ...list].slice(0, 10));
}

export function toggleWatch(ticker: string): string[] {
  const list = readList(WATCH);
  const next = list.includes(ticker) ? list.filter((t) => t !== ticker) : [...list, ticker];
  writeStore(WATCH, next);
  syncWatchlist(next);
  return next;
}

/** The server keeps one copy of the watchlist so it can evaluate alerts; the browser's list is the source. */
export function syncWatchlist(list: string[] = readList(WATCH)): void {
  if (!CAN_COMPUTE) return; // no engine to keep a copy
  getJSON("/watchlist", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tickers: list }),
  })
    .then(() => window.dispatchEvent(new Event("alerts-changed")))
    .catch(() => {
      /* offline or engine down: alerts will catch up on the next sync */
    });
}

export function useRecent(): string[] {
  return useStored<string[]>(RECENT, [])[0];
}

export function useWatchlist(): [string[], (v: string[]) => void] {
  return useStored<string[]>(WATCH, []);
}
