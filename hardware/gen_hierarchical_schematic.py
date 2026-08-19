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
from design_metadata import (
  DESIGN_VERSION,
  DNP_REFERENCES,
  NON_ASSEMBLY_REFERENCES,
  PROJECT_NAME,
)


HERE = Path(__file__).resolve().parent
LIBS = HERE / "libraries"
POWER_LIB = Path(
  "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols/power.kicad_sym"
)
STANDARD_SYMBOL_DIR = Path(
  "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
)
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
  passive_callouts: tuple[tuple[str, float, float, float], ...]


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
      "C_vbus": p(112, 68, 270),
      "U6": p(125, 50),
      "R_prog": p(103, 50, 180),
      "R_chrg": p(148, 50, 180),
      "C_bat": p(138, 68, 270),
      "U9": p(180, 50),
      "C_ldoi": p(168, 68, 270),
      "C_ldoo": p(192, 68, 270),
      "U5": p(235, 50),
      "C_fg": p(218, 68, 270),
      "U7": p(75, 130, 180),
      # Rotate the dual MOSFET so its gate traces do not run through the
      # intervening source pins on either side of the symbol.
      "U8": p(105, 128, 90),
      "R_dvcc": p(48, 118),
      "R_dvm": p(92, 130, 180),
      # Both pins face outward: VDD above and BAT_NEG directly on the trunk.
      "C_dprot": p(58, 138, 270),
      "Q1": p(185, 130),
      "R_q1g": p(176, 116, 270),
      "Q2": p(225, 130),
      "R_q2g": p(216, 116, 270),
      "TP1": p(18, 148),
      "TP2": p(30, 148),
      "TP3": p(195, 112),
      "TP4": p(205, 112),
    },
    notes=(
      ("USB-C input, ESD, and charger", g(12), g(12), 1.8),
      ("3.3 V regulation and fuel gauge", g(165), g(12), 1.8),
      ("Cell protection", g(12), g(100), 1.8),
      ("Switched peripheral rails", g(165), g(94), 1.8),
    ),
    passive_callouts=(
      (
        "J1/U10 support: R5/R6 CC pull-downs; C5 USB input bulk",
        g(12), g(84), 1.0,
      ),
      (
        "U6 support: R7 charge-current set; R8 CHRG pull-up; C5/C6 bulk",
        g(88), g(84), 1.0,
      ),
      (
        "U9/U5 support: C8/C9 LDO stability; C10 fuel-gauge bypass",
        g(168), g(84), 1.0,
      ),
      (
        "U7/U8 support: R9 supply feed; R10 pack sense; C7 bypass",
        g(12), g(158), 1.0,
      ),
      (
        "Q1/Q2 support: R11/R12 gate pull-ups (rails default off)",
        g(165), g(103), 1.0,
      ),
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
      # Draw the two supply capacitors as distinct parallel shunts, rather
      # than a close horizontal pair that can be mistaken for a series path.
      "C_mcu1": p(58, 43, 270),
      "C_mcu2": p(75, 43, 270),
      "R_en": p(87, 58, 270),
      # Keep the MCU's leftmost wiring inside its own visual column.
      "C_en": p(72, 70, 270),
      "R_io0": p(148, 82, 270),
      "R_vbh": p(145, 60, 270),
      "R_vbl": p(145, 68, 270),
      "C_vb": p(158, 68, 270),
      # Keep the EN test point left of U1's dense label fanout.
      "TP5": p(78, 80),
      "TP6": p(148, 96),
    },
    notes=(
      ("Controller, boot straps, decoupling, and battery ADC", g(12), g(12), 1.8),
      ("Named labels keep long inter-block connections readable.", g(12), g(20), 1.1),
    ),
    passive_callouts=(
      (
        "C1/C2 -> U1: 3V3 bypass + bulk; "
        "R1/C3 -> U1 EN: pull-up + startup timing",
        g(12), g(28), 1.0,
      ),
      (
        "R2 -> U1 IO0: boot pull-up; "
        "R3/R4/C4 -> U1 IO1: battery divider + filter",
        g(12), g(115), 1.0,
      ),
    ),
  ),
  SheetSpec(
    key="sensors_nfc",
    refs=frozenset({
      "U2", "C_nfc", "U3", "C_imu1", "C_imu2", "U4", "C_sht",
      "R_scl", "R_sda", "R_nfc_irq", "C_nfc_tune", "L2",
    }),
    placements={
      "U2": p(50, 45),
      "C_nfc": p(78, 45, 270),
      "R_nfc_irq": p(88, 58, 270),
      "L2": p(35, 45, 90),
      "C_nfc_tune": p(35, 58, 270),
      "U3": p(52, 96),
      "C_imu1": p(82, 84, 270),
      "C_imu2": p(96, 96, 270),
      "U4": p(125, 96),
      "C_sht": p(150, 96, 270),
      "R_scl": p(112, 38, 270),
      "R_sda": p(128, 38, 270),
    },
    notes=(
      ("NFC dynamic tag", g(12), g(12), 1.8),
      ("Motion and environmental sensors", g(12), g(75), 1.8),
      ("I2C pull-ups", g(105), g(12), 1.8),
    ),
    passive_callouts=(
      (
        "C11 -> U2: NFC bypass; R17 -> GPO pull-up; C29 -> RF trim (DNP)",
        g(12), g(22), 1.0,
      ),
      (
        "R13/R14 -> I2C bus U1-U5: SCL/SDA pull-ups",
        g(105), g(22), 1.0,
      ),
      (
        "C12/C13 -> U3: IMU bypass + bulk",
        g(12), g(122), 1.0,
      ),
      (
        "C14 -> U4: environmental-sensor bypass",
        g(105), g(122), 1.0,
      ),
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
      # Leave room for the connector value and right-facing net labels before
      # the page frame.
      "J2": p(150, 70),
      "L1": p(50, 58, 90),
      "Q3": p(72, 64),
      "D2": p(90, 32),
      "D3": p(90, 43),
      # Put the anode directly on EPD_SW and face the cathode toward EPD_VGH.
      "D4": p(94, 58, 180),
      "R_epdg": p(62, 82, 270),
      "R_epds": p(82, 82, 270),
      # C20 is the local EPD_VCI reservoir at L1's input.
      "C_epd_in": p(38, 72, 270),
      # Vertical orientation keeps the charge-pump and switch-node terminals
      # on opposite sides instead of routing one net through the capacitor.
      "C_epd_pump": p(72, 43, 270),
      # The five simple J2-to-capacitor rails sit around the connector. Their
      # GND terminals face away from J2 and their signal wires use nested,
      # non-crossing lanes.
      "C_epd_vsh2": p(128, 63, 180),
      "C_epdvdd": p(172, 86),
      "C_epd_vsh1": p(172, 94),
      "C_epd_vgh": p(112, 58),
      "C_epd_vsl": p(172, 102),
      "C_epd_vgl": p(112, 32),
      "C_epd_vcom": p(172, 110),
    },
    notes=(
      ("GDEY029T94 24-pin FPC interface", g(12), g(12), 1.8),
      ("Booster and boosted gate rails", g(35), g(22), 1.2),
      ("J2 panel connector and direct rail reservoirs", g(125), g(22), 1.2),
    ),
    passive_callouts=(
      (
        "C20/L1: VCI input; C21/D2-D4/Q3: boost conversion",
        g(35), g(112), 1.0,
      ),
      (
        "R15/R16: Q3 gate pull-down and current sense",
        g(35), g(120), 1.0,
      ),
      (
        "C22-C24/C26/C28: direct J2 rail reservoirs",
        g(125), g(118), 1.0,
      ),
      (
        "C25/C27: boosted VGH/VGL reservoirs",
        g(125), g(126), 1.0,
      ),
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
      "SW4": p(180, 55),
      # Offset the capacitors from the switches; the signal leg can then
      # dogleg around pin 3 instead of appearing to join its GND stub.
      "C_btn1": p(32, 67, 270),
      "C_btn2": p(82, 67, 270),
      "C_btn3": p(132, 67, 270),
      "C_btn4": p(172, 67, 270),
      "D1": p(125, 118),
      "C_led": p(88, 118, 270),
    },
    notes=(
      ("User buttons with hardware debounce", g(12), g(12), 1.8),
      ("Status LED", g(82), g(96), 1.8),
    ),
    passive_callouts=(
      (
        "C16-C19 -> SW1-SW4/U1: button debounce",
        g(12), g(22), 1.0,
      ),
      (
        "C15 -> D1: LED supply bypass",
        g(82), g(105), 1.0,
      ),
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
    passive_callouts=sheet.passive_callouts,
  )
  for sheet in SHEETS
)

