# The Card website

Public, static-first product and hardware-release website for The Card.

## Local development

Requires Node.js 22.13 or newer.

```bash
npm ci
npm run dev
```

Set `SITE_ORIGIN` to the final public origin when building for production so
canonical and social-image metadata use the deployed URL. It defaults to
`http://localhost:3000` for local development.

Run the production checks with:

```bash
npm test
npm run lint
```

## GitHub Pages

The public site is deployed to
<https://clouds56-mcu.github.io/the-card/> after the hardware and website CI
checks pass on `main`. The Pages build uses Vinext's static export mode and the
repository base path reported by GitHub, while local and Worker builds remain
root-mounted.

GitHub Pages serves static files and therefore does not execute the Worker or
its `_headers` policy. CI compensates by rejecting active PDF scripting and
active or externally referenced SVG content before deployment.

To reproduce the Pages build locally:

```bash
SITE_ORIGIN=https://clouds56-mcu.github.io \
SITE_ASSET_PREFIX=https://clouds56-mcu.github.io/the-card \
NEXT_PUBLIC_SITE_BASE_PATH=/the-card \
npm run build:pages

SITE_ORIGIN=https://clouds56-mcu.github.io \
SITE_ASSET_PREFIX=https://clouds56-mcu.github.io/the-card \
NEXT_PUBLIC_SITE_BASE_PATH=/the-card \
npm run test:pages
```

## Hardware assets

The checked design v0.2.0 candidate is mirrored under
`public/hardware/candidates/v0.2.0/`. Its `release.json` is the authoritative
identity, metadata, and checksum index. The website intentionally labels these
files as a prototype candidate until every manual release gate has physical
evidence. The unbuilt v0.1.0 draft remains available through Git history only;
it is not served as a fabrication download because v0.2.0 fixes its NFC design.

Future releases should be promoted from a checked hardware-output artifact,
then mirrored as an immutable directory rather than fetched from expiring
GitHub Actions artifacts at browser runtime.
