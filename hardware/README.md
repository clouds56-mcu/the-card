# hardware/ — Schematic & PCB (KiCad, code-first)

The electrical design of **the-card**, captured in code and emitted as both a
KiCad **schematic** (`.kicad_sch`) and a **netlist** (`.net`). KiCad 10 is
installed; the schematic opens in eeschema and is ERC-clean (0 errors).

```
hardware/
├── parts.yaml              # parts/procurement manifest, kept in sync with circuit.py
├── pyproject.toml + uv.lock# uv project: skidl + easyeda2kicad (+ pypdf dev)
├── circuit.py              # the design in SKiDL (connectivity) -> the-card.net
├── gen_hierarchical_schematic.py # current deterministic A2 layout generator
├── gen_pcb.py              # deterministic placement, routing, planes, and keepouts
├── pcb_router.py           # board-specific fanout and deterministic maze routing
├── verify_schematic.py     # compare every KiCad pin's peers with circuit.py
├── gen_schematic.py        # legacy flat-layout generator; not used currently
├── the-card.kicad_pro      # KiCad 10 project
├── the-card.kicad_sch      # GENERATED single-page A2 schematic
├── the-card.kicad_pcb      # GENERATED four-layer PCB layout
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
kicad-cli sch erc --severity-all --output /tmp/erc.json --format json the-card.kicad_sch
```

The verifier exports the complete KiCad schematic and compares the peer set of
every component pin with the canonicalized SKiDL circuit. The expected result is
75 components and 286 component pins with identical connectivity. KiCad ERC has
0 violations.

Generate the PCB layout with KiCad's bundled Python:

```bash
/Applications/KiCad/KiCad.app/Contents/Frameworks/\
Python.framework/Versions/3.9/bin/python3 gen_pcb.py
kicad-cli pcb drc --output /tmp/pcb-drc.json --format json the-card.kicad_pcb
```

The board is a portrait ID-1 outline (53.98 × 85.60 mm), four layers, and
0.8 mm thick. The display and controls are on the front; the ESP32, battery,
sensors, power circuitry, USB-C, and display connector are on the rear. The
generator encodes display, 603048 battery, ESP32 antenna, and NFC plane
keepouts. F.Cu and B.Cu carry local signals over ground pours, In1.Cu is the
primary ground plane, and In2.Cu is the primary 3V3 plane plus longer signal
routes. Ground stitching ties the pours together. The generated board is fully
routed and passes KiCad DRC with 0 violations and 0 unconnected items.

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
schematic, then run `verify_schematic.py` before accepting the result. See
[`FABRICATION.md`](FABRICATION.md) for stackup, ordering, and assembly checks.

## Verification status (done)

The originally flagged sections were checked against datasheets (see
`../PROGRESS.md` §7 and the full pinout cross-check). The bare panel's required
SSD1680 booster and 25 V bypass network are now present on the host PCB. Residual
PCB-layout items are:

- **ST25DV04KC antenna** — the routed two-turn loop uses the available front-left
  strip and is connectivity/DRC complete. The approved placement constrains its
  area and keeps rear-side sensors and ground beneath part of the loop, so tune
  resonance and verify read range on the first prototype. A revised coil or
  matching network may be needed after measurement.
- **Display FPC** — J2 is now the verified single-row Hirose
  FH12-24S-0.5SH(55): 24 positions, 0.5 mm pitch, bottom contact, for a 0.30 mm
  FPC. The project footprint numbers its two hold-down tabs 25 and 26 so both
  are tied to ground by the schematic. Rear silkscreen marks pin 1; confirm the
  folded panel orientation with a paper or physical mock-up before ordering.
- **JST-PH battery polarity** — rear silkscreen marks `BAT+` and `BAT-`, but the
  selected pack's cable must still be verified before plugging it in.

The DW01A/FS8205A protection stage has been checked against both datasheets:
R9=100 Ω, R10=1 kΩ, DOUT drives G1 on the cell-negative side, and COUT drives
G2 on the pack-negative side.

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