SHEET_BY_REF = {ref: sheet for sheet in SHEETS for ref in sheet.refs}

# Preserve each functional block's local placement and tile the blocks onto A2.
# Values are grid units and are applied before any pin or wire coordinates are
# calculated.
SINGLE_PAGE_OFFSETS = {
  "power_usb": (g(0), g(0)),
  # Start below the final power-section callout instead of sharing its band.
  "mcu": (g(130), g(145)),
  "sensors_nfc": (g(265), g(0)),
  "epaper": (g(270), g(165)),
  "ui": (g(0), g(165)),
}

# These widely separated or intentionally symbolic endpoints are clearer as
# repeated named stubs than as long wires.
LABEL_EACH_NETS = {
  ("sensors_nfc", "NFC_AC0"),
  ("sensors_nfc", "NFC_AC1"),
  ("sensors_nfc", "I2C_SCL"),
  ("sensors_nfc", "I2C_SDA"),
}

# Some named nets contain multiple compact circuits separated by enough space
# that one continuous wire would obscure the signal flow. Wire each compact
# cluster locally and emit one label for the cluster, instead of labeling every
# component pin. Endpoint keys are explicit so a circuit change cannot silently
# alter the drawing convention.
NET_LABEL_CLUSTERS = {
  # EPD_VCI crosses the power and e-paper regions. Keep the two J2 pins as
  # compact label stubs, but wire C20 directly to the L1 input locally.
  ("epaper", "EPD_VCI"): (
    (("J2", "15"),),
    (("J2", "16"),),
    (("L1", "1"), ("C20", "1")),
  ),
  ("epaper", "EPD_GDR"): (
    (("J2", "2"),),
    (("Q3", "1"), ("R15", "1")),
  ),
  ("epaper", "EPD_RESE"): (
    (("J2", "3"),),
    (("Q3", "2"), ("R16", "1")),
  ),
  ("epaper", "EPD_VGH"): (
    (("J2", "21"),),
    (("D4", "1"), ("C25", "1")),
  ),
  ("epaper", "EPD_VGL"): (
    (("J2", "23"),),
    (("D2", "2"), ("C27", "1")),
  ),
}

