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

## Hardware assets

The checked Revision A candidate is mirrored under
`public/hardware/candidates/v0.1.0/`. Its `release.json` is the authoritative
metadata and checksum index. The website intentionally labels these files as a
prototype candidate until every manual release gate has physical evidence.

Future releases should be promoted from a checked hardware-output artifact,
then mirrored as an immutable directory rather than fetched from expiring
GitHub Actions artifacts at browser runtime.
