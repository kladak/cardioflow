import type { NextConfig } from "next";

const apiOrigin = process.env.CARDIOFLOW_API_ORIGIN || "http://127.0.0.1:8010";

const nextConfig: NextConfig = {
  turbopack: { root: process.cwd() },
  agentRules: false,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiOrigin}/api/:path*`,
      },
    ];
  },
};
export default nextConfig;
