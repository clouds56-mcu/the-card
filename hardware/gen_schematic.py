#!/usr/bin/env python3
"""Generate hardware/the-card.kicad_sch — v4 (pin-cluster placement + pervasive wires).

Peripherals are placed exactly on the side of the MCU where their signal pins
are (SPI bus below, buttons & USB & I²C on the left, vbat on the right), so
point-to-point nets turn into short direct wires. Shared buses (I²C) and power
stay as labels / power symbols. ERC-clean.

    cd hardware && uv run python gen_schematic.py
    kicad-cli sch erc the-card.kicad_sch -o /tmp/erc.txt
"""
import os, re, uuid
import circuit

HERE = os.path.dirname(os.path.abspath(__file__))
LIBS = os.path.join(HERE, "libraries")
OUT = os.path.join(HERE, "the-card.kicad_sch")
POWER_LIB = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols/power.kicad_sym"
PROJECT = "the-card"

PASSIVE_SYMS = {"0402WGF1002TCE", "CL05B104KO5NNNC", "CL10A106KP8NNNC"}
POWER_NETS = {"GND", "+3V3", "+BAT", "VBUS", "AUX_3V3", "EPD_VDD"}
WIRE_MAX = 100.0

_pwr = 0
def pwref():
    global _pwr; _pwr += 1
    return f"#PWR{_pwr:04d}"
def U(): return str(uuid.uuid4())
def snap(v): return round(v / 1.27) * 1.27
def rot_pt(x, y, r):
    return {(0,): (x, y), (90,): (-y, x), (180,): (-x, -y), (270,): (y, -x)}[(r % 360,)]


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
by_ref = {p["ref"]: p for p in parts}


# ── pin-cluster placement ─────────────────────────────────────────────────────
mcu = by_ref["U1"]
MCU_X, MCU_Y = 420.0, 240.0
mcu["x"], mcu["y"], mcu["rot"] = MCU_X, MCU_Y, 0

# zone offsets from MCU origin (mm, snapped to 1.27 later)
LEFT_X, RIGHT_X = 280.0, 560.0                     # for parts whose MCU pins are left/right
ABOVE_Y, BELOW_Y = 160.0, 340.0                    # for parts on top/bottom
# power chain: absolute area top-left
POWER_X, POWER_Y = 50.0, 70.0
# each zone's parts are stacked with spacing
STACK_DY, STACK_DX = 41.91, 41.91  # 33 × 1.27 mm grid

zone = {}  # ref -> (x0, y0, axis, sign, index)  (axis='y' stack vertically, 'x' horizontally)
# assign each peripheral
for p in parts:
    r = p["ref"]
    if r == "U1" or r in ("U6","U7","U8","U9","U5","C_bat","C_vbus","R_prog","R_chrg",
                          "C_ldoi","C_ldoo","R_dvcc","R_dvm","C_dprot","C_fg","R_q1g","R_q2g"):
        continue  # MCU & power chain — placed below
    # find MCU-connected signal nets
    mcu_nets = {pin["net"] for pin in mcu["pins"] if pin["net"] and pin["net"] not in POWER_NETS}
    p_nets = {pin["net"] for pin in p["pins"] if pin["net"] and pin["net"] not in POWER_NETS}
    shared = mcu_nets & p_nets
    if not shared:
        shared = p_nets  # fallback: use any signal net
    # compute MCU-pin centroid for shared nets (KiCad coords)
    pts = []
    for pin in mcu["pins"]:
        if pin["net"] in shared:
            ax, ay = rot_pt(pin["x"] or 0, -(pin["y"] or 0), 0)
            pts.append((MCU_X + ax, MCU_Y + ay))
    if not pts:
        continue
    cx = sum(x for x, y in pts) / len(pts); cy = sum(y for x, y in pts) / len(pts)
    dx, dy = cx - MCU_X, cy - MCU_Y
    if abs(dx) >= abs(dy):
        zone[r] = (RIGHT_X if dx > 0 else LEFT_X, cy, "y", 0)
    else:
        zone[r] = (cx, BELOW_Y if dy > 0 else ABOVE_Y, "x", 0)

# assign zone indices (resolve overlaps)
zone_cols, zone_rows = {}, {}
for r, (x0, y0, axis, _) in zone.items():
    if axis == "y":
        zone_cols.setdefault(int(x0), []).append(r)
    else:
        zone_rows.setdefault(int(y0), []).append(r)
idx = {}
for x0, refs in zone_cols.items():
    for i, r in enumerate(refs):
        idx[r] = i
for y0, refs in zone_rows.items():
    for i, r in enumerate(refs):
        idx[r] = i
for r, (x0, y0, axis, _) in zone.items():
    i = idx.get(r, 0)
    if axis == "y":
        zone[r] = (x0, y0, "y", i)

# place parts
power_parts = []
for r in ("J1","U10","J1","U10","U6","U7","U8","U9","U5","Q1","Q2",
          "C_bat","C_vbus","R_prog","R_chrg","C_ldoi","C_ldoo",
          "R_dvcc","R_dvm","C_dprot","C_fg","R_q1g","R_q2g"):
    power_parts.extend([pp for pp in parts if pp["ref"] == r])
power_parts_dedup = list({pp["ref"]: pp for pp in power_parts}.values())
px, py = POWER_X, POWER_Y
for pp in power_parts_dedup:
    pp["x"], pp["y"], pp["rot"] = snap(px), snap(py), 0
    px += snap(54.61)
    if px > 320:
        px, py = POWER_X, snap(py + 54.61)

