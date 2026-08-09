# Progress — the-card

> Living status log for the ESP32-S3 e-paper smart badge. Last updated 2026-08-09.

## Status

🟢 **Single-page schematic generated as a real `.kicad_sch` (KiCad 10, 75 parts,
   ERC 0 violations).** Connectivity is verified against the SKiDL circuit. The
   design is ready to move into PCB placement after the FPC footprint check.

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

Headline numbers: component BOM ~$21.5 (@100), landed ~$28/unit; daily-use battery
life ~6–9 months on a 1000 mAh cell.

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
| E-ink FPC connector | C262682 (16-pin) | C6081230 (24-pin) |

Also caught: **ESP32-S3-WROOM-1 does not break out GPIO33/34** (reserved by
internal SPI) → `EPD_PWR_EN` moved to GPIO16.

### 6. Schematic in code
`hardware/circuit.py` captures the full electrical design:
ESP32-S3 MCU · USB-C + ESD · TP4056 charger · DW01A + FS8205A protection ·
ME6211 LDO · MAX17048 fuel gauge · ST25DV04KC NFC · LSM6DSO IMU · SHT40 ·
WS2812 LED · 2× SI2301 power gates · 4× buttons · battery connector · e-ink FPC
connector and complete host-side SSD1680 boost network.

Power muxing: switchable AUX branch rail (Q1, status LED only) and a gated e-ink
VCI/booster input (Q2). The I²C sensors remain on +3V3 with the bus pullups to
avoid back-powering an unpowered device.

**ERC: 0 violations · 75 components · 286 component pins.** EN, IO0, battery,
3.3 V, and ground test points are included for first-board bring-up. Output:
`the-card.net` plus the generated single-page `the-card.kicad_sch`.

Reproducible pipeline: `parts.yaml → fetch_libs.sh → libraries/ → circuit.py → the-card.net`.

### 7. Datasheet verification (VERIFY items resolved)
Using Exa web search + the Good Display datasheet PDF:

- **DW01A + FS8205A** ✓ — pin mapping confirmed (EasyEDA `DOUT/VM/COUT` = HMSEMI
  `DO/CS/CO` = discharge / sense / charge). Found **3 missing required parts** and
  added them: R1 470Ω (VCC←B+), R2 2kΩ (VM←P-), C1 100nF (VCC-VSS). Gate
  assignment COUT→G1 / DOUT→G2 and S1=B- / S2=P- verified correct.
- **ST25DV04KC** ✓ — SO-8 pinout matches the symbol; **internal tuning cap
  28.5 pF** means the antenna connects directly to AC0/AC1 with **no external
  cap**. Only the PCB antenna geometry remains (a layout task).
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
| U1 | ESP32-S3-WROOM-1-N8R2 | C2913204 | MCU (WiFi+BLE, 8 MB Flash, 2 MB PSRAM) |
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
| Q3 | Si1304BDL | stock KiCad | 30 V N-MOSFET for e-paper boost stage |
| D1 | WS2812B-Mini | C527089 | RGB status LED |
| D2–D4 | MBR0530 | stock KiCad | 30 V / 500 mA e-paper Schottky diodes |
| J1 | TYPE-C-31-M-12 | C165948 | USB-C receptacle |
| J3 | JST-PH 2-pin horizontal | stock KiCad | 1S battery connector |
| SW1–4 | TS-1187A | C318884 | Tactile button ×4 |
| J2 | FPC 0.5-24P flip-lock | C6081230 | E-ink panel FPC (24 sig + 2 mount) |

### Display (not LCSC — distributor)
- **GDEY029T94** — 2.9" e-paper 296×128, SSD1680 (Good Display / buy-lcd / Waveshare)

### Passive templates (LCSC, symbol reused; value set in `circuit.py`)

| Part | LCSC | Used for |
|---|---|---|
| 0402 resistor (0402WGF1002TCE) | C25744 | all R (pullups/dividers/limit/DW01 R1/R2) |
| 0402 capacitor (CL05B104KO5NNNC) | C1525 | all 0402 decouple/filter (incl. DW01 C1) |
| 0603 capacitor (CL10A106KP8NNNC) | C19702 | all 0603 bulk (10 µF / e-ink VDD) |

Battery (3.7 V 1000 mAh, 603048) and lanyard hardware are sourced from
distributors (no LCSC number).

---

## ✅ Datasheet verification (done) — full part cross-check

Beyond the three flagged sections (§7), every active part's pinout/connections
were cross-checked against the archived datasheets using pypdf text extraction:
USBLC6-2 (D±/VBUS/GND), TP4056 (TEMP/CE/PROG), MAX17048 (CTG/QSTRT/CELL),
LSM6DSO (CS=high→I²C, addr), ME6211 (CE active-high), SI2301 (1=G/2=S/3=D),
SHT40 (1=SDA/2=SCL/3=VDD/4=VSS). **No wiring errors found.**

TP4056 RPROG is 2.2 kΩ, limiting charge current to approximately 500 mA. This is
a more conservative first-board setting for the planned 1000 mAh cell and gives
the linear charger more thermal margin.

Remaining items are layout refinements, not blockers:

- **DW01A+FS8205A** — topology confirmed; do a final eyeball of the Fortune
  FS8205A app circuit before routing the negative-path FETs.
- **ST25DV04KC antenna** — route the continuous 13.56 MHz PCB loop between AC0/AC1.
- **C6081230 FPC footprint** is *staggered* in EasyEDA — verify it fits the
  panel's flat 24-pin FFC, or pick a non-staggered alternative.
- **JST-PH battery polarity** — confirm the selected cell's cable orientation.

---

## Next steps (roadmap)

- [x] Confirm the 3 VERIFY items against datasheets
- [x] Generate and verify a single-page `.kicad_sch` from `circuit.py`
- [ ] Start PCB layout from `the-card.kicad_sch`
  (antenna keepout, FPC placement, lanyard CG, battery clearance)
- [ ] ESP-IDF firmware scaffold: display / button / NFC / BLE modules + deep-sleep wake flow
- [ ] Mechanical: case + lanyard CAD
