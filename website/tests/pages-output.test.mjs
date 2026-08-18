import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const output_root = new URL("../dist/client/", import.meta.url);
const site_origin = process.env.SITE_ORIGIN;
const site_base_path = process.env.NEXT_PUBLIC_SITE_BASE_PATH ?? "";

if (!site_origin) {
  throw new Error("SITE_ORIGIN is required for the Pages output test");
}

const site_url = new URL(`${site_base_path}/`, site_origin);

function outputUrlForPath(pathname) {
  if (pathname === site_base_path || pathname === `${site_base_path}/`) {
    return new URL("index.html", output_root);
  }
  assert.ok(
    pathname.startsWith(`${site_base_path}/`),
    `${pathname} is outside ${site_base_path || "/"}`,
  );
  return new URL(pathname.slice(site_base_path.length + 1), output_root);
}

test("exports a complete project-path site for GitHub Pages", async () => {
  const html = await readFile(new URL("index.html", output_root), "utf8");
  assert.match(html, /<title>The Card — Open E-Paper Badge<\/title>/i);
  assert.ok(html.includes(`rel="canonical" href="${site_url}"`));
  assert.ok(html.includes(`${site_url}og.png`));
  assert.ok(html.includes(`${site_base_path}/hardware/candidates/v0.1.0/`));
  if (site_base_path) {
    assert.doesNotMatch(html, /(?:href|src)="\/(?:_next|hardware|og\.png)/);
  }

  const local_urls = new Set();
  for (const match of html.matchAll(/(?:href|src)="([^"]+)"/g)) {
    const value = match[1];
    if (value.startsWith("#")) continue;
    const resolved = new URL(value, site_url);
    if (resolved.origin === site_url.origin) local_urls.add(resolved);
  }

  assert.ok(local_urls.size >= 10, `expected at least 10 local URLs, got ${local_urls.size}`);
  await Promise.all(
    [...local_urls].map(async (url) => {
      const output_url = outputUrlForPath(url.pathname);
      await access(output_url);
    }),
  );

  await access(new URL("index.rsc", output_root));
});
