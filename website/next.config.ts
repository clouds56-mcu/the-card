import type { NextConfig } from "next";
import { normalizeAssetPrefix } from "./site-config";

const static_export = process.env.VINEXT_STATIC_EXPORT === "1";

const nextConfig: NextConfig = {
  assetPrefix: normalizeAssetPrefix(process.env.SITE_ASSET_PREFIX),
  images: {
    unoptimized: true,
  },
  output: static_export ? "export" : undefined,
  trailingSlash: static_export,
};

export default nextConfig;
