# hardware/ — Schematic & PCB (KiCad, code-first)

The electrical design of **the-card**, captured in code and emitted as both a
KiCad **schematic** (`.kicad_sch`) and a **netlist** (`.net`). KiCad 10 is
installed; the schematic opens in eeschema and is ERC-clean (0 errors).

```
hardware/
├── parts.yaml              # parts/procurement manifest, kept in sync with circuit.py
├── design_metadata.py      # shared project name and physical hardware revision
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
├── scripts/normalize_libraries.py # reviewed corrections to fetched footprints
├── scripts/release_fabrication.py # checked Gerber/drill/BOM/placement release
├── scripts/export_design_review.py # portable CI schematic/PCB review exports
├── scripts/release_manifest.py # versioned release.json metadata + hashes
├── scripts/rasterize_svg.py # review PNGs from KiCad SVG plots
└── libraries/              # Reviewed 2D libs tracked; generated 3D models ignored
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

The verifier exports the complete KiCad schematic and compares both the peer
set of every component pin and every explicitly named net with the canonicalized
SKiDL circuit. The expected result is 75 components and 286 component pins with
identical connectivity across 42 canonical named nets. KiCad ERC has 0
violations.

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
routed and passes KiCad DRC with 0 violations and 0 unconnected items. Four
non-fabrication reference images are embedded beside the board in PCB Editor,
showing F.Cu, In1.Cu, In2.Cu, and B.Cu simultaneously without affecting plots.

## CI design review

For every CI run, `.github/workflows/ci.yml` publishes a short-lived
`design-review-<commit>` artifact after ERC and DRC pass. It contains the
schematic as PDF/SVG/PNG, a thumbnail, a multipage PCB PDF, and front, inner,
and mirrored back PCB PNGs. These files make schematic and layout changes easy
to inspect without KiCad; they are previews from one commit, not approved
fabrication outputs. The separate `kicad-reports` artifact retains the ERC and
DRC JSON reports, including reports from failed runs when available.

Run the manual `Hardware output` workflow when a complete candidate handoff is
needed. It rebuilds all release gates in the pinned KiCad environment and
uploads the fabrication, preview, assembly, reports, manifest, and checksums as
one 30-day Actions artifact. The workflow does not publish a GitHub Release or
mark the physical approval gates complete.

Build a manufacturing handoff into a new directory after generation:

```bash
uv run python scripts/release_fabrication.py \
  --release-version 0.1.0 \
  --hardware-revision A \
  --output ../outputs/the-card-hardware-v0.1.0
```

The physical `--hardware-revision` must match `HARDWARE_REVISION` in
`design_metadata.py`, which is rendered into both KiCad title blocks and the PCB
silkscreen. When manufactured bare boards must be distinguished, update that
source value and regenerate the schematic and PCB before building the matching
release. The semantic `--release-version` identifies an artifact handoff and
can advance for corrected exports, sourcing data, documentation, or release
tooling without renaming an unchanged PCB revision.

The release command refuses to overwrite an existing directory or use a dirty
worktree. It runs the connectivity and canonical-net-name verifier, then
requires a clean full DRC, schematic parity check, and ERC. The output tree is:

```text
fabrication/       # Gerbers, PTH/NPTH drills, notes, fabrication-only ZIP
preview/           # schematic/PCB PDFs and PNGs, layer/drill plots, preview ZIP
assembly/
├── canonical/     # normalized BOM/placement CSV+JSON and assembly drawings
└── jlcpcb/        # upload-ready BOM and position CSVs
reports/           # ERC, DRC/parity, and drill reports
release.json       # release identity, provenance, validation, pending approval
SHA256SUMS         # hashes for every artifact and release.json
```

Pass `--include-3d` only when all ignored supplier 3D models referenced by the
board are present and reviewed. Without it, the release remains complete for
fabrication and assembly and uses 2D previews generated from tracked design
files. The internal assembly BOM reports unresolved sourcing explicitly; a
clean board does not imply that every row is ready for a turnkey PCBA order. See
[`FABRICATION.md`](FABRICATION.md) before sending any files to a board house.

`assembly/jlcpcb/bom.csv` follows JLC's eight-column
`Comment, Description, Designator, Footprint, LibRef, Pins, Quantity, JLCPCB Part #`
format. Exact LCSC/JLC codes are written to `JLCPCB Part #` when assigned.
`assembly/jlcpcb/positions.csv` is the matching millimetre CPL with
`Designator, Mid X, Mid Y, Rotation, Layer` and normalized `Top`/`Bottom`
layer names.

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

`parts.yaml` holds procurement and part data. Its `lcsc_parts` section drives
EasyEDA library fetching, while `assembly_parts` records exact BOM selections
that reuse existing project or KiCad symbols and footprints. An
`assembly_parts` entry with the same reference as an `lcsc_parts` entry
overrides only the procurement selection, allowing a verified pin-compatible
replacement to keep the existing symbol and footprint. `fetch_libs.sh`
builds the two KiCad libraries, while `circuit.py` defines electrical
connectivity and emits `the-card.net`. The layout generator imports that circuit
and changes only its presentation: one A2 page containing Power/USB, MCU,
NFC/sensors, e-paper, and UI
regions. For an electrical change, update `circuit.py`, regenerate the netlist and
schematic, then run `verify_schematic.py` before accepting the result. See
[`FABRICATION.md`](FABRICATION.md) for stackup, ordering, and assembly checks.

Every resistor and capacitor also receives hidden `Related To` and `Function`
properties from `circuit.py`. The single-page schematic shows compact functional
callouts, while KiCad properties and the internal assembly BOM retain the exact
per-reference annotations without crowding the drawing. The layout keeps support
passives beside their related blocks and emits explicit dots at true wire
junctions; visually crossing wires without a dot are not connected.

## Verification status (done)

The originally flagged sections were checked against datasheets (see
`../PROGRESS.md` §7 and the full pinout cross-check). The bare panel's required
SSD1680 booster, 25 V pump capacitors, and 50 V rail bypass network are now
present on the host PCB. Residual
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

The DW01A/HXY 8205A protection stage has been checked against both datasheets:
R9=100 Ω, R10=1 kΩ, DOUT drives G1 on the cell-negative side, and COUT drives
G2 on the pack-negative side.

## Gotchas

- **easyeda2kicad 1.0.1:** `--output` must be **absolute** with
  `--project-relative` (relative paths crash). `fetch_libs.sh` handles this.
- **EasyEDA API 403:** rate-limits after a big batch — re-run in a few minutes.
- **SKiDL reports pin Y inverted** vs KiCad (math y-up vs KiCad y-down); the
  layout generator handles KiCad's screen-coordinate rotations explicitly.
- **ESP32-S3-WROOM-1-N16R8** uses GPIO33–37 for its Octal PSRAM;
  `circuit.py` leaves GPIO35–37 unconnected and uses GPIO16 for `EPD_PWR_EN`.
- The generator sets embedded part pins to `passive` because several EasyEDA
  symbols have incorrect electrical types. `verify_schematic.py` independently
  checks actual connectivity rather than relying on those types.
