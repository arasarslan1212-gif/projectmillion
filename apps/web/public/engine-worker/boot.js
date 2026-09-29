/**
 * Boots the analysis engine inside Pyodide (CPython compiled to WebAssembly).
 *
 * Used by the browser's worker (worker.js) and by the CI smoke test (scripts/engine-smoke.mjs), so both run the
 * same steps. The bundle it loads is built by services/engine/engine/tools/build_browser_bundle.py, and the
 * Python side is services/engine/engine/browser.py.
 *
 * @param {object} o
 * @param {(opts: object) => Promise<any>} o.loadPyodide  Pyodide's loader (from its CDN, or the npm package in Node)
 * @param {object} o.bundle  the parsed bundle.json
 * @param {(file: string) => Promise<Uint8Array>} o.fetchBytes  reads a file of the bundle
 * @param {string} [o.indexURL]  where Pyodide and its packages live (default: the bundle's CDN URL)
 * @param {(path: string) => Uint8Array | null} [o.fetchFixtureSync]  reads one recorded provider response
 *   (bundle.fixtures + path) synchronously, for real-data bundles; the engine calls it the first time a request
 *   needs that file
 * @param {(stage: string) => void} [o.onStatus]
 */
export async function bootEngine({
  loadPyodide,
  bundle,
  fetchBytes,
  fetchFixtureSync,
  indexURL,
  onStatus = () => {},
}) {
  const home = "/home/pyodide";
  onStatus("Loading Python");
  const py = await loadPyodide(indexURL === null ? {} : { indexURL: indexURL ?? bundle.pyodide.index_url });

  onStatus("Loading numpy, pandas and scipy");
  // Fetch the engine's own files while Pyodide's packages download.
  const own = Promise.all([
    Promise.all(bundle.wheels.map((w) => fetchBytes(`wheels/${w}`))),
    fetchBytes(bundle.engine),
    fetchBytes(bundle.seed_db),
  ]);
  const problems = [];
  await py.loadPackage(bundle.pyodide.packages, {
    messageCallback: () => {},
    errorCallback: (msg) => problems.push(msg),
  });
  const missing = bundle.pyodide.packages.filter((p) => !(p in py.loadedPackages));
  if (missing.length) {
    // loadPackage reports failed downloads through the callback instead of throwing
    console.error(problems.join("\n"));
    throw new Error(`could not download ${missing.join(", ")} from Pyodide's package server`);
  }
  const [wheels, engineZip, seed] = await own;

  onStatus("Unpacking the engine");
  py.FS.mkdirTree(`${home}/site`);
  for (const w of wheels) py.unpackArchive(w, "zip", { extractDir: `${home}/site` });
  py.unpackArchive(engineZip, "zip", { extractDir: `${home}/repo` });
  py.FS.writeFile(`${home}/seed.db.gz`, seed);
  py.runPython(`import sys; sys.path[:0] = ["${home}/site", "${home}/repo/services/engine"]`);

  onStatus("Starting the engine");
  const browser = py.pyimport("engine.browser");
  const info = browser.start.callKwargs(`${home}/seed.db.gz`, {
    env: py.toPy(bundle.env ?? {}),
    fetch_fixture: bundle.fixtures && fetchFixtureSync ? fetchFixtureSync : null,
  });
  const health = info.toJs({ dict_converter: Object.fromEntries });
  info.destroy();

  let queue = Promise.resolve();
  return {
    health,
    /** One API call; calls run one at a time, as the engine is single-threaded here. */
    request(method, path, body) {
      const run = async () => {
        const res = await browser.request(method, path, body ?? null);
        const [status, text] = res.toJs();
        res.destroy();
        return { status, text };
      };
      const result = queue.then(run, run);
      queue = result.catch(() => {});
      return result;
    },
  };
}
