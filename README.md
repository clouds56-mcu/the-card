# The Card — E-Paper Smart Badge

[![CI](https://github.com/clouds56-mcu/the-card/actions/workflows/ci.yml/badge.svg)](https://github.com/clouds56-mcu/the-card/actions/workflows/ci.yml)

**Website:** <https://clouds56-mcu.github.io/the-card/>

> An **ESP32-S3** based DIY/learning smart badge: e-paper wallpapers, Bluetooth, NFC, multi-button watch-style control, and on-board sensors, worn around the neck like an ID badge.

## 📋 Project Brief

| Item | Spec |
|---|---|
| **Positioning** | DIY / open learning platform (open-source, flashable, well-documented) |
| **MCU** | ESP32-S3-WROOM-1-N16R8 (16 MB Flash + 8 MB Octal PSRAM) |
| **Display** | 2.9" e-paper 296×128 (SSD1680, partial refresh / 4-gray) |
| **Wireless** | Bluetooth 5 LE (on-module) + NFC (ST25DV04KC dynamic tag, etched v0.2 antenna) |
| **Input** | 4× tactile buttons (up/down/select/menu, watch-style) |
| **Sensors** | 6-axis IMU (LSM6DSO) + Temp/Humidity (SHT40) |
| **Power** | 3.7 V Li-Po + USB-C charging + fuel gauge |
| **Wear** | Lanyard badge form factor |

## 📚 Documentation Index

| Doc | Description |
|---|---|
| [docs/architecture.md](docs/architecture.md) | System block diagram, subsystem design, **GPIO pin map** |
| [docs/bom.md](docs/bom.md) | Full BOM (with LCSC part #s / unit prices / links) + cost analysis |
| [docs/power-budget.md](docs/power-budget.md) | State-based power model + battery-life scenarios |
| [website/README.md](website/README.md) | Product site, hardware previews, and candidate release downloads |

## 💰 Key Takeaways

- **Component BOM (incl. panel + battery, excl. PCB/case):** ~$29 (1-off) / ~$21 (@100) / ~$18 (@1k)
- **Landed cost (incl. PCBA + case + assembly):** ~$40 (1-off) / ~$28 (@100) / ~$21 (@1k)
- **Cost driver:** e-paper panel (~$7, 33%) + MCU (~$4, 18%) + battery/IMU (~$2.5 each)
- **Battery life:** ~5.4 months theoretical for modeled daily use (1000 mAh), with ~4–5 months as a planning range; prototype measurement is pending
- **#1 power gotcha:** keep the WS2812 gated; the always-enabled SO-8 ST25DV and ME6211 dominate the revised ~0.16–0.17 mA sleep estimate

## 🚧 Optional Expansion (not in core BOM)

- Microphone (INMP441 / MSM261S) — voice interaction
- Ambient light (BH1750) — auto contrast
- Solar harvesting (paired with ST25DV's EH pin)
- Color e-paper (2.66" R/Y/B/W, slow 11 s refresh)

---

## 📄 License

This project is released under the **[MIT License](LICENSE)** — firmware, hardware designs, and documentation alike. Build it, modify it, ship it.

---

*Prices reflect 2026-08 LCSC / JLCPCB / Good Display market data and are for reference only — confirm at order time.*
