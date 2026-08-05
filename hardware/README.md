# hardware/ — Schematic & PCB (KiCad, code-first)

The electrical design of **the-card**, captured in code and regenerated into a
KiCad netlist. No EDA GUI is needed to produce the netlist — KiCad is only
required later for PCB layout.

```
hardware/
├── parts.yaml              # SOURCE OF TRUTH: parts, LCSC#s, nets, passives
├── pyproject.toml          # uv project: skidl + easyeda2kicad
├── uv.lock                 # pinned dependency lockfile (committed)
├── circuit.py              # the schematic in SKiDL  ->  the-card.net
├── the-card.net            # GENERATED (gitignored) KiCad netlist
├── scripts/
│   └── fetch_libs.sh       # regenerate libraries/ from LCSC#s in parts.yaml
└── libraries/              # GENERATED (gitignored): symbols / footprints / 3D
```

## One-time setup

```bash
cd hardware
uv sync                     # create .venv, install skidl + easyeda2kicad
./scripts/fetch_libs.sh     # fetch symbol/footprint/3D for every LCSC part
```

## Generate the netlist

```bash
uv run python circuit.py   # runs ERC, writes the-card.net (0 errors expected)
```

Import `the-card.net` into KiCad PCBNEW (**File → Import → Netlist**) to place
footprints and route the board.

## How it fits together

`parts.yaml` is the single source of truth. `fetch_libs.sh` reads it to build
two KiCad libraries (regenerable, gitignored); `circuit.py` instantiates those
parts, wires every net, runs ERC, and emits the netlist. Change the design →
edit `circuit.py` → re-run.

## ⚠️ Verify before tape-out

`circuit.py` flags these sections that depend on datasheet details:

- **DW01A + FS8205A** battery-protection topology (safety-critical — pin naming
  in the EasyEDA symbol is non-standard; confirm against the reference design).
- **GDEY029T94 FPC pinout** (the 1:GND, 2:VDD, 3:MOSI … mapping must match the
  panel's FFC; the connector footprint from EasyEDA is *staggered* — verify it
  fits the panel's flat FFC).
- **ST25DV04KC NFC antenna** geometry (a PCB layout task; AC0/AC1 are left as
  named nets `NFC_ANT_A/B`).

## Gotchas

- **easyeda2kicad 1.0.1:** `--output` must be **absolute** with
  `--project-relative` (relative paths crash). `fetch_libs.sh` handles this.
- **EasyEDA API 403:** rate-limits after a big batch — re-run the script in a
  few minutes.
- **ESP32-S3-WROOM-1** does **not** break out GPIO33/34 (reserved by internal
  SPI); `circuit.py` uses GPIO16 for `EPD_PWR_EN` instead.
- Harmless `KICAD*_SYMBOL_DIR` warnings at runtime are expected (we use the
  project libraries, not KiCad's stock symbols).