# A clustered net normally derives its label direction from the cluster's first
# component pin. These free-space anchors keep selected labels horizontal on an
# existing local wire. Coordinates are relative to the functional region.
CLUSTER_LABEL_ANCHORS = {
  ("epaper", "EPD_RESE", ("Q3", "2")): (g(78), g(68)),
}

# Visible property locations that need to follow the schematic's local
# functional layout rather than the generic symbol bounds. Coordinates are
# offsets from the component centre in grid units.
PROPERTY_LAYOUT = {
  "C20": ((-6, -1, 270), (-6, 2, 270)),
  "C21": ((-6, -1, 270), (-6, 2, 270)),
  "L1": ((0, -4, 90), (0, 4, 90)),
  "Q3": ((0, -9, 0), (0, 9, 0)),
  "J2": ((0, -17, 0), (0, 18, 0)),
}

# Most parts use the standard 1.2 mm reference and 1.0 mm value sizes. J2 keeps
# the standard reference hierarchy while its long centred part number is
# reduced to fit beside the surrounding net labels.
PROPERTY_FONT_SIZES = {
  "J2": (1.2, 0.8),
}

# The 8205A exposes its common drain on two opposite pins. Repeated labels
# communicate that internal node without drawing a misleading wire through the body.
LABEL_EACH_LOCAL_NETS = {("power_usb", "FET_DRAIN")}

