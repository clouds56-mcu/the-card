#!/usr/bin/env bash
# Fetch KiCad symbol + footprint + 3D model for every LCSC part in parts.yaml.
# Regenerates hardware/libraries/ (gitignored — reproducible from this script).
#
# Usage:
#   cd hardware && uv sync                 # one-time: create venv + install
#   ./scripts/fetch_libs.sh                # generate libraries/
#
# Requires: uv (https://docs.astral.sh/uv/) and network access to LCSC/EasyEDA.
set -euo pipefail

cd "$(dirname "$0")/.."   # -> hardware/

IDS=$(uv run python -c "
import yaml
d = yaml.safe_load(open('parts.yaml'))
print(' '.join(p['lcsc'] for p in d['lcsc_parts']))
")

count=$(echo "$IDS" | wc -w | tr -d ' ')
echo ">> Fetching $count parts from LCSC/EasyEDA:"
echo "   $IDS"

# NOTE: --output must be ABSOLUTE for easyeda2kicad 1.0.1 + --project-relative
#       (relative paths hit a pathlib bug). Keep it absolute.
mkdir -p libraries
uv run easyeda2kicad \
  --lcsc_id $IDS \
  --full \
  --output "$(pwd)/libraries/the-card.kicad_sym" \
  --project-relative \
  --overwrite

echo ""
echo ">> Done."
echo "   Symbols:   libraries/the-card.kicad_sym"
echo "   Footprints: libraries/the-card.pretty/"
echo "   3D models: libraries/the-card.3dshapes/"
echo ""
echo "   If you saw HTTP 403 errors, the EasyEDA API is rate-limiting — wait a"
echo "   few minutes and re-run. Already-fetched parts are skipped cleanly."
