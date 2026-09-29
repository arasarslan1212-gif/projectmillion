import { readFileSync } from "node:fs";
import type { NextConfig } from "next";

const ENGINE_URL = process.env.ENGINE_URL ?? "http://127.0.0.1:8000";
// STATIC_DEMO=1 builds a static site (GitHub Pages) that reads exported engine responses from public/data and,
// with NEXT_PUBLIC_BROWSER_ENGINE=1, computes the rest with the engine running in the browser; see lib/static.ts.
const STATIC_DEMO = process.env.STATIC_DEMO === "1";
// the tickers with saved answers, so the site doesn't ask for files that were never exported
const exported = STATIC_DEMO
  ? JSON.parse(readFileSync("public/data/manifest.json", "utf8")).tickers.join(",")
  : "";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // The dev server only serves its assets to the host it started on; allow the usual local names.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  ...(STATIC_DEMO
    ? {
        output: "export",
        env: { NEXT_PUBLIC_EXPORTED_TICKERS: exported },
        basePath: process.env.NEXT_PUBLIC_BASE_PATH || undefined,
        trailingSlash: true,
        images: { unoptimized: true },
      }
    : {
        async rewrites() {
          return [{ source: "/api/engine/:path*", destination: `${ENGINE_URL}/api/:path*` }];
        },
      }),
};

export default nextConfig;
