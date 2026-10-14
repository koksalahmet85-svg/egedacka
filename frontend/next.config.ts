import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone", // Docker imajı ~150MB, node_modules taşınmaz
  poweredByHeader: false,
};

export default config;
