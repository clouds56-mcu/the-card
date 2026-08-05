# Datasheets

Reference manuals for the-card's components. Critical ones are **archived
locally** (PDF) so the design is reviewable offline; the rest are linked.

PDFs are committed on purpose — manufacturer pages and URLs change or disappear,
and for a hardware project an archived datasheet is part of the design record.

## Archived locally (PDF)

| Ref | Part | File | Source |
|---|---|---|---|
| U7 | DW01A | `DW01A_Fortune.pdf` | Fortune Semiconductor |
| U8 | FS8205A | `FS8205A_Fortune.pdf` | Fortune Semiconductor |
| J2 / panel | GDEY029T94 | `GDEY029T94_GoodDisplay.pdf` | Good Display (full 37-page spec) |
| J2 / panel | GDEY029T94 | `GDEY029T94_extracted.md` | text extraction of the above (searchable) |
| — | SSD1680 (e-ink driver IC) | `SSD1680_SolomonSystech.pdf` | Solomon Systech |
| U2 | ST25DV04KC | `ST25DV04KC_ST.pdf` | STMicroelectronics (via Farnell mirror) |

## All parts — datasheet links + LCSC

LCSC product page pattern: `https://www.lcsc.com/product-detail/C<LCSC>.html`

| Ref | Part | LCSC | Datasheet / manual URL |
|---|---|---|---|
| U1 | ESP32-S3-WROOM-1-N8R2 | C2913204 | 🔗 espressif: `esp32-s3-wroom-1_datasheet_en.pdf` (under https://www.espressif.com/en/support/documents/technical-documents) |
| U1 | ESP32-S3 (chip) | — | 🔗 https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf |
| U2 | ST25DV04KC-IE8S3 | C5221752 | ✅ local · 🔗 https://www.st.com/resource/en/datasheet/st25dv04kc.pdf |
| U3 | LSM6DSOTR | C2655100 | 🔗 https://www.st.com/resource/en/datasheet/lsm6dso.pdf |
| U4 | SHT40-BD1B-R2 | C7461849 | 🔗 Sensirion SHT4x datasheet (CDL_280902_SHT4x.pdf) on sensirion.com |
| U5 | MAX17048G+T10 | C2682616 | 🔗 https://www.analog.com/media/en/technical-documentation/data-sheets/max17048-max17049.pdf |
| U6 | TP4056 | C382139 | 🔗 LCSC C382139 page hosts the TPOWER TP4056 datasheet |
| U7 | DW01A | C18164398 | ✅ local · 🔗 http://www.ic-fortune.com/upload/Download/DW01A-DS-11_EN.pdf |
| U8 | FS8205A | C16052 | ✅ local · 🔗 https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/1809050110_Fortune-Semicon-FS8205A_C16052.pdf |
| U9 | ME6211C33M5G | C82942 | 🔗 MICRONE/Merge ME6211 — via LCSC C82942 page |
| U10 | USBLC6-2SC6 | C7519 | 🔗 https://www.st.com/resource/en/datasheet/usblc6-2.pdf |
| Q1, Q2 | SI2301 | C10487 | 🔗 Vishay SI2301CDS: https://www.vishay.com/docs/71095/si2301cds.pdf |
| D1 | WS2812B-Mini | C527089 | 🔗 Worldsemi WS2812B-Mini-V3 — via LCSC C527089 page |
| J1 | TYPE-C-31-M-12 | C165948 | 🔗 via LCSC C165948 page |
| SW1–4 | TS-1187A | C318884 | 🔗 via LCSC C318884 page |
| J2 / panel | GDEY029T94 | — (distributor) | ✅ local · 🔗 https://www.laskakit.cz/user/related_files/gdey029t94.pdf |
| — | SSD1680 (e-ink driver IC) | — | ✅ local · 🔗 https://download.kamami.pl/p1184877-SSD1680_Datasheet.pdf |

## Notes

- `st.com` and `espressif.com` block scripted downloads (anti-bot), so those are
  link-only here — open in a browser to save. The locally archived ones came from
  mirrors that allow it (Fortune, LCSC, laskakit, Farnell, kamami).
- Battery (3.7 V 1000 mAh, 603048) and lanyard hardware have no part datasheet.
- Re-verify any datasheet revision before tape-out; pinouts can change between
  revs (the GDEY029T94 has been reissued, e.g. `24.10.22`).
