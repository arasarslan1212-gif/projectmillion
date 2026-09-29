/**
 * Web worker that runs the analysis engine in the browser (see boot.js), so the page stays responsive while
 * Python computes. Messages in: {type: "boot"} and {type: "request", id, method, path, body}.
 * Messages out: {type: "status", stage}, {type: "ready", health, seconds}, {type: "failed", error} and
 * {type: "response", id, status, text}.
 */
import { bootEngine } from "./boot.js";

const bundleDir = new URL("../engine/", self.location.href);
let engine = null;
let booting = null;

/** One line for the page: a Python traceback's last line names the exception. */
function summary(err) {
  const lines = String(err?.message ?? err)
    .trim()
    .split("\n");
  return lines[0].startsWith("Traceback") ? lines[lines.length - 1] : lines[0];
}

async function fetchBytes(file) {
  const r = await fetch(new URL(file, bundleDir));
  if (!r.ok) throw new Error(`could not download ${file} (HTTP ${r.status})`);
  return new Uint8Array(await r.arrayBuffer());
}

/** A recorded provider response, read synchronously (allowed in workers): the engine asks for it mid-request. */
function fetchFixtureSync(path) {
  const xhr = new XMLHttpRequest();
  xhr.open("GET", new URL(`fixtures/${path}`, bundleDir).href, false);
  xhr.responseType = "arraybuffer";
  xhr.send();
  return xhr.status === 200 ? new Uint8Array(xhr.response) : null;
}

async function boot() {
  const t0 = performance.now();
  const r = await fetch(new URL("bundle.json", bundleDir));
  if (!r.ok) throw new Error(`the engine bundle is missing (HTTP ${r.status})`);
  const bundle = await r.json();
  const { loadPyodide } = await import(/* webpackIgnore: true */ `${bundle.pyodide.index_url}pyodide.mjs`);
  engine = await bootEngine({
    loadPyodide,
    bundle,
    fetchBytes,
    fetchFixtureSync,
    onStatus: (stage) => self.postMessage({ type: "status", stage }),
  });
  self.postMessage({ type: "ready", health: engine.health, seconds: (performance.now() - t0) / 1000 });
}

self.onmessage = async (e) => {
  const msg = e.data;
  if (msg.type === "boot") {
    booting ??= boot().catch((err) => {
      console.error(err);
      self.postMessage({ type: "failed", error: summary(err) });
    });
    return;
  }
  if (msg.type === "request") {
    try {
      await booting;
      if (!engine) throw new Error("it did not start");
      const res = await engine.request(msg.method, msg.path, msg.body);
      self.postMessage({ type: "response", id: msg.id, ...res });
    } catch (err) {
      const detail = `The in-browser engine is unavailable: ${summary(err)}`;
      self.postMessage({ type: "response", id: msg.id, status: 503, text: JSON.stringify({ detail }) });
    }
  }
};
