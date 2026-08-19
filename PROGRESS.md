# Progress — the-card

> Living status log for the ESP32-S3 e-paper smart badge. Last updated 2026-08-19.

## Status

🟢 **Design v0.2.0 single-page schematic and routed four-layer PCB source generated
   (KiCad 10, 78 parts).** The revision adds the mandatory NFC GPO pull-up, moves
   its interrupt off a strap pin, and replaces the provisional antenna with a
   tunable nine-turn coil in an all-layer RF quiet area. Automated ERC/DRC and
   connectivity checks are release gates; antenna resonance and range remain
   mandatory measurements on the first assembled board. The earlier v0.1.0
   draft remains available through Git history, not as a fabrication download.

---

## Completed

### 1. Product definition
ESP32-S3 based **DIY / learning smart badge**: e-paper wallpaper, Bluetooth, NFC,
watch-style buttons, on-board sensors, lanyard form factor. Open-source, MIT.

### 2. Documentation baseline (English)
- `README.md` — project brief + key takeaways
- `docs/architecture.md` — block diagram, subsystem design, **GPIO pin map**
- `docs/bom.md` — full BOM (LCSC #s / prices) + landed-cost analysis
- `docs/power-budget.md` — state-based power model + battery-life scenarios

Headline numbers: component BOM ~$21.5 (@100), landed ~$28/unit. The corrected
datasheet-based daily-use model is about 5.4 months theoretical on a 1000 mAh
cell, with 4–5 months used only as a planning range until v0.2.0 is measured.

### 3. Repository
Local git repo, MIT license, `main` branch.

### 4. Toolchain (uv-managed, self-contained)
`skidl` (Python netlist) + `easyeda2kicad` (LCSC → KiCad libs). Web search via
Exa (API key in `~/.pi/web-search.json`). No KiCad GUI needed to generate the
netlist — only for later PCB layout.

### 5. BOM validation (caught by running easyeda2kicad early)
6 wrong/stale LCSC numbers found and fixed:

| Part | Was | Now |
|---|---|---|
| LSM6DSO | C967483 | C2655100 |
| USBLC6-2SC6 | C7936 | C7519 |
| DW01A | C142001 | C18164398 |
| FS8205A | C32253 | C16052 |
| WS2812B-Mini | C5275773 | C527089 |
| E-ink FPC connector | C262682 / C6081230 | FH12-24S-0.5SH(55), distributor |

Also caught: **ESP32-S3-WROOM-1 does not break out GPIO33/34**, and the selected
N16R8 variant also reserves GPIO35–37 for Octal PSRAM. `EPD_PWR_EN` therefore
uses GPIO16.

### 6. Schematic in code
`hardware/circuit.py` captures the full electrical design:
ESP32-S3 MCU · USB-C + ESD · TP4056 charger · DW01A + FS8205A protection ·
ME6211 LDO · MAX17048 fuel gauge · ST25DV04KC NFC · LSM6DSO IMU · SHT40 ·
WS2812 LED · 2× SI2301 power gates · 4× buttons · battery connector · e-ink FPC
connector and complete host-side SSD1680 boost network.

Power muxing: switchable AUX branch rail (Q1, status LED only) and a gated e-ink
VCI/booster input (Q2). The I²C sensors remain on +3V3 with the bus pullups to
avoid back-powering an unpowered device.

**Expected generated design: 78 components · 292 component pins · 43 canonical
named nets.** EN, IO0, battery,
3.3 V, and ground test points are included for first-board bring-up. Output:
`the-card.net` plus the generated single-page `the-card.kicad_sch`.

Reproducible pipeline: `parts.yaml → fetch_libs.sh → libraries/ → circuit.py → the-card.net`.

### 7. Datasheet verification (VERIFY items resolved)
Using Exa web search + the Good Display datasheet PDF:

- **DW01A + FS8205A** ✓ — pin mapping confirmed (EasyEDA `DOUT/VM/COUT` = HMSEMI
  `DO/CS/CO` = discharge / sense / charge). Found **3 missing required parts** and
  added them: R9 100 Ω (VCC←B+), R10 1 kΩ (VM←P-), C7 100 nF (VCC-VSS). Gate
  assignment DOUT→G1 / COUT→G2 and S1=B- / S2=P- is verified.
- **ST25DV04KC** ✓ — SO-8 pinout matches the symbol. Its GPO is open-drain, so
  Design v0.2.0 adds mandatory 10 kΩ pull-up R17 and connects `NFC_IRQ` to RTC-capable,
  non-strapping GPIO21 instead of GPIO3. The 28.5 pF internal tuning capacitance
  is modeled with distinct `NFC_AC0`/`NFC_AC1` nets, etched-coil model L2, and a
  DNP 0–22 pF C0G/NP0 tuning footprint C29. The SO-8 device has no LPD pin and is
  specified at 76 µA typical / 100 µA maximum static standby at 3.3 V (up to
  85 °C), not the previously assumed 1 µA.
- **GDEY029T94** ✓ — the assumed 8-signal pinout was **wrong**; the real 24-pin
  FFC brings out raw SSD1680 pins. Rewired: SPI on pins 9–14, VCI/VDDIO/VSS on
  15–17, BS1=GND (4-wire SPI), and intentionally unused pins marked NC. The
  panel-specific reference design confirms that the 47 µH boost stage, 30 V
  MOSFET/diodes, pump capacitors, and HV rail bypass capacitors are host-side;
  all are now included.

---

## Components & part numbers (authoritative: `hardware/parts.yaml`)

### Actives / ICs / connectors (LCSC)

| Ref | Part | LCSC | Role |
|---|---|---|---|
| U1 | ESP32-S3-WROOM-1-N16R8 | C2913202 | MCU (WiFi+BLE, 16 MB Flash, 8 MB Octal PSRAM) |
| U2 | ST25DV04KC-IE8S3 | C5221752 | NFC dynamic tag with GPO wake |
| U3 | LSM6DSOTR | C2655100 | 6-axis IMU |
| U4 | SHT40-BD1B-R2 | C7461849 | Temp / Humidity |
| U5 | MAX17048G+T10 | C2682616 | Li-ion fuel gauge (ModelGauge) |
| U6 | TP4056 | C382139 | Li-ion charger, configured for ~500 mA |
| U7 | DW01A | C18164398 | Battery protection IC |
| U8 | FS8205A | C16052 | Dual N-MOSFET (protection) |
| U9 | ME6211C33M5G | C82942 | LDO 3.3 V / 500 mA |
| U10 | USBLC6-2SC6 | C7519 | USB ESD protection |
| Q1, Q2 | SI2301 | C10487 | P-MOSFET ×2 (AUX rail + e-ink VCI gates) |
| Q3 | SI1308EDL-T1-GE3 | C469327 | 30 V N-MOSFET for e-paper boost stage |
| D1 | WS2812B-Mini | C527089 | RGB status LED |
| D2–D4 | LMBR0530T1G | C18863 | 30 V / 500 mA e-paper Schottky diodes |
| J1 | TYPE-C-31-M-12 | C165948 | USB-C receptacle |
| J3 | JST S2B-PH-SM4-TB(LF)(SN) | C295747 | 1S battery connector, right-angle SMT |
| SW1–4 | TS-1187A | C318884 | Tactile button ×4 |
| J2 | FH12-24S-0.5SH(55) | distributor | E-ink panel FPC (24 sig + 2 mount) |

### Display (not LCSC — distributor)
- **GDEY029T94** — 2.9" e-paper 296×128, SSD1680 (Good Display / buy-lcd / Waveshare)

### Assembly passives (exact LCSC/JLCPCB picks)

| Part | LCSC | Used for |
|---|---|---|
| 100 nF 16 V X7R 0402 (CL05B104KO5NNNC) | C1525 | C1/C4/C7/C10–C12/C14–C19 |
| 10 µF 10 V X5R 0603 (CL10A106KP8NNNC) | C19702 | C2/C5/C6/C13 |
| 1 µF 50 V X5R 0603 (CL10A105KB8NNNC) | C15849 | C3/C8/C9 |
| 4.7 µF 25 V X5R 0805 (CL21A475KAQNNNE) | C1779 | C20/C21 |
| 1 µF 50 V X7R 0805 (CL21B105KBFNNNE) | C28323 | C22–C28 |
| 0402 resistors, value-specific MPNs | C11702/C25076/C25744/C25774/C25879/C25900/C25905/C26083 | R1–R15, R17 |
| 2.2 Ω 0.75 W pulse-rated 1206 (CRCW12062R20FKEAHP) | C1854860 | R16 |

C29 is a DNP 0–22 pF C0G/NP0 tuning footprint and L2 represents copper etched into
the PCB; neither is an initially populated assembly item.

Battery (3.7 V 1000 mAh, 603048) and lanyard hardware are sourced from
distributors (no LCSC number).

---

## ✅ Datasheet verification (done) — full part cross-check

Beyond the three flagged sections (§7), every active part's pinout/connections
were cross-checked against the archived datasheets using pypdf text extraction:
USBLC6-2 (D±/VBUS/GND), TP4056 (TEMP/CE/PROG), MAX17048 (CTG/QSTRT/CELL),
LSM6DSO (CS=high→I²C, addr), ME6211 (CE active-high), SI2301 (1=G/2=S/3=D),
SHT40 (1=SDA/2=SCL/3=VDD/4=VSS). **No wiring errors found.**

The selected ME6211C33 is specified at 60 µA typical supply current while
enabled. Its 0.1 µA standby figure applies only with CE low; this design ties CE
to `+BAT`, so the power model uses 60 µA.

TP4056 RPROG is 2.2 kΩ, limiting charge current to approximately 500 mA. This is
a more conservative first-board setting for the planned 1000 mAh cell and gives
the linear charger more thermal margin.

Remaining items are first-prototype validation risks, not CAD blockers:

- **DW01A+FS8205A** — topology and routing are complete; verify U8 orientation
  and negative-path continuity before connecting a cell.
- **ST25DV04KC antenna** — design v0.2.0 uses a nine-turn, 0.20 mm F.Cu spiral in an
  all-copper-layer quiet area. The ST square-equivalent heuristic gives about
  4.52 µH, while an NXP rectangular-coil cross-check brackets about
  3.19–3.98 µH. That lower bracket implies roughly 6.1–14.7 pF nominal added
  capacitance before antenna stray capacitance and assembly loading. Keep C29
  DNP initially; measure assembled resonance/Q, then select the smallest
  suitable C0G/NP0 value and test read/write range with multiple phones in the
  final display/battery enclosure. Treat a required value above about 15–18 pF,
  poor Q, or inadequate range as an antenna-respin signal.
- **FH12 FPC orientation** — verify the physical panel FPC reaches the
  bottom-contact connector without twisting before ordering.
- **JST-PH battery polarity** — confirm the selected cell's cable orientation.

---

## Next steps (roadmap)

- [x] Confirm the 3 VERIFY items against datasheets
- [x] Generate and verify a single-page `.kicad_sch` from `circuit.py`
- [x] Generate, route, and verify the four-layer PCB layout
- [ ] Order and bring up the first prototype
- [ ] ESP-IDF firmware scaffold: display / button / NFC / BLE modules + deep-sleep wake flow
- [ ] Mechanical: case + lanyard CAD
