import { readFileSync } from "node:fs";
import { join } from "node:path";

/** Build-time list of what the static demo exported (empty outside static builds, where routes render on demand). */
export function staticManifest(): { tickers: string[]; snapshot_tokens: string[] } {
  if (process.env.STATIC_DEMO !== "1") return { tickers: [], snapshot_tokens: [] };
  const raw = readFileSync(join(process.cwd(), "public", "data", "manifest.json"), "utf8");
  return JSON.parse(raw);
}
