# Single-page schematic layout guide (KiCad eeschema)

The schematic is generated as a hand-placed A2 landscape page. `circuit.py`
remains the electrical source of truth; this guide documents the intended grouping
and signal flow for reviewing or adjusting the placement tables in
`gen_hierarchical_schematic.py`.

The Python source uses semantic passive names such as `R_prog` and `C_epd_vcom`
inside the placement tables. `circuit.py` maps those names to conventional KiCad
references (`R7`, `C28`, and so on) in the generated schematic.

## Setup

1. Install KiCad: `brew install --cask kicad`
2. Open `hardware/` as a KiCad project (or create a new project there). The
   `sym-lib-table` / `fp-lib-table` already register our two libraries:
   - **the-card** — all actives/connectors (ESP32 module, ST25DV, …)
   - **passives** — R/C templates + the e-ink FPC connector
3. Generate and verify the schematic from `hardware/`:

   ```bash
   uv run python gen_hierarchical_schematic.py
   uv run python verify_schematic.py
   ```

Five functional regions share one A2 sheet: Power/USB across the upper left,
NFC/sensors across the upper right, MCU in the center, UI along the lower left,
and e-paper along the lower right. Named labels replace long cross-page wires.

## Power rails (global labels, reused across regions)

`+3V3` (always-on system rail) · `+BAT` (cell+) · `VBUS` (USB 5 V) ·
`AUX_3V3` (switched LED rail via Q1) · `EPD_VCI` (switched e-ink rail via Q2) ·
`GND` · `BAT_NEG` (cell-, ⚠️ not GND).

## Region 1 — Power & Charging

Parts: J1 (USB-C) · U10 (USBLC6-2) · U6 (TP4056) · U7 (DW01A) · U8 (FS8205A) ·
U9 (ME6211 LDO) · U5 (MAX17048) · Q1, Q2 (SI2301) · J3 (battery) ·
TP1–TP4 · power passives.

- J1: VBUS→`VBUS`, GND+EH→GND, **CC1/CC2 each 5.1 k to GND**, DN1/DN2 and DP1/DP2
  into U10. SBU1/SBU2 NC.
- U10 (USBLC6-2SC6, SOT-23-6): I/O1 (pin1,6)=D- path, I/O2 (pin3,4)=D+ path,
  pin2=GND, pin5=VBUS. → `USB_DM`/`USB_DP` to MCU.
- U6 (TP4056): VCC←VBUS, BAT→`+BAT`, PROG→2.2 k→GND (~500 mA), TEMP→GND (no NTC), CE→VBUS,
  ~CHRG→10 k pullup to +3V3 → net `~CHRG` (to MCU). Add 10 µF on VBUS and on +BAT.
- U7+U8 protection: VDD(pin5)←100 Ω←+BAT, VSS(pin6)→`BAT_NEG`, VM(pin2)←1 k←GND,
  DOUT(pin1)→FS8205A G1, COUT(pin3)→G2; 100 nF VDD-VSS. FS8205A: S1→BAT_NEG,
  S2→GND, D12=floating internal node.
- U9 (ME6211): VIN←+BAT, VOUT→`+3V3`, CE←+BAT (always on), 1 µF in/out.
- U5 (MAX17048): CELL+VDD←+BAT, CTG+QSTRT→GND, SCL/SDA→I²C, ~ALRT NC, 100 nF on VDD.
- J3: pin 1→`+BAT`, pin 2→`BAT_NEG`. Confirm the actual battery cable polarity;
  JST-PH packs are not universally wired the same way.
- Q1 (AUX rail): S→+3V3, D→`AUX_3V3`, G←net `PWR_AUX` + 10 k pullup to +3V3.
- Q2 (e-ink rail): S→+3V3, D→`EPD_VCI`, G←net `EPD_PWR_EN` + 10 k pullup.
- TP1–TP4 expose `+BAT`, `BAT_NEG`, `+3V3`, and `GND` for bring-up.

## Region 2 — MCU (ESP32-S3-WROOM-1, U1)

