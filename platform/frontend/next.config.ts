import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone", // Docker imajı ~150 MB
  poweredByHeader: false,
  reactStrictMode: true,
};

export default config;
