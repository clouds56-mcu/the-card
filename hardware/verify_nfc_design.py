#!/usr/bin/env python3
"""Verify the Rev B NFC schematic and PCB invariants.

The KiCad DRC remains authoritative. This checker adds focused, readable
failures for the electrical connections that made the GPO usable and for any
foreign copper that enters the antenna's all-layer quiet area.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from itertools import pairwise
import math
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from nfc_antenna import (
  ANTENNA_NETS,
  QUIET_AREA,
  RULE_AREA_NAME,
  TRACK_WIDTH_MM,
  global_rectangle,
  spiral_points,
)
from verify_schematic import find_kicad_cli


HERE = Path(__file__).resolve().parent
DEFAULT_SCHEMATIC = HERE / "the-card.kicad_sch"
DEFAULT_BOARD = HERE / "the-card.kicad_pcb"
COPPER_LAYERS = frozenset({"F.Cu", "In1.Cu", "In2.Cu", "B.Cu"})
Node = tuple[str, str]
Point = tuple[float, float]

EXPECTED_EXACT_NETS: dict[str, frozenset[Node]] = {
  "NFC_IRQ": frozenset({("R17", "2"), ("U1", "23"), ("U2", "7")}),
  "NFC_AC0": frozenset({("C29", "1"), ("L2", "1"), ("U2", "2")}),
  "NFC_AC1": frozenset({("C29", "2"), ("L2", "2"), ("U2", "3")}),
}
EXPECTED_SCHEMATIC_COMPONENTS = {
  "U2": {
    "value": "ST25DV04KC-IE8S3",
    "footprint": "the-card:SO-8_L4.9-W3.9-P1.27-LS6.0-BL",
  },
  "R17": {
    "value": "10k",
    "footprint": "Resistor_SMD:R_0402_1005Metric",
  },
  "C29": {
    "value": "DNP 0-22pF C0G/NP0",
    "footprint": "Capacitor_SMD:C_0402_1005Metric",
    "datasheet": "",
    "properties": frozenset({"dnp"}),
  },
  "L2": {
    "value": "PCB NFC antenna",
    "footprint": "NetTie:NetTie-2_SMD_Pad0.5mm",
    "properties": frozenset({"exclude_from_bom"}),
  },
}
EXPECTED_BOARD_COMPONENTS = {
  "U2": {
    "value": "ST25DV04KC-IE8S3",
    "footprint": "the-card:SO-8_L4.9-W3.9-P1.27-LS6.0-BL",
    "attributes": frozenset(),
  },
  "R17": {
    "value": "10k",
    "footprint": "Resistor_SMD:R_0402_1005Metric",
    "attributes": frozenset(),
  },
  "C29": {
    "value": "DNP 0-22pF C0G/NP0",
    "footprint": "Capacitor_SMD:C_0402_1005Metric",
    "attributes": frozenset({"dnp"}),
    "properties": {"Datasheet": ""},
  },
  "L2": {
    "value": "PCB NFC antenna",
    "footprint": "NetTie:NetTie-2_SMD_Pad0.5mm",
    "attributes": frozenset({"exclude_from_bom", "exclude_from_pos_files"}),
    "net_tie_pad_groups": "1, 2",
    "bridge_layer": "B.Cu",
    "bridge_polygon": frozenset({
      (-0.5, -0.25),
      (-0.5, 0.25),
      (0.5, -0.25),
      (0.5, 0.25),
    }),
  },
}


@dataclass(frozen=True)
class Bounds:
  left: float
  top: float
  right: float
  bottom: float

  def expanded(self, amount: float) -> "Bounds":
    return Bounds(
      self.left - amount,
      self.top - amount,
      self.right + amount,
      self.bottom + amount,
    )

  def inset(self, amount: float) -> "Bounds":
    return self.expanded(-amount)


def quiet_bounds() -> Bounds:
  quiet = global_rectangle(QUIET_AREA)
  return Bounds(
    quiet.x,
    quiet.y,
    quiet.x + quiet.width,
    quiet.y + quiet.height,
  )


def export_netlist_xml(
  schematic: Path,
  kicad_cli: Path | None = None,
) -> ET.Element:
  executable = find_kicad_cli(kicad_cli)
  with tempfile.TemporaryDirectory(prefix="the-card-nfc-") as temp_dir:
    xml_path = Path(temp_dir) / "schematic.xml"
    subprocess.run(
      [
        executable,
        "sch",
        "export",
        "netlist",
        "--format",
        "kicadxml",
        "--output",
        str(xml_path),
        str(schematic),
      ],
      check=True,
    )
    return ET.parse(xml_path).getroot()


def net_nodes(root: ET.Element) -> dict[str, frozenset[Node]]:
  return {
    net.attrib["name"]: frozenset(
      (node.attrib["ref"], node.attrib["pin"])
      for node in net.findall("node")
    )
    for net in root.findall("./nets/net")
  }


def _schematic_component_problems(root: ET.Element) -> list[str]:
  components = {
    component.attrib["ref"]: component
    for component in root.findall("./components/comp")
  }
  problems: list[str] = []
  for reference, expected in EXPECTED_SCHEMATIC_COMPONENTS.items():
    component = components.get(reference)
    if component is None:
      problems.append(f"{reference}: missing NFC component metadata")
      continue
    for field in ("value", "footprint", "datasheet"):
      if field not in expected:
        continue
      # KiCad omits an unassigned datasheet from exported XML, so absence and
      # an empty element both express the reviewed "no selected part" intent.
      actual = component.findtext(field) or ""
      if actual != expected[field]:
        problems.append(
          f"{reference}: expected {field}={expected[field]!r}, "
          f"actual={actual!r}"
        )
    properties = {
      prop.attrib["name"]
      for prop in component.findall("property")
    }
    missing_properties = sorted(expected.get("properties", set()) - properties)
    if missing_properties:
      problems.append(
        f"{reference}: missing properties={missing_properties}"
      )
  return problems


def schematic_problems(root: ET.Element) -> list[str]:
  nets = net_nodes(root)
  problems = _schematic_component_problems(root)
  for name, expected in EXPECTED_EXACT_NETS.items():
    actual = nets.get(name, frozenset())
    if actual != expected:
      problems.append(
        f"{name}: expected={sorted(expected)}, actual={sorted(actual)}"
      )

  power_nodes = nets.get("+3V3", frozenset())
  if ("R17", "1") not in power_nodes:
    problems.append("R17.1 must connect the NFC GPO pull-up to +3V3")

  gpio3_nets = [
    name for name, nodes in nets.items()
    if ("U1", "15") in nodes
  ]
  if not gpio3_nets:
    problems.append("U1.15 / GPIO3 is absent from the exported netlist")
  elif any(not name.startswith("unconnected-") for name in gpio3_nets):
    problems.append(
      "U1.15 / GPIO3 must remain unconnected, found "
      f"{sorted(gpio3_nets)}"
    )
  return problems


def _balanced_form(text: str, start: int) -> str:
  depth = 0
  quoted = False
  escaped = False
  for index in range(start, len(text)):
    character = text[index]
    if quoted:
      if escaped:
        escaped = False
      elif character == "\\":
        escaped = True
      elif character == '"':
        quoted = False
      continue
    if character == '"':
      quoted = True
    elif character == "(":
      depth += 1
    elif character == ")":
      depth -= 1
      if depth == 0:
        return text[start:index + 1]
  raise ValueError(f"unterminated S-expression at byte {start}")


def forms_named(text: str, name: str) -> list[str]:
  forms: list[str] = []
  needle = f"({name}"
  position = 0
  while True:
    start = text.find(needle, position)
    if start < 0:
      return forms
    boundary = start + len(needle)
    if boundary < len(text) and not text[boundary].isspace() \
        and text[boundary] != ")":
      position = boundary
      continue
    form = _balanced_form(text, start)
    forms.append(form)
    position = start + len(form)


def _number_pair(form: str, field: str) -> Point | None:
  match = re.search(
    rf"\({re.escape(field)}\s+([-+\d.eE]+)\s+([-+\d.eE]+)",
    form,
  )
  if match is None:
    return None
  return float(match.group(1)), float(match.group(2))


def _number(form: str, field: str, default: float = 0.0) -> float:
  match = re.search(
    rf"\({re.escape(field)}\s+([-+\d.eE]+)",
    form,
  )
  return default if match is None else float(match.group(1))


def _quoted(form: str, field: str) -> str | None:
  match = re.search(
    rf'\({re.escape(field)}\s+"((?:\\.|[^"\\])*)"',
    form,
  )
  return None if match is None else match.group(1)


def _property(form: str, name: str) -> str | None:
  match = re.search(
    rf'\(property\s+"{re.escape(name)}"\s+"((?:\\.|[^"\\])*)"',
    form,
  )
  return None if match is None else match.group(1)


def _footprint_name(form: str) -> str | None:
  match = re.match(r'^\(footprint\s+"([^"]+)"', form)
  return None if match is None else match.group(1)


def _footprint_attributes(form: str) -> frozenset[str]:
  match = re.search(r"\(attr\s+([^)]*)\)", form)
  return frozenset() if match is None else frozenset(match.group(1).split())


def _layers(form: str) -> frozenset[str]:
  match = re.search(r"\(layers?\s+([^\n\r)]*)\)", form)
  if match is None:
    return frozenset()
  return frozenset(re.findall(r'"([^"]+)"', match.group(1)))


def _point_inside(point: Point, bounds: Bounds) -> bool:
  return (
    bounds.left <= point[0] <= bounds.right
    and bounds.top <= point[1] <= bounds.bottom
  )


def _orientation(a: Point, b: Point, c: Point) -> float:
  return (b[0] - a[0]) * (c[1] - a[1]) \
    - (b[1] - a[1]) * (c[0] - a[0])


def _segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
  epsilon = 1e-9
  orientations = (
    _orientation(a, b, c),
    _orientation(a, b, d),
    _orientation(c, d, a),
    _orientation(c, d, b),
  )
  if (
    (orientations[0] > epsilon and orientations[1] < -epsilon
      or orientations[0] < -epsilon and orientations[1] > epsilon)
    and (orientations[2] > epsilon and orientations[3] < -epsilon
      or orientations[2] < -epsilon and orientations[3] > epsilon)
  ):
    return True

  def on_segment(start: Point, point: Point, end: Point) -> bool:
    return (
      abs(_orientation(start, point, end)) <= epsilon
      and min(start[0], end[0]) - epsilon <= point[0]
      <= max(start[0], end[0]) + epsilon
      and min(start[1], end[1]) - epsilon <= point[1]
      <= max(start[1], end[1]) + epsilon
    )

  return (
    on_segment(a, c, b)
    or on_segment(a, d, b)
    or on_segment(c, a, d)
    or on_segment(c, b, d)
  )


def _line_intersects_bounds(start: Point, end: Point, bounds: Bounds) -> bool:
  if _point_inside(start, bounds) or _point_inside(end, bounds):
    return True
  corners = (
    (bounds.left, bounds.top),
    (bounds.right, bounds.top),
    (bounds.right, bounds.bottom),
    (bounds.left, bounds.bottom),
  )
  return any(
    _segments_intersect(start, end, edge_start, edge_end)
    for edge_start, edge_end in zip(corners, (*corners[1:], corners[0]))
  )


def _point_in_polygon(point: Point, polygon: list[Point]) -> bool:
  inside = False
  previous = polygon[-1]
  for current in polygon:
    if (
      (current[1] > point[1]) != (previous[1] > point[1])
      and point[0]
      < (previous[0] - current[0])
      * (point[1] - current[1])
      / (previous[1] - current[1])
      + current[0]
    ):
      inside = not inside
    previous = current
  return inside


def _polygon_intersects_bounds(polygon: list[Point], bounds: Bounds) -> bool:
  if any(_point_inside(point, bounds) for point in polygon):
    return True
  corners = (
    (bounds.left, bounds.top),
    (bounds.right, bounds.top),
    (bounds.right, bounds.bottom),
    (bounds.left, bounds.bottom),
  )
  if any(_point_in_polygon(corner, polygon) for corner in corners):
    return True
  return any(
    _line_intersects_bounds(start, end, bounds)
    for start, end in zip(polygon, (*polygon[1:], polygon[0]))
  )


def _net_name(form: str) -> str:
  return _quoted(form, "net") or "<no net>"


def _arc_points(form: str) -> list[Point]:
  start = _number_pair(form, "start")
  middle = _number_pair(form, "mid")
  end = _number_pair(form, "end")
  if start is None or middle is None or end is None:
    return [point for point in (start, middle, end) if point is not None]

  ax, ay = start
  bx, by = middle
  cx, cy = end
  denominator = 2 * (
    ax * (by - cy) + bx * (cy - ay) + cx * (ay - by)
  )
  if abs(denominator) < 1e-12:
    return [start, middle, end]
  center_x = (
    (ax * ax + ay * ay) * (by - cy)
    + (bx * bx + by * by) * (cy - ay)
    + (cx * cx + cy * cy) * (ay - by)
  ) / denominator
  center_y = (
    (ax * ax + ay * ay) * (cx - bx)
    + (bx * bx + by * by) * (ax - cx)
    + (cx * cx + cy * cy) * (bx - ax)
  ) / denominator
  angles = [
    math.atan2(point[1] - center_y, point[0] - center_x)
    for point in (start, middle, end)
  ]
  full_turn = 2 * math.pi
  ccw_sweep = (angles[2] - angles[0]) % full_turn
  ccw_to_middle = (angles[1] - angles[0]) % full_turn
  sweep = ccw_sweep if ccw_to_middle <= ccw_sweep else ccw_sweep - full_turn
  steps = max(2, math.ceil(abs(sweep) / math.radians(5)))
  radius = math.hypot(ax - center_x, ay - center_y)
  return [
    (
      center_x + radius * math.cos(angles[0] + sweep * index / steps),
      center_y + radius * math.sin(angles[0] + sweep * index / steps),
    )
    for index in range(steps + 1)
  ]


def _track_problems(board_text: str, bounds: Bounds) -> list[str]:
  problems: list[str] = []
  for kind in ("segment", "arc"):
    for form in forms_named(board_text, kind):
      net = _net_name(form)
      if net in ANTENNA_NETS:
        continue
      width = _number(form, "width")
      points = _arc_points(form) if kind == "arc" else [
        point for field in ("start", "end")
        if (point := _number_pair(form, field)) is not None
      ]
      if any(
        _line_intersects_bounds(start, end, bounds.expanded(width / 2))
        for start, end in pairwise(points)
      ):
        problems.append(f"foreign {kind} on {net} enters NFC quiet area")

  for form in forms_named(board_text, "via"):
    net = _net_name(form)
    if net in ANTENNA_NETS:
      continue
    center = _number_pair(form, "at")
    radius = _number(form, "size") / 2
    if center is not None and _point_inside(center, bounds.expanded(radius)):
      problems.append(f"foreign via on {net} enters NFC quiet area")
  return problems


def _segment_key(start: Point, end: Point) -> tuple[Point, Point]:
  # pcbnew serializes some exact decimal tenths as values such as 29.299999.
  # Four decimal places remain much tighter than the project's DRC grid while
  # making the modeled and serialized geometry comparable.
  return tuple(sorted((
    (round(start[0], 4), round(start[1], 4)),
    (round(end[0], 4), round(end[1], 4)),
  )))


def _rounded_point(point: Point) -> Point:
  return round(point[0], 4), round(point[1], 4)


def _track_inventory_key(
  kind: str,
  net: str,
  layer: str,
  points: list[Point],
) -> tuple[object, ...]:
  geometry: object
  if kind == "segment" and len(points) == 2:
    geometry = _segment_key(points[0], points[1])
  else:
    geometry = tuple(_rounded_point(point) for point in points)
  return net, layer, kind, geometry


def _expected_antenna_tracks() -> Counter[tuple[object, ...]]:
  coil = spiral_points()
  feed_via = (28.50, 27.40)
  feed_corner = (coil[0][0], feed_via[1])
  inner_endpoint = coil[-1]
  tracks = [
    *(("NFC_AC0", "F.Cu", start, end) for start, end in pairwise(coil)),
    ("NFC_AC0", "F.Cu", feed_via, feed_corner),
    ("NFC_AC0", "F.Cu", feed_corner, coil[0]),
    ("NFC_AC0", "B.Cu", (30.45, 24.43), (28.80, 24.28)),
    ("NFC_AC0", "B.Cu", (28.80, 24.28), (28.50, 25.20)),
    ("NFC_AC0", "B.Cu", (28.50, 25.20), feed_via),
    ("NFC_AC0", "B.Cu", inner_endpoint, (inner_endpoint[0], 25.80)),
    ("NFC_AC0", "B.Cu", (inner_endpoint[0], 25.80), (26.00, 25.80)),
    ("NFC_AC0", "B.Cu", (26.00, 25.80), (26.00, 23.30)),
    ("NFC_AC1", "B.Cu", (30.45, 23.17), (28.80, 23.32)),
    ("NFC_AC1", "B.Cu", (28.80, 23.32), (27.00, 23.30)),
  ]
  return Counter(
    _track_inventory_key("segment", net, layer, [start, end])
    for net, layer, start, end in tracks
  )


def _via_inventory_key(form: str) -> tuple[object, ...] | None:
  center = _number_pair(form, "at")
  if center is None:
    return None
  return (
    _net_name(form),
    _rounded_point(center),
    round(_number(form, "size"), 4),
    round(_number(form, "drill"), 4),
    tuple(sorted(_layers(form))),
  )


def _expected_antenna_vias() -> Counter[tuple[object, ...]]:
  return Counter({
    (
      "NFC_AC0",
      _rounded_point(spiral_points()[-1]),
      0.60,
      0.30,
      ("B.Cu", "F.Cu"),
    ): 1,
    (
      "NFC_AC0",
      (28.50, 27.40),
      0.60,
      0.30,
      ("B.Cu", "F.Cu"),
    ): 1,
  })


def _antenna_route_problems(board_text: str) -> list[str]:
  actual_tracks: Counter[tuple[object, ...]] = Counter()
  wrong_width = 0
  for kind in ("segment", "arc"):
    for form in forms_named(board_text, kind):
      net = _net_name(form)
      if net not in ANTENNA_NETS:
        continue
      width = _number(form, "width")
      points = _arc_points(form) if kind == "arc" else [
        point for field in ("start", "end")
        if (point := _number_pair(form, field)) is not None
      ]
      layer = _quoted(form, "layer") or "<no layer>"
      actual_tracks[_track_inventory_key(kind, net, layer, points)] += 1
      if not math.isclose(width, TRACK_WIDTH_MM, abs_tol=1e-6):
        wrong_width += 1

  expected_tracks = _expected_antenna_tracks()
  missing_tracks = sum((expected_tracks - actual_tracks).values())
  extra_tracks = sum((actual_tracks - expected_tracks).values())
  problems: list[str] = []
  if missing_tracks:
    problems.append(
      f"etched NFC antenna is missing {missing_tracks} reviewed track segments"
    )
  if extra_tracks:
    problems.append(
      f"etched NFC antenna has {extra_tracks} unreviewed track segments"
    )
  if wrong_width:
    problems.append(
      f"{wrong_width} etched NFC antenna segments do not use "
      f"the modeled {TRACK_WIDTH_MM:.2f} mm width"
    )

  actual_vias: Counter[tuple[object, ...]] = Counter()
  for form in forms_named(board_text, "via"):
    net = _net_name(form)
    if net not in ANTENNA_NETS:
      continue
    key = _via_inventory_key(form)
    if key is not None:
      actual_vias[key] += 1
  expected_vias = _expected_antenna_vias()
  missing_vias = sum((expected_vias - actual_vias).values())
  extra_vias = sum((actual_vias - expected_vias).values())
  if missing_vias:
    problems.append(f"etched NFC antenna is missing {missing_vias} reviewed vias")
  if extra_vias:
    problems.append(f"etched NFC antenna has {extra_vias} unreviewed vias")
  antenna_zones = sum(
    1
    for zone in forms_named(board_text, "zone")
    if "(keepout" not in zone and _net_name(zone) in ANTENNA_NETS
  )
  if antenna_zones:
    problems.append(
      f"etched NFC antenna has {antenna_zones} unreviewed copper zones"
    )
  return problems


def _transform(point: Point, origin: Point, angle_degrees: float) -> Point:
  angle = math.radians(angle_degrees)
  cosine = math.cos(angle)
  sine = math.sin(angle)
  return (
    origin[0] + point[0] * cosine - point[1] * sine,
    origin[1] + point[0] * sine + point[1] * cosine,
  )


def _board_component_problems(board_text: str) -> list[str]:
  footprints: dict[str, list[str]] = {}
  for footprint in forms_named(board_text, "footprint"):
    reference = _property(footprint, "Reference")
    if reference is not None:
      footprints.setdefault(reference, []).append(footprint)

  problems: list[str] = []
  for reference, expected in EXPECTED_BOARD_COMPONENTS.items():
    matches = footprints.get(reference, [])
    if len(matches) != 1:
      problems.append(
        f"{reference}: expected one PCB footprint, actual={len(matches)}"
      )
      continue
    footprint = matches[0]
    actual_name = _footprint_name(footprint) or ""
    if actual_name != expected["footprint"]:
      problems.append(
        f"{reference}: expected PCB footprint={expected['footprint']!r}, "
        f"actual={actual_name!r}"
      )
    actual_value = _property(footprint, "Value") or ""
    if actual_value != expected["value"]:
      problems.append(
        f"{reference}: expected PCB value={expected['value']!r}, "
        f"actual={actual_value!r}"
      )
    for name, expected_value in expected.get("properties", {}).items():
      actual_value = _property(footprint, name)
      if actual_value != expected_value:
        problems.append(
          f"{reference}: expected PCB {name}={expected_value!r}, "
          f"actual={actual_value!r}"
        )
    attributes = _footprint_attributes(footprint)
    missing_attributes = sorted(expected["attributes"] - attributes)
    if missing_attributes:
      problems.append(
        f"{reference}: missing PCB attributes={missing_attributes}"
      )
    expected_pad_groups = expected.get("net_tie_pad_groups")
    if expected_pad_groups is not None:
      actual_pad_groups = _quoted(footprint, "net_tie_pad_groups")
      if actual_pad_groups != expected_pad_groups:
        problems.append(
          f"{reference}: expected net_tie_pad_groups="
          f"{expected_pad_groups!r}, actual={actual_pad_groups!r}"
        )
    expected_bridge = expected.get("bridge_polygon")
    if expected_bridge is not None:
      bridge_layer = expected["bridge_layer"]
      actual_bridges = [
        frozenset(
          _rounded_point((float(x), float(y)))
          for x, y in re.findall(
            r"\(xy\s+([-+\d.eE]+)\s+([-+\d.eE]+)\)",
            polygon,
          )
        )
        for polygon in forms_named(footprint, "fp_poly")
        if _quoted(polygon, "layer") == bridge_layer
        and "(fill yes)" in polygon
      ]
      if actual_bridges != [expected_bridge]:
        problems.append(
          f"{reference}: expected one exact filled {bridge_layer} "
          "net-tie bridge between pads 1 and 2"
        )
  return problems


def _pad_problems(board_text: str, bounds: Bounds) -> list[str]:
  problems: list[str] = []
  for footprint in forms_named(board_text, "footprint"):
    origin = _number_pair(footprint, "at")
    if origin is None:
      continue
    footprint_layer = _quoted(footprint, "layer") or "F.Cu"
    footprint_at = re.search(
      r"\(at\s+[-+\d.eE]+\s+[-+\d.eE]+(?:\s+([-+\d.eE]+))?",
      footprint,
    )
    angle = (
      0.0
      if footprint_at is None or footprint_at.group(1) is None
      else float(footprint_at.group(1))
    )
    if footprint_layer == "B.Cu":
      angle = -angle
    reference = _property(footprint, "Reference") or "?"
    for pad in forms_named(footprint, "pad"):
      layers = _layers(pad)
      if not any(layer.endswith(".Cu") or layer == "*.Cu" for layer in layers):
        continue
      local = _number_pair(pad, "at")
      size = _number_pair(pad, "size")
      if local is None or size is None:
        continue
      center = _transform(local, origin, angle)
      radius = math.hypot(*size) / 2
      net = _net_name(pad)
      pad_number_match = re.match(r'\(pad\s+"([^"]*)"', pad)
      pad_number = "?" if pad_number_match is None else pad_number_match.group(1)
      if _point_inside(center, bounds.expanded(radius)):
        qualifier = "antenna-net" if net in ANTENNA_NETS else "foreign"
        problems.append(
          f"{qualifier} pad {reference}.{pad_number} on {net} "
          "enters NFC quiet area"
        )

      pad_at = re.search(
        r"\(at\s+[-+\d.eE]+\s+[-+\d.eE]+(?:\s+([-+\d.eE]+))?",
        pad,
      )
      pad_angle = (
        0.0
        if pad_at is None or pad_at.group(1) is None
        else float(pad_at.group(1))
      )
      if footprint_layer == "B.Cu":
        pad_angle = -pad_angle
      for kind in (
        "gr_line",
        "gr_arc",
        "gr_rect",
        "gr_circle",
        "gr_poly",
        "gr_curve",
      ):
        for primitive in forms_named(pad, kind):
          if _graphic_intersects(
            kind,
            primitive,
            bounds,
            center,
            angle + pad_angle,
          ):
            problems.append(
              f"custom-pad copper {reference}.{pad_number} on {net} "
              "enters NFC quiet area"
            )
  return problems


def _graphic_intersects(
  kind: str,
  form: str,
  bounds: Bounds,
  origin: Point = (0.0, 0.0),
  angle: float = 0.0,
) -> bool:
  width = _number(form, "width")
  expanded = bounds.expanded(width / 2)

  def transformed(field: str) -> Point | None:
    point = _number_pair(form, field)
    return None if point is None else _transform(point, origin, angle)

  if kind.endswith("text_box"):
    local_start = _number_pair(form, "start")
    local_end = _number_pair(form, "end")
    if local_start is None or local_end is None:
      return False
    rectangle = [
      _transform(local_start, origin, angle),
      _transform((local_end[0], local_start[1]), origin, angle),
      _transform(local_end, origin, angle),
      _transform((local_start[0], local_end[1]), origin, angle),
    ]
    return _polygon_intersects_bounds(rectangle, expanded)
  if kind.endswith("text"):
    center = transformed("at")
    font_size = _number_pair(form, "size")
    if center is None or font_size is None:
      return False
    text_match = re.match(r'^\([^\s]+\s+"((?:\\.|[^"\\])*)"', form)
    contents = "" if text_match is None else text_match.group(1)
    lines = contents.split("\\n")
    half_width = max(1, max(map(len, lines))) * font_size[0] / 2
    half_height = max(1, len(lines)) * font_size[1] / 2
    radius = math.hypot(half_width, half_height) + width / 2
    return _point_inside(center, bounds.expanded(radius))
  if kind.endswith("line"):
    start = transformed("start")
    end = transformed("end")
    return start is not None and end is not None \
      and _line_intersects_bounds(start, end, expanded)
  if kind.endswith("arc"):
    points = [
      _transform(point, origin, angle)
      for point in _arc_points(form)
    ]
    return any(
      _line_intersects_bounds(start, end, expanded)
      for start, end in pairwise(points)
    )
  if kind.endswith("rect"):
    local_start = _number_pair(form, "start")
    local_end = _number_pair(form, "end")
    if local_start is None or local_end is None:
      return False
    rectangle = [
      _transform(local_start, origin, angle),
      _transform((local_end[0], local_start[1]), origin, angle),
      _transform(local_end, origin, angle),
      _transform((local_start[0], local_end[1]), origin, angle),
    ]
    return _polygon_intersects_bounds(rectangle, expanded)
  if kind.endswith("circle"):
    center = transformed("center")
    end = transformed("end")
    if center is None or end is None:
      return False
    radius = math.hypot(end[0] - center[0], end[1] - center[1]) + width / 2
    nearest_x = min(max(center[0], bounds.left), bounds.right)
    nearest_y = min(max(center[1], bounds.top), bounds.bottom)
    return math.hypot(center[0] - nearest_x, center[1] - nearest_y) <= radius
  if kind.endswith("poly") or kind.endswith("curve"):
    polygon = [
      _transform((float(x), float(y)), origin, angle)
      for x, y in re.findall(
        r"\(xy\s+([-+\d.eE]+)\s+([-+\d.eE]+)\)",
        form,
      )
    ]
    return len(polygon) >= 2 and (
      _polygon_intersects_bounds(polygon, expanded)
      if len(polygon) >= 3
      else _line_intersects_bounds(polygon[0], polygon[1], expanded)
    )
  return False


def _graphic_problems(board_text: str, bounds: Bounds) -> list[str]:
  problems: list[str] = []
  board_graphics = (
    "gr_line",
    "gr_arc",
    "gr_rect",
    "gr_circle",
    "gr_poly",
    "gr_curve",
    "gr_text",
    "gr_text_box",
  )
  for kind in board_graphics:
    for form in forms_named(board_text, kind):
      layer = _quoted(form, "layer")
      if layer in COPPER_LAYERS \
          and _graphic_intersects(kind, form, bounds):
        problems.append(
          f"foreign copper graphic {kind} on {layer} enters NFC quiet area"
        )

  footprint_graphics = tuple(
    kind.replace("gr_", "fp_") for kind in board_graphics
  )
  for footprint in forms_named(board_text, "footprint"):
    origin = _number_pair(footprint, "at")
    if origin is None:
      continue
    footprint_layer = _quoted(footprint, "layer") or "F.Cu"
    footprint_at = re.search(
      r"\(at\s+[-+\d.eE]+\s+[-+\d.eE]+(?:\s+([-+\d.eE]+))?",
      footprint,
    )
    angle = (
      0.0
      if footprint_at is None or footprint_at.group(1) is None
      else float(footprint_at.group(1))
    )
    if footprint_layer == "B.Cu":
      angle = -angle
    reference = _property(footprint, "Reference") or "?"
    for kind in footprint_graphics:
      for form in forms_named(footprint, kind):
        layer = _quoted(form, "layer")
        if layer in COPPER_LAYERS \
            and _graphic_intersects(kind, form, bounds, origin, angle):
          problems.append(
            f"foreign copper graphic {reference}/{kind} on {layer} "
            "enters NFC quiet area"
          )
  return problems


def _zone_problems(board_text: str, bounds: Bounds) -> list[str]:
  problems: list[str] = []
  for zone in forms_named(board_text, "zone"):
    if "(keepout" in zone:
      continue
    net = _net_name(zone)
    if net in ANTENNA_NETS:
      continue
    for filled in forms_named(zone, "filled_polygon"):
      polygon = [
        (float(x), float(y))
        for x, y in re.findall(
          r"\(xy\s+([-+\d.eE]+)\s+([-+\d.eE]+)\)",
          filled,
        )
      ]
      if len(polygon) >= 3 \
          and _polygon_intersects_bounds(polygon, bounds.inset(1e-4)):
        layer = _quoted(filled, "layer") or _quoted(zone, "layer") or "?"
        problems.append(
          f"foreign zone fill on {net} / {layer} enters NFC quiet area"
        )
        break
  return problems


def _rule_area_problems(board_text: str, bounds: Bounds) -> list[str]:
  layers: set[str] = set()
  problems: list[str] = []
  for zone in forms_named(board_text, "zone"):
    if _quoted(zone, "name") != RULE_AREA_NAME:
      continue
    layer = _quoted(zone, "layer")
    if layer is not None:
      layers.add(layer)
    polygon_form = next(iter(forms_named(zone, "polygon")), "")
    polygon = [
      (float(x), float(y))
      for x, y in re.findall(
        r"\(xy\s+([-+\d.eE]+)\s+([-+\d.eE]+)\)",
        polygon_form,
      )
    ]
    expected_corners = {
      (bounds.left, bounds.top),
      (bounds.right, bounds.top),
      (bounds.right, bounds.bottom),
      (bounds.left, bounds.bottom),
    }
    if set(polygon) != expected_corners:
      problems.append(
        f"{RULE_AREA_NAME} on {layer or '?'} has unexpected outline"
      )
    if "(copperpour not_allowed)" not in zone:
      problems.append(
        f"{RULE_AREA_NAME} on {layer or '?'} does not block zone fills"
      )
    if "(footprints not_allowed)" not in zone:
      problems.append(
        f"{RULE_AREA_NAME} on {layer or '?'} does not block footprints"
      )
  missing_layers = sorted(COPPER_LAYERS - layers)
  extra_layers = sorted(layers - COPPER_LAYERS)
  if missing_layers or extra_layers:
    problems.append(
      f"{RULE_AREA_NAME} layers: missing={missing_layers}, extra={extra_layers}"
    )
  return problems


def board_problems(board_text: str) -> list[str]:
  bounds = quiet_bounds()
  return [
    *_board_component_problems(board_text),
    *_rule_area_problems(board_text, bounds),
    *_antenna_route_problems(board_text),
    *_track_problems(board_text, bounds),
    *_pad_problems(board_text, bounds),
    *_graphic_problems(board_text, bounds),
    *_zone_problems(board_text, bounds),
  ]


def verify(
  schematic: Path,
  board: Path,
  kicad_cli: Path | None = None,
) -> None:
  problems = [
    *schematic_problems(export_netlist_xml(schematic, kicad_cli)),
    *board_problems(board.read_text()),
  ]
  if problems:
    raise RuntimeError(
      "Rev B NFC verification failed:\n  - " + "\n  - ".join(problems)
    )
  print(
    "NFC design OK: GPIO21 pull-up, split AC nets, "
    "nine-turn antenna quiet area"
  )


def main() -> None:
  parser = argparse.ArgumentParser()
  parser.add_argument("--schematic", type=Path, default=DEFAULT_SCHEMATIC)
  parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
  parser.add_argument("--kicad-cli", type=Path)
  args = parser.parse_args()
  verify(
    args.schematic.resolve(),
    args.board.resolve(),
    args.kicad_cli,
  )


if __name__ == "__main__":
  main()
