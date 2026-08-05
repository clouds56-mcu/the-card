# hardware/ — Schematic & PCB (KiCad)

This directory holds the **electrical design** for the-card, generated code-first:

```
hardware/
├── parts.yaml              # single source of truth: parts, LCSC#s, nets, passives
├── pyproject.toml          # uv project: skidl + easyeda2kicad
├── uv.lock                 # pinned dependency lockfile (committed)
├── scripts/
│   └── fetch_libs.sh       # regenerate libraries/ from LCSC#s in parts.yaml
├── libraries/              # GENERATED (gitignored) — symbols/footprints/3D
├── circuit.py              # (next) SKiDL circuit → KiCad netlist
└── the-card.kicad_pro      # (next) KiCad project for PCBNEW layout
```

## Toolchain

- **uv** for the Python env (skidl + easyeda2kicad)
- **KiCad 8/9** for the symbol library (passives: `Device:R/C`) and PCBNEW layout

## Setup

```bash
cd hardware
uv sync                     # create .venv, install skidl + easyeda2kicad (from uv.lock)
./scripts/fetch_libs.sh     # fetch symbol/footprint/3D for every LCSC part
```

`uv sync` reproduces the exact environment from `uv.lock`. The generated
`libraries/` is **gitignored** — it is fully reproducible from `parts.yaml`
via `fetch_libs.sh`, so we don't commit LCSC's (large, binary) 3D models.

## Why code-first?

The circuit lives in `circuit.py` (SKiDL) and `parts.yaml` — both are text,
diffable, and reviewable. Running it emits a KiCad netlist that PCBNEW imports
for layout. This keeps the *electrical design* version-controlled while the
*physical layout* stays a GUI task in KiCad.

## Notes / gotchas

- **easyeda2kicad 1.0.1 bug:** `--output` must be an **absolute** path when used
  with `--project-relative` (relative paths crash). `fetch_libs.sh` handles this.
- **EasyEDA API 403:** rate-limits after a big batch. Re-run the script in a few
  minutes; already-fetched parts are harmless to re-fetch.
- **Passives** (R/C) use KiCad's stock `Device` library, so `circuit.py` needs to
  find KiCad's symbol dir — set `KICAD9_SYMBOL_DIR` (or 8) to e.g.
  `/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols`.
