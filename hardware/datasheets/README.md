# Datasheets

Reference manuals for the-card's components — **all archived locally as PDF** so
the design is reviewable offline and survives link-rot. PDFs are committed on
purpose: manufacturer pages and URLs change or disappear, and for a hardware
project an archived datasheet is part of the design record.

## Local archive

| Ref | Part | LCSC | File | Source |
|---|---|---|---|---|
| U1 | ESP32-S3-WROOM-1 (module) | C2913202 | `ESP32-S3-WROOM-1_Espressif.pdf` | Espressif |
| U1 | ESP32-S3 (chip) | — | `ESP32-S3_Espressif.pdf` | Espressif |
| U2 | ST25DV04KC | C5221752 | `ST25DV04KC_ST.pdf` | ST (Farnell mirror) |
| U3 | LSM6DSO | C2655100 | `LSM6DSO_ST.pdf` | ST (LCSC) |
| U4 | SHT40 | C7461849 | `SHT40_Sensirion.pdf` | Sensirion (SparkFun CDN) |
| U5 | MAX17048 | C2682616 | `MAX17048_Maxim.pdf` | Maxim/ADI (LCSC) |
| U6 | TP4056 | C382139 | `TP4056.pdf` | TPOWER (LCSC wmsc) |
| U7 | DW01A | C18164398 | `DW01A_Fortune.pdf` | Fortune Semiconductor |
| U8 | FS8205A | C16052 | `FS8205A_Fortune.pdf` | Fortune Semiconductor |
| U9 | ME6211C33 | C82942 | `ME6211_Microne.pdf` | MICRONE (LCSC) |
| U10 | USBLC6-2SC6 | C7519 | `USBLC6-2_ST.pdf` | ST (LCSC) |
| Q1, Q2 | SI2301 | C10487 | `SI2301_Vishay.pdf` | Vishay (LCSC) |
| D1 | WS2812B-Mini | C527089 | `WS2812B-Mini_Worldsemi.pdf` | Worldsemi (LCSC) |
| J1 | TYPE-C-31-M-12 | C165948 | `TYPE-C-31-M-12.pdf` | LCSC |
| SW1–4 | TS-1187A | C318884 | `TS-1187A.pdf` | LCSC |
| J2 / panel | GDEY029T94 | — (distributor) | `GDEY029T94_GoodDisplay.pdf` + `GDEY029T94_extracted.md` | Good Display |
| — | SSD1680 (e-ink driver IC) | — | `SSD1680_SolomonSystech.pdf` | Solomon Systech |

LCSC product page pattern: `https://www.lcsc.com/product-detail/C<LCSC>.html`

## Notes

- `st.com` and `espressif.com` block scripted downloads, so those were fetched
  via mirrors (LCSC, Farnell, DigiKey, SparkFun/Adafruit CDNs) that allow it.
- The GDEY029T94 has a text extraction (`GDEY029T94_extracted.md`) for quick
  grep of the pin table — the §5 pin assignment was used to verify `circuit.py`.
- Battery (3.7 V 1000 mAh, 603048) and lanyard hardware have no part datasheet.
- **Re-verify the revision before tape-out.** Datasheets get reissued (e.g.
  GDEY029T94 `24.10.22`) and pinouts/footprints can shift between revs.
