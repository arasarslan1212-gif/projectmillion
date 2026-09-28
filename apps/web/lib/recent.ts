"use client";

import { useStored, writeStore } from "./store";

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
  return next;
}

export function useRecent(): string[] {
  return useStored<string[]>(RECENT, [])[0];
}

export function useWatchlist(): [string[], (v: string[]) => void] {
  return useStored<string[]>(WATCH, []);
}
