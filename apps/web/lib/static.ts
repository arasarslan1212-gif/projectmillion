/**
 * Static demo mode (GitHub Pages): no engine is running, so each API request is answered from JSON files exported
 * by `python -m engine.tools.export_static` (the exact responses of the live API for the synthetic market).
 * The file layout mirrors services/engine/engine/tools/export_static.py.
 */

export const STATIC_DEMO = process.env.NEXT_PUBLIC_STATIC_DEMO === "1";
export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export const STATIC_NOTE =
  "This is a static demo of the app on synthetic data, so it can only show what was exported ahead of time. Run the app locally (see the README) for the live engine.";

const key = (tickers: string) =>
  tickers
    .split(",")
    .map((t) => t.trim().toUpperCase())
    .filter(Boolean)
    .sort()
    .join("_");

/** The static file for an API path, or null when the demo has no answer for it. */
export function staticFile(path: string): string | null {
  const url = new URL(path, "http://x");
  const p = url.pathname.replace(/\/+$/, "");
  const q = url.searchParams;
  let m: RegExpMatchArray | null;
  if (p === "/health") return "health.json";
  if (p === "/meta/definitions") return "meta/definitions.json";
  if (p === "/meta/methodology") return "meta/methodology.json";
  if ((m = p.match(/^\/report\/([^/]+)\/section\/([^/]+)$/)))
    return `report/${decodeURIComponent(m[1]).toUpperCase()}/${m[2]}.json`;
  if (p === "/compare") return `compare/${key(q.get("tickers") ?? "")}_${q.get("range") ?? "1y"}.json`;
  if (p === "/watchlist/summary") {
    const k = key(q.get("tickers") ?? "");
    return `watchlist/${k || "_empty"}.json`;
  }
  if (p === "/track-record")
    return `track-record/${q.get("kind") ?? "backtest"}/${q.get("profile") || "_all"}.json`;
  if ((m = p.match(/^\/track-record\/([^/]+)$/)))
    return `track-record/ticker/${decodeURIComponent(m[1]).toUpperCase()}.json`;
  if ((m = p.match(/^\/snapshot\/([^/]+)$/))) return `snapshot/${m[1]}.json`;
  if (p === "/alerts") return "alerts/inbox.json";
  if (p === "/alerts/unread") return "alerts/unread.json";
  return null;
}

export function staticUrl(file: string): string {
  return `${BASE_PATH}/data/${file}`;
}
