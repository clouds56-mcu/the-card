# Schematic drawing guide (KiCad eeschema)

How to capture the-card's schematic in KiCad eeschema, page by page. `circuit.py`
is the electrical source of truth — this guide just sequences the drawing so it's
fast and cross-checks the netlist.

## Setup

1. Install KiCad: `brew install --cask kicad`
2. Open `hardware/` as a KiCad project (or create a new project there). The
   `sym-lib-table` / `fp-lib-table` already register our two libraries:
   - **the-card** — all actives/connectors (ESP32 module, ST25DV, …)
   - **passives** — R/C templates + the e-ink FPC connector
3. Place symbols from those libs; assign footprints from `the-card.pretty`.
   Values for passives match `circuit.py` (e.g. PROG = 1.2 k, I²C pullups = 4.7 k).

Use a hierarchical sheet per block below (5 sheets) — keeps each page readable.

## Power rails (global labels, reused on every sheet)

`+3V3` (always-on system rail) · `+BAT` (cell+) · `VBUS` (USB 5 V) ·
`AUX_3V3` (switched sensor/LED rail via Q1) · `EPD_VDD` (switched e-ink rail via Q2) ·
`GND` · `BAT_NEG` (cell-, ⚠️ not GND).

## Sheet 1 — Power & Charging

Parts: J1 (USB-C) · U10 (USBLC6-2) · U6 (TP4056) · U7 (DW01A) · U8 (FS8205A) ·
U9 (ME6211 LDO) · U5 (MAX17048) · Q1, Q2 (SI2301) · power passives.

- J1: VBUS→`VBUS`, GND+EH→GND, **CC1/CC2 each 5.1 k to GND**, DN1/DN2 and DP1/DP2
  into U10. SBU1/SBU2 NC.
- U10 (USBLC6-2SC6, SOT-23-6): I/O1 (pin1,6)=D- path, I/O2 (pin3,4)=D+ path,
  pin2=GND, pin5=VBUS. → `USB_DM`/`USB_DP` to MCU.
- U6 (TP4056): VCC←VBUS, BAT→`+BAT`, PROG→1.2 k→GND, TEMP→GND (no NTC), CE→VBUS,
  ~CHRG→10 k pullup to +3V3 → net `~CHRG` (to MCU). Add 10 µF on VBUS and on +BAT.
- U7+U8 protection: VDD(pin5)←470 Ω←+BAT, VSS(pin6)→`BAT_NEG`, VM(pin2)←2 k←GND,
  COUT(pin3)→FS8205A G1, DOUT(pin1)→G2; 100 nF VDD-VSS. FS8205A: S1→BAT_NEG,
  S2→GND, D12=floating internal node.
- U9 (ME6211): VIN←+BAT, VOUT→`+3V3`, CE←+BAT (always on), 1 µF in/out.
- U5 (MAX17048): CELL+VDD←+BAT, CTG+QSTRT→GND, SCL/SDA→I²C, ~ALRT NC, 100 nF on VDD.
- Q1 (AUX rail): S→+3V3, D→`AUX_3V3`, G←net `PWR_AUX` + 10 k pullup to +3V3.
- Q2 (e-ink rail): S→+3V3, D→`EPD_VDD`, G←net `EPD_PWR_EN` + 10 k pullup.

## Sheet 2 — MCU (ESP32-S3-WROOM-1, U1)

- 3V3→`+3V3`; 3× GND→GND; 100 nF + 10 µF on 3V3.
- EN: 10 k pullup to +3V3 + 1 µF to GND (no reset button).
- IO0: 10 k pullup to +3V3 (boot). **IO33/IO34 are not on the module — don't use.**
- USB: IO19=`USB_DM`, IO20=`USB_DP` (from sheet 1).
- E-ink SPI: IO9=MOSI, IO10=SCLK, IO11=BUSY, IO12=CS, IO13=DC, IO14=RST.
- I²C: IO8=SCL, IO18=SDA (+ 4.7 k pullups to +3V3 on sheet 4).
- IRQs/status: IO3=`NFC_IRQ`, IO2=`IMU_INT`, IO15=`~CHRG`.
- Buttons: IO4=UP, IO5=DOWN, IO6=SEL, IO7=MENU.
- Controls: IO47=`PWR_AUX`, IO16=`EPD_PWR_EN`, IO48=`LED_DIN`, IO21=`MOTOR_PWM`.
- Vbat divider: IO1 ← midpoint of 1 M / 300 k from +BAT to GND (+ 100 nF).
- Spare (IO35–42, IO45/46, RXD0/TXD0): leave on an expansion header.

## Sheet 3 — E-ink panel (J2, 24-pin FPC)

GDEY029T94 pinout (verified, Good Display §5). Wire from the J2 connector:
- 8 (BS1)→GND (4-wire SPI) · 15+16 (VDDIO+VCI)→`EPD_VDD` · 17 (VSS)→GND · 18 (VDD)→1 µF→GND
- 9=BUSY · 10=RES# · 11=D/C# · 12=CS# · 13=SCL · 14=SDA(MOSI)  ← from MCU SPI nets
- 2,3 (GDR/RESE) & 5,20–24 (VSH/VGH/VSL/VGL/VCOM): panel-side booster → leave as
  named nets (confirm vs DESPI ref at layout). 1,4=NC · 19=VPP(test) · 25,26=shell→GND.

## Sheet 4 — NFC + IMU + Temp/Humidity (I²C bus)

- I²C pullups: 4.7 k on `I2C_SCL` and `I2C_SDA` to +3V3.
- U2 (ST25DV04KC): VCC→+3V3, VSS→GND, SCL/SDA→I²C, GPO→`NFC_IRQ`, V_EH→testpoint,
  AC0/AC1→`NFC_ANT_A/B` (PCB trace antenna; internal 28.5 pF, **no external cap**). 100 nF on VCC.
- U3 (LSM6DSO): VDD+VDDIO→`AUX_3V3`, GND→GND, SCL/SDA→I²C, INT1→`IMU_INT`,
  CS→`AUX_3V3` (=high→I²C mode), SDO/SA0→GND (addr 0x6A); 100 nF + 10 µF on AUX.
- U4 (SHT40): VDD→`AUX_3V3`, VSS→GND, EP→GND, SCL/SDA→I²C; 100 nF on VDD.

## Sheet 5 — UI: buttons + LED

- SW1–4 (TS-1187A): pin A→`BTN_UP/DOWN/SEL/MENU`, pin C→GND, 100 nF across each.
- D1 (WS2812B-Mini): VDD→`AUX_3V3`, DIN←`LED_DIN`, VSS→GND, 100 nF on VDD.

## After drawing

- Run **Inspect → Electrical Rules Checker** in eeschema; expect the same
  "unconnected spare GPIO/NC pin" warnings as `circuit.py`'s ERC (0 errors).
- Then **Tools → Update PCB from Schematic** (or import `the-card.net`) to start layout.
