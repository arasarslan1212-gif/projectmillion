import { readFileSync } from "node:fs";
import { join } from "node:path";

type Manifest = { tickers: string[]; companies?: string[]; snapshot_tokens: string[] };

/** Build-time list of what the static site pre-renders (empty outside static builds, where routes render on
 * demand). With the browser engine, every synthetic company gets a page; without it, only the exported ones. */
export function staticManifest(): { tickers: string[]; snapshot_tokens: string[] } {
  if (process.env.STATIC_DEMO !== "1") return { tickers: [], snapshot_tokens: [] };
  const m: Manifest = JSON.parse(
    readFileSync(join(process.cwd(), "public", "data", "manifest.json"), "utf8"),
  );
  const engine = process.env.NEXT_PUBLIC_BROWSER_ENGINE === "1";
  return { tickers: engine && m.companies ? m.companies : m.tickers, snapshot_tokens: m.snapshot_tokens };
}
