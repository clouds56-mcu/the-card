# Power Budget & Battery-Life Estimate

> Target battery: **3.7 V 1000 mAh Li-Po** (~900 mAh usable at 90% derating).
> Units: current mA / charge mAh. Battery life = usable capacity ÷ daily consumption.
> These are planning estimates from bundled component datasheets, not measured
> v0.2.0 results; firmware duty cycle, cell quality, temperature, and regulator
> dropout will change the real runtime.

---

## 1. Per-state Current Model (ESP32-S3-WROOM-1-N16R8)

Sources: ESP32-S3 datasheet + Espressif official power-measurement guide +
community measurements. The corrected always-on figures come from the bundled
[ST25DV04KC datasheet](../hardware/datasheets/ST25DV04KC_ST.pdf) (DS13519 Rev 3,
Table 249) and [ME6211 datasheet](../hardware/datasheets/ME6211_Microne.pdf)
(ME6211C33 electrical-characteristics table).

| State | Module current | Notes |
|---|---|---|
| **Deep Sleep (RTC + ULP off)** | ~10 µA | module-level measured ~7–11 µA |
| Deep Sleep (ULP running) | ~180 µA | when ULP monitors a sensor |
| Light Sleep (auto) | ~0.13–0.24 mA | while keeping WiFi link |
| Modem Sleep (DTIM1) | ~20 mA | WiFi stays connected |
| Active (CPU 240 MHz, radios off) | ~40 mA | rendering an e-paper frame |
| Active + WiFi connect burst | ~150–250 mA (peak) | OTA / wallpaper download |
| BLE peripheral advertising (1 s) | ~3 mA (avg) | |
| BLE connected (1 s interval) | ~0.2–0.8 mA (avg) | |

## 2. Peripheral Current

| Peripheral | Standby / active current | Notes |
|---|---|---|
| E-paper SSD1680 | static **0 µA** (bistable) / ~3 mA during refresh (host boost stage) | during refresh the ESP is also Active, total ~30 mA |
| ST25DV04KC NFC | **0.076 mA typ, 0.100 mA max** (static standby at 3.3 V, up to 85 °C) | the selected SO-8 package has no LPD pin; RF operation can be field-powered |
| LSM6DSO IMU | LP 0.012 mA / shutdown 3 µA | |
| SHT40 T/RH | 0.0004 mA standby / 1.2 mA × 2 ms | negligible at 1/min sampling |
| MAX17048 fuel gauge | **0.003 mA (always on)** | can't be cut; always resident |
| ME6211C33 LDO | **0.060 mA typ supply current** | CE is tied high, so the 0.1 µA CE-low standby value does not apply |
| TP4056 (not charging) | ~0.005 mA (BAT side) | |
| WS2812 (**~0.6 mA even when off**) | **must be MOSFET-gated** | ⚠️ the biggest leakage killer |
| AUX branch rail after MOSFET cut | 0 µA | status LED fully cut; sensors remain on +3V3 |

> **Critical:** WS2812 still draws ~0.6 mA when "off" due to internal latching. Ungated, a 1000 mAh cell **lasts only ~60 days on leakage alone**. This project gates the branch rail via `PWR_AUX` (GPIO47) → P-MOSFET.

## 3. Deep-sleep Baseline (the core of runtime)

Always-on devices summed (MCU in deep sleep, branch rail cut):

```
ESP32-S3 deep sleep   10 µA
MAX17048 fuel gauge    3 µA
ST25DV04KC standby    76 µA
LSM6DSO LP mode       12 µA (or 3 µA shutdown)
SHT40 standby          0.4 µA
ME6211C33 enabled      60 µA
TP4056 BAT current     ~5 µA
divider network       ~2.8 µA (1 MΩ + 300 kΩ at ~3.7 V)
─────────────────────────
baseline total      ~169 µA  →  4.06 mAh/day
```

> With the IMU in shutdown (button-wake instead of motion-wake), the baseline is
> still about **160 µA (3.85 mAh/day)**. The always-enabled ME6211 and the SO-8
> ST25DV now dominate the estimate. The ST25DV datasheet's 1.3 µA low-power-down
> figure at 3.3 V is not available on the selected package because it has no LPD
> pin.

---

## 4. Battery-life Scenarios

### Scenario A — daily badge use (baseline)
> Glance at screen 10×/day, change wallpaper 2×, BLE sync to phone 2×, one nightly OTA check.