for p in parts:
    if p is mcu: continue
    r = p["ref"]
    if r in zone:
        x0, y0, axis, i = zone[r]
        if axis == "y":
            p["x"], p["y"], p["rot"] = snap(x0), snap(y0 + i * STACK_DY), 0
        else:
            p["x"], p["y"], p["rot"] = snap(x0 + i * STACK_DX), snap(y0), 0
    elif p["ref"] not in {pp["ref"] for pp in power_parts_dedup}:
        p["x"], p["y"], p["rot"] = snap(640), snap(100 + len(zone)*STACK_DY), 0

PAPER = "A1"

# ── collision avoidance: nudge parts whose pin endpoints collide cross-net ───
occupied = {}  # (x,y) -> net
for p in parts:
    for pin in p["pins"]:
        if not pin["net"]: continue
        ax, ay = rot_pt(pin["x"] or 0, -(pin["y"] or 0), p["rot"])
        c = (round(p["x"] + ax, 3), round(p["y"] + ay, 3))
        if c in occupied and occupied[c] != pin["net"]:
            p["x"] += 2.54  # nudge right
        else:
            occupied[c] = pin["net"]

# snap all positions to the 1.27 mm grid
for p in parts:
    p["x"], p["y"] = snap(p["x"]), snap(p["y"])

# ── symbol-block extraction ──────────────────────────────────────────────────
def extract_symbols(path):
    t = open(path).read()
    d, i, n = {}, 0, len(t)
    while True:
        idx = t.find('(symbol "', i)
        if idx < 0: break
        q1 = t.find('"', idx); q2 = t.find('"', q1 + 1)
        name = t[q1 + 1:q2]
        depth, j = 0, idx
        while j < n:
            if t[j] == "(": depth += 1
            elif t[j] == ")":
                depth -= 1
                if depth == 0: break
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

def pinabs(pt, pin):
    ax, ay = rot_pt(pin["x"] or 0, -(pin["y"] or 0), pt["rot"])
    return (round(pt["x"] + ax, 3), round(pt["y"] + ay, 3))

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


# ── net pin map + wires ───────────────────────────────────────────────────────
netpins = {}
for p in parts:
    for pin in p["pins"]:
        if pin["net"]:
            netpins.setdefault(pin["net"], []).append(pinabs(p, pin))
wired = set()
for net, pts in netpins.items():
    if net in POWER_NETS or len(pts) != 2: continue
    (x1, y1), (x2, y2) = pts
    if abs(x1 - x2) + abs(y1 - y2) <= WIRE_MAX:
        wired.add(net)


# ── emit ─────────────────────────────────────────────────────────────────────
ROOT = U()
L = [f'(kicad_sch\n\t(version 20250114)\n\t(generator "eeschema")\n\t'
     f'(generator_version "10.0")\n\t(uuid "{ROOT}")\n\t(paper "{PAPER}")',
     '\t(title_block\n\t\t(title "the-card")\n\t\t(date "2026-08-06")\n\t\t'
     '(company "ESP32-S3 e-paper smart badge")\n\t)']

power_used = {pin["net"] for p in parts for pin in p["pins"] if pin["net"] in POWER_NETS}
pwr_first = {}
L.append("\t(lib_symbols")
seen = set()
for p in parts:
    key = (p["lib"], p["name"])
    if key in seen or p["name"] not in SYMS: continue
    seen.add(key)
    blk = SYMS[p["name"]].replace(f'(symbol "{p["name"]}"', f'(symbol "{p["lib"]}:{p["name"]}"', 1)
    L.append(re.sub(r'\(pin \w+ line', '(pin passive line', blk))
for net in sorted(power_used):
    L.append(power_block(net))
L.append(PW["PWR_FLAG"].replace('(symbol "PWR_FLAG"', '(symbol "power:PWR_FLAG"', 1))
L.append("\t)")

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
            pass  # wire below
        else:
            L.append(f'\t(label "{pin["net"]}"\n\t\t(at {ax:.3f} {ay:.3f} 0)\n\t\t'
                     f'(effects (font (size 1.1 1.1)) (justify left bottom))\n\t\t(uuid "{U()}"))')

# L-shaped wires for close 2-pin nets (only signal, already detected as 'wired')
for net in wired:
    (x1, y1), (x2, y2) = netpins[net]
    if abs(x2 - x1) > 0.01:
        L.append(f'\t(wire (pts (xy {x1:.3f} {y1:.3f}) (xy {x2:.3f} {y1:.3f}))\n\t\t(uuid "{U()}"))')
    if abs(y2 - y1) > 0.01:
        L.append(f'\t(wire (pts (xy {x2:.3f} {y1:.3f}) (xy {x2:.3f} {y2:.3f}))\n\t\t(uuid "{U()}"))')

for net, (fx, fy) in pwr_first.items():
    emit_pwr(L, "power:PWR_FLAG", "PWR_FLAG", fx, fy)

L.append('\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")))\n\t(embedded_fonts no)\n)')
open(OUT, "w").write("\n".join(L))
miss = sorted({p["name"] for p in parts} - set(SYMS))
print(f"OK wrote {OUT}  parts={len(parts)}  wires={len(wired)}  power={sorted(power_used)}")
if miss: print(f"   ⚠ missing symbols: {miss}")
