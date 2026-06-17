import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output is for production Docker images only. Enabling it during
  // `next dev` (especially with a host-mounted .next cache) breaks the RSC
  // client manifest and surfaces errors like global-error.js not found.
  ...(process.env.NODE_ENV === "production" ? { output: "standalone" as const } : {}),
};

export default nextConfig;
