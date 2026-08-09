# System Architecture

## 1. Block Diagram

```
                           ┌─────────────────────────────────────────────┐
                           │              ESP32-S3-WROOM-1-N8R2          │
                           │   (Dual-core 240MHz · 8MB Flash · 2MB PSRAM)│
                           │                                             │
   USB-C ──┬─ ESD ── D+/D-─┤  USB-Serial-JTAG (native USB, no CH340)     │
   5V  ────┤               │                                             │
           │               │  SPI  ──► [E-ink SSD1680 2.9" 296×128]       │
   TP4056 ◄─┘ charge        │  I2C0 ─► { ST25DV04KC · LSM6DSO · SHT40     │
   DW01+MOS ◄─ protection   │             · MAX17048 }                    │
           │                │  GPIO ► 4× Tactile Buttons (deep-sleep wake)│
   Li-ion 3.7V              │  GPIO ─► WS2812 RGB (via MOSFET power gate)│
   1000mAh ─┬─ LDO 3.3V ───►│                                             │
           │                │  IRQ  ◄─ NFC GPO / IMU INT                  │
           └────────────────┤  ADC  ◄─ VBATT divider (MAX17048 primary)   │
                            └─────────────────────────────────────────────┘
```

## 2. Subsystem Design

### 2.1 MCU — why ESP32-S3

| Candidate | Trade-off | Verdict |
|---|---|---|
| **ESP32-S3-WROOM-1-N8R2** ✅ | 8 MB Flash for wallpaper library + 2 MB PSRAM for frame buffer, native USB (no downloader chip), richest ecosystem | **Selected** |
| N4 (4 MB, no PSRAM) | Frame buffer squeezes SRAM, large-image refresh struggles | Alt (max savings) |
| S3-MINI-1 | Smaller but dense routing, less DIY-friendly | No |
| Bare die S3FN8 | Requires own RF + Flash routing, not for a learning platform | No |

- **N8R2 over N8R8:** wallpaper library fits in Flash; 2 MB PSRAM is plenty for double buffering (296×128×2 = 76 KB), and saves money.
- On-module PCB antenna → **no RF design required**, DIY-friendly.

### 2.2 Display Subsystem

- **Main panel:** 2.9" 296×128 monochrome e-paper (GDEY029T94, SSD1680 controller)
  - 4-wire SPI, supports **partial refresh 0.3 s / full refresh 1.5 s** / 4-gray
  - Bistable: **zero power for a static image** — the core of badge battery life
  - Outline 79×36.7 mm — exactly standard badge aspect ratio
- Routing: 24-pin 0.5 mm FPC flip connector for easy panel swap
- Host support: 47 µH SSD1680 boost stage, 30 V MOSFET/Schottky diodes, and
  25 V-rated pump/HV bypass capacitors per the panel reference design
- **Note:** SSD1680 has no power-enable pin; Q2 cuts the panel VCI/booster input

### 2.3 Wireless Subsystem

| Channel | Chip | Role |
|---|---|---|
| Bluetooth 5 LE | ESP32-S3 on-module | Phone app pushes wallpapers, config, OTA |
| NFC 13.56 MHz | **ST25DV04KC** (4 Kbit dynamic tag) | Phone tap reads badge info / vCard / URL; MCU rewrites tag content anytime over I2C |

**Why ST25DV04KC over NXP NTAG I2C Plus:**
- ✅ Dynamic tag memory can be updated by the MCU over I²C
- ✅ **GPO wake pin:** phone proximity triggers an MCU interrupt (enables "tap to check-in")
- ✅ Cheaper (~$0.44 @100 vs NT3H2211 ~$0.7)
- ⚠️ Type 5 (ISO15693); modern phones support NDEF fine; only very old devices are slightly less compatible than Type 2

The IC supports energy harvesting, but `V_EH` is intentionally left unconnected
in this first revision to keep the power architecture simple.

### 2.4 Sensor Subsystem

| Sensor | Model | Purpose | Low power |
|---|---|---|---|
| 6-axis IMU | **LSM6DSO** | Flip-to-wake, step count, raise-to-wake, gestures | LP 0.012 mA |
| Temp/Humidity | **SHT40** | Environment (shown in a screen corner) | Standby 0.4 µA |

- Both sensors share **I2C0 bus** (multiplexed with NFC + fuel gauge)
- During deep sleep the IMU stays in low-power mode and wakes the MCU via its INT pin

### 2.5 Power Subsystem

```
 USB-C 5V ──► TP4056 (~500mA CC) ──► [DW01 + FS8205A protection] ──► BAT+ 3.0~4.2V
                                                                  │
                                                  ME6211 LDO 3.3V ◄┘
                                                       │ 3.3V system rail
                              ┌────────────────────────┼──────────────┐
                              │                        │              │
                     ESP32-S3 + sensors          Load Switch ──► status LED
                        (always powered)          (P-MOSFET, cut in deep sleep)
```

