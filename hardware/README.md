# hardware/ — Schematic & PCB (KiCad, code-first)

The electrical design of **the-card**, captured in code and emitted as both a
KiCad **schematic** (`.kicad_sch`) and a **netlist** (`.net`). KiCad 10 is
installed; the schematic opens in eeschema and is ERC-clean (0 errors).

```
hardware/
├── parts.yaml              # SOURCE OF TRUTH: parts, LCSC#s, nets, passives
├── pyproject.toml + uv.lock# uv project: skidl + easyeda2kicad (+ pypdf dev)
├── circuit.py              # the design in SKiDL (connectivity) -> the-card.net
├── gen_schematic.py        # circuit.py + libs -> the-card.kicad_sch (placed)
├── the-card.kicad_pro      # KiCad 10 project
├── the-card.kicad_sch      # GENERATED schematic (53 parts, ERC 0 errors)
├── sym-lib-table / fp-lib-table  # register our the-card + passives libraries
├── SCHEMATIC-GUIDE.md      # per-sheet drawing notes (if hand-tidying in eeschema)
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

## Generate the schematic + netlist

```bash
uv run python circuit.py        # SKiDL: build circuit, ERC, write the-card.net
uv run python gen_schematic.py  # place parts + net-label every pin -> the-card.kicad_sch
kicad-cli sch erc the-card.kicad_sch -o /tmp/erc.txt   # 0 errors expected
```

Open the schematic:
```bash
/Applications/KiCad/KiCad.app/Contents/MacOS/eeschema the-card.kicad_sch
```

> `gen_schematic.py` **overwrites** `the-card.kicad_sch`. Run it to regenerate
> from `circuit.py`; once you start hand-editing in eeschema, stop regenerating.
> v3.1 uses **hand-crafted placement** (signal-flow layout: power top-left, MCU
> centre, sensors left, e-ink/LED below, buttons bottom) + real KiCad power symbols
> + PWR_FLAGs + net labels for shared buses (I²C). Point-to-point signal nets
> (SPI bus, buttons, USB, LED, etc.) that land close become direct L-wires.
> ERC: 0 errors, 13 wires. Tidy wire-label overlaps in eeschema for final polish.

## How it fits together

`parts.yaml` is the single source of truth. `fetch_libs.sh` builds the two KiCad
libraries; `circuit.py` wires the circuit (ERC-verified, datasheet-cross-checked);
`gen_schematic.py` places the parts and emits the `.kicad_sch`. Change the design
→ edit `circuit.py` → re-run both generators.

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
- **skidl reports pin Y inverted** vs KiCad (math y-up vs KiCad y-down);
  `gen_schematic.py` negates Y when placing labels.
- **ESP32-S3-WROOM-1** does **not** break out GPIO33/34 (reserved by internal
  SPI); `circuit.py` uses GPIO16 for `EPD_PWR_EN`.
- `gen_schematic.py` sets all embedded pins to `passive` type (EasyEDA mistypes
  them) so KiCad ERC is clean; real connectivity is verified in `circuit.py`.
