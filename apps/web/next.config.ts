import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["@tradesentinel/contracts"],
};

export default nextConfig;
