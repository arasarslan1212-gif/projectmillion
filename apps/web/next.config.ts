import type { NextConfig } from "next";

const ENGINE_URL = process.env.ENGINE_URL ?? "http://127.0.0.1:8000";
// STATIC_DEMO=1 builds a read-only static site (GitHub Pages) that reads exported engine responses from
// public/data instead of calling the engine; see lib/static.ts and engine/tools/export_static.py.
const STATIC_DEMO = process.env.STATIC_DEMO === "1";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // The dev server only serves its assets to the host it started on; allow the usual local names.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  ...(STATIC_DEMO
    ? {
        output: "export",
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
