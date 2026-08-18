import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { access, readFile, stat } from "node:fs/promises";
import test from "node:test";

const project_root = new URL("../", import.meta.url);
const release_root = new URL(
  "../public/hardware/candidates/v0.1.0/",
  import.meta.url,
);

async function render(headers = {}) {
  const worker_url = new URL("../dist/server/index.js", import.meta.url);
  worker_url.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(worker_url.href);

  return worker.fetch(
    new Request("https://hardware.example/", {
      headers: {
        accept: "text/html",
        host: "hardware.example",
        ...headers,
      },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

async function sha256(path) {
  const contents = await readFile(path);
  return createHash("sha256").update(contents).digest("hex");
}

test("renders the finished hardware website and candidate status", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>The Card — Open E-Paper Badge<\/title>/i);
  assert.match(html, /An open e-paper badge, down to the last trace\./);
  assert.match(html, /CAD candidate/);
  assert.match(html, /physical approval pending/);
  assert.match(html, /See every copper layer\./);
  assert.match(html, /Build Revision A\./);
  assert.match(html, /Prototype candidate—not production approved\./);
  assert.match(html, /CAD checks pass\./);
  assert.match(html, /hardware\/candidates\/v0\.1\.0\/fabrication/);
  assert.match(html, /53\.98 × 85\.60/);
  assert.match(html, /69<\/strong><span>placed components/);
  assert.doesNotMatch(html, /codex-preview|SkeletonPreview|react-loading-skeleton/);
});

test("emits configured social metadata and ignores forwarded-host spoofing", async () => {
  const response = await render({
    "x-forwarded-host": "attacker.example",
    "x-forwarded-proto": "https",
  });
  const html = await response.text();

  assert.match(html, /property="og:title" content="The Card — Open E-Paper Badge"/);
  assert.match(
    html,
    /<meta(?=[^>]*property="og:image")(?=[^>]*content="http:\/\/localhost:3000\/og\.png")[^>]*>/,
  );
  assert.match(html, /name="twitter:card" content="summary_large_image"/);
  assert.match(
    html,
    /<meta(?=[^>]*name="twitter:image")(?=[^>]*content="http:\/\/localhost:3000\/og\.png")[^>]*>/,
  );
  assert.match(html, /rel="canonical" href="http:\/\/localhost:3000"/);
  assert.doesNotMatch(html, /attacker\.example/);
  assert.doesNotMatch(html, /fonts\.(?:googleapis|gstatic)\.com/);
});

test("mirrored candidate tree matches the public release manifest and checksums", async () => {
  const manifest = JSON.parse(
    await readFile(new URL("release.json", release_root), "utf8"),
  );
  assert.equal(manifest.schema_version, 1);
  assert.equal(manifest.release_version, "0.1.0");
  assert.equal(manifest.hardware_revision, "A");
  assert.equal(manifest.manual_approval.status, "pending");
  assert.equal(manifest.validation.erc_violations, 0);
  assert.equal(manifest.validation.drc_violations, 0);
  assert.equal(manifest.validation.schematic_parity_violations, 0);

  const response = await render();
  const html = await response.text();
  assert.equal(manifest.artifacts.length, 78);
  for (const artifact of manifest.artifacts) {
    assert.ok(!artifact.path.startsWith("/"), artifact.path);
    assert.ok(!artifact.path.split("/").includes(".."), artifact.path);
    const artifact_url = new URL(artifact.path, release_root);
    const artifact_stat = await stat(artifact_url);
    assert.equal(artifact_stat.size, artifact.bytes, artifact.path);
    assert.equal(await sha256(artifact_url), artifact.sha256, artifact.path);
    if (artifact.path.endsWith(".pdf")) {
      const pdf_text = (await readFile(artifact_url)).toString("latin1");
      assert.doesNotMatch(
        pdf_text,
        /\/(?:JavaScript|JS)\b/,
        `${artifact.path} contains active PDF JavaScript`,
      );
    }
  }

  const bundles = manifest.artifacts.filter(({ path }) => path.endsWith(".zip"));
  assert.equal(bundles.length, 3);
  for (const bundle of bundles) {
    assert.ok(
      html.includes(`/hardware/candidates/v0.1.0/${bundle.path}`),
      bundle.path,
    );
    assert.ok(html.includes(bundle.sha256.slice(0, 10)), bundle.sha256);
  }

  const checksum_lines = (
    await readFile(new URL("SHA256SUMS", release_root), "utf8")
  ).trim().split("\n");
  assert.equal(checksum_lines.length, 79);
  for (const line of checksum_lines) {
    const match = line.match(/^([0-9a-f]{64})[ ]{2}([^/].*)$/);
    assert.ok(match, line);
    const [, expected_sha256, path] = match;
    assert.ok(!path.split("/").includes(".."), path);
    assert.equal(await sha256(new URL(path, release_root)), expected_sha256, path);
  }
});

test("sets baseline browser security headers", async () => {
  const response = await render();
  assert.equal(response.headers.get("x-content-type-options"), "nosniff");
  assert.equal(response.headers.get("x-frame-options"), "DENY");
  assert.match(response.headers.get("content-security-policy") ?? "", /frame-ancestors 'none'/);
  assert.match(response.headers.get("permissions-policy") ?? "", /camera=\(\)/);

  const static_headers = await readFile(
    new URL("dist/client/_headers", project_root),
    "utf8",
  );
  assert.match(static_headers, /frame-ancestors 'none'/);
  assert.match(static_headers, /\/hardware\/\*/);
  assert.match(static_headers, /sandbox; default-src 'none'/);
});

test("ships real previews and a bespoke social card", async () => {
  const expected_assets = [
    "preview/pcb-front.png",
    "preview/pcb-inner-1.png",
    "preview/pcb-inner-2.png",
    "preview/pcb-back.png",
    "preview/schematic-thumbnail.png",
    "preview/schematic.pdf",
    "preview/pcb.pdf",
    "assembly/canonical/assembly-front.png",
    "assembly/canonical/assembly-back.png",
  ];
  await Promise.all(expected_assets.map((path) => access(new URL(path, release_root))));

  const social_card = await readFile(new URL("public/og.png", project_root));
  assert.equal(social_card.subarray(1, 4).toString("ascii"), "PNG");
  assert.equal(social_card.readUInt32BE(16), 1672);
  assert.equal(social_card.readUInt32BE(20), 941);
});