- 3V3→`+3V3`; 3× GND→GND; 100 nF + 10 µF on 3V3.
- EN: 10 k pullup to +3V3 + 1 µF to GND; TP5 permits a temporary reset-to-GND jumper.
- IO0: 10 k pullup to +3V3; TP6 permits a temporary boot-to-GND jumper.
  **IO33/IO34 are not on the module, and N16R8 reserves IO35–37 for Octal
  PSRAM — don't use them.**
- USB: IO19=`USB_DM`, IO20=`USB_DP` (from the power region).
- E-ink SPI: IO9=MOSI, IO10=SCLK, IO11=BUSY, IO12=CS, IO13=DC, IO14=RST.
- I²C: IO8=SCL, IO18=SDA (+ 4.7 k pullups to +3V3 in the sensor region).
- IRQs/status: IO3=`NFC_IRQ`, IO2=`IMU_INT`, IO15=`~CHRG`.
- Buttons: IO4=UP, IO5=DOWN, IO6=SEL, IO7=MENU.
- Controls: IO47=`PWR_AUX`, IO16=`EPD_PWR_EN`, IO48=`LED_DIN`.
- Vbat divider: IO1 ← midpoint of 1 M / 300 k from +BAT to GND (+ 100 nF).
- Spare (IO21, IO38–42, IO45/46, RXD0/TXD0): left unconnected for future revisions.
  IO35–37 are reserved by the N16R8 module's Octal PSRAM.

## Region 3 — E-ink panel (J2, 24-pin FPC)

GDEY029T94 pinout and support circuit (verified against the Good Display reference
design). Wire from the J2 connector:

- 8 (BS1)→GND (4-wire SPI) · 15+16 (VDDIO+VCI)→`EPD_VCI` · 17 (VSS)→GND ·
  18 (VDD core)→1 µF/25 V→GND.
- 9=BUSY · 10=RES# · 11=D/C# · 12=CS# · 13=SCL · 14=SDA(MOSI)  ← from MCU SPI nets
- GDR/RESE drive Q3 (Si1304BDL) through the 47 µH boost network; use a 1 MΩ
  gate pulldown and 2.2 Ω RESE current-sense resistor.
- D2–D4 are MBR0530 Schottky diodes. The boost input and pump use 4.7 µF/25 V;
  VSH2, VSH1, VGH, VSL, VGL, and VCOM each use 1 µF/25 V to GND.
- 1, 4, 6, 7, and 19 are intentionally NC; 25 and 26 (shell)→GND.

## Region 4 — NFC + IMU + Temp/Humidity (I²C bus)

- I²C pullups: 4.7 k on `I2C_SCL` and `I2C_SDA` to +3V3.
- U2 (ST25DV04KC): VCC→+3V3, VSS→GND, SCL/SDA→I²C, GPO→`NFC_IRQ`, V_EH NC.
  AC0 and AC1 share `NFC_ANTENNA`, which the PCB turns into one continuous loop;
  the IC variant has internal tuning capacitance, so no external capacitor is fitted.
- U3 (LSM6DSO): VDD+VDDIO→`+3V3`, GND→GND, SCL/SDA→I²C, INT1→`IMU_INT`,
  CS→`+3V3` (=high→I²C mode), SDO/SA0→GND (addr 0x6A); 100 nF + 10 µF on +3V3.
- U4 (SHT40): VDD→`+3V3`, VSS→GND, exposed pad NC, SCL/SDA→I²C; 100 nF on VDD.

Keeping the sensors on the same always-on rail as the I²C pullups prevents the
bus from back-powering an unpowered sensor. `AUX_3V3` therefore powers only D1.

## Region 5 — UI: buttons + LED

- SW1–4 (TS-1187A): pin A→`BTN_UP/DOWN/SEL/MENU`, pin C→GND, 100 nF across each.
- D1 (WS2812B-Mini): VDD→`AUX_3V3`, DIN←`LED_DIN`, VSS→GND, 100 nF on VDD.

## After layout changes

- Regenerate from the script; do not maintain one-off generated-file edits.
- Run `verify_schematic.py`; expect 75 components and 286 pins with identical
  peer sets to `circuit.py`.
- Run **Inspect → Electrical Rules Checker** in eeschema. Expect 0 violations.
- Then **Tools → Update PCB from Schematic** (or import `the-card.net`) to start layout.
