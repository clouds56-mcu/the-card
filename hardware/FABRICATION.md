# Fabrication and first-assembly notes

This file is the handoff checklist for the first prototype. The KiCad design is
the source of truth; manufacturer settings must not silently change its layer
order or finished thickness.

## PCB order

- Four copper layers, 0.80 mm finished thickness, FR-4.
- Layer use: F.Cu signals/GND pour; In1.Cu primary GND; In2.Cu primary +3V3 and
  longer signals; B.Cu signals/GND pour.
- Use the board house's 0.8 mm four-layer stackup with approximately 0.10 mm
  prepreg between F.Cu and In1.Cu (JLCPCB's 3313-family option is the reference).
- Outer copper 1 oz and inner copper 0.5 oz.
- Specify 90 Ω differential impedance for `USB_DP`/`USB_DM`, referenced from
  F.Cu to the continuous In1.Cu ground plane. Confirm the final trace width and
  spacing in the selected board house's current calculator before ordering; do
  not substitute the thicker 7628 outer dielectric without recalculation.
- The board rules are 0.15 mm minimum track, 0.20 mm default clearance, and
  0.50/0.25 mm minimum via/drill. The FPC and USB net classes intentionally use
  local 0.10/0.15 mm clearances.
- ENIG is preferred for the 0.5 mm-pitch FPC connector and 0402 parts because it
  is flatter than HASL. Use green solder mask for the lowest-risk first build.

The board currently uses the ESP32-S3 full-speed USB interface. The
length-matched pair and uninterrupted In1.Cu reference remain required even
though it is not the 480 Mb/s high-speed USB mode.

## Before assembly

1. Print a 1:1 board plot and place the actual display FPC over J2. Confirm that
   panel pin 1 reaches the `J2 PIN 1` end without twisting the cable and that the
   exposed contacts face the connector's bottom contacts after folding.
2. Identify the actual battery connector with a multimeter. J3 pin 1 must be
   cell positive (`BAT+`); J3 pin 2 must be cell negative (`BAT-`/`BAT_NEG`).
3. Confirm the cell is a bare, unprotected 1S Li-ion/LiPo if the on-board
   DW01A/8205A protection is populated. A protected pack is electrically safe
   but duplicates cut-off circuitry and can complicate recovery behavior.
4. Inspect U8 orientation and verify continuity before connecting a cell:
   S1 side to `BAT_NEG`, S2 side to system GND, and the common drains internal.

## First power-up

1. Leave the battery disconnected. Power from a current-limited 5 V USB supply
   and confirm VBUS and +3V3 at TP3/TP4.
2. Connect a current-limited cell simulator or protected test cell with the
   USB supply removed. Confirm polarity at TP1/TP2 before connecting it.
3. Confirm charge current and TP4056 temperature before a long charge test.
4. Bring up the display only after +3V3 and the switched `EPD_VCI` rail are
   correct. Check the e-paper high-voltage rails with an appropriate probe.

## Release gate

Regenerate the schematic and PCB, then require all of the following from the
same committed design: connectivity verifier passes, KiCad ERC has zero
violations, KiCad DRC has zero violations, zero unconnected items, and zero
schematic parity issues, and the Gerber/drill preview matches the
53.98 x 85.60 mm outline.

The physical hardware revision and release version identify different things:

- `--hardware-revision A` identifies the fabricated PCB design and must match
  both the revision marked on the board and the PCB title-block revision carried
  into the Gerber job. When the bare-board design requires a new identity, update
  `HARDWARE_REVISION` in `design_metadata.py`, regenerate the schematic and PCB,
  and then pass that same revision to the release command.
- `--release-version 0.1.0` identifies one semantic-versioned artifact handoff.
  It may advance when the same hardware revision receives corrected exports,
  sourcing data, documentation, or release tooling.

Do not use successive release versions as substitute PCB revisions, and do not
advance the hardware revision merely because the handoff was regenerated.

Build the handoff into a new directory from `hardware/`:

```bash
uv run python scripts/release_fabrication.py \
  --release-version 0.1.0 \
  --hardware-revision A \
  --output ../outputs/the-card-hardware-v0.1.0
```

The command refuses to overwrite an existing output directory or release from a
dirty worktree. By default it creates 2D review material from the tracked design
without depending on the ignored supplier 3D-model directory. Add
`--include-3d` only when every model referenced by the board is available and
has been reviewed; this adds `preview/3d/` renders but does not change the
fabrication files.

The generated handoff is organized by audience:

```text
the-card-hardware-v0.1.0/
├── fabrication/
│   ├── gerbers/                       # production Gerbers
│   ├── drill/                         # separate PTH/NPTH Excellon files
│   ├── fabrication-notes.md           # stackup and ordering cautions
│   └── the-card-hardware-v0.1.0-fabrication.zip
├── preview/
│   ├── schematic.pdf + schematic.svg + schematic.png
│   ├── schematic-thumbnail.png
│   ├── pcb.pdf + pcb-front.png + two inner PNGs + pcb-back.png
│   ├── schematic/ + pcb/ + layers/ + drill/
│   ├── 3d/                            # only with --include-3d
│   └── the-card-hardware-v0.1.0-preview.zip
├── assembly/
│   ├── canonical/                     # normalized CSV/JSON + assembly drawings
│   ├── jlcpcb/                        # upload-ready BOM and position CSVs
│   └── the-card-hardware-v0.1.0-assembly.zip
├── reports/                           # ERC, DRC/parity, and drill reports
├── release.json                       # versioned manifest and provenance
└── SHA256SUMS                         # hashes every published file above
```

`fabrication/the-card-hardware-v0.1.0-fabrication.zip` contains only the
Gerbers and separate PTH/NPTH drill files intended for the board house. The
assembly data, reports, checksums, manifest, and review material remain outside
that ZIP. Do not upload the whole release directory, preview archive, or
assembly archive as the PCB fabrication archive. `release.json` deliberately
records the physical approval state as pending; passing automated gates does
not complete the physical checks below.

The release includes the detailed internal sourcing BOM plus the upload-ready
`assembly/jlcpcb/bom.csv` and `assembly/jlcpcb/positions.csv` pair. The
normalized, board-house-independent records and printable front/back assembly
drawings are kept under `assembly/canonical/`.
The JLC BOM follows the requested eight-column format and assigns exact
LCSC/JLCPCB codes in `JLCPCB Part #` to every board-placed electrical component
except J2, the intentionally distributor-sourced Hirose FPC connector. The JLC
position file uses millimetres, `Top`/`Bottom` layer names, and KiCad's exported
counter-clockwise rotations. Recheck stock, lifecycle status, package, and
assembly-side rotation against the generated position file before placing an
order; a closed BOM is not a substitute for the board house's live
manufacturability review.
