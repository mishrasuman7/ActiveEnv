import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a self-contained server bundle so the Docker image stays small.
  // Harmless for Vercel, which ignores it.
  output: "standalone",
};

export default nextConfig;
