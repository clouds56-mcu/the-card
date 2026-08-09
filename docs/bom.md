# Bill of Materials & Cost Analysis

> Prices reflect **2026-08** LCSC / JLCPCB / Good Display market data. Unit prices are reference values — confirm live at order time.
> **Reference quantity: @100 units** (small-batch / DIY group buy); @1 (prototype) and @1k (production trend) also listed.

📌 Price columns show **line totals** (unit price × "Qty"), not unit prices.

---

## 1. Core BOM

| # | Category | Part | MPN | LCSC | Qty | @1 (USD) | @100 (USD) | @1k (USD) |
|---|---|---|---|---|---|---|---|---|
| 1 | MCU | WiFi+BLE module | ESP32-S3-WROOM-1-N8R2 | C2913204 | 1 | 5.08 | **4.03** | 3.84 |
| 2 | Display | 2.9" e-paper 296×128 SSD1680 | GDEY029T94 (Good Display) | distributor¹ | 1 | 7.60 | **7.00** | 5.50 |
| 3 | Display aux | FPC connector 24P 0.5 mm flip | FPC0.5-24P | C6081230 | 1 | 0.25 | 0.10 | 0.06 |
| 4 | NFC | Dynamic tag IC with GPO wake | ST25DV04KC-IE8S3 | C5221752 | 1 | 0.91 | **0.55** | 0.44 |
| 5 | IMU | 6-axis accel + gyro | LSM6DSOTR | C2655100 | 1 | 3.50 | **2.50** | 2.20 |
| 6 | Temp/Humidity | Digital T/RH | SHT40-BD1B-R2 | C7461849 | 1 | 1.93 | **1.32** | 1.21 |
| 7 | Fuel gauge | Li-ion ModelGauge | MAX17048G+T10 | C2682616 | 1 | 2.50 | **1.50** | 1.35 |
| 8 | Charger | Li-ion charger, configured for ~500 mA | TP4056 (TPOWER) | C382139 | 1 | 0.20 | **0.12** | 0.10 |
| 9 | Protection | Battery protection IC | DW01A | C18164398 | 1 | 0.10 | 0.06 | 0.05 |
| 10 | Protection | Dual N-MOSFET | FS8205A | C16052 | 1 | 0.12 | 0.07 | 0.06 |
| 11 | Regulator | LDO 3.3 V 500 mA low-IQ | ME6211C33M5G | C82942 | 1 | 0.15 | 0.10 | 0.08 |
| 12 | Switch | P-MOSFET (branch-rail gate) | SI2301 | C10487 | 2 | 0.20 | **0.12** | 0.10 |
| 13 | LED | RGB status | WS2812B-Mini | C527089 | 1 | 0.20 | 0.12 | 0.10 |
| 14 | Connector | USB-C receptacle 6P | TYPE-C-31-M-12 | C165948 | 1 | 0.25 | 0.15 | 0.12 |
| 15 | ESD | USB bidirectional TVS | USBLC6-2SC6 | C7519 | 1 | 0.18 | 0.12 | 0.10 |
| 16 | Button | Tactile switch 6×6×5 SMD | TS-1187A | C318884 | 4 | 0.24 | **0.16** | 0.12 |
| 17 | Display aux | 47 µH boost network, 30 V MOSFET/diodes | SRU5016-470Y / Si1304BDL / MBR0530 | distributor | 1 set | 0.80 | 0.45 | 0.30 |
| 18 | Connector | 1S battery connector, 2-pin horizontal | JST-PH S2B-PH-K | distributor | 1 | 0.15 | 0.10 | 0.07 |
| 19 | Passives | R/C/bead assortment, including 25 V e-paper capacitors | 0402/0603/0805 kit | — | 1 kit | 0.60 | 0.35 | 0.25 |
| 20 | Hardware | Lanyard / clip hardware | — | distributor | 1 kit | 1.00 | 0.50 | 0.35 |
| 21 | Battery | Li-Po 3.7 V 1000 mAh | 603048 | distributor | 1 | 4.00 | **2.50** | 2.00 |
| 22 | PCB | 4-layer, 0.8 mm | JLCPCB | — | 1 | 5.00 | **1.50** | 0.80 |

¹ E-paper panels are bought from the OEM (Good Display / 大连佳显), buy-lcd.com, or Waveshare. LCSC sometimes stocks them but the model range is incomplete.

### Component subtotal (excl. #20 hardware and #22 PCB)

