const base_path_pattern = /^\/[A-Za-z0-9._~-]+(?:\/[A-Za-z0-9._~-]+)*$/;

export function normalizePublicBasePath(value: string) {
  if (value === "") return "";
  const segments = value.slice(1).split("/");
  if (
    !base_path_pattern.test(value) ||
    segments.some((segment) => segment === "." || segment === "..")
  ) {
    throw new Error(
      "NEXT_PUBLIC_SITE_BASE_PATH must be empty or a slash-prefixed URL path without a trailing slash",
    );
  }
  return value;
}

export function normalizeSiteOrigin(value: string) {
  const origin = new URL(value);
  if (origin.protocol !== "http:" && origin.protocol !== "https:") {
    throw new Error("SITE_ORIGIN must use http or https");
  }
  if (
    origin.username ||
    origin.password ||
    origin.pathname !== "/" ||
    origin.search ||
    origin.hash
  ) {
    throw new Error("SITE_ORIGIN must be an origin without credentials, path, query, or hash");
  }
  return new URL(origin.origin);
}

export function normalizeAssetPrefix(value: string | undefined) {
  if (!value) return undefined;
  const prefix = new URL(value);
  if (prefix.protocol !== "https:") {
    throw new Error("SITE_ASSET_PREFIX must use https");
  }
  if (prefix.username || prefix.password || prefix.search || prefix.hash) {
    throw new Error("SITE_ASSET_PREFIX must not contain credentials, a query, or a fragment");
  }
  return prefix.toString().replace(/\/$/, "");
}

export const public_base_path = normalizePublicBasePath(
  process.env.NEXT_PUBLIC_SITE_BASE_PATH ?? "",
);

export function withPublicBasePath(path: `/${string}`) {
  if (path.startsWith("//") || path.split("/").includes("..")) {
    throw new Error(`Unsafe public path: ${path}`);
  }
  return `${public_base_path}${path}`;
}
