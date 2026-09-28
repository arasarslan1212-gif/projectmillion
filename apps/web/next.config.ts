import type { NextConfig } from "next";

const ENGINE_URL = process.env.ENGINE_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // The dev server only serves its assets to the host it started on; allow the usual local names.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async rewrites() {
    return [{ source: "/api/engine/:path*", destination: `${ENGINE_URL}/api/:path*` }];
  },
};

export default nextConfig;
