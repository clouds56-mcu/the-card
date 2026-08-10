#!/usr/bin/env bash
# Regenerate KiCad libraries from LCSC/EasyEDA for every part in parts.yaml.
#   - libraries/the-card.kicad_sym  : supplier-specific parts (symbol+footprint+3D)
#   - libraries/passives.kicad_sym  : generic R/C templates (symbol only)
# Output is gitignored — fully reproducible from this script + parts.yaml.
#
# Usage:
#   cd hardware && uv sync            # one-time
#   ./scripts/fetch_libs.sh
set -euo pipefail
cd "$(dirname "$0")/.."   # -> hardware/

ACTIVE_IDS=$(uv run python -c "
import yaml
d = yaml.safe_load(open('parts.yaml'))
parts = d['lcsc_parts']
ids = [
  str(p['lcsc'])
  for p in parts
  if str(p.get('lcsc', '')).startswith('C')
  and str(p['lcsc'])[1:].isdigit()
]
print(' '.join(ids))
")
PASSIVE_IDS=$(uv run python -c "
import yaml
d = yaml.safe_load(open('parts.yaml'))
parts = d.get('passive_templates', [])
ids = [
  str(p['lcsc'])
  for p in parts
  if str(p.get('lcsc', '')).startswith('C')
  and str(p['lcsc'])[1:].isdigit()
]
print(' '.join(ids))
")

mkdir -p libraries

echo ">> [1/2] supplier parts: $(echo "$ACTIVE_IDS" | wc -w | tr -d ' ') parts (symbol+footprint+3D)"
# --output MUST be absolute for easyeda2kicad 1.0.1 + --project-relative.
uv run easyeda2kicad --lcsc_id $ACTIVE_IDS --full \
  --output "$(pwd)/libraries/the-card.kicad_sym" --project-relative --overwrite
uv run python scripts/normalize_libraries.py

echo ">> [2/2] passives: $(echo "$PASSIVE_IDS" | wc -w | tr -d ' ') templates (symbol only)"
uv run easyeda2kicad --lcsc_id $PASSIVE_IDS --symbol \
  --output "$(pwd)/libraries/passives.kicad_sym" --overwrite

cat <<EOF

>> Done.
   the-card  : libraries/the-card.kicad_sym   (+ .pretty/ + .3dshapes/)
   passives  : libraries/passives.kicad_sym
   netlist   : run  uv run python circuit.py
EOF
