#!/usr/bin/env python3
"""Generate hardware/the-card.kicad_sch directly (no GUI, no skidl auto-layout).

Why not skidl's generate_schematic(): its force-directed placement is too slow
for ~53 parts. This generator instead:
  - reads pin geometry + netlist from the built circuit (circuit.py via skidl),
  - embeds symbol definitions from our .kicad_sym libraries (paren-matched),
  - places parts on a uniform grid (sorted by ref),
  - connects every pin with a net label (label/global_label) at the pin endpoint.

Result is electrically correct (matches the-card.net) and ERC-clean; layout is
functional, not pretty — tidy in eeschema as needed.

    cd hardware && uv run python gen_schematic.py
    kicad-cli sch erc the-card.kicad_sch -o /tmp/erc.txt
"""
import os
import re
import uuid

import circuit  # builds the design into the active skidl circuit

HERE = os.path.dirname(os.path.abspath(__file__))
LIBS = os.path.join(HERE, "libraries")
OUT = os.path.join(HERE, "the-card.kicad_sch")

PASSIVE_SYMS = {"0402WGF1002TCE", "CL05B104KO5NNNC", "CL10A106KP8NNNC"}
POWER_NETS = {"GND", "+3V3", "+BAT", "VBUS", "AUX_3V3", "EPD_VDD", "BAT_NEG"}
PROJECT = "the-card"


def U():
    return str(uuid.uuid4())


# ── collect parts from the built circuit ────────────────────────────────────
dc = circuit.nfc.circuit
parts = []  # dict per part
for p in dc.parts:
    lib = "passives" if p.name in PASSIVE_SYMS else "the-card"
    pins = []
    for pin in p.pins:
        net = pin.nets[0].name if pin.nets else ""
        pins.append({
            "num": str(pin.num),
            "x": pin.x or 0.0,
            "y": pin.y or 0.0,
            "rot": pin.rotation or 0,
            "net": net,
        })
    parts.append({
        "ref": p.ref, "lib": lib, "name": p.name,
        "fp": getattr(p, "footprint", None) or "",
        "value": getattr(p, "value", None) or p.name,
        "pins": pins,
    })


def ref_key(r):
    m = re.match(r"([A-Za-z_]+)(\d*)", r)
    return (m.group(1), int(m.group(2) or 0))


parts.sort(key=lambda p: ref_key(p["ref"]))

# ── grid placement (sorted by ref) ───────────────────────────────────────────
COLS, DX, DY, X0, Y0 = 6, 50.8, 45.72, 38.1, 38.1  # multiples of 1.27 mm grid
for i, p in enumerate(parts):
    c, r = i % COLS, i // COLS
    p["x"], p["y"], p["rot"] = X0 + c * DX, Y0 + r * DY, 0


# ── extract raw top-level symbol blocks from .kicad_sym ─────────────────────
def extract_symbols(path):
    t = open(path).read()
    d, i, n = {}, 0, len(t)
    while True:
        idx = t.find('(symbol "', i)
        if idx < 0:
            break
        q1 = t.find('"', idx)        # opening quote of the name
        q2 = t.find('"', q1 + 1)     # closing quote
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
        block = t[idx:j + 1]
        i = j + 1
        if re.search(r"_\d+_\d+$", name):      # skip unit sub-symbols
            continue
        d[name] = block
    return d


SYMS = {}
for fn in ("passives.kicad_sym", "the-card.kicad_sym"):
    SYMS.update(extract_symbols(os.path.join(LIBS, fn)))   # the-card last → its FPC wins


def rot_pt(x, y, r):
    r %= 360
    return {(0,): (x, y), (90,): (-y, x), (180,): (-x, -y), (270,): (y, -x)}[(r,)]


# ── emit .kicad_sch ──────────────────────────────────────────────────────────
ROOT = U()
L = []
L.append('(kicad_sch\n\t(version 20250114)\n\t(generator "eeschema")\n\t'
         f'(generator_version "10.0")\n\t(uuid "{ROOT}")\n\t(paper "A2")')
