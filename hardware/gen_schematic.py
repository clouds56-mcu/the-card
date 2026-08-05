#!/usr/bin/env python3
"""Generate hardware/the-card.kicad_sch directly — v2 (grouped + power symbols).

  - parts grouped by subsystem (POWER / MCU / DISPLAY / SENSORS / UI), each in its
    own labelled band instead of sorted-by-ref;
  - power rails (GND/+3V3/+BAT/VBUS/AUX_3V3/EPD_VDD) use real KiCad power symbols
    from the installed power.kicad_sym, with one PWR_FLAG per rail (power_out pin
    satisfies ERC's "power input not driven");
  - signals use net labels; intentionally-unused pins get no_connect.

    cd hardware && uv run python gen_schematic.py
    kicad-cli sch erc the-card.kicad_sch -o /tmp/erc.txt   # expect 0 errors
"""
import os
import re
import uuid

import circuit

HERE = os.path.dirname(os.path.abspath(__file__))
LIBS = os.path.join(HERE, "libraries")
OUT = os.path.join(HERE, "the-card.kicad_sch")
POWER_LIB = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols/power.kicad_sym"
PROJECT = "the-card"

PASSIVE_SYMS = {"0402WGF1002TCE", "CL05B104KO5NNNC", "CL10A106KP8NNNC"}
POWER_NETS = {"GND", "+3V3", "+BAT", "VBUS", "AUX_3V3", "EPD_VDD"}  # BAT_NEG stays a label

_pwr = 0
def pwref():
    global _pwr; _pwr += 1
    return f"#PWR{_pwr:04d}"

def U():
    return str(uuid.uuid4())


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


# ── subsystem bands ──────────────────────────────────────────────────────────
GROUPS = {
    "POWER SUPPLY & CHARGING": [
        "J1", "U10", "U6", "U7", "U8", "U9", "U5", "Q1", "Q2",
        "R_prog", "R_dvcc", "R_dvm", "R_chrg", "R_q1g", "R_q2g",
        "C_bat", "C_vbus", "C_dprot", "C_ldoi", "C_ldoo", "C_fg"],
    "MCU — ESP32-S3": [
        "U1", "C_mcu1", "C_mcu2", "C_en", "C_vb", "R_en", "R_io0", "R_vbh", "R_vbl"],
    "E-INK DISPLAY": ["J2", "C_epdvdd"],
    "SENSORS & NFC (I2C)": [
        "U2", "U3", "U4", "C_nfc", "C_imu1", "C_imu2", "C_sht", "R_scl", "R_sda"],
    "USER INTERFACE": [
        "D1", "SW1", "SW2", "SW3", "SW4", "C_led", "C_btn1", "C_btn2", "C_btn3", "C_btn4"],
}
GX0, BAND_H, PART_DX, ROW_DY, MAXX = 38.1, 88.9, 25.4, 38.1, 533.4  # 1.27 mm grid
occupied = {}  # pin-endpoint coord -> net (avoid cross-net collisions)

def _pincoords(pr, x, y):
    return {(round(x + pin["x"], 3), round(y - pin["y"], 3)): pin["net"] for pin in pr["pins"]}

def _clear(pr, sx, sy):
    x, y = sx, sy
    for _ in range(6000):
        pc = _pincoords(pr, x, y)
        if all((c not in occupied) or (occupied[c] == net) for c, net in pc.items()):
            for c, net in pc.items():
                occupied[c] = net
            return x, y
        x = x + 2.54 if x + 2.54 <= MAXX else GX0
        if x == GX0:
            y += ROW_DY
    return x, y

for gi, (title, refs) in enumerate(GROUPS.items()):
    cx = GX0
    for ref in refs:
        pr = next((p for p in parts if p["ref"] == ref), None)
        if pr is None:
            continue
        x, y = _clear(pr, cx, 50.8 + gi * BAND_H)
        pr["x"], pr["y"], pr["rot"] = x, y, 0
        cx = x + PART_DX
cx = GX0
for p in parts:
    if "x" not in p:
        x, y = _clear(p, cx, 50.8 + len(GROUPS) * BAND_H)
        p["x"], p["y"], p["rot"] = x, y, 0
        cx = x + PART_DX
PAPER = "A1"