# Explicit trunks keep the interleaved reversible USB-C data pins readable.
TRUNK_ROUTES = {
  ("power_usb", "N$6"): ("horizontal", g(72)),
  ("power_usb", "N$7"): ("horizontal", g(28)),
  # Keep the boost switch node on D4's anode so the diode reads left-to-right.
  ("epaper", "EPD_SW"): ("horizontal", g(58)),
}

# Two-terminal nets normally use a single orthogonal corner. These nets need a
# third segment so that the route does not pass through unrelated symbol pins.
# The coordinate is the lane used between the two endpoints.
TWO_PIN_DOGLEG_ROUTES = {
  ("power_usb", "N$10"): ("horizontal", g(146)),
  ("power_usb", "N$11"): ("horizontal", g(113)),
  ("ui", "BTN_UP"): ("vertical", g(28)),
  ("ui", "BTN_DOWN"): ("vertical", g(78)),
  ("ui", "BTN_SEL"): ("vertical", g(128)),
  ("ui", "BTN_MENU"): ("vertical", g(168)),
  # Fan the four adjacent right-side J2 rails into a spaced capacitor bank.
  # Decreasing lane X while increasing capacitor Y keeps the routes nested.
  ("epaper", "EPD_VDD_CORE"): ("vertical", g(168)),
  ("epaper", "EPD_VSH1"): ("vertical", g(166)),
  ("epaper", "EPD_VSL"): ("vertical", g(164)),
  ("epaper", "EPD_VCOM"): ("vertical", g(162)),
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

# Put the visible label branch on the existing local route, away from component
# pins. These are true three-way electrical junctions and therefore get dots.
LABEL_JUNCTION_POINTS = {
  ("power_usb", "PWR_AUX"): (g(176), g(130)),
  ("power_usb", "EPD_PWR_EN"): (g(216), g(130)),
  ("ui", "BTN_UP"): (g(28), g(53)),
  ("ui", "BTN_DOWN"): (g(78), g(53)),
  ("ui", "BTN_SEL"): (g(128), g(53)),
  ("ui", "BTN_MENU"): (g(168), g(53)),
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
  if start == end:
    raise ValueError(f"Zero-length wire for {seed}: {start}")
  return (
    "\t(wire\n"
    f"\t\t(pts (xy {fmt(start[0])} {fmt(start[1])}) "
    f"(xy {fmt(end[0])} {fmt(end[1])}))\n"
    "\t\t(stroke (width 0) (type default))\n"
    f"\t\t(uuid \"{uid('wire', seed, *start, *end)}\")\n"
    "\t)"
  )


def wire_path(
  seed: str,
  points: list[tuple[float, float]],
) -> list[str]:
  """Emit the non-zero orthogonal segments in a route."""
  result = []
  for start, end in zip(points, points[1:]):
    if start != end:
      result.append(wire(seed, start, end))
  return result


def point_on_segment(
  point: tuple[float, float],
  segment: tuple[tuple[float, float], tuple[float, float]],
) -> bool:
  """Return whether a point lies on an orthogonal wire segment."""
  start, end = segment
  if start[0] == end[0] == point[0]:
    return min(start[1], end[1]) <= point[1] <= max(start[1], end[1])
  if start[1] == end[1] == point[1]:
    return min(start[0], end[0]) <= point[0] <= max(start[0], end[0])
  return False


def junction(seed: str, point: tuple[float, float]) -> str:
  return (
    "\t(junction\n"
    f"\t\t(at {fmt(point[0])} {fmt(point[1])})\n"
    "\t\t(diameter 0)\n"
    "\t\t(color 0 0 0 0)\n"
    f"\t\t(uuid \"{uid('junction', seed, *point)}\")\n"
    "\t)"
  )


def route_net(
  sheet_key: str,
  net_name: str,
  points: list[tuple[float, float]],
  explicit_junctions: tuple[tuple[float, float], ...] = (),
) -> list[str]:
  """Route a small local net as an orthogonal tree."""
  unique_points = list(dict.fromkeys(points))
  if len(unique_points) < 2:
    return []
  seed = f"{sheet_key}:{net_name}"
  offset_x, offset_y = SINGLE_PAGE_OFFSETS[sheet_key]
  segments: list[
    tuple[tuple[float, float], tuple[float, float]]
  ] = []
  junction_points: set[tuple[float, float]] = set()
  if len(unique_points) == 2:
    start, end = unique_points
    dogleg = TWO_PIN_DOGLEG_ROUTES.get((sheet_key, net_name))
    if dogleg:
      axis, coordinate = dogleg
      coordinate = snap(
        coordinate + (offset_x if axis == "vertical" else offset_y)
      )
      if axis == "vertical":
        route_points = [start, (coordinate, start[1]), (coordinate, end[1]), end]
      else:
        route_points = [start, (start[0], coordinate), (end[0], coordinate), end]
    else:
      route_points = [start, (end[0], start[1]), end]
    segments.extend(
      (segment_start, segment_end)
      for segment_start, segment_end in zip(route_points, route_points[1:])
      if segment_start != segment_end
    )
  else:
    xs = [point[0] for point in unique_points]
    ys = [point[1] for point in unique_points]
    override = TRUNK_ROUTES.get((sheet_key, net_name))
    if override:
      axis, coordinate = override
      coordinate = snap(
        coordinate + (offset_x if axis == "vertical" else offset_y)
      )
    elif max(xs) - min(xs) >= max(ys) - min(ys):
      axis, coordinate = "horizontal", snap(sorted(ys)[len(ys) // 2])
    else:
      axis, coordinate = "vertical", snap(sorted(xs)[len(xs) // 2])

    if axis == "horizontal":
      trunk_start = min(xs), coordinate
      trunk_end = max(xs), coordinate
    else:
      trunk_start = coordinate, min(ys)
      trunk_end = coordinate, max(ys)
    if trunk_start != trunk_end:
      segments.append((trunk_start, trunk_end))

    branches: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for point in unique_points:
      if axis == "horizontal":
        branch = point[0], coordinate
        branch_is_internal = min(xs) < branch[0] < max(xs)
      else:
        branch = coordinate, point[1]
        branch_is_internal = min(ys) < branch[1] < max(ys)
      if point != branch:
        segments.append((point, branch))
        branches.append((point, branch))
      if branch_is_internal:
        junction_points.add(branch)

    # A trunk endpoint can still be a true junction when multiple branches
    # meet there (for example, the two source pins of U8).
    branch_end_counts: dict[tuple[float, float], int] = {}
    for _, end in branches:
      branch_end_counts[end] = branch_end_counts.get(end, 0) + 1
    for point, count in branch_end_counts.items():
      if count > 1 and point in {trunk_start, trunk_end}:
        junction_points.add(point)

    # Mark a secondary branch that terminates on another same-net branch.
    for index, (start, end) in enumerate(branches):
      for other_start, other_end in branches[index + 1:]:
        same_vertical = start[0] == end[0] == other_start[0] == other_end[0]
        same_horizontal = start[1] == end[1] == other_start[1] == other_end[1]
        if same_vertical:
          for point in (start, end, other_start, other_end):
            on_first = min(start[1], end[1]) < point[1] < max(start[1], end[1])
            on_second = (
              min(other_start[1], other_end[1]) < point[1]
              < max(other_start[1], other_end[1])
            )
            if on_first or on_second:
              junction_points.add(point)
        elif same_horizontal:
          for point in (start, end, other_start, other_end):
            on_first = min(start[0], end[0]) < point[0] < max(start[0], end[0])
            on_second = (
              min(other_start[0], other_end[0]) < point[0]
              < max(other_start[0], other_end[0])
            )
            if on_first or on_second:
              junction_points.add(point)

  segments = [segment for segment in segments if segment[0] != segment[1]]

  pin_points = set(unique_points)
  for point in explicit_junctions:
    if point in pin_points:
      raise ValueError(
        f"Explicit junction for {sheet_key}:{net_name} is on a component pin: "
        f"{point}"
      )
    if not any(point_on_segment(point, segment) for segment in segments):
      raise ValueError(
        f"Explicit junction for {sheet_key}:{net_name} is not on its route: "
        f"{point}"
      )
    junction_points.add(point)

  result = [
    wire(seed, start, end)
    for start, end in segments
    if start != end
  ]
  result.extend(
    junction(f"{seed}:junction", point)
    for point in sorted(junction_points)
  )
  return result


def global_label(
  sheet_key: str,
  net_name: str,
  part: dict,
  point: tuple[float, float],
  pin: dict | None,
  *,
  label_id: str | None = None,
  at_point: bool = False,
) -> list[str]:
  pin_number = pin["number"] if pin is not None else label_id
  if pin_number is None:
    raise ValueError(f"Label {sheet_key}:{net_name} requires a stable ID")
  direction = outward_direction(part, point, pin)
  is_mcu = part["ref"] == "U1"
  distance = 0 if at_point else g(5) if is_mcu else g(4)
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
  result = []
  if point != anchor:
    result.append(
      wire(f"label:{sheet_key}:{net_name}:{part['ref']}:{pin_number}", point, anchor)
    )
  result.append(label)
  return result


def hidden_global_label(
  sheet_key: str,
  net_name: str,
  ref: str,
  pin_number: str,
  point: tuple[float, float],
  *,
  uuid_seed: str = "hidden-power-label",
) -> str:
  """Name a connected tree without adding visible schematic annotation."""
  return (
    f"\t(global_label \"{esc(net_name)}\"\n"
    "\t\t(shape bidirectional)\n"
    f"\t\t(at {fmt(point[0])} {fmt(point[1])} 0)\n"
    "\t\t(effects (font (size 0.01 0.01)) (hide yes))\n"
    f"\t\t(uuid \"{uid(uuid_seed, sheet_key, net_name, ref, pin_number)}\")\n"
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
    f"\t\t(instances (project \"{PROJECT_NAME}\" (path \"{path}\" "
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


def text_note(
  sheet_key: str,
  value: str,
  x: float,
  y: float,
  size: float,
  *,
  bold: bool = True,
) -> str:
  bold_clause = " (bold yes)" if bold else ""
  return (
    f"\t(text \"{esc(value)}\"\n"
    "\t\t(exclude_from_sim no)\n"
    f"\t\t(at {fmt(x)} {fmt(y)} 0)\n"
    f"\t\t(effects (font (size {fmt(size)} {fmt(size)}){bold_clause}) "
    "(justify left bottom))\n"
    f"\t\t(uuid \"{uid('text', sheet_key, value)}\")\n"
    "\t)"
  )


def build_parts() -> tuple[list[dict], dict[str, set[str]], set[str]]:
  design = circuit.nfc.circuit
  design.merge_net_names()
  design.merge_nets()
  explicit_net_names = {
    str(net.name)
    for net in design.nets
    if net.name != "__NOCONNECT" and not net.is_implicit()
  }
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
    datasheet = getattr(skidl_part, "datasheet", None)
    if datasheet is None:
      datasheet = symbol_field(skidl_part.name, "Datasheet")
    parts.append({
      "ref": skidl_part.ref,
      "name": skidl_part.name,
      "library": library,
      "value": str(getattr(skidl_part, "value", None) or skidl_part.name),
      "footprint": footprint,
      "datasheet": datasheet,
      "fields": {
        str(name): str(value)
        for name, value in skidl_part.fields.items()
      },
      "in_bom": skidl_part.ref not in NON_ASSEMBLY_REFERENCES,
      "dnp": skidl_part.ref in DNP_REFERENCES,
      "pins": pins,
      "sheet": sheet.key,
      "x": placement.x + offset_x,
      "y": placement.y + offset_y,
      "rotation": placement.rotation,
    })
  return parts, net_sheets, explicit_net_names


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
  property_layout = PROPERTY_LAYOUT.get(part["ref"])
  if property_layout:
    reference_layout, value_layout = property_layout
    reference_x = snap(part["x"] + g(reference_layout[0]))
    reference_y = snap(part["y"] + g(reference_layout[1]))
    reference_angle = reference_layout[2]
    value_x = snap(part["x"] + g(value_layout[0]))
    value_y = snap(part["y"] + g(value_layout[1]))
    value_angle = value_layout[2]
  reference_size, value_size = PROPERTY_FONT_SIZES.get(part["ref"], (1.2, 1.0))
  path = f"/{ROOT_UUID}"
  in_bom = (
    "no"
    if part["ref"].startswith("TP") or not part["in_bom"]
    else "yes"
  )
  dnp = "yes" if part["dnp"] else "no"
  lines = [
    "\t(symbol",
    f"\t\t(lib_id \"{part['library']}:{part['name']}\")",
    f"\t\t(at {fmt(part['x'])} {fmt(part['y'])} {part['rotation']})",
    "\t\t(unit 1)",
    "\t\t(exclude_from_sim no)",
    f"\t\t(in_bom {in_bom})",
    "\t\t(on_board yes)",
    f"\t\t(dnp {dnp})",
    f"\t\t(uuid \"{uid('part', part['ref'])}\")",
    f"\t\t(property \"Reference\" \"{esc(part['ref'])}\"",
    f"\t\t\t(at {fmt(reference_x)} {fmt(reference_y)} {reference_angle})",
    f"\t\t\t(effects (font (size {fmt(reference_size)} "
    f"{fmt(reference_size)}) (bold yes)))",
    "\t\t)",
    f"\t\t(property \"Value\" \"{esc(part['value'])}\"",
    f"\t\t\t(at {fmt(value_x)} {fmt(value_y)} {value_angle})",
    f"\t\t\t(effects (font (size {fmt(value_size)} {fmt(value_size)})))",
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
  for name, value in sorted(part["fields"].items()):
    lines.extend([
      f"\t\t(property \"{esc(name)}\" \"{esc(value)}\"",
      f"\t\t\t(at {fmt(part['x'])} {fmt(part['y'])} 0)",
      "\t\t\t(effects (font (size 1 1)) (hide yes))",
      "\t\t)",
    ])
  for pin in part["pins"]:
    lines.append(
      f"\t\t(pin \"{esc(pin['number'])}\" "
      f"(uuid \"{uid('part-pin', part['ref'], pin['number'])}\"))"
    )
  lines.extend([
    f"\t\t(instances (project \"{PROJECT_NAME}\" (path \"{path}\"",
    f"\t\t\t(reference \"{esc(part['ref'])}\") (unit 1))))",
    "\t)",
  ])
  return "\n".join(lines)


ROOT_UUID = uid("root")


def render_group(
  sheet: SheetSpec,
  all_parts: list[dict],
  net_sheets: dict[str, set[str]],
  explicit_net_names: set[str],
) -> list[str]:
  parts = [part for part in all_parts if part["sheet"] == sheet.key]
  lines: list[str] = []
  offset_x, offset_y = SINGLE_PAGE_OFFSETS[sheet.key]
  for note, x, y, size in sheet.notes:
    lines.append(text_note(sheet.key, note, x + offset_x, y + offset_y, size))
  for note, x, y, size in sheet.passive_callouts:
    lines.append(text_note(
      sheet.key,
      note,
      x + offset_x,
      y + offset_y,
      size,
      bold=False,
    ))

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

    clusters = NET_LABEL_CLUSTERS.get((sheet.key, net_name))
    if clusters:
      entries_by_pin = {
        (part["ref"], pin["number"]): (part, pin, point)
        for part, pin, point in entries
      }
      clustered_keys = {key for cluster in clusters for key in cluster}
      if clustered_keys != set(entries_by_pin):
        raise ValueError(
          f"Label clusters for {sheet.key}:{net_name} do not match pins: "
          f"missing={sorted(set(entries_by_pin) - clustered_keys)}, "
          f"extra={sorted(clustered_keys - set(entries_by_pin))}"
        )
      for cluster in clusters:
        cluster_entries = [entries_by_pin[key] for key in cluster]
        lines.extend(route_net(
          sheet.key,
          net_name,
          [entry[2] for entry in cluster_entries],
        ))
        part, pin, point = cluster_entries[0]
        anchor = CLUSTER_LABEL_ANCHORS.get(
          (sheet.key, net_name, (part["ref"], pin["number"]))
        )
        if anchor:
          label_point = anchor[0] + offset_x, anchor[1] + offset_y
          lines.extend(global_label(
            sheet.key,
            net_name,
            part,
            label_point,
            None,
            label_id=pin["number"],
            at_point=True,
          ))
        else:
          lines.extend(global_label(sheet.key, net_name, part, point, pin))
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

    label_point = LABEL_JUNCTION_POINTS.get((sheet.key, net_name))
    if label_point:
      label_point = label_point[0] + offset_x, label_point[1] + offset_y
    lines.extend(route_net(
      sheet.key,
      net_name,
      [entry[2] for entry in entries],
      (label_point,) if label_point else (),
    ))
    # A wire preserves connectivity, but KiCad invents a Net-(ref-pin) name
    # unless the connected tree also contains a label or power symbol. Visible
    # labels communicate distant or symbolic connections; a hidden label keeps
    # canonical names on compact local circuits without cluttering the drawing.
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
      if label_point:
        point = label_point
      lines.extend(global_label(sheet.key, net_name, part, point, pin))
    elif net_name in explicit_net_names:
      part, pin, point = entries[0]
      lines.append(hidden_global_label(
        sheet.key,
        net_name,
        part["ref"],
        pin["number"],
        point,
        uuid_seed="hidden-local-label",
      ))

  return lines


def render_single_page(
  all_parts: list[dict],
  net_sheets: dict[str, set[str]],
  explicit_net_names: set[str],
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
    f"\t\t(rev \"{DESIGN_VERSION}\")",
    f"\t\t(company \"{PROJECT_NAME}\")",
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
    lines.extend(render_group(
      sheet,
      all_parts,
      net_sheets,
      explicit_net_names,
    ))

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
  clustered_symbol_power_nets = sorted({
    net_name
    for _, net_name in NET_LABEL_CLUSTERS
    if net_name in SYMBOL_POWER_NETS
  })
  if clustered_symbol_power_nets:
    raise ValueError(
      "Symbol power nets require placement-aware symbols, not label clusters: "
      f"{clustered_symbol_power_nets}"
    )


def main() -> None:
  parts, net_sheets, explicit_net_names = build_parts()
  validate_configuration(parts)
  output = HERE / "the-card.kicad_sch"
  output.write_text(render_single_page(
    parts,
    net_sheets,
    explicit_net_names,
  ))
  print(f"wrote {output.name}")
  print(
    f"parts={len(parts)} sheets=1 groups={len(SHEETS)} "
    f"nets={len(net_sheets)} named_nets={len(explicit_net_names)}"
  )


if __name__ == "__main__":
  main()
