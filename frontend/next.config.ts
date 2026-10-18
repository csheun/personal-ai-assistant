import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lets the e2e suite keep a mock-mode and an HTTP-mode build side by side.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  cacheComponents: true,
  partialPrefetching: true,
  reactCompiler: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