| Tier | Subtotal |
|---|---|
| **@1 (prototype)** | ≈ $29.0 |
| **@100 (small batch)** | ≈ **$21.5** |
| **@1k (production)** | ≈ $18.1 |

---

## 2. Landed Cost (incl. PCBA + case)

| Item | @1 | @100 | @1k |
|---|---|---|---|
| Components (incl. panel/battery) | 29.0 | 21.5 | 18.1 |
| PCB (4-layer, 0.8 mm) | 5.0 | 1.5 | 0.8 |
| SMT assembly + stencil | —² | 1.5 | 0.9 |
| Case (3D print / DIY) | 3.0 | 2.0 | 0.8 (injection) |
| Lanyard hardware | 1.0 | 0.5 | 0.35 |
| Assembly labor / test | 2.0 | 1.0 | 0.4 |
| **Per-unit total** | **~$40** | **~$28** | **~$22** |

² A single prototype is usually hand-soldered or run as a 1-off PCBA order (adds ~$15–30 NRE, high when amortized to one board).

> Recommendation: **first run 5–10 prototypes** (PCBA ~$40–50 each), validate, then do a small batch of 100 (~$28/unit).

---

## 3. Cost-Structure Breakdown

```
@100 unit component breakdown (base $21.5)
E-paper   █████████████████        33%   ← biggest line item
MCU       █████████                19%
IMU       ██████                   12%
Battery   ██████                   12%
Fuel gauge███                       7%
T/RH      ███                       6%
Rest      █████                     11%  ← NFC / power / connectors / passives
```

### Cost-reduction Levers (ranked by savings)

| Measure | Saving | Trade-off |
|---|---|---|
| Swap panel to 2.13" GDEY0213B74 (250×122) | -$3 | 30% less display area |
| Drop MCU to N4 (4 MB, no PSRAM) | -$1 | Large-image refresh needs frame-buffer tuning |
| Drop MAX17048 fuel gauge, use divider only | -$1.5 | Inaccurate battery % (non-linear Li-ion curve) |
| Drop IMU (only T/RH + motion?) | -$2.5 | Loses flip-wake / step count |
| NFC → passive NTAG216 sticker | -$0.3 | Loses MCU dynamic rewrite / GPO wake |
| Swap to color 2.66" panel | **+$3** | 11 s refresh, worse UX |

**Verdict:** the current selection is already the **best value point** for a DIY/learning platform. To save more, touch the panel size first.

---

## 4. Sourcing & Ordering

### 4.1 Channel split
- **Main ICs + passives** → LCSC, bundled with JLCPCB for **one-stop SMT** (BOM with LCSC #s = one-click order)
- **E-paper panel** → Good Display / buy-lcd.com / Waveshare (note: **bare FPC panel** vs **module with driver board** — this project uses a bare panel on the PCB)
- **Battery** → a Li-Po specialist (mind protection/ Certification; air freight restricted)
- **Case** → 3D print (FDM/SLA) DIY, or injection molding at volume

### 4.2 BOM-kit strategy
- LCSC lets you load the full BOM (with LCSC #s) into the cart; selecting "JLCPCB assembly" auto-checks stock and SMT feasibility
- **Basic-part** components incur no setup fee — preferring Basic parts saves ~$1/board
- Extended parts (e.g. MAX17048, LSM6DSO) add a small changeover fee, negligible at small batch

### 4.3 Risk / long lead-time parts
- **E-paper panel:** in peak season (Q4) lead time can stretch to 2–4 weeks; over-order the first batch by ~20%
- **ESP32-S3-WROOM-1-N8R2:** 24k+ in stock normally, low risk
- **ST25DV04KC:** 2k+ in stock; the SO-8 package (C5221752) hand-solders better than UFDFPN — prefer SO-8
- **Battery:** air freight restricted (domestic ground for China); overseas buyers need a local Li-Po vendor

---

## 5. Optional Expansion (not in core BOM)

| Add-on | Model | Purpose | ~@100 |
|---|---|---|---|
| Digital mic | INMP441 / MSM261S4030H0 | Voice / recording | $1.2 |
| Ambient light | BH1750FVI | Auto contrast | $0.4 |
| Barometric pressure | BMP390 / LPS22HB | Altimeter / floors | $1.5 |
| External Flash | W25Q128 | Bigger wallpaper library | $0.6 |
| Solar | amorphous-Si low-light cell | Extend runtime via EH | $1.0 |