| Event | Times/day | Duration | Current | mAh/day |
|---|---|---|---|---|
| Deep-sleep baseline | — | 24 h | 169 µA | 4.06 |
| Button wake + UI render | 10 | 4 s | 40 mA | 0.44 |
| E-paper full refresh | 3 | 3 s | 30 mA | 0.075 |
| BLE sync (wallpaper push) | 2 | 15 s | 8 mA (avg) | 0.067 |
| WiFi OTA check | 1 | 20 s | 150 mA (avg) | 0.833 |
| **Daily total** | | | | **~5.5 mAh/day** |

**Life** = 900 / 5.5 ≈ **164 days (5.4 months theoretical)**. Use roughly
**4–5 months** as a first planning range; only measurements on an assembled v0.2.0
board with production firmware can establish a real runtime.

### Scenario B — light use (display-focused, rare OTA)
> Only change wallpaper, daily OTA off, BLE sync ~1×/week.

| Item | mAh/day |
|---|---|
| Deep-sleep baseline | 4.06 |
| Wake + render ×5 | 0.22 |
| Full refresh ×2 | 0.05 |
| BLE sync (weekly avg) | 0.01 |
| **Total** | **~4.3 mAh/day** |

**Life** ≈ **207 days (6.8 months theoretical)**; roughly **5–6 months** is a
reasonable planning range before prototype measurements.

### Scenario C — heavy development (radios always on)
> Persistent WiFi + serial logging + frequent refresh.

| Item | mAh/day |
|---|---|
| Modem/Light-sleep holding WiFi | ~480 (20 mA × 24 h) |
| Frequent CPU activity | ~50 |
| **Total** | **~530 mAh/day** |

**Life** ≈ **1.7 days** — normal in development; production firmware must turn off radios and deep-sleep.

### Scenario D — pure standby (factory state)
> Deep sleep only, wake once daily via RTC to refresh the clock.

With the IMU shut down, **life** ≈ 900 / 3.85 ≈ **234 days (7.7 months
theoretical)**. This is an electrical-load estimate, not a shelf-life guarantee.

---

## 5. Runtime-improvement Checklist (ranked)

| # | Measure | Saving | Difficulty |
|---|---|---|---|
| 1 | **Keep the WS2812 MOSFET-gated** | saves ~14 mAh/day of LED leakage | ⭐ must-do |
| 2 | Wake by RTC timer + buttons, not motion | saves IMU 0.3 mAh/day | ⭐ |
| 3 | Use 1 MΩ high-value VBATT divider, or sample only when awake | saves ~0.1 mAh/day | ⭐ |
| 4 | Consider an LPD-capable ST25DV package in a later hardware revision | about 1.8 mAh/day versus SO-8 static standby | ⭐⭐⭐ redesign |
| 5 | Stretch BLE connection interval to 1–4 s (tolerable for wallpaper push) | big BLE average drop | ⭐⭐ |
| 6 | Lower OTA-check frequency (daily → weekly) | saves ~0.8 mAh/day | ⭐ |
| 7 | Use partial refresh instead of full (0.3 s vs 1.5 s) | 5× lower refresh energy | ⭐⭐ |
| 8 | Underclock CPU to 80/160 MHz (enough for rendering) | ~30% lower active current | ⭐⭐ |
| 9 | ULP co-processor polls buttons/sensors | saves MCU wake overhead | ⭐⭐⭐ advanced |

---

## 6. Battery Sizing

| Capacity | Size (ref.) | Scenario A life | Trade-off |
|---|---|---|---|
| 500 mAh | 502030 (~5 mm) | ~2 months | ultra-thin, short runtime |
| **1000 mAh** ✅ | 603048 (~6 mm) | ~4–5 months | **recommended, balanced** |
| 1500 mAh | 803040 (~8 mm) | ~6–7 months | thicker, OK for a lanyard |
| 2000 mAh | 904050 (~9 mm) | ~8–10 months | bulky/heavy |

> Badge thickness should stay ≤8 mm → **1000–1500 mAh is the practical size
> range**. Runtime figures above are estimates and do not include a measured
> cell self-discharge curve.

---

## 7. Charge Time

- TP4056 set to approximately 500 mA charge current (`PROG` pin = 2.2 kΩ)
- 1000 mAh cell: CC phase ~2 h plus CV taper ≈ **full charge ~3 h**
- USB-C 5 V/1 A input is enough — no fast-charge needed
