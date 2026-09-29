/**
 * Smoke test for the in-browser engine, run in CI before the static site deploys (Node, not a browser: same
 * Pyodide release, same boot code in public/engine-worker/boot.js, same bundle in public/engine).
 *
 * Usage: node scripts/engine-smoke.mjs [--bundle <dir>] [--data <dir>]  (defaults: public/engine, public/data)
 * Needs the `pyodide` npm package at the bundle's version (`npm install --no-save pyodide@<version>`); Pyodide
 * downloads numpy, pandas and scipy from its CDN. Fails on any unexpected status; reports, without failing,
 * where a live answer differs from the saved one (the browser's numpy/pandas/scipy are not uv.lock's).
 */
import { readFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { loadPyodide, version } from "pyodide";
import { bootEngine } from "../public/engine-worker/boot.js";

const arg = (name, dflt) => {
  const i = process.argv.indexOf(name);
  return i > 0 ? pathToFileURL(`${process.argv[i + 1]}/`) : new URL(dflt, import.meta.url);
};
const bundleDir = arg("--bundle", "../public/engine/");
const dataDir = arg("--data", "../public/data/");
const bundle = JSON.parse(await readFile(new URL("bundle.json", bundleDir), "utf8"));
if (version !== bundle.pyodide.version) {
  throw new Error(`pyodide npm package is ${version}, the bundle needs ${bundle.pyodide.version}`);
}

const t0 = performance.now();
const secs = () => ((performance.now() - t0) / 1000).toFixed(1);
const engine = await bootEngine({
  loadPyodide,
  bundle,
  indexURL: null, // the npm package; Node fetches packages from the CDN and caches them there
  fetchBytes: async (f) => new Uint8Array(await readFile(new URL(f, bundleDir))),
  fetchFixtureSync: (p) => {
    try {
      return new Uint8Array(readFileSync(new URL(`fixtures/${p}`, bundleDir)));
    } catch {
      return null;
    }
  },
  onStatus: (s) => console.log(`[${secs()}s] ${s}`),
});
console.log(`[${secs()}s] engine ready: ${JSON.stringify(engine.health)}`);

let failures = 0;
async function call(method, path, body, expect = 200) {
  const t = performance.now();
  const r = await engine.request(method, path, body ? JSON.stringify(body) : null);
  const ms = Math.round(performance.now() - t);
  const ok = r.status === expect;
  if (!ok) failures++;
  console.log(
    `${ok ? "ok  " : "FAIL"} ${method} ${path} -> ${r.status} in ${ms} ms${ok ? "" : `: ${r.text.slice(0, 500)}`}`,
  );
  return ok && r.status < 400 ? JSON.parse(r.text) : null;
}

const VOLATILE = new Set([
  "fetched_at",
  "timing_ms",
  "generated_at",
  "created_at",
  "computed_at",
  "report_id",
]);
function diff(a, b, path = "", out = []) {
  if (a && b && typeof a === "object" && typeof b === "object") {
    for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) {
      if (VOLATILE.has(k)) continue;
      if (!(k in a) || !(k in b)) out.push(`${path}/${k}: only in ${k in a ? "saved" : "live"}`);
      else diff(a[k], b[k], `${path}/${k}`, out);
    }
  } else if (typeof a === "number" && typeof b === "number") {
    if (Math.abs(a - b) > 1e-6 * Math.max(1, Math.abs(a))) out.push(`${path}: ${a} vs ${b}`);
  } else if (a !== b) out.push(`${path}: ${String(a).slice(0, 50)} vs ${String(b).slice(0, 50)}`);
  return out;
}

// every report section of one exported stock, compared with the saved answer
const manifest = JSON.parse(await readFile(new URL("manifest.json", dataDir), "utf8"));
const t = manifest.tickers[0];
const sections = (await call("GET", `/report/${t}/sections`))?.sections ?? [];
for (const s of sections) {
  const name = typeof s === "string" ? s : s.name;
  const live = await call("GET", `/report/${t}/section/${name}`);
  const saved = JSON.parse(await readFile(new URL(`report/${t}/${name}.json`, dataDir), "utf8"));
  const d = live ? diff(saved, live) : [];
  console.log(
    `     ${name}: ${d.length ? `${d.length} differences from the saved answer, e.g. ${d.slice(0, 3).join(" | ")}` : "identical to the saved answer"}`,
  );
}

// what the static files can't answer
const recorded = !!bundle.fixtures; // real data: replaying the build's recording
const other = manifest.tickers.find((x) => x !== t) ?? t;
const unsaved = recorded ? null : (manifest.companies?.find((c) => !manifest.tickers.includes(c)) ?? "ZQT01");
if (unsaved) {
  const headline = await call("GET", `/report/${unsaved}/section/headline`);
  if (headline && !(headline.target?.p50 > 0)) failures++;
}
await call("GET", `/report/${t}/section/peers?peers=${unsaved ?? other}`);
await call("GET", `/compare?tickers=${t},${other}&range=1y`);
const dcf = await call("POST", `/valuation/${t}/dcf`, { wacc: 0.1 });
if (dcf && !(dcf.per_share > 0)) failures++;
await call("POST", `/valuation/${t}/dcf`, { wacc: 9 }, 422);
await call("POST", `/report/${t}/refresh`);
await call("PUT", "/watchlist", { tickers: [t, other] });
await call("POST", "/alerts/run");
await call("GET", "/alerts");
await call("GET", "/report/NOPE/section/company", null, 404);

console.log(`[${secs()}s] ${failures ? `${failures} FAILED` : "all checks passed"}`);
process.exit(failures ? 1 : 0);