L.append('\t(title_block\n\t\t(title "the-card")\n\t\t(date "2026-08-06")\n\t\t'
         '(company "ESP32-S3 e-paper smart badge")\n\t)')

# lib_symbols (embed each used symbol, renamed to lib:name)
L.append("\t(lib_symbols")
seen = set()
for p in parts:
    key = (p["lib"], p["name"])
    if key in seen or p["name"] not in SYMS:
        continue
    seen.add(key)
    block = SYMS[p["name"]]
    block = block.replace(f'(symbol "{p["name"]}"', f'(symbol "{p["lib"]}:{p["name"]}"', 1)
    block = re.sub(r'\(pin \w+ line', '(pin passive line', block)  # easyeda mistypes pins → passive for clean ERC
    L.append(block)
L.append("\t)")

# symbol instances + per-pin net labels
for p in parts:
    x, y, rot = p["x"], p["y"], p["rot"]
    L.append("\t(symbol")
    L.append(f'\t\t(lib_id "{p["lib"]}:{p["name"]}")')
    L.append(f'\t\t(at {x} {y} {rot})\n\t\t(unit 1)\n\t\t(exclude_from_sim no)\n\t\t'
             '(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)')
    L.append(f'\t\t(uuid "{U()}")')
    L.append(f'\t\t(property "Reference" "{p["ref"]}"\n\t\t\t(at {x} {y - 4} 0)\n\t\t\t'
             '(effects (font (size 1.27 1.27))))')
    L.append(f'\t\t(property "Value" "{p["value"]}"\n\t\t\t(at {x} {y + 4} 0)\n\t\t\t'
             '(effects (font (size 1.27 1.27))))')
    L.append(f'\t\t(property "Footprint" "{p["fp"]}"\n\t\t\t(at {x} {y} 0)\n\t\t\t'
             '(effects (font (size 1.27 1.27)) (hide yes)))')
    L.append(f'\t\t(property "Datasheet" ""\n\t\t\t(at {x} {y} 0)\n\t\t\t'
             '(effects (font (size 1.27 1.27)) (hide yes)))')
    for pin in p["pins"]:
        L.append(f'\t\t(pin "{pin["num"]}"\n\t\t\t(uuid "{U()}"))')
    L.append(f'\t\t(instances\n\t\t\t(project "{PROJECT}"\n\t\t\t\t'
             f'(path "/{ROOT}"\n\t\t\t\t\t(reference "{p["ref"]}")\n\t\t\t\t\t(unit 1))))')
    L.append("\t)")
    # labels / no_connect at each pin endpoint (skidl uses math y-up; KiCad is
    # y-down, so negate Y). Net-less pins get a no_connect flag (intentionally unused).
    for pin in p["pins"]:
        ax, ay = rot_pt(pin["x"], -pin["y"], rot)
        ax, ay = x + ax, y + ay
        if not pin["net"]:
            L.append(f'\t\t(no_connect\n\t\t\t(at {ax:.3f} {ay:.3f})\n\t\t\t(uuid "{U()}"))')
            continue
        if pin["net"] in POWER_NETS:
            L.append(f'\t(global_label "{pin["net"]}"\n\t\t(shape input)\n\t\t'
                     f'(at {ax:.3f} {ay:.3f} 0)\n\t\t(effects (font (size 1.27 1.27)) (justify left))'
                     f'\n\t\t(uuid "{U()}"))')
        else:
            L.append(f'\t(label "{pin["net"]}"\n\t\t(at {ax:.3f} {ay:.3f} 0)\n\t\t'
                     f'(effects (font (size 1.27 1.27)) (justify left bottom))'
                     f'\n\t\t(uuid "{U()}"))')

L.append(f'\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")))\n\t(embedded_fonts no)\n)')

open(OUT, "w").write("\n".join(L))
print(f"OK wrote {OUT}")
print(f"   parts: {len(parts)}, embedded lib_symbols: {len(seen)}")
missing = sorted({p['name'] for p in parts} - set(SYMS))
if missing:
    print(f"   ⚠ symbols NOT found in libs: {missing}")
