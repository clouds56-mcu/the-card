#!/usr/bin/env python3
"""Generate hardware/the-card.kicad_sch — v3 (hand-crafted layout + local wires).

The auto grid looked bad, so placement is now a hand-designed table (parts placed
by signal flow: power chain top-left, MCU centre, peripherals on the side their
MCU pins are on, decoupling caps against their ICs). Power rails use KiCad power
symbols + PWR_FLAG; signals use net labels; and 2-pin signal nets whose endpoints
land close together are wired directly (the rest stay labels — an MCU-fanout
board can't be all-wire without spaghetti).

    cd hardware && uv run python gen_schematic.py
    kicad-cli sch erc the-card.kicad_sch -o /tmp/erc.txt   # expect 0 errors
"""
import os
import re
import uuid

import circuit
from design_metadata import DESIGN_VERSION, PROJECT_NAME

HERE = os.path.dirname(os.path.abspath(__file__))
LIBS = os.path.join(HERE, "libraries")
OUT = os.path.join(HERE, "the-card.kicad_sch")
POWER_LIB = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols/power.kicad_sym"
PROJECT = PROJECT_NAME

PASSIVE_SYMS = {"0402WGF1002TCE", "CL05B104KO5NNNC", "CL10A106KP8NNNC"}
POWER_NETS = {"GND", "+3V3", "+BAT", "VBUS", "AUX_3V3", "EPD_VDD"}
WIRE_MAX = 120.0  # mm; 2-pin signal nets closer than this get a wire, else a label

_pwr = 0
def pwref():
    global _pwr; _pwr += 1
    return f"#PWR{_pwr:04d}"

def U():
    return str(uuid.uuid4())

def snap(v):
    return round(v / 1.27) * 1.27


# ── hand-crafted placement (mm, snapped to 1.27 grid) ─────────────────────────
# POWER chain top-left · MCU centre · sensors left (I2C) · e-ink/LED below ·
# buttons bottom · IMU/vbat/gates right. Decoupling caps hug their ICs.
RAW_PLACE = {
    # power chain top-left (USB moved to MCU side; only charger/prot/LDO/FG/gates here)
    "U6": (50, 75), "U9": (125, 75),
    "C_vbus": (90, 50), "C_bat": (90, 100), "R_prog": (78, 108), "R_chrg": (108, 50),
    "C_ldoi": (155, 60), "C_ldoo": (155, 92),
    "U7": (50, 160), "U8": (120, 160), "U5": (195, 160),
    "R_dvcc": (78, 143), "R_dvm": (158, 178), "C_dprot": (90, 180),
    "C_fg": (225, 143), "Q1": (270, 75), "Q2": (270, 160),
    "R_q1g": (298, 56), "R_q2g": (298, 143),
    # USB-C + ESD (moved to MCU left side, near USB_DM/DP pins)
    "J1": (265, 115), "U10": (310, 115),
    # MCU centre + local support (decoupling caps hugging the module)
    "U1": (420, 220), "C_mcu1": (390, 152), "C_mcu2": (400, 152),
    "C_en": (450, 152), "R_en": (450, 132), "R_io0": (454, 270),
    "R_vbh": (486, 185), "R_vbl": (510, 207), "C_vb": (486, 207),
    # sensors / NFC (right of USB, near MCU I2C pins on the left edge)
    "U2": (310, 170), "U3": (310, 245), "U4": (355, 245),
    "C_nfc": (280, 170), "C_imu1": (280, 245), "C_imu2": (310, 275),
    "C_sht": (355, 275), "R_scl": (280, 198), "R_sda": (295, 198),
    # e-ink + LED (below MCU, near SPI/LED pins)
    "J2": (370, 320), "C_epdvdd": (370, 292), "D1": (465, 320), "C_led": (465, 292),
    # buttons (below J2/LED area, near MCU left-side BTN pins)
    "SW1": (290, 385), "SW2": (330, 385), "SW3": (370, 385), "SW4": (410, 385),
    "C_btn1": (290, 408), "C_btn2": (330, 408), "C_btn3": (370, 408), "C_btn4": (410, 408),
}


# ── parts from the built circuit ─────────────────────────────────────────────
dc = circuit.nfc.circuit
parts = []
for p in dc.parts:
    lib = "passives" if p.name in PASSIVE_SYMS else "the-card"
    pins = []
    for pin in p.pins:
        net = pin.nets[0].name if pin.nets else ""
        pins.append({"num": str(pin.num), "x": pin.x or 0.0, "y": pin.y or 0.0,
                     "rot": pin.rotation or 0, "net": net})
    parts.append({"ref": p.ref, "lib": lib, "name": p.name,
                  "fp": getattr(p, "footprint", None) or "",
                  "value": getattr(p, "value", None) or p.name, "pins": pins})

