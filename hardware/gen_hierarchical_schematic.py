#!/usr/bin/env python3
"""Generate a deterministic, hand-laid-out single-page KiCad schematic.

`circuit.py` remains the electrical source of truth. This module only decides
how the already-built circuit is split across sheets and drawn. It deliberately
does not use SKiDL's force-directed schematic placer: this design is small
enough that an explicit signal-flow layout is clearer and produces stable diffs.

Run from `hardware/`:

    uv run python gen_hierarchical_schematic.py

The output is `the-card.kicad_sch`, an A2 landscape drawing divided into five
functional regions. All coordinates are on KiCad's 1.27 mm connection grid.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import circuit


HERE = Path(__file__).resolve().parent
LIBS = HERE / "libraries"
POWER_LIB = Path(
  "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols/power.kicad_sym"
)
STANDARD_SYMBOL_DIR = Path(
  "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
)
PROJECT = "the-card"
TITLE = "the-card - ESP32-S3 e-paper smart badge"
DATE = "2026-08-09"
GRID = 1.27
NAMESPACE = uuid.UUID("fc4df8d7-161d-494c-8bdb-f31f5ce3a8c0")

PASSIVE_SYMS = {"0402WGF1002TCE", "CL05B104KO5NNNC", "CL10A106KP8NNNC"}
STANDARD_SYMBOL_LIBS = {
  "Conn_01x02": "Connector_Generic",
  "D": "Device",
  "L": "Device",
  "Q_NMOS_GSD": "Transistor_FET",
  "TestPoint": "Connector",
}
SYMBOL_POWER_NETS = {"GND", "+3V3", "VBUS"}
CUSTOM_POWER_NETS = {"+BAT", "AUX_3V3", "EPD_VCI"}


def uid(*parts: object) -> str:
  """Return a stable UUID so regeneration produces reviewable diffs."""
  return str(uuid.uuid5(NAMESPACE, "::".join(str(part) for part in parts)))


def esc(value: object) -> str:
  return str(value).replace("\\", "\\\\").replace('"', '\\"')


def g(value: float) -> float:
  """Convert grid units to millimetres."""
  return round(value * GRID, 3)


def snap(value: float) -> float:
  return round(round(value / GRID) * GRID, 3)


def fmt(value: float) -> str:
  return f"{value:.3f}".rstrip("0").rstrip(".")


@dataclass(frozen=True)
class Placement:
  x: float
  y: float
  rotation: int = 0


@dataclass(frozen=True)
class SheetSpec:
  key: str
  refs: frozenset[str]
  placements: dict[str, Placement]
  notes: tuple[tuple[str, float, float, float], ...]


def p(x: float, y: float, rotation: int = 0) -> Placement:
  return Placement(g(x), g(y), rotation)


SHEETS = (
  SheetSpec(
    key="power_usb",
    refs=frozenset({
      "J1", "J3", "U10", "R_cc1", "R_cc2", "C_vbus",
      "U6", "R_prog", "R_chrg", "C_bat",
      "U7", "U8", "R_dvcc", "R_dvm", "C_dprot",
      "U9", "C_ldoi", "C_ldoo", "U5", "C_fg",
      "Q1", "R_q1g", "Q2", "R_q2g",
      "TP1", "TP2", "TP3", "TP4",
    }),
    placements={
      "J1": p(65, 50),
      "J3": p(20, 140),
      "U10": p(25, 50, 180),
      "R_cc1": p(47, 37),
      "R_cc2": p(47, 65),
      "C_vbus": p(112, 76, 270),
      "U6": p(125, 50),
      "R_prog": p(103, 50, 180),
      "R_chrg": p(135, 38, 270),
      "C_bat": p(142, 76, 270),
      "U9": p(190, 50),
      "C_ldoi": p(176, 76, 270),
      "C_ldoo": p(205, 76, 270),
      "U5": p(265, 50),
      "C_fg": p(240, 76, 270),
      "U7": p(75, 130, 180),
      "U8": p(120, 130),
      "R_dvcc": p(48, 118),
      "R_dvm": p(95, 130, 180),
      "C_dprot": p(55, 145, 270),
      "Q1": p(190, 130),
      "R_q1g": p(187, 116, 270),
      "Q2": p(245, 130),
      "R_q2g": p(242, 116, 270),
      "TP1": p(18, 152),
      "TP2": p(30, 152),
      "TP3": p(205, 152),
      "TP4": p(217, 152),
    },
    notes=(
      ("USB-C input, ESD, and charger", g(12), g(12), 1.8),
      ("3.3 V regulation and fuel gauge", g(165), g(12), 1.8),
      ("Cell protection", g(12), g(100), 1.8),
      ("Switched peripheral rails", g(165), g(100), 1.8),
    ),
  ),
  SheetSpec(
    key="mcu",
    refs=frozenset({
      "U1", "C_mcu1", "C_mcu2", "R_en", "C_en", "R_io0",
      "R_vbh", "R_vbl", "C_vb", "TP5", "TP6",
    }),
    placements={
      "U1": p(115, 70),
      "C_mcu1": p(72, 43),
      "C_mcu2": p(96, 43),
      "R_en": p(87, 58, 270),
      "C_en": p(67, 70, 270),
      "R_io0": p(148, 82, 270),
      "R_vbh": p(145, 60, 270),
      "R_vbl": p(145, 68, 270),
      "C_vb": p(158, 68, 270),
      "TP5": p(70, 102),
      "TP6": p(158, 102),
    },
    notes=(
      ("Controller, boot straps, decoupling, and battery ADC", g(12), g(12), 1.8),
      ("Named labels keep long inter-block connections readable.", g(12), g(20), 1.1),
    ),
  ),
  SheetSpec(
    key="sensors_nfc",
    refs=frozenset({
      "U2", "C_nfc", "U3", "C_imu1", "C_imu2", "U4", "C_sht",
      "R_scl", "R_sda",
    }),
    placements={
      "U2": p(50, 45),
      "C_nfc": p(78, 45, 270),
      "U3": p(52, 96),
      "C_imu1": p(84, 90, 270),
      "C_imu2": p(96, 102, 270),
      "U4": p(158, 50),
      "C_sht": p(183, 50, 270),
      "R_scl": p(112, 38, 270),
      "R_sda": p(128, 38, 270),
    },
    notes=(
      ("NFC dynamic tag", g(12), g(12), 1.8),
      ("Motion and environmental sensors", g(12), g(75), 1.8),
      ("I2C pull-ups", g(105), g(12), 1.8),
    ),
  ),
  SheetSpec(
    key="epaper",
    refs=frozenset({
      "J2", "L1", "Q3", "D2", "D3", "D4", "R_epdg", "R_epds",
      "C_epd_in", "C_epd_pump", "C_epdvdd", "C_epd_vsh2",
      "C_epd_vsh1", "C_epd_vgh", "C_epd_vsl", "C_epd_vgl",
      "C_epd_vcom",
    }),
    placements={
      "J2": p(170, 70),
      "L1": p(45, 55),
      "Q3": p(75, 70),
      "D2": p(95, 25),
      "D3": p(95, 38),
      "D4": p(105, 55),
      "R_epdg": p(65, 95, 270),
      "R_epds": p(85, 95, 270),
      "C_epd_in": p(25, 85),
      "C_epd_pump": p(58, 30),
      "C_epd_vsh2": p(130, 25),
      "C_epd_vgh": p(130, 43),
      "C_epd_vsh1": p(130, 61),
      "C_epdvdd": p(130, 79),
      "C_epd_vsl": p(130, 97),
      "C_epd_vgl": p(130, 115),
      "C_epd_vcom": p(130, 122),
    },
    notes=(
      ("GDEY029T94 24-pin FPC interface", g(12), g(12), 1.8),
      ("Panel-specific SSD1680 booster and 25 V rail capacitors", g(12), g(20), 1.1),
    ),
  ),
  SheetSpec(
    key="ui",
    refs=frozenset({
      "D1", "C_led", "SW1", "SW2", "SW3", "SW4",
      "C_btn1", "C_btn2", "C_btn3", "C_btn4",
    }),
    placements={
      "SW1": p(40, 55),
      "SW2": p(90, 55),
      "SW3": p(140, 55),
      "SW4": p(190, 55),
      "C_btn1": p(36, 67, 270),
      "C_btn2": p(86, 67, 270),
      "C_btn3": p(136, 67, 270),
      "C_btn4": p(186, 67, 270),
      "D1": p(125, 118),
      "C_led": p(88, 118, 270),
    },
    notes=(
      ("User buttons with hardware debounce", g(12), g(12), 1.8),
      ("Status LED", g(82), g(96), 1.8),
    ),
  ),
)

# Placement tables remain readable through circuit.py's semantic passive names,
# while generated KiCad references use conventional R1/C1 designators.
SHEETS = tuple(
  SheetSpec(
    key=sheet.key,
    refs=frozenset(circuit.physical_ref(ref) for ref in sheet.refs),
    placements={
      circuit.physical_ref(ref): placement
      for ref, placement in sheet.placements.items()
    },
    notes=sheet.notes,
  )
  for sheet in SHEETS
)

SHEET_BY_REF = {ref: sheet for sheet in SHEETS for ref in sheet.refs}

# Preserve each functional block's local placement and tile the blocks onto A2.
# Values are grid units and are applied before any pin or wire coordinates are
# calculated.
SINGLE_PAGE_OFFSETS = {
  "power_usb": (g(0), g(0)),
  "mcu": (g(130), g(135)),
  "sensors_nfc": (g(265), g(0)),
  "epaper": (g(270), g(165)),
  "ui": (g(0), g(165)),
}

# These shared buses are clearer as repeated named stubs than as long wires.
LABEL_EACH_NETS = {
  ("mcu", "MCU_BOOT"),
  ("mcu", "MCU_EN"),
  ("sensors_nfc", "NFC_ANTENNA"),
  ("sensors_nfc", "I2C_SCL"),
  ("sensors_nfc", "I2C_SDA"),
  ("epaper", "EPD_VCOM"),
  ("epaper", "EPD_GDR"),
  ("epaper", "EPD_RESE"),
  ("epaper", "EPD_VDD_CORE"),
  ("epaper", "EPD_VGH"),
  ("epaper", "EPD_VGL"),
  ("epaper", "EPD_VSH1"),
  ("epaper", "EPD_VSH2"),
  ("epaper", "EPD_VSL"),
}

# The FS8205A exposes its common drain on two opposite pins. Repeated labels
# communicate that internal node without drawing a misleading wire through the body.
LABEL_EACH_LOCAL_NETS = {("power_usb", "FET_DRAIN")}

# Explicit trunks keep the interleaved reversible USB-C data pins readable.
TRUNK_ROUTES = {
  ("power_usb", "N$6"): ("horizontal", g(72)),
  ("power_usb", "N$7"): ("horizontal", g(28)),
}

# Prefer these pins when a multi-pin local branch also needs a global label.
LABEL_PIN = {
  ("power_usb", "~CHRG"): ("U6", "7"),
  ("power_usb", "PWR_AUX"): ("Q1", "1"),
  ("power_usb", "EPD_PWR_EN"): ("Q2", "1"),
  ("ui", "BTN_UP"): ("SW1", "1"),
  ("ui", "BTN_DOWN"): ("SW2", "1"),
  ("ui", "BTN_SEL"): ("SW3", "1"),
  ("ui", "BTN_MENU"): ("SW4", "1"),
}


def extract_symbols(path: Path) -> dict[str, str]:
  """Extract top-level symbol blocks from a KiCad symbol library."""
  text = path.read_text()
  symbols: dict[str, str] = {}
  cursor = 0
  while True:
    start = text.find('(symbol "', cursor)
    if start < 0:
      return symbols
    q1 = text.find('"', start)
    q2 = text.find('"', q1 + 1)
    name = text[q1 + 1:q2]
    depth = 0
    end = start
    while end < len(text):
      if text[end] == "(":
        depth += 1
      elif text[end] == ")":
        depth -= 1
        if depth == 0:
          break
      end += 1
    if not re.search(r"_\d+_\d+$", name):
      symbols[name] = text[start:end + 1]
    cursor = end + 1


SYMBOLS: dict[str, str] = {}
for library_filename in ("passives.kicad_sym", "the-card.kicad_sym"):
  SYMBOLS.update(extract_symbols(LIBS / library_filename))
for library_name in sorted(set(STANDARD_SYMBOL_LIBS.values())):
  SYMBOLS.update(extract_symbols(STANDARD_SYMBOL_DIR / f"{library_name}.kicad_sym"))
POWER_SYMBOLS = extract_symbols(POWER_LIB)


def symbol_field(symbol_name: str, field_name: str) -> str:
  block = SYMBOLS[symbol_name]
  match = re.search(
    rf'\(property\s+"{re.escape(field_name)}"\s+"([^"]*)"',
    block,
    re.MULTILINE,
  )
  return match.group(1) if match else ""


def power_block(net_name: str) -> str:
  """Return an embedded power symbol, synthesizing custom rail symbols."""
  if net_name == "GND":
    # Use KiCad's familiar three-bar earth graphic. A hidden GND global label at
    # the same anchor retains the circuit's electrical net name.
    symbol_name = "Earth"
    block = POWER_SYMBOLS[symbol_name]
  elif net_name in POWER_SYMBOLS:
    symbol_name = net_name
    block = POWER_SYMBOLS[net_name]
  else:
    symbol_name = net_name
    block = POWER_SYMBOLS["+3V3"].replace("+3V3", net_name)
  block = block.replace(
    f'(symbol "{symbol_name}"', f'(symbol "power:{symbol_name}"', 1
  )
  return re.sub(r"\(pin\s+power_in\s+line", "(pin passive line", block)


def passive_symbol_block(symbol_name: str, library: str) -> str:
  block = SYMBOLS[symbol_name].replace(
    f'(symbol "{symbol_name}"', f'(symbol "{library}:{symbol_name}"', 1
  )
  return re.sub(r"\(pin\s+[^\s()]+\s+line", "(pin passive line", block)


def rot_point(x: float, y: float, rotation: int) -> tuple[float, float]:
  rotation %= 360
  if rotation == 0:
    return x, y
  if rotation == 90:
    return y, -x
  if rotation == 180:
    return -x, -y
  if rotation == 270:
    return -y, x
  raise ValueError(f"Unsupported rotation: {rotation}")


def pin_position(part: dict, pin: dict) -> tuple[float, float]:
  local_x, local_y = rot_point(pin["x"], -pin["y"], part["rotation"])
  return snap(part["x"] + local_x), snap(part["y"] + local_y)


def outward_direction(
  part: dict,
  point: tuple[float, float],
  pin: dict | None = None,
) -> str:
  if pin is not None:
    total_rotation = (pin["rotation"] + part["rotation"]) % 360
    return {
      0: "left",
      90: "down",
      180: "right",
      270: "up",
    }[total_rotation]
  dx = point[0] - part["x"]
  dy = point[1] - part["y"]
  if abs(dx) >= abs(dy):
    return "right" if dx >= 0 else "left"
  return "down" if dy >= 0 else "up"


def direction_vector(direction: str, distance: float) -> tuple[float, float]:
  return {
    "right": (distance, 0.0),
    "left": (-distance, 0.0),
    "down": (0.0, distance),
    "up": (0.0, -distance),
  }[direction]


def wire(seed: str, start: tuple[float, float], end: tuple[float, float]) -> str:
  return (
    "\t(wire\n"
    f"\t\t(pts (xy {fmt(start[0])} {fmt(start[1])}) "
    f"(xy {fmt(end[0])} {fmt(end[1])}))\n"
    "\t\t(stroke (width 0) (type default))\n"
    f"\t\t(uuid \"{uid('wire', seed, *start, *end)}\")\n"
    "\t)"
  )


def junction(seed: str, point: tuple[float, float]) -> str:
  return (
    "\t(junction\n"
    f"\t\t(at {fmt(point[0])} {fmt(point[1])})\n"
    "\t\t(diameter 0)\n"
    "\t\t(color 0 0 0 0)\n"
    f"\t\t(uuid \"{uid('junction', seed, *point)}\")\n"
    "\t)"
  )


def route_net(sheet_key: str, net_name: str, points: list[tuple[float, float]]) -> list[str]:
  """Route a small local net as an orthogonal tree."""
  unique_points = list(dict.fromkeys(points))
  if len(unique_points) < 2:
    return []
  seed = f"{sheet_key}:{net_name}"
  if len(unique_points) == 2:
    start, end = unique_points
    corner = end[0], start[1]
    result = []
    if start != corner:
      result.append(wire(seed, start, corner))
    if corner != end:
      result.append(wire(seed, corner, end))
    return result

  xs = [point[0] for point in unique_points]
  ys = [point[1] for point in unique_points]
  override = TRUNK_ROUTES.get((sheet_key, net_name))
  if override:
    axis, coordinate = override
  elif max(xs) - min(xs) >= max(ys) - min(ys):
    axis, coordinate = "horizontal", snap(sorted(ys)[len(ys) // 2])
  else:
    axis, coordinate = "vertical", snap(sorted(xs)[len(xs) // 2])

  result: list[str] = []
  if axis == "horizontal":
    trunk_start = min(xs), coordinate
    trunk_end = max(xs), coordinate
    if trunk_start != trunk_end:
      result.append(wire(seed, trunk_start, trunk_end))
    for index, point in enumerate(unique_points):
      branch = point[0], coordinate
      if point != branch:
        result.append(wire(f"{seed}:{index}", point, branch))
      if len(unique_points) > 2 and min(xs) < branch[0] < max(xs):
        result.append(junction(f"{seed}:{index}", branch))
  else:
    trunk_start = coordinate, min(ys)
    trunk_end = coordinate, max(ys)
    if trunk_start != trunk_end:
      result.append(wire(seed, trunk_start, trunk_end))
    for index, point in enumerate(unique_points):
      branch = coordinate, point[1]
      if point != branch:
        result.append(wire(f"{seed}:{index}", point, branch))
      if len(unique_points) > 2 and min(ys) < branch[1] < max(ys):
        result.append(junction(f"{seed}:{index}", branch))
  return result


def global_label(
  sheet_key: str,
  net_name: str,
  part: dict,
  point: tuple[float, float],
  pin: dict,
) -> list[str]:
  pin_number = pin["number"]
  direction = outward_direction(part, point, pin)
  is_mcu = part["ref"] == "U1"
  distance = g(5) if is_mcu else g(4)
  font_size = 0.8 if is_mcu else 1
  dx, dy = direction_vector(direction, distance)
  anchor = snap(point[0] + dx), snap(point[1] + dy)
  angle, justify = {
    "right": (0, "left"),
    "left": (180, "right"),
    "down": (270, "right"),
    "up": (90, "left"),
  }[direction]
  label = (
    f"\t(global_label \"{esc(net_name)}\"\n"
    "\t\t(shape bidirectional)\n"
    f"\t\t(at {fmt(anchor[0])} {fmt(anchor[1])} {angle})\n"
    f"\t\t(effects (font (size {fmt(font_size)} {fmt(font_size)})) "
    f"(justify {justify}))\n"
    f"\t\t(uuid \"{uid('label', sheet_key, net_name, part['ref'], pin_number)}\")\n"
    "\t)"
  )
  return [wire(f"label:{sheet_key}:{net_name}:{part['ref']}:{pin_number}", point, anchor), label]


def hidden_global_label(
  sheet_key: str,
  net_name: str,
  ref: str,
  pin_number: str,
  point: tuple[float, float],
) -> str:
  """Name a power stub while leaving the conventional power symbol visible."""
  return (
    f"\t(global_label \"{esc(net_name)}\"\n"
    "\t\t(shape bidirectional)\n"
    f"\t\t(at {fmt(point[0])} {fmt(point[1])} 0)\n"
    "\t\t(effects (font (size 0.01 0.01)) (hide yes))\n"
    f"\t\t(uuid \"{uid('hidden-power-label', sheet_key, net_name, ref, pin_number)}\")\n"
    "\t)"
  )


def power_symbol(
  ref: str,
  sheet: SheetSpec,
  net_name: str,
  point: tuple[float, float],
  direction: str,
) -> str:
  intrinsic = 90
  label_angle = {"right": 180, "left": 0, "up": 270, "down": 90}[direction]
  angle = (label_angle - intrinsic) % 360
  dx, dy = direction_vector(direction, g(2.5))
  value_x, value_y = snap(point[0] + dx), snap(point[1] + dy)
  justify = "left" if direction == "right" else "right" if direction == "left" else ""
  justify_clause = f" (justify {justify})" if justify else ""
  value_visibility = " (hide yes)" if net_name == "GND" else ""
  symbol_name = "Earth" if net_name == "GND" else net_name
  path = f"/{ROOT_UUID}"
  return (
    "\t(symbol\n"
    f"\t\t(lib_id \"power:{esc(symbol_name)}\")\n"
    f"\t\t(at {fmt(point[0])} {fmt(point[1])} {angle})\n"
    "\t\t(unit 1)\n"
    "\t\t(exclude_from_sim no)\n"
    "\t\t(in_bom no)\n"
    "\t\t(on_board yes)\n"
    "\t\t(dnp no)\n"
    f"\t\t(uuid \"{uid('power', sheet.key, ref, net_name, *point)}\")\n"
    f"\t\t(property \"Reference\" \"{ref}\"\n"
    f"\t\t\t(at {fmt(point[0])} {fmt(point[1])} 0)\n"
    "\t\t\t(effects (font (size 1 1)) (hide yes))\n"
    "\t\t)\n"
    f"\t\t(property \"Value\" \"{esc(symbol_name)}\"\n"
    f"\t\t\t(at {fmt(value_x)} {fmt(value_y)} 0)\n"
    f"\t\t\t(effects (font (size 1 1)){justify_clause}{value_visibility})\n"
    "\t\t)\n"
    f"\t\t(property \"Footprint\" \"\" (at {fmt(point[0])} {fmt(point[1])} 0) "
    "(effects (font (size 1 1)) (hide yes)))\n"
    f"\t\t(property \"Datasheet\" \"\" (at {fmt(point[0])} {fmt(point[1])} 0) "
    "(effects (font (size 1 1)) (hide yes)))\n"
    f"\t\t(pin \"1\" (uuid \"{uid('power-pin', sheet.key, ref, net_name, *point)}\"))\n"
    f"\t\t(instances (project \"{PROJECT}\" (path \"{path}\" "
    f"(reference \"{ref}\") (unit 1))))\n"
    "\t)"
  )


def no_connect(sheet_key: str, ref: str, pin_number: str, point: tuple[float, float]) -> str:
  return (
    "\t(no_connect\n"
    f"\t\t(at {fmt(point[0])} {fmt(point[1])})\n"
    f"\t\t(uuid \"{uid('no-connect', sheet_key, ref, pin_number)}\")\n"
    "\t)"
  )


def text_note(sheet_key: str, value: str, x: float, y: float, size: float) -> str:
  return (
    f"\t(text \"{esc(value)}\"\n"
    "\t\t(exclude_from_sim no)\n"
    f"\t\t(at {fmt(x)} {fmt(y)} 0)\n"
    f"\t\t(effects (font (size {fmt(size)} {fmt(size)}) (bold yes)) "
    "(justify left bottom))\n"
    f"\t\t(uuid \"{uid('text', sheet_key, value)}\")\n"
    "\t)"
  )


def build_parts() -> tuple[list[dict], dict[str, set[str]]]:
  design = circuit.nfc.circuit
  design.merge_net_names()
  design.merge_nets()
  parts: list[dict] = []
  net_sheets: dict[str, set[str]] = {}
  for skidl_part in design.parts:
    sheet = SHEET_BY_REF[skidl_part.ref]
    placement = sheet.placements[skidl_part.ref]
    offset_x, offset_y = SINGLE_PAGE_OFFSETS[sheet.key]
    if skidl_part.name in PASSIVE_SYMS:
      library = "passives"
    else:
      library = STANDARD_SYMBOL_LIBS.get(skidl_part.name, "the-card")
    pins = []
    for skidl_pin in skidl_part.pins:
      net_name = skidl_pin.nets[0].name if skidl_pin.nets else ""
      pins.append({
        "number": str(skidl_pin.num),
        "name": str(skidl_pin.name),
        "x": float(skidl_pin.x or 0.0),
        "y": float(skidl_pin.y or 0.0),
        "rotation": int(skidl_pin.rotation or 0),
        "net": net_name,
      })
      if net_name:
        net_sheets.setdefault(net_name, set()).add(sheet.key)
    footprint = getattr(skidl_part, "footprint", None) or symbol_field(
      skidl_part.name, "Footprint"
    )
    datasheet = getattr(skidl_part, "datasheet", None) or symbol_field(
      skidl_part.name, "Datasheet"
    )
    parts.append({
      "ref": skidl_part.ref,
      "name": skidl_part.name,
      "library": library,
      "value": str(getattr(skidl_part, "value", None) or skidl_part.name),
      "footprint": footprint,
      "datasheet": datasheet,
      "pins": pins,
      "sheet": sheet.key,
      "x": placement.x + offset_x,
      "y": placement.y + offset_y,
      "rotation": placement.rotation,
    })
  return parts, net_sheets


def part_instance(part: dict, sheet: SheetSpec) -> str:
  pin_points = [pin_position(part, pin) for pin in part["pins"]]
  half_height = max((abs(point[1] - part["y"]) for point in pin_points), default=g(4))
  reference_x = part["x"]
  reference_y = snap(part["y"] - half_height - g(2.5))
  reference_angle = 0
  value_x = part["x"]
  value_y = snap(part["y"] + half_height + g(2.5))
  value_angle = 0
  if part["rotation"] in {90, 270}:
    reference_x = snap(part["x"] - g(3))
    reference_y = part["y"]
    reference_angle = 90
    value_x = snap(part["x"] + g(3))
    value_y = part["y"]
    value_angle = 90
  if part["ref"] == "U1":
    value_x = part["x"]
    value_y = snap(part["y"] - g(10))
    value_angle = 0
  elif part["ref"] == "J2":
    value_x = snap(part["x"] + g(14))
    value_y = snap(part["y"] + half_height + g(5))
    value_angle = 0
  path = f"/{ROOT_UUID}"
  lines = [
    "\t(symbol",
    f"\t\t(lib_id \"{part['library']}:{part['name']}\")",
    f"\t\t(at {fmt(part['x'])} {fmt(part['y'])} {part['rotation']})",
    "\t\t(unit 1)",
    "\t\t(exclude_from_sim no)",
    "\t\t(in_bom yes)",
    "\t\t(on_board yes)",
    "\t\t(dnp no)",
    f"\t\t(uuid \"{uid('part', part['ref'])}\")",
    f"\t\t(property \"Reference\" \"{esc(part['ref'])}\"",
    f"\t\t\t(at {fmt(reference_x)} {fmt(reference_y)} {reference_angle})",
    "\t\t\t(effects (font (size 1.2 1.2) (bold yes)))",
    "\t\t)",
    f"\t\t(property \"Value\" \"{esc(part['value'])}\"",
    f"\t\t\t(at {fmt(value_x)} {fmt(value_y)} {value_angle})",
    "\t\t\t(effects (font (size 1 1)))",
    "\t\t)",
    f"\t\t(property \"Footprint\" \"{esc(part['footprint'])}\"",
    f"\t\t\t(at {fmt(part['x'])} {fmt(part['y'])} 0)",
    "\t\t\t(effects (font (size 1 1)) (hide yes))",
    "\t\t)",
    f"\t\t(property \"Datasheet\" \"{esc(part['datasheet'])}\"",
    f"\t\t\t(at {fmt(part['x'])} {fmt(part['y'])} 0)",
    "\t\t\t(effects (font (size 1 1)) (hide yes))",
    "\t\t)",
  ]
  for pin in part["pins"]:
    lines.append(
      f"\t\t(pin \"{esc(pin['number'])}\" "
      f"(uuid \"{uid('part-pin', part['ref'], pin['number'])}\"))"
    )
  lines.extend([
    f"\t\t(instances (project \"{PROJECT}\" (path \"{path}\"",
    f"\t\t\t(reference \"{esc(part['ref'])}\") (unit 1))))",
    "\t)",
  ])
  return "\n".join(lines)


ROOT_UUID = uid("root")


def render_group(
  sheet: SheetSpec,
  all_parts: list[dict],
  net_sheets: dict[str, set[str]],
) -> list[str]:
  parts = [part for part in all_parts if part["sheet"] == sheet.key]
  lines: list[str] = []
  offset_x, offset_y = SINGLE_PAGE_OFFSETS[sheet.key]
  for note, x, y, size in sheet.notes:
    lines.append(text_note(sheet.key, note, x + offset_x, y + offset_y, size))

  for part in parts:
    lines.append(part_instance(part, sheet))

  net_pins: dict[str, list[tuple[dict, dict, tuple[float, float]]]] = {}
  for part in parts:
    for pin in part["pins"]:
      point = pin_position(part, pin)
      if pin["net"]:
        net_pins.setdefault(pin["net"], []).append((part, pin, point))
      else:
        lines.append(no_connect(sheet.key, part["ref"], pin["number"], point))

  power_counter = 0
  for net_name, entries in sorted(net_pins.items()):
    if net_name in SYMBOL_POWER_NETS:
      for part, pin, point in entries:
        power_counter += 1
        direction = outward_direction(part, point, pin)
        dx, dy = direction_vector(direction, g(4))
        anchor = snap(point[0] + dx), snap(point[1] + dy)
        lines.append(wire(
          f"power-stub:{sheet.key}:{part['ref']}:{pin['number']}:{net_name}",
          point,
          anchor,
        ))
        lines.append(hidden_global_label(
          sheet.key,
          net_name,
          part["ref"],
          pin["number"],
          anchor,
        ))
        lines.append(power_symbol(
          f"#PWR{SHEET_INDEX[sheet.key]:02d}{power_counter:02d}",
          sheet,
          net_name,
          anchor,
          direction,
        ))
      continue

    if net_name in CUSTOM_POWER_NETS:
      for part, pin, point in entries:
        lines.extend(global_label(sheet.key, net_name, part, point, pin))
      continue

    is_cross_sheet = len(net_sheets[net_name]) > 1
    label_each = (sheet.key, net_name) in LABEL_EACH_NETS
    label_each_local = (sheet.key, net_name) in LABEL_EACH_LOCAL_NETS
    if label_each or label_each_local:
      for part, pin, point in entries:
        lines.extend(global_label(sheet.key, net_name, part, point, pin))
      continue

    lines.extend(route_net(sheet.key, net_name, [entry[2] for entry in entries]))
    if is_cross_sheet or len(entries) == 1:
      preferred = LABEL_PIN.get((sheet.key, net_name))
      if preferred:
        part_ref, pin_number = preferred
        part, pin, point = next(
          entry for entry in entries
          if entry[0]["ref"] == part_ref and entry[1]["number"] == pin_number
        )
      else:
        part, pin, point = entries[0]
      lines.extend(global_label(sheet.key, net_name, part, point, pin))

  return lines


def render_single_page(
  all_parts: list[dict],
  net_sheets: dict[str, set[str]],
) -> str:
  used_power_nets = sorted({
    pin["net"]
    for part in all_parts
    for pin in part["pins"]
    if pin["net"] in SYMBOL_POWER_NETS
  })
  lines = [
    "(kicad_sch",
    "\t(version 20250114)",
    "\t(generator \"eeschema\")",
    "\t(generator_version \"10.0\")",
    f"\t(uuid \"{ROOT_UUID}\")",
    "\t(paper \"A2\")",
    "\t(title_block",
    f"\t\t(title \"{TITLE}\")",
    f"\t\t(date \"{DATE}\")",
    "\t\t(company \"the-card\")",
    "\t\t(comment 1 \"Single-page functional schematic\")",
    "\t\t(comment 2 \"Connectivity generated from circuit.py\")",
    "\t)",
    "\t(lib_symbols",
  ]
  seen_symbols: set[tuple[str, str]] = set()
  for part in all_parts:
    symbol_key = part["library"], part["name"]
    if symbol_key in seen_symbols:
      continue
    seen_symbols.add(symbol_key)
    lines.append(passive_symbol_block(part["name"], part["library"]))
  for net_name in used_power_nets:
    lines.append(power_block(net_name))
  lines.append("\t)")

  for sheet in SHEETS:
    lines.extend(render_group(sheet, all_parts, net_sheets))

  lines.extend([
    "\t(sheet_instances (path \"/\" (page \"1\")))",
    "\t(embedded_fonts no)",
    ")",
  ])
  return "\n".join(lines) + "\n"


SHEET_INDEX = {sheet.key: index + 1 for index, sheet in enumerate(SHEETS)}


def validate_configuration(parts: list[dict]) -> None:
  expected_refs = {part["ref"] for part in parts}
  configured_refs = set(SHEET_BY_REF)
  if expected_refs != configured_refs:
    raise ValueError(
      "Sheet partition does not match circuit parts: "
      f"missing={sorted(expected_refs - configured_refs)}, "
      f"extra={sorted(configured_refs - expected_refs)}"
    )
  for sheet in SHEETS:
    if set(sheet.placements) != set(sheet.refs):
      raise ValueError(
        f"Placement table mismatch for {sheet.key}: "
        f"missing={sorted(sheet.refs - set(sheet.placements))}, "
        f"extra={sorted(set(sheet.placements) - sheet.refs)}"
      )
  missing_symbols = sorted({part["name"] for part in parts} - set(SYMBOLS))
  if missing_symbols:
    raise ValueError(f"Missing embedded symbols: {missing_symbols}")


def main() -> None:
  parts, net_sheets = build_parts()
  validate_configuration(parts)
  output = HERE / "the-card.kicad_sch"
  output.write_text(render_single_page(parts, net_sheets))
  print(f"wrote {output.name}")
  print(
    f"parts={len(parts)} sheets=1 groups={len(SHEETS)} "
    f"nets={len(net_sheets)}"
  )


if __name__ == "__main__":
  main()
