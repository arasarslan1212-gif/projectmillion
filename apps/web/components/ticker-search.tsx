"use client";

import { Search as SearchIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { search, useDebounced } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { SearchResult } from "@/lib/types";

/** Combobox with keyboard navigation (ArrowUp/Down, Enter, Escape). */
export function TickerSearch({
  autoFocus,
  compact,
  onPick,
}: {
  autoFocus?: boolean;
  compact?: boolean;
  onPick?: (t: string) => void;
}) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const dq = useDebounced(q, 150);
  const listId = useId();
  const shown = q.trim() && dq.trim() ? results : [];
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!dq.trim()) return;
    const ctrl = new AbortController();
    search(dq, ctrl.signal)
      .then((r) => {
        setResults(r.results);
        setActive(0);
        setError(null);
      })
      .catch((e) => {
        if (!ctrl.signal.aborted) setError(e.message ?? "Search is unavailable");
      });
    return () => ctrl.abort();
  }, [dq]);

  const go = (ticker: string) => {
    setOpen(false);
    setQ("");
    if (onPick) onPick(ticker);
    else router.push(`/stock/${encodeURIComponent(ticker)}`);
  };

  return (
    <div className="relative w-full">
      <label htmlFor={`${listId}-input`} className="sr-only">
        Search by ticker or company name
      </label>
      <div
        className={cn(
          "flex items-center gap-2 rounded-xl border border-line bg-surface px-3 focus-within:border-accent",
          compact ? "h-9" : "h-12",
        )}
      >
        <SearchIcon className="size-4 text-muted" aria-hidden />
        <input
          id={`${listId}-input`}
          ref={inputRef}
          autoFocus={autoFocus}
          role="combobox"
          aria-expanded={open && shown.length > 0}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && shown[active] ? `${listId}-${active}` : undefined}
          value={q}
          placeholder="Ticker or company, e.g. AAPL or Apple"
          className={cn(
            "w-full bg-transparent outline-none placeholder:text-muted",
            compact ? "text-sm" : "text-base",
          )}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(a + 1, shown.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              if (shown[active]) go(shown[active].ticker);
              else if (q.trim()) go(q.trim().toUpperCase());
            } else if (e.key === "Escape") {
              setOpen(false);
            }
          }}
        />
      </div>
      {open && (shown.length > 0 || error) && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-40 mt-1 max-h-80 w-full overflow-auto rounded-xl border border-line bg-surface py-1 shadow-lg"
        >
          {error && <li className="px-3 py-2 text-sm text-critical-ink">{error}</li>}
          {shown.map((r, i) => (
            <li
              key={r.ticker}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                go(r.ticker);
              }}
              onMouseEnter={() => setActive(i)}
              className={cn(
                "flex cursor-pointer items-baseline gap-3 px-3 py-2 text-sm",
                i === active && "bg-surface-2",
              )}
            >
              <span className="w-16 shrink-0 font-semibold">{r.ticker}</span>
              <span className="truncate text-ink-2">{r.name}</span>
              {r.exchange && <span className="ml-auto shrink-0 text-xs text-muted">{r.exchange}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
