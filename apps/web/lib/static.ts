/**
 * Static site mode (GitHub Pages): there is no server. GET requests are answered from JSON files exported by
 * `python -m engine.tools.export_static` (the exact responses of the live API for the synthetic market); the file
 * layout mirrors services/engine/engine/tools/export_static.py. With the browser engine on, everything else
 * (edits, what-ifs, other companies, alerts) is computed by the engine itself, running in the browser
 * (lib/engine-client.ts).
 */

export const STATIC_DEMO = process.env.NEXT_PUBLIC_STATIC_DEMO === "1";
export const BROWSER_ENGINE = STATIC_DEMO && process.env.NEXT_PUBLIC_BROWSER_ENGINE === "1";
/** Whether actions that compute on request (what-if DCF, peer edits, refresh, alert checks) are available. */
export const CAN_COMPUTE = !STATIC_DEMO || BROWSER_ENGINE;
export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export const STATIC_NOTE =
  "This is a static demo of the app on synthetic data, so it can only show what was exported ahead of time. Run the app locally (see the README) for the live engine.";

const split = (tickers: string) =>
  tickers
    .split(",")
    .map((t) => t.trim().toUpperCase())
    .filter(Boolean);
const key = (tickers: string) => split(tickers).sort().join("_");

// Set at build time from the export's manifest (empty, e.g. in unit tests: assume everything was exported).
const EXPORTED = new Set(split(process.env.NEXT_PUBLIC_EXPORTED_TICKERS ?? ""));
const saved = (...tickers: string[]) => !EXPORTED.size || tickers.every((t) => EXPORTED.has(t));
// Whether compare sets and multi-stock watchlists were saved (only for short lists; see export_static.py).
const COMBOS = process.env.NEXT_PUBLIC_EXPORTED_COMBOS !== "0";

/** Tickers refreshed in this session: their reports come from the engine from then on. */
const liveTickers = new Set<string>();

/** Keep the saved answers in step with what the engine changed. */
export function noteEngineChange(method: string, path: string): void {
  const m = path.match(/^\/report\/([^/]+)\/refresh/);
  if (method === "POST" && m) liveTickers.add(decodeURIComponent(m[1]).toUpperCase());
}

/** Answers that change as the engine runs: once it is ready, ask it rather than the saved file. */
export const isStateful = (path: string) => path.startsWith("/alerts");

/** The static file for an API path, or null when the demo has no answer for it. */
export function staticFile(path: string): string | null {
  const url = new URL(path, "http://x");
  const p = url.pathname.replace(/\/+$/, "");
  const q = url.searchParams;
  let m: RegExpMatchArray | null;
  if (p === "/health") return "health.json";
  if (p === "/meta/definitions") return "meta/definitions.json";
  if (p === "/meta/methodology") return "meta/methodology.json";
  if ((m = p.match(/^\/report\/([^/]+)\/section\/([^/]+)$/))) {
    // saved with default settings only: a query (custom peers) or a refreshed report must be computed
    const t = decodeURIComponent(m[1]).toUpperCase();
    return url.search || liveTickers.has(t) || !saved(t) ? null : `report/${t}/${m[2]}.json`;
  }
  if (p === "/compare") {
    const ts = q.get("tickers") ?? "";
    return COMBOS && saved(...split(ts)) ? `compare/${key(ts)}_${q.get("range") ?? "1y"}.json` : null;
  }
  if (p === "/watchlist/summary") {
    const ts = q.get("tickers") ?? "";
    const n = split(ts).length;
    return (COMBOS || n <= 1) && saved(...split(ts)) ? `watchlist/${key(ts) || "_empty"}.json` : null;
  }
  if (p === "/track-record")
    return `track-record/${q.get("kind") ?? "backtest"}/${q.get("profile") || "_all"}.json`;
  if ((m = p.match(/^\/track-record\/([^/]+)$/))) {
    const t = decodeURIComponent(m[1]).toUpperCase();
    return saved(t) ? `track-record/ticker/${t}.json` : null;
  }
  if ((m = p.match(/^\/snapshot\/([^/]+)$/))) return `snapshot/${m[1]}.json`;
  if (p === "/alerts") return "alerts/inbox.json";
  if (p === "/alerts/unread") return "alerts/unread.json";
  return null;
}

export function staticUrl(file: string): string {
  return `${BASE_PATH}/data/${file}`;
}
