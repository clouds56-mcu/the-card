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
   DW01A/FS8205A protection is populated. A protected pack is electrically safe
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
same revision: connectivity verifier passes, KiCad ERC has zero violations,
KiCad DRC has zero violations, zero unconnected items, and zero schematic parity
issues, and the Gerber/drill preview matches the 53.98 x 85.60 mm outline.

Build the handoff into a new directory from `hardware/`:

```bash
uv run python scripts/release_fabrication.py \
  --revision rev-a \
  --output ../outputs/the-card-rev-a
```

`the-card-rev-a-fabrication.zip` contains only the Gerbers and separate PTH/NPTH
drill files intended for the board house. Assembly CSVs, DRC/ERC reports,
checksums, manifests, 3D renders, and layer previews remain beside the ZIP for
review. Do not upload the whole release directory as a fabrication archive.

The generated assembly BOM is intentionally conservative. Rows without an
exact purchasable code are marked `needs_sourcing`; the current manifest assigns
LCSC codes to 18 of 69 placed components, identifies one distributor-sourced
connector, and leaves 50 passives or standard parts for exact sourcing. The PCB
files are fabrication-ready, but the BOM is not yet a one-click turnkey assembly
order.
