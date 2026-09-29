/**
 * End-to-end test of the static site with the in-browser engine, in headless Chromium (CI, before deploy).
 * Serves out/ under the base path, waits for the engine to start, then uses it through the UI: the what-if
 * DCF on an exported stock, and a full report for a company that has no saved answers.
 *
 * Usage: node scripts/engine-e2e.mjs [--base /projectmillion] [--pyodide-dir <dir>]
 * --pyodide-dir serves Pyodide from a local copy instead of its CDN (for machines that can't reach it).
 * Needs the `playwright` package and a Chromium it can launch.
 */
import { createReadStream, existsSync, readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { chromium } from "playwright";

const arg = (name, dflt) => {
  const i = process.argv.indexOf(name);
  return i > 0 ? process.argv[i + 1] : dflt;
};
const base = arg("--base", "");
const pyodideDir = arg("--pyodide-dir", null);
const root = new URL("../out/", import.meta.url).pathname;
const manifest = JSON.parse(readFileSync(join(root, "data", "manifest.json"), "utf8"));
const first = manifest.tickers[0];
const other = manifest.tickers.find((x) => x !== first) ?? first;
const unsaved = (manifest.companies ?? []).find((c) => !manifest.tickers.includes(c)); // synthetic peers only
const TYPES = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".json": "application/json",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".txt": "text/plain",
  ".gz": "application/gzip",
  ".wasm": "application/wasm",
  ".zip": "application/zip",
  ".whl": "application/zip",
};

function serve(req, res) {
  let p = decodeURIComponent(new URL(req.url, "http://x").pathname);
  if (!p.startsWith(`${base}/`)) return notFound(res);
  p = normalize(p.slice(base.length));
  let file = join(root, p);
  if (file.endsWith("/") || (existsSync(file) && statSync(file).isDirectory()))
    file = join(file, "index.html");
  if (!file.startsWith(root) || !existsSync(file)) return notFound(res);
  res.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" });
  createReadStream(file).pipe(res);
}
function notFound(res) {
  res.writeHead(404, { "content-type": "text/html" });
  createReadStream(join(root, "404.html")).pipe(res);
}

const server = createServer(serve).listen(0, "127.0.0.1");
await new Promise((r) => server.once("listening", r));
const origin = `http://127.0.0.1:${server.address().port}${base}`;

const browser = await chromium.launch(
  process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
);
const context = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
if (pyodideDir) {
  await context.route(/cdn\.jsdelivr\.net\/pyodide\//, (route) => {
    const f = join(pyodideDir, new URL(route.request().url()).pathname.split("/").pop());
    return existsSync(f)
      ? route.fulfill({ path: f, contentType: TYPES[extname(f)] ?? "application/octet-stream" })
      : route.fulfill({ status: 404, body: "not in the local Pyodide copy" });
  });
}
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(`page error: ${e.message}`));
page.on("console", (m) => m.type() === "error" && errors.push(`console: ${m.text().slice(0, 300)}`));

const t0 = Date.now();
const secs = () => ((Date.now() - t0) / 1000).toFixed(1);
let failed = 0;
async function step(name, fn) {
  try {
    await fn();
    console.log(`ok   [${secs()}s] ${name}`);
  } catch (e) {
    failed++;
    console.log(`FAIL [${secs()}s] ${name}: ${String(e.message).split("\n")[0]}`);
    await page.screenshot({ path: `e2e-${failed}.png` }).catch(() => {});
  }
}

await step("home page loads and the engine starts", async () => {
  await page.goto(`${origin}/`);
  const status = page.getByRole("status").filter({ hasText: "Running in your browser" });
  await status.getByText(/Engine ready|Engine unavailable/).waitFor({ timeout: 300_000 });
  const text = await status.innerText();
  console.log(`     banner: ${text.replace(/\s+/g, " ").slice(-120)}`);
  if (!/Engine ready/.test(text)) throw new Error("the engine did not start");
});

await step("what-if DCF recomputes in the browser", async () => {
  await page.goto(`${origin}/stock/${first}/`);
  await page.getByRole("tab", { name: "What-if" }).click();
  const box = page.getByText("DCF value per share with your assumptions").locator("..");
  const value = box.locator("div.text-3xl");
  await value.getByText(/\$/).waitFor({ timeout: 240_000 });
  const before = await value.innerText();
  const wacc = page.getByRole("slider", { name: "WACC" });
  await wacc.focus();
  for (let i = 0; i < 8; i++) await wacc.press("ArrowRight");
  await page.waitForFunction(
    ([el, prev]) => el.textContent !== prev && el.textContent.includes("$"),
    [await value.elementHandle(), before],
    { timeout: 60_000 },
  );
  console.log(`     per-share value ${before} -> ${await value.innerText()} after raising WACC`);
});

if (unsaved) {
  await step("a company without saved answers is analyzed live", async () => {
    await page.goto(`${origin}/stock/${unsaved}/`);
    await page.getByText("Trust Rating").first().waitFor({ timeout: 60_000 });
    await page
      .getByText(/\d+\/100/)
      .first()
      .waitFor({ timeout: 240_000 });
    const h1 = await page.locator("h1").first().innerText();
    console.log(
      `     ${h1}: ${(
        await page
          .getByText(/\d+\/100/)
          .first()
          .innerText()
      ).trim()}`,
    );
  });
} else {
  await step("a comparison with no saved answer is computed live", async () => {
    await page.goto(`${origin}/compare/?t=${first},${other}&range=3y`);
    const row = page.getByRole("row", { name: /Trust Rating/ }).first();
    await row.waitFor({ timeout: 240_000 });
    console.log(`     ${first} vs ${other}: ${(await row.innerText()).replace(/\s+/g, " ").trim()}`);
  });
}

for (const e of errors) console.log(`     ${e}`);
await browser.close();
server.close();
console.log(failed ? `${failed} step(s) FAILED` : "all steps passed");
process.exit(failed ? 1 : 0);
