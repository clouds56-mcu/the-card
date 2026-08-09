# hardware/ — Schematic & PCB (KiCad, code-first)

The electrical design of **the-card**, captured in code and emitted as both a
KiCad **schematic** (`.kicad_sch`) and a **netlist** (`.net`). KiCad 10 is
installed; the schematic opens in eeschema and is ERC-clean (0 errors).

```
hardware/
├── parts.yaml              # SOURCE OF TRUTH: parts, LCSC#s, nets, passives
├── pyproject.toml + uv.lock# uv project: skidl + easyeda2kicad (+ pypdf dev)
├── circuit.py              # the design in SKiDL (connectivity) -> the-card.net
├── gen_hierarchical_schematic.py # current deterministic A2 layout generator
├── verify_schematic.py     # compare every KiCad pin's peers with circuit.py
├── gen_schematic.py        # legacy flat-layout generator; not used currently
├── the-card.kicad_pro      # KiCad 10 project
├── the-card.kicad_sch      # GENERATED single-page A2 schematic
├── sym-lib-table / fp-lib-table  # register our the-card + passives libraries
├── SCHEMATIC-GUIDE.md      # functional-region drawing and review notes
├── datasheets/             # archived datasheet PDFs + index
├── scripts/fetch_libs.sh   # regenerate libraries/ from LCSC#s in parts.yaml
└── libraries/              # GENERATED (gitignored): symbols / footprints / 3D
```

## One-time setup

```bash
cd hardware
uv sync                     # create .venv, install skidl + easyeda2kicad
./scripts/fetch_libs.sh     # fetch symbol/footprint/3D for every LCSC part
```

## Generate and verify

```bash
uv run python circuit.py
uv run python gen_hierarchical_schematic.py
uv run python verify_schematic.py
kicad-cli sch erc --severity-all the-card.kicad_sch -o /tmp/erc.txt
```

The verifier exports the complete KiCad schematic and compares the peer set of
every component pin with the canonicalized SKiDL circuit. The expected result is
53 components and 247 component pins with identical connectivity. KiCad ERC has
0 errors and 17 intentional `isolated_pin_label` warnings for one-ended test,
antenna, motor, and e-paper panel nets.

Open the schematic:
```bash
/Applications/KiCad/KiCad.app/Contents/MacOS/eeschema the-card.kicad_sch
```

> `gen_hierarchical_schematic.py` is retained under its original filename, but it
> now emits one A2 sheet. It overwrites `the-card.kicad_sch`; put durable layout
> changes into its placement and region-offset tables so regeneration stays
> deterministic. `gen_schematic.py` is the previous flat A1 generator and is
> retained only as a reference.

## How it fits together

`parts.yaml` holds procurement and part data. `fetch_libs.sh` builds the two KiCad
libraries, while `circuit.py` defines electrical connectivity and emits
`the-card.net`. The layout generator imports that circuit and changes only its
presentation: one A2 page containing Power/USB, MCU, NFC/sensors, e-paper, and UI
regions. For an electrical change, update `circuit.py`, regenerate the netlist and
schematic, then run `verify_schematic.py` before accepting the result.

## Verification status (done)

All three originally-flagged sections were checked against datasheets (see
`../PROGRESS.md` §7 and the full pinout cross-check). No wiring errors found.
Residual layout-time items (non-blocking):

- **DW01A+FS8205A** — topology confirmed; final eyeball of the FS8205A app circuit.
- **GDEY029T94 booster/HV caps** — confirm host-side need vs DESPI reference.
- **ST25DV04KC antenna** — design the 13.56 MHz PCB trace coil on AC0/AC1.
- **C6081230 FPC footprint** is *staggered* in EasyEDA — verify it fits the panel's
  flat 24-pin FFC, or pick a non-staggered alternative.

## Gotchas

- **easyeda2kicad 1.0.1:** `--output` must be **absolute** with
  `--project-relative` (relative paths crash). `fetch_libs.sh` handles this.
- **EasyEDA API 403:** rate-limits after a big batch — re-run in a few minutes.
- **SKiDL reports pin Y inverted** vs KiCad (math y-up vs KiCad y-down); the
  layout generator handles KiCad's screen-coordinate rotations explicitly.
- **ESP32-S3-WROOM-1** does **not** break out GPIO33/34 (reserved by internal
  SPI); `circuit.py` uses GPIO16 for `EPD_PWR_EN`.
- The generator sets embedded part pins to `passive` because several EasyEDA
  symbols have incorrect electrical types. `verify_schematic.py` independently
  checks actual connectivity rather than relying on those types.