# apply placement
by_ref = {p["ref"]: p for p in parts}
cx, cy = 520, 90
for p in parts:
    if p["ref"] in RAW_PLACE:
        x, y = RAW_PLACE[p["ref"]]
    else:
        x, y = cx, cy
        cx += 25.4
        if cx > 700:
            cx, cy = 520, cy + 30
    p["x"], p["y"], p["rot"] = snap(x), snap(y), 0
PAPER = "A1"

# ── collision avoidance: nudge parts whose pin endpoints collide cross-net ───
occupied = {}
for p in parts:
    for pin in p["pins"]:
        if not pin["net"]: continue
        ax = p["x"] + (pin["x"] or 0)
        ay = p["y"] - (pin["y"] or 0)
        c = (round(ax, 3), round(ay, 3))
        if c in occupied and occupied[c] != pin["net"]:
            p["x"] += 2.54
        else:
            occupied[c] = pin["net"]

# ── symbol-block extraction ──────────────────────────────────────────────────
def extract_symbols(path):
    t = open(path).read()
    d, i, n = {}, 0, len(t)
    while True:
        idx = t.find('(symbol "', i)
        if idx < 0:
            break
        q1 = t.find('"', idx); q2 = t.find('"', q1 + 1)
        name = t[q1 + 1:q2]
        depth, j = 0, idx
        while j < n:
            if t[j] == "(":
                depth += 1
            elif t[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if not re.search(r"_\d+_\d+$", name):
            d[name] = t[idx:j + 1]
        i = j + 1
    return d

SYMS = {}
for fn in ("passives.kicad_sym", "the-card.kicad_sym"):
    SYMS.update(extract_symbols(os.path.join(LIBS, fn)))
PW = extract_symbols(POWER_LIB)


def power_block(net):
    blk = PW[net] if net in PW else PW["+3V3"].replace("+3V3", net)
    return blk.replace(f'(symbol "{net}"', f'(symbol "power:{net}"', 1)


def rot_pt(x, y, r):
    r %= 360
    return {(0,): (x, y), (90,): (-y, x), (180,): (-x, -y), (270,): (y, -x)}[(r,)]


def pinabs(part, pin):
    ax, ay = rot_pt(pin["x"], -pin["y"], part["rot"])
    return (round(part["x"] + ax, 3), round(part["y"] + ay, 3))


def emit_pwr(L, lib_id, value, x, y):
    r = pwref()
    L.append("\t(symbol")
    L.append(f'\t\t(lib_id "{lib_id}")\n\t\t(at {x:.3f} {y:.3f} 0)\n\t\t'
             '(unit 1)\n\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t'
             '(on_board yes)\n\t\t(dnp no)')
    L.append(f'\t\t(uuid "{U()}")')
    L.append(f'\t\t(property "Reference" "{r}"\n\t\t\t(at {x:.3f} {y:.3f} 0)\n\t\t\t'
             '(effects (font (size 1.27 1.27)) (hide yes)))')
    L.append(f'\t\t(property "Value" "{value}"\n\t\t\t(at {x:.3f} {y:.3f} 0)\n\t\t\t'
             '(effects (font (size 1.27 1.27))))')
    L.append(f'\t\t(property "Footprint" ""\n\t\t\t(at {x:.3f} {y:.3f} 0)\n\t\t\t'
             '(effects (font (size 1.27 1.27)) (hide yes)))')
    L.append(f'\t\t(property "Datasheet" ""\n\t\t\t(at {x:.3f} {y:.3f} 0)\n\t\t\t'
             '(effects (font (size 1.27 1.27)) (hide yes)))')
    L.append(f'\t\t(pin "1"\n\t\t\t(uuid "{U()}"))')
    L.append(f'\t\t(instances\n\t\t\t(project "{PROJECT}"\n\t\t\t\t'
             f'(path "/{ROOT}"\n\t\t\t\t\t(reference "{r}")\n\t\t\t\t\t(unit 1))))')
    L.append("\t)")


# ── net pin map + decide which signal nets get a wire ─────────────────────────
netpins = {}
for p in parts:
    for pin in p["pins"]:
        if pin["net"]:
            netpins.setdefault(pin["net"], []).append(pinabs(p, pin))
wired = set()
for net, pts in netpins.items():
    if net in POWER_NETS or len(pts) != 2:
        continue
    (x1, y1), (x2, y2) = pts
    if abs(x1 - x2) + abs(y1 - y2) <= WIRE_MAX:
        wired.add(net)

# ── emit ─────────────────────────────────────────────────────────────────────
ROOT = U()
L = [f'(kicad_sch\n\t(version 20250114)\n\t(generator "eeschema")\n\t'
     f'(generator_version "10.0")\n\t(uuid "{ROOT}")\n\t(paper "{PAPER}")',
     '\t(title_block\n\t\t(title "the-card")\n\t\t(date "2026-08-06")\n'
     f'\t\t(rev "{DESIGN_VERSION}")\n\t\t'
     '(company "ESP32-S3 e-paper smart badge")\n\t)']

power_used = {pin["net"] for p in parts for pin in p["pins"] if pin["net"] in POWER_NETS}
pwr_first = {}
L.append("\t(lib_symbols")
seen = set()
for p in parts:
    key = (p["lib"], p["name"])
    if key in seen or p["name"] not in SYMS:
        continue
    seen.add(key)
    blk = SYMS[p["name"]].replace(f'(symbol "{p["name"]}"', f'(symbol "{p["lib"]}:{p["name"]}"', 1)
    L.append(re.sub(r'\(pin \w+ line', '(pin passive line', blk))
for net in sorted(power_used):
    L.append(power_block(net))
L.append(PW["PWR_FLAG"].replace('(symbol "PWR_FLAG"', '(symbol "power:PWR_FLAG"', 1))
L.append("\t)")

# part instances
for p in parts:
    x, y, rot = p["x"], p["y"], p["rot"]
    L.append("\t(symbol")
    L.append(f'\t\t(lib_id "{p["lib"]}:{p["name"]}")\n\t\t(at {x} {y} {rot})\n\t\t'
             '(unit 1)\n\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t'
             '(on_board yes)\n\t\t(dnp no)')
    L.append(f'\t\t(uuid "{U()}")')
    L.append(f'\t\t(property "Reference" "{p["ref"]}"\n\t\t\t(at {x} {y - 8} 0)\n\t\t\t'
             '(effects (font (size 1.6 1.6))))')
    L.append(f'\t\t(property "Value" "{p["value"]}"\n\t\t\t(at {x} {y + 8} 0)\n\t\t\t'
             '(effects (font (size 1.4 1.4))))')
    L.append(f'\t\t(property "Footprint" "{p["fp"]}"\n\t\t\t(at {x} {y} 0)\n\t\t\t'
             '(effects (font (size 1.27 1.27)) (hide yes)))')
    L.append(f'\t\t(property "Datasheet" ""\n\t\t\t(at {x} {y} 0)\n\t\t\t'
             '(effects (font (size 1.27 1.27)) (hide yes)))')
    for pin in p["pins"]:
        L.append(f'\t\t(pin "{pin["num"]}"\n\t\t\t(uuid "{U()}"))')
    L.append(f'\t\t(instances\n\t\t\t(project "{PROJECT}"\n\t\t\t\t'
             f'(path "/{ROOT}"\n\t\t\t\t\t(reference "{p["ref"]}")\n\t\t\t\t\t(unit 1))))')
    L.append("\t)")
    for pin in p["pins"]:
        ax, ay = pinabs(p, pin)
        if not pin["net"]:
            L.append(f'\t\t(no_connect\n\t\t\t(at {ax:.3f} {ay:.3f})\n\t\t\t(uuid "{U()}"))')
        elif pin["net"] in POWER_NETS:
            pwr_first.setdefault(pin["net"], (ax, ay))
            emit_pwr(L, f'power:{pin["net"]}', pin["net"], ax, ay)
        elif pin["net"] in wired:
            pass  # connected by a wire (emitted below)
        else:
            L.append(f'\t(label "{pin["net"]}"\n\t\t(at {ax:.3f} {ay:.3f} 0)\n\t\t'
                     f'(effects (font (size 1.1 1.1)) (justify left bottom))\n\t\t(uuid "{U()}"))')

# direct wires for close 2-pin signal nets
for net in wired:
    (x1, y1), (x2, y2) = netpins[net]
    L.append(f'\t\t(wire (pts (xy {x1:.3f} {y1:.3f}) (xy {x2:.3f} {y1:.3f}))\n\t\t\t(uuid "{U()}"))' if x1 != x2 else "")
    L.append(f'\t\t(wire (pts (xy {x2:.3f} {y1:.3f}) (xy {x2:.3f} {y2:.3f}))\n\t\t\t(uuid "{U()}"))' if y1 != y2 else "")
L = [x for x in L if x]  # drop blanks from straight wires

# one PWR_FLAG per power rail
for net, (fx, fy) in pwr_first.items():
    emit_pwr(L, "power:PWR_FLAG", "PWR_FLAG", fx, fy)

L.append('\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")))\n\t(embedded_fonts no)\n)')
open(OUT, "w").write("\n".join(L))
miss = sorted({p["name"] for p in parts} - set(SYMS))
print(f"OK wrote {OUT}  parts={len(parts)} wires={len(wired)} power={sorted(power_used)}")
if miss:
    print(f"   ⚠ missing symbols: {miss}")
