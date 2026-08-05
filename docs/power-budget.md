# Power Budget & Battery-Life Estimate

> Target battery: **3.7 V 1000 mAh Li-Po** (~900 mAh usable at 90% derating).
> Units: current mA / charge mAh. Battery life = usable capacity ÷ daily consumption.

---

## 1. Per-state Current Model (ESP32-S3-WROOM-1-N8R2)

Sources: ESP32-S3 datasheet + Espressif official power-measurement guide + community measurements.

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
| E-paper SSD1680 | static **0 µA** (bistable) / ~3 mA during refresh (on-panel boost) | during refresh the ESP is also Active, total ~30 mA |
| ST25DV04KC NFC | ~1 µA (standby, no RF field) | under RF field, powered by the phone |
| LSM6DSO IMU | LP 0.012 mA / shutdown 3 µA | |
| SHT40 T/RH | 0.0004 mA standby / 1.2 mA × 2 ms | negligible at 1/min sampling |
| MAX17048 fuel gauge | **0.003 mA (always on)** | can't be cut; always resident |
| ME6211 LDO | 0.003 mA | always resident |
| TP4056 (not charging) | ~0.005 mA (BAT side) | |
| WS2812 (**~0.6 mA even when off**) | **must be MOSFET-gated** | ⚠️ the biggest leakage killer |
| Branch rail after MOSFET cut | 0 µA | sensors/LED/motor all cut |

> **Critical:** WS2812 still draws ~0.6 mA when "off" due to internal latching. Ungated, a 1000 mAh cell **lasts only ~60 days on leakage alone**. This project gates the branch rail via `PWR_AUX` (GPIO47) → P-MOSFET.

## 3. Deep-sleep Baseline (the core of runtime)

Always-on devices summed (MCU in deep sleep, branch rail cut):

```
ESP32-S3 deep sleep   10 µA
MAX17048 fuel gauge    3 µA
ST25DV04KC standby     1 µA
LSM6DSO LP mode       12 µA (or 3 µA shutdown)
SHT40 standby          0.4 µA
LDO/TP4056 leakage     5 µA
divider network       ~5 µA (1 MΩ high-value → ~1 µA)
─────────────────────────
baseline total       ~36 µA  →  0.86 mAh/day
```

> With the IMU in shutdown (button-wake instead of motion-wake) and a 1 MΩ divider, the baseline drops to **~15–20 µA (0.4 mAh/day)**.

---

## 4. Battery-life Scenarios

### Scenario A — daily badge use (baseline)
> Glance at screen 10×/day, change wallpaper 2×, BLE sync to phone 2×, one nightly OTA check.

| Event | Times/day | Duration | Current | mAh/day |
|---|---|---|---|---|
| Deep-sleep baseline | — | 24 h | 36 µA | 0.86 |
| Button wake + UI render | 10 | 4 s | 40 mA | 0.44 |
| E-paper full refresh | 3 | 3 s | 30 mA | 0.075 |
| BLE sync (wallpaper push) | 2 | 15 s | 8 mA (avg) | 0.067 |
| WiFi OTA check | 1 | 20 s | 150 mA (avg) | 0.833 |
| **Daily total** | | | | **~2.3 mAh/day** |

**Life** = 900 / 2.3 ≈ **390 days (theoretical)** → after Li-ion self-discharge (~3%/month), **~6–9 months real-world**.

### Scenario B — light use (display-focused, rare OTA)
> Only change wallpaper, daily OTA off, BLE sync ~1×/week.

| Item | mAh/day |
|---|---|
| Deep-sleep baseline | 0.86 |
| Wake + render ×5 | 0.22 |
| Full refresh ×2 | 0.05 |
| BLE sync (weekly avg) | 0.01 |
| **Total** | **~1.1 mAh/day** |

**Life** ≈ **800 days theoretical / ~12 months real-world** (self-discharge dominates).

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

**Life** ≈ 900 / 0.9 ≈ **1000 days theoretical**, but in practice the cell self-discharges first (~18–24 months; the battery ages out before it drains).

---

## 5. Runtime-improvement Checklist (ranked)

| # | Measure | Saving | Difficulty |
|---|---|---|---|
| 1 | **MOSFET-gate WS2812 / sensors** | saves ~14 mAh/day (leakage) | ⭐ must-do |
| 2 | Wake by RTC timer + buttons, not motion | saves IMU 0.3 mAh/day | ⭐ |
| 3 | Use 1 MΩ high-value VBATT divider, or sample only when awake | saves ~0.1 mAh/day | ⭐ |
| 4 | Stretch BLE connection interval to 1–4 s (tolerable for wallpaper push) | big BLE average drop | ⭐⭐ |
| 5 | Lower OTA-check frequency (daily → weekly) | saves ~0.8 mAh/day | ⭐ |
| 6 | Use partial refresh instead of full (0.3 s vs 1.5 s) | 5× lower refresh energy | ⭐⭐ |
| 7 | Underclock CPU to 80/160 MHz (enough for rendering) | ~30% lower active current | ⭐⭐ |
| 8 | ULP co-processor polls buttons/sensors | saves MCU wake overhead | ⭐⭐⭐ advanced |

---

## 6. Battery Sizing

| Capacity | Size (ref.) | Scenario A life | Trade-off |
|---|---|---|---|
| 500 mAh | 502030 (~5 mm) | ~3 months | ultra-thin, short runtime |
| **1000 mAh** ✅ | 603048 (~6 mm) | ~6–9 months | **recommended, balanced** |
| 1500 mAh | 803040 (~8 mm) | ~10–12 months | thicker, OK for a lanyard |
| 2000 mAh | 904050 (~9 mm) | ~14 months | bulky/heavy |

> Badge thickness should stay ≤8 mm → **1000–1500 mAh is the sweet spot**.
> Note: past ~6 months, **Li-ion self-discharge (2–3%/month) dominates**, so bigger cells give diminishing returns.

---

## 7. Charge Time

- TP4056 set to 1 A charge current (`PROG` pin = 1.2 kΩ)
- 1000 mAh cell: CC phase ~1 h + CV phase ~1 h ≈ **full charge ~2 h**
- USB-C 5 V/1 A input is enough — no fast-charge needed