# ── extract raw symbol blocks ────────────────────────────────────────────────
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
    if net in PW:
        blk = PW[net]
    else:
        blk = PW["+3V3"].replace("+3V3", net)
    return blk.replace(f'(symbol "{net}"', f'(symbol "power:{net}"', 1)


def rot_pt(x, y, r):
    r %= 360
    return {(0,): (x, y), (90,): (-y, x), (180,): (-x, -y), (270,): (y, -x)}[(r,)]


def emit_power_inst(L, lib_id, value, x, y):
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


# ── emit ─────────────────────────────────────────────────────────────────────
ROOT = U()
L = [f'(kicad_sch\n\t(version 20250114)\n\t(generator "eeschema")\n\t'
     f'(generator_version "10.0")\n\t(uuid "{ROOT}")\n\t(paper "{PAPER}")',
     '\t(title_block\n\t\t(title "the-card")\n\t\t(date "2026-08-06")\n\t\t'
     '(company "ESP32-S3 e-paper smart badge")\n\t)']

power_used, pwr_first = set(), {}
L.append("\t(lib_symbols")
seen = set()
for p in parts:
    key = (p["lib"], p["name"])
    if key in seen or p["name"] not in SYMS:
        continue
    seen.add(key)
    blk = SYMS[p["name"]].replace(f'(symbol "{p["name"]}"', f'(symbol "{p["lib"]}:{p["name"]}"', 1)
    blk = re.sub(r'\(pin \w+ line', '(pin passive line', blk)
    L.append(blk)
    for pin in p["pins"]:
        if pin["net"] in POWER_NETS:
            power_used.add(pin["net"])
for net in sorted(power_used):
    L.append(power_block(net))
L.append(PW["PWR_FLAG"].replace('(symbol "PWR_FLAG"', '(symbol "power:PWR_FLAG"', 1))
L.append("\t)")

for title in GROUPS:
    gy = 50.8 + list(GROUPS).index(title) * BAND_H
    L.append(f'\t(text "{title}"\n\t\t(at {GX0 - 5} {gy - 15} 0)\n\t\t'
             f'(effects (font (size 3.5 3.5) bold) (justify left)))')

for p in parts:
    x, y, rot = p["x"], p["y"], p["rot"]
    L.append("\t(symbol")
    L.append(f'\t\t(lib_id "{p["lib"]}:{p["name"]}")\n\t\t(at {x} {y} {rot})\n\t\t'
             '(unit 1)\n\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t'
             '(on_board yes)\n\t\t(dnp no)')
    L.append(f'\t\t(uuid "{U()}")')
    L.append(f'\t\t(property "Reference" "{p["ref"]}"\n\t\t\t(at {x} {y - 6} 0)\n\t\t\t'
             '(effects (font (size 1.5 1.5))))')
    L.append(f'\t\t(property "Value" "{p["value"]}"\n\t\t\t(at {x} {y + 6} 0)\n\t\t\t'
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
        ax, ay = rot_pt(pin["x"], -pin["y"], rot)
        ax, ay = x + ax, y + ay
        if not pin["net"]:
            L.append(f'\t\t(no_connect\n\t\t\t(at {ax:.3f} {ay:.3f})\n\t\t\t(uuid "{U()}"))')
        elif pin["net"] in POWER_NETS:
            pwr_first.setdefault(pin["net"], (ax, ay))
            emit_power_inst(L, f'power:{pin["net"]}', pin["net"], ax, ay)
        else:
            L.append(f'\t(label "{pin["net"]}"\n\t\t(at {ax:.3f} {ay:.3f} 0)\n\t\t'
                     f'(effects (font (size 1.1 1.1)) (justify left bottom))\n\t\t(uuid "{U()}"))')

# one PWR_FLAG per power rail (power_out pin satisfies "power input not driven")
for net, (fx, fy) in pwr_first.items():
    emit_power_inst(L, "power:PWR_FLAG", "PWR_FLAG", fx, fy)

L.append('\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")))\n\t(embedded_fonts no)\n)')
open(OUT, "w").write("\n".join(L))
miss = sorted({p["name"] for p in parts} - set(SYMS))
print(f"OK wrote {OUT}  parts={len(parts)} groups={len(GROUPS)} paper={PAPER} power={sorted(power_used)}")
if miss:
    print(f"   ⚠ missing symbols: {miss}")