- **Charge:** TP4056 (~500 mA CC/CV from 2.2 kΩ RPROG, thermal regulation)
- **Protection:** DW01A (over-charge / over-discharge / short) + FS8205A dual MOSFET
- **Regulation:** ME6211C33 (3.3 V, IQ ~3 µA, 500 mA)
- **Fuel gauge:** MAX17048 (ModelGauge algorithm, 3 µA, I2C, no sense resistor) → accurate % on screen
- **Key:** the WS2812 sits on a **switchable branch rail** (P-MOSFET), fully cut
  in deep sleep. The sensors share always-on +3V3 with the I²C pullups so the bus
  cannot back-power an unpowered sensor.

### 2.6 Input Subsystem

- **4 tactile buttons** (watch-style layout):
  - `UP` / `DOWN`: browse wallpaper list
  - `SELECT`: confirm / set full-screen wallpaper
  - `MENU`: enter settings / Bluetooth / battery / sensor page
- All on GPIO with internal pull-ups, **support ext0/ext1 + button-combo wake from deep sleep**
- Hardware RC debounce + software debounce

---

## 3. GPIO Pin Map (ESP32-S3-WROOM-1-N8R2)

> Module internally uses: GPIO26–32 (Flash/PSRAM SPI, not pinned out), GPIO19/20 (USB), GPIO0/45/46 (strapping — use carefully).

| GPIO | Function | Dir | Notes |
|---|---|---|---|
| **—— E-ink SPI (FSPI) ——** | | | |
| GPIO11 | EPD_BUSY | IN | Panel busy |
| GPIO12 | EPD_CS | OUT | Chip select |
| GPIO13 | EPD_DC | OUT | Data/command |
| GPIO14 | EPD_RST | OUT | Reset |
| GPIO10 | EPD_SCLK | OUT | SPI clock |
| GPIO9  | EPD_SDA(DIN) | OUT | SPI MOSI |
| **—— I2C0 (sensors + NFC + fuel gauge) ——** | | | |
| GPIO8  | I2C_SCL | OUT/OD | Bus clock |
| GPIO18 | I2C_SDA | I/O/OD | Bus data |
| **—— Interrupt inputs ——** | | | |
| GPIO3  | NFC_IRQ | IN | ST25DV GPO wake |
| GPIO2  | IMU_INT | IN | LSM6DSO motion/flip interrupt |
| GPIO15 | CHRG_STAT | IN | TP4056 charge status |
| **—— Buttons (deep-sleep wake, internal pull-up) ——** | | | |
| GPIO4  | BTN_UP | IN | Up |
| GPIO5  | BTN_DOWN | IN | Down |
| GPIO6  | BTN_SEL | IN | Select |
| GPIO7  | BTN_MENU | IN | Menu |
| **—— Outputs / peripherals ——** | | | |
| GPIO47 | PWR_AUX | OUT | Branch-rail P-MOS gate (cuts the status LED) |
| GPIO16 | EPD_PWR_EN | OUT | E-paper VCI/booster P-MOS gate |
| GPIO48 | LED_DIN | OUT | WS2812 data (GPIO48 is the classic S3 RGB pin, on branch rail) |
| **—— USB (native, fixed) ——** | | | |
| GPIO19 | USB_D- | I/O | Programming + power |
| GPIO20 | USB_D+ | I/O | Programming + power |
| **—— Battery monitor ——** | | | |
| GPIO1  | VBATT_DIV | IN(ADC1_CH0) | Divider sample (backup; MAX17048 is primary) |
| **—— Reserved expansion ——** | | | |
| GPIO17/21/35–46 | Expansion | — | Unconnected; GPIO18 is used by I2C |

> ⚠️ On ESP32-S3, ADC2 is unavailable while WiFi is on, so battery-voltage sampling must use **ADC1 (GPIO1–10)**. The table above already respects this.

---

## 4. Key Design Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | WROOM module, not bare die | No RF design, DIY-friendly, easier certification |
| 2 | N8R2 (8 MB Flash + 2 MB PSRAM) | Wallpaper library + frame buffer both satisfied; best value |
| 3 | NFC uses dynamic tag ST25DV04KC | MCU rewrite + GPO wake; `V_EH` is deferred |
| 4 | Native USB, no CH340 | Saves a chip, space, and cost |
| 5 | Gate the WS2812, keep I²C sensors on +3V3 | Removes LED leakage without I²C back-power paths |
| 6 | 2.9" monochrome e-paper (not color) | Color is slow (11 s) and pricier; mono partial refresh 0.3 s feels great |
| 7 | MAX17048 fuel gauge (not a plain divider) | Li-ion discharge curve is non-linear; ModelGauge gives an accurate on-screen % |
