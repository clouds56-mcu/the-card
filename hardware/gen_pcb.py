#!/usr/bin/env python3
"""Generate the-card's four-layer PCB layout from the schematic.

Run this script with KiCad's bundled Python so the ``pcbnew`` module is
available:

  /Applications/KiCad/KiCad.app/Contents/Frameworks/\
Python.framework/Versions/3.9/bin/python3 gen_pcb.py

The schematic remains authoritative for components and connectivity. This file
owns board mechanics, placement, layer assignment, keepouts, routing, and
net-class defaults.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile
import textwrap
import xml.etree.ElementTree as ET

import pcbnew

from pcb_router import route_board


HERE = Path(__file__).resolve().parent
PROJECT = HERE / "the-card.kicad_pro"
SCHEMATIC = HERE / "the-card.kicad_sch"
OUTPUT = HERE / "the-card.kicad_pcb"
PROJECT_PRETTY = HERE / "libraries" / "the-card.pretty"

KICAD_APP = Path("/Applications/KiCad/KiCad.app/Contents")
KICAD_CLI = KICAD_APP / "MacOS" / "kicad-cli"
KICAD_FOOTPRINTS = KICAD_APP / "SharedSupport" / "footprints"

BOARD_X = 20.0
BOARD_Y = 20.0
BOARD_W = 53.98
BOARD_H = 85.60
CORNER_R = 3.18

DISPLAY_X = 8.64
DISPLAY_Y = 3.30
DISPLAY_W = 36.70
DISPLAY_H = 79.00

# 603048 means approximately 6.0 mm thick, 30 mm wide, and 48 mm long.
BATTERY_X = 13.50
BATTERY_Y = 27.00
BATTERY_W = 30.00
BATTERY_H = 48.00

# Non-fabrication copper-layer thumbnails displayed beside the real board in
# PCB Editor. Coordinates are absolute because the images are injected into the
# saved board file after KiCad exports and rasterizes each SVG layer plot.
LAYER_REFERENCE_VIEWS = (
  ("F.Cu", "L1  F.Cu", 92.60, 40.00, "73b59665-b9b6-4dd7-8a24-028f7ae36dda"),
  ("In1.Cu", "L2  In1.Cu", 122.75, 40.00, "eb349994-862d-4d0d-bfd6-fdb6ac2aec24"),
  ("In2.Cu", "L3  In2.Cu", 92.60, 84.90, "b62a3980-d435-4a87-b44d-4af47b18a15e"),
  ("B.Cu", "L4  B.Cu", 122.75, 84.90, "6752edb1-510d-4e52-9044-e5f8bbcc7f34"),
)
LAYER_REFERENCE_RASTER_WIDTH = 540
LAYER_REFERENCE_SCALE = 0.55

SCHEMATIC_FIELD_EXCLUSIONS = {
  "Component Class",
  "Footprint",
  "Reference",
  "Value",
}


@dataclass(frozen=True)
class Placement:
  x: float
  y: float
  rotation: float = 0.0
  side: str = "B"


def p(x: float, y: float, rotation: float = 0.0, side: str = "B") -> Placement:
  return Placement(x, y, rotation, side)


# Coordinates are local to the top-left of the board. The front is reserved for
# the display and user controls; electronics and the battery live on the rear.
PLACEMENTS = {
  # MCU and its local support parts.
  "U1": p(27.00, 16.90, 180),
  "C1": p(38.00, 8.20, 90),
  "C2": p(40.50, 8.20, 90),
  "C3": p(40.00, 11.20, 90),
  "C4": p(14.00, 8.50, 90),
  "R1": p(37.50, 11.20, 90),
  "R2": p(14.00, 24.00, 90),
  "R3": p(14.00, 11.20, 90),
  "R4": p(14.00, 13.70, 90),
  "TP3": p(42.00, 16.00),
  "TP4": p(42.00, 19.00),
  "TP5": p(42.00, 13.00),
  "TP6": p(11.00, 24.00),

  # NFC and I2C sensors in the rear left service strip.
  "U2": p(6.00, 34.00, 90),
  "C11": p(11.20, 31.50),
  "R13": p(11.00, 34.50),
  "R14": p(11.00, 36.50),
  "U3": p(6.00, 43.00, 90),
  "C12": p(11.00, 41.50),
  "C13": p(11.00, 44.50),
  "U4": p(6.00, 51.00, 90),
  "C14": p(11.00, 51.00),
  "U5": p(6.00, 58.50, 90),
  "C10": p(11.00, 58.50),
  "U9": p(6.00, 63.50, 90),
  "C8": p(11.00, 62.00),
  "C9": p(11.00, 64.50),

  # USB, charger, cell protection, and battery connection.
  "J1": p(6.00, 80.50),
  "U10": p(14.50, 81.00, 90),
  "R5": p(12.50, 76.50, 90),
  "R6": p(14.50, 76.50, 90),
  "C5": p(16.50, 76.50, 90),
  "U6": p(6.00, 71.50, 90),
  "R7": p(11.50, 69.50),
  "R8": p(11.50, 71.50),
  "C6": p(11.50, 73.50),
  "J3": p(48.75, 24.00, 90),
  "U7": p(48.00, 73.50, 90),
  "U8": p(48.00, 79.00, 90),
  "R9": p(44.50, 72.00, 90),
  "R10": p(51.00, 72.00, 90),
  "C7": p(44.50, 74.50, 90),
  "TP1": p(8.50, 60.50),
  "TP2": p(51.00, 75.00),

  # E-paper power and 24-pin FPC connector in the rear right strip.
  "Q2": p(47.00, 30.50, 90),
  "R12": p(50.50, 30.50, 90),
  "C20": p(47.00, 33.00),
  "L1": p(48.00, 38.00),
  "Q3": p(47.00, 43.00, 90),
  "R15": p(50.50, 42.00, 90),
  "R16": p(50.50, 44.40),
  "D4": p(46.50, 48.00, 90),
  "D3": p(50.50, 48.00, 90),
  "D2": p(46.50, 53.20, 90),
  "C21": p(50.50, 53.20),
  "C22": p(46.00, 57.00),
  "C23": p(50.00, 57.00),
  "C24": p(46.00, 60.00),
  "C25": p(50.00, 60.00),
  "C26": p(46.00, 63.00),
  "C27": p(50.00, 63.00),
  "C28": p(46.00, 66.00),
  "Q1": p(9.00, 67.00, 90),
  "R11": p(12.00, 68.50),
  "J2": p(27.00, 80.40),

  # Front-facing controls and local debounce/decoupling capacitors.
  "D1": p(4.70, 64.00, 0, "F"),
  "C15": p(8.00, 64.00, 90, "F"),
  "SW1": p(49.50, 38.50, 0, "F"),
  "SW2": p(49.50, 49.50, 0, "F"),
  "SW3": p(49.50, 60.50, 0, "F"),
  "SW4": p(49.50, 71.50, 0, "F"),
  "C16": p(46.20, 38.50, 90, "F"),
  "C17": p(46.20, 49.50, 90, "F"),
  "C18": p(46.20, 60.50, 90, "F"),
  "C19": p(46.20, 71.50, 90, "F"),
}


POWER_NETS = {
  "+BAT",
  "+3V3",
  "AUX_3V3",
  "EPD_VCI",
  "EPD_VDD_CORE",
  "GND",
  "VBUS",
}
EPD_HV_NETS = {
  "EPD_PUMP",
  "EPD_SW",
  "EPD_VCOM",
  "EPD_VGH",
  "EPD_VGL",
  "EPD_VSH1",
  "EPD_VSH2",
  "EPD_VSL",
}
USB_NETS = {"USB_DP", "USB_DM", "Net-(J1-DP1)", "Net-(J1-DN1)"}


def mm(value: float) -> int:
  return pcbnew.FromMM(value)


def point(x: float, y: float) -> pcbnew.VECTOR2I:
  return pcbnew.VECTOR2I(mm(BOARD_X + x), mm(BOARD_Y + y))


def export_netlist() -> ET.Element:
  with tempfile.NamedTemporaryFile(suffix=".xml") as output:
    subprocess.run(
      [
        str(KICAD_CLI),
        "sch",
        "export",
        "netlist",
        "--format",
        "kicadxml",
        "--output",
        output.name,
        str(SCHEMATIC),
      ],
      check=True,
    )
    return ET.parse(output.name).getroot()


def footprint_path(identifier: str) -> tuple[Path, str]:
  library, name = identifier.split(":", 1)
  if library == "the-card":
    return PROJECT_PRETTY, name
  return KICAD_FOOTPRINTS / f"{library}.pretty", name


def add_netclass(
  board: pcbnew.BOARD,
  name: str,
  clearance: float,
  track_width: float,
  via_diameter: float,
  via_drill: float,
) -> pcbnew.NETCLASS:
  netclass = pcbnew.NETCLASS(name)
  netclass.SetClearance(mm(clearance))
  netclass.SetTrackWidth(mm(track_width))
  netclass.SetViaDiameter(mm(via_diameter))
  netclass.SetViaDrill(mm(via_drill))
  board.GetNetClasses()[name] = netclass
  return netclass


def configure_board(board: pcbnew.BOARD) -> dict[str, pcbnew.NETCLASS]:
  board.SetCopperLayerCount(4)
  settings = board.GetDesignSettings()
  settings.SetBoardThickness(mm(0.80))
  settings.m_TrackMinWidth = mm(0.15)
  settings.m_ViasMinSize = mm(0.50)
  settings.m_MinThroughDrill = mm(0.25)

  default = pcbnew.NETCLASS("Default")
  default.SetClearance(mm(0.20))
  default.SetTrackWidth(mm(0.20))
  default.SetViaDiameter(mm(0.60))
  default.SetViaDrill(mm(0.30))
  board.GetNetClasses()["Default"] = default

  power = add_netclass(board, "Power", 0.20, 0.50, 0.70, 0.35)
  epd_hv = add_netclass(board, "EPD_HV", 0.30, 0.25, 0.60, 0.30)
  usb = add_netclass(board, "USB", 0.15, 0.18, 0.50, 0.25)
  usb.SetDiffPairWidth(mm(0.18))
  usb.SetDiffPairGap(mm(0.15))
  nfc = add_netclass(board, "NFC", 0.25, 0.50, 0.70, 0.35)
  return {
    "Default": default,
    "Power": power,
    "EPD_HV": epd_hv,
    "USB": usb,
    "NFC": nfc,
  }


def add_nets(
  board: pcbnew.BOARD,
  netlist: ET.Element,
  netclasses: dict[str, pcbnew.NETCLASS],
) -> tuple[dict[str, pcbnew.NETINFO_ITEM], dict[tuple[str, str], str]]:
  nets: dict[str, pcbnew.NETINFO_ITEM] = {}
  pad_nets: dict[tuple[str, str], str] = {}
  for xml_net in netlist.find("nets") or []:
    name = xml_net.attrib["name"]
    net = pcbnew.NETINFO_ITEM(board, name)
    board.Add(net)
    if name in POWER_NETS:
      net.SetNetClass(netclasses["Power"])
    elif name in EPD_HV_NETS:
      net.SetNetClass(netclasses["EPD_HV"])
    elif name in USB_NETS:
      net.SetNetClass(netclasses["USB"])
    elif name == "NFC_ANTENNA":
      net.SetNetClass(netclasses["NFC"])
    nets[name] = net
    for node in xml_net:
      pad_nets[(node.attrib["ref"], node.attrib["pin"])] = name
  return nets, pad_nets


def add_footprints(
  board: pcbnew.BOARD,
  netlist: ET.Element,
  nets: dict[str, pcbnew.NETINFO_ITEM],
  pad_nets: dict[tuple[str, str], str],
) -> None:
  components = list(netlist.find("components") or [])
  refs = {component.attrib["ref"] for component in components}
  missing = sorted(refs - PLACEMENTS.keys())
  extra = sorted(PLACEMENTS.keys() - refs)
  if missing or extra:
    raise ValueError(f"placement mismatch: missing={missing}, extra={extra}")

  for component in components:
    ref = component.attrib["ref"]
    value = component.findtext("value") or ""
    identifier = component.findtext("footprint") or ""
    library_path, footprint_name = footprint_path(identifier)
    footprint = pcbnew.FootprintLoad(str(library_path), footprint_name)
    if footprint is None:
      raise FileNotFoundError(f"unable to load footprint {identifier}")
    if ref == "J3":
      # KiCad 10 ships this exact JST footprint but not its matching 3D model.
      # Reuse the supplier model fetched from LCSC so 3D assembly review still
      # shows the connector while retaining KiCad's reviewed land pattern.
      models = footprint.Models()
      if len(models) != 1:
        raise ValueError(f"expected one 3D model for {identifier}")
      model = models[0]
      model.m_Filename = (
        "${KIPRJMOD}/libraries/the-card.3dshapes/"
        "CONN-SMD_P2.00_S2B-PH-SM4-TB-LF-SN.step"
      )
      models[0] = model
    # Library footprints carry stable UUIDs. Each board instance needs fresh
    # UUIDs or KiCad's connectivity and DRC engines cannot distinguish copies.
    footprint.FixUuids()
    footprint.SetFPIDAsString(identifier)

    placement = PLACEMENTS[ref]
    board.Add(footprint)
    footprint.SetReference(ref)
    footprint.SetValue(value)
    if ref.startswith("TP"):
      footprint.SetExcludedFromBOM(True)
      footprint.SetExcludedFromPosFiles(True)
    footprint.SetPosition(point(placement.x, placement.y))
    if ref == "J1":
      # The USB-C receptacle mixes SMD contacts with plated through-hole shell
      # tabs. KiCad classifies mixed footprints by their through-hole pads.
      footprint.SetAttributes(pcbnew.FP_THROUGH_HOLE)
    if placement.side == "B":
      footprint.Flip(footprint.GetPosition(), False)
    footprint.SetOrientationDegrees(placement.rotation)

    footprint.Value().SetVisible(False)
    footprint.Reference().SetLayer(
      pcbnew.F_Fab if placement.side == "F" else pcbnew.B_Fab
    )
    footprint.Reference().SetTextSize(pcbnew.VECTOR2I(mm(0.80), mm(0.80)))
    footprint.Reference().SetTextThickness(mm(0.12))

    footprint_pads = {pad.GetNumber() for pad in footprint.Pads()}
    for pad in footprint.Pads():
      net_name = pad_nets.get((ref, pad.GetNumber()))
      if net_name:
        pad.SetNet(nets[net_name])
      if ref in {"U3", "U5", "U9"}:
        # These fine-pitch packages need a manufacturer-standard 0.10 mm local
        # escape clearance before tracks widen into the board defaults.
        pad.SetLocalClearance(mm(0.10))
      if ref == "J1":
        if not pad.GetNumber():
          pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
        else:
          # The receptacle's 0.5 mm contact pitch and wide power tabs use the
          # manufacturer's 0.10 mm local copper clearance.
          pad.SetLocalClearance(mm(0.10))
    expected_pads = {
      pin
      for (node_ref, pin), _net_name in pad_nets.items()
      if node_ref == ref
    }
    unresolved = sorted(expected_pads - footprint_pads)
    if unresolved:
      raise ValueError(f"{ref} is missing footprint pads {unresolved}")


def sync_schematic_fields(board: pcbnew.BOARD, netlist: ET.Element) -> None:
  """Copy schematic metadata after geometry UUIDs have been allocated.

  Creating a missing custom field consumes a KiCad UUID. Keeping that work
  after routing prevents a metadata-only edit from perturbing deterministic
  track, via, zone, or footprint UUIDs. KiCad owns the identity fields listed
  above; every other exported field must stay in schematic/footprint parity.
  """
  fields_by_ref = {
    component.attrib["ref"]: {
      field.attrib["name"]: field.text or ""
      for field in component.findall("./fields/field")
      if field.attrib["name"] not in SCHEMATIC_FIELD_EXCLUSIONS
    }
    for component in netlist.findall("./components/comp")
  }
  for footprint in board.GetFootprints():
    for field_name, value in fields_by_ref[footprint.GetReference()].items():
      footprint.SetField(field_name, value)
      footprint.GetField(field_name).SetVisible(False)


def add_line(
  board: pcbnew.BOARD,
  start: tuple[float, float],
  end: tuple[float, float],
  layer: int,
  width: float = 0.05,
) -> None:
  shape = pcbnew.PCB_SHAPE(board)
  shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
  shape.SetStart(point(*start))
  shape.SetEnd(point(*end))
  shape.SetLayer(layer)
  shape.SetWidth(mm(width))
  board.Add(shape)


def add_arc(
  board: pcbnew.BOARD,
  start: tuple[float, float],
  mid: tuple[float, float],
  end: tuple[float, float],
) -> None:
  shape = pcbnew.PCB_SHAPE(board)
  shape.SetShape(pcbnew.SHAPE_T_ARC)
  shape.SetArcGeometry(point(*start), point(*mid), point(*end))
  shape.SetLayer(pcbnew.Edge_Cuts)
  shape.SetWidth(mm(0.05))
  board.Add(shape)


def add_outline(board: pcbnew.BOARD) -> None:
  width = BOARD_W
  height = BOARD_H
  radius = CORNER_R
  diagonal = radius * 0.292893218
  tangent = radius * 0.707106782

  add_line(board, (radius, 0), (width - radius, 0), pcbnew.Edge_Cuts)
  add_arc(
    board,
    (width - radius, 0),
    (width - diagonal, radius - tangent),
    (width, radius),
  )
  add_line(board, (width, radius), (width, height - radius), pcbnew.Edge_Cuts)
  add_arc(
    board,
    (width, height - radius),
    (width - diagonal, height - radius + tangent),
    (width - radius, height),
  )
  add_line(board, (width - radius, height), (radius, height), pcbnew.Edge_Cuts)
  add_arc(
    board,
    (radius, height),
    (diagonal, height - radius + tangent),
    (0, height - radius),
  )
  add_line(board, (0, height - radius), (0, radius), pcbnew.Edge_Cuts)
  add_arc(
    board,
    (0, radius),
    (diagonal, radius - tangent),
    (radius, 0),
  )


def add_rectangle(
  board: pcbnew.BOARD,
  x: float,
  y: float,
  width: float,
  height: float,
  layer: int,
  line_width: float = 0.10,
) -> None:
  add_line(board, (x, y), (x + width, y), layer, line_width)
  add_line(board, (x + width, y), (x + width, y + height), layer, line_width)
  add_line(board, (x + width, y + height), (x, y + height), layer, line_width)
  add_line(board, (x, y + height), (x, y), layer, line_width)


def add_text(
  board: pcbnew.BOARD,
  text: str,
  x: float,
  y: float,
  layer: int,
  size: float = 1.0,
) -> None:
  item = pcbnew.PCB_TEXT(board)
  item.SetText(text)
  item.SetPosition(point(x, y))
  item.SetLayer(layer)
  item.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
  item.SetTextThickness(mm(max(0.10, size * 0.14)))
  if layer in {pcbnew.B_SilkS, pcbnew.B_Fab}:
    item.SetMirrored(True)
  board.Add(item)


def add_rule_area(
  board: pcbnew.BOARD,
  name: str,
  x: float,
  y: float,
  width: float,
  height: float,
  layers: list[int],
  block_footprints: bool,
  block_copper: bool,
) -> None:
  for layer in layers:
    zone = pcbnew.ZONE(board)
    zone.SetZoneName(name)
    zone.SetIsRuleArea(True)
    zone.SetLayer(layer)
    zone.SetDoNotAllowFootprints(block_footprints)
    zone.SetDoNotAllowPads(False)
    zone.SetDoNotAllowTracks(block_copper)
    zone.SetDoNotAllowVias(block_copper)
    zone.SetDoNotAllowZoneFills(block_copper)
    outline = zone.Outline()
    outline.NewOutline()
    outline.Append(point(x, y))
    outline.Append(point(x + width, y))
    outline.Append(point(x + width, y + height))
    outline.Append(point(x, y + height))
    board.Add(zone)


def add_ground_zone(board: pcbnew.BOARD, gnd: pcbnew.NETINFO_ITEM, layer: int) -> None:
  inset = 0.35
  zone = pcbnew.ZONE(board)
  zone.SetNet(gnd)
  zone.SetLayer(layer)
  zone.SetLocalClearance(mm(0.20))
  zone.SetMinThickness(mm(0.20))
  zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
  outline = zone.Outline()
  outline.NewOutline()
  outline.Append(point(inset, inset))
  outline.Append(point(BOARD_W - inset, inset))
  outline.Append(point(BOARD_W - inset, BOARD_H - inset))
  outline.Append(point(inset, BOARD_H - inset))
  board.Add(zone)


def add_zone_fill_keepout(
  board: pcbnew.BOARD,
  name: str,
  x: float,
  y: float,
  width: float,
  height: float,
) -> None:
  """Keep plane pours out while allowing the intentional antenna tracks."""
  for layer in [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu]:
    zone = pcbnew.ZONE(board)
    zone.SetZoneName(name)
    zone.SetIsRuleArea(True)
    zone.SetLayer(layer)
    zone.SetDoNotAllowFootprints(False)
    zone.SetDoNotAllowPads(False)
    zone.SetDoNotAllowTracks(False)
    zone.SetDoNotAllowVias(False)
    zone.SetDoNotAllowZoneFills(True)
    outline = zone.Outline()
    outline.NewOutline()
    outline.Append(point(x, y))
    outline.Append(point(x + width, y))
    outline.Append(point(x + width, y + height))
    outline.Append(point(x, y + height))
    board.Add(zone)


def add_power_zone(board: pcbnew.BOARD, power: pcbnew.NETINFO_ITEM) -> None:
  inset = 0.55
  zone = pcbnew.ZONE(board)
  zone.SetNet(power)
  zone.SetLayer(pcbnew.In2_Cu)
  zone.SetLocalClearance(mm(0.20))
  zone.SetMinThickness(mm(0.20))
  zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
  outline = zone.Outline()
  outline.NewOutline()
  outline.Append(point(inset, inset))
  outline.Append(point(BOARD_W - inset, inset))
  outline.Append(point(BOARD_W - inset, BOARD_H - inset))
  outline.Append(point(inset, BOARD_H - inset))
  board.Add(zone)


def add_mechanics(board: pcbnew.BOARD) -> None:
  add_outline(board)
  add_rectangle(
    board,
    DISPLAY_X,
    DISPLAY_Y,
    DISPLAY_W,
    DISPLAY_H,
    pcbnew.F_Fab,
  )
  add_text(
    board,
    "DISPLAY GDEY029T94 36.7 x 79 mm",
    DISPLAY_X + DISPLAY_W / 2,
    DISPLAY_Y + 2.0,
    pcbnew.F_Fab,
    0.90,
  )
  add_rectangle(
    board,
    BATTERY_X,
    BATTERY_Y,
    BATTERY_W,
    BATTERY_H,
    pcbnew.B_Fab,
  )
  add_text(
    board,
    "BATTERY 603048 30 x 48 mm",
    BATTERY_X + BATTERY_W / 2,
    BATTERY_Y + 2.0,
    pcbnew.B_Fab,
    0.90,
  )
  add_text(board, "THE CARD", 27.0, 84.0, pcbnew.F_SilkS, 1.0)
  add_text(board, "REV A - 4L / 0.8 mm", 27.0, 28.5, pcbnew.B_SilkS, 0.80)
  # These assembly-critical marks are intentionally explicit instead of relying
  # on connector conventions: battery leads are not polarity-standardized, and
  # the bottom-contact FPC connector otherwise has no visible pin-1 cue.
  add_text(board, "BAT+", 42.0, 24.0, pcbnew.B_SilkS, 0.80)
  add_text(board, "BAT-", 42.0, 22.0, pcbnew.B_SilkS, 0.80)
  add_text(board, "J2 PIN 1", 21.0, 73.5, pcbnew.B_SilkS, 0.80)
  add_text(
    board,
    "COPPER LAYER REFERENCE VIEWS - NON-FABRICATION",
    87.70,
    -7.50,
    pcbnew.Cmts_User,
    1.20,
  )
  for _, label, x, y, _ in LAYER_REFERENCE_VIEWS:
    label_y = y - 22.20
    add_text(board, label, x - BOARD_X, label_y - BOARD_Y, pcbnew.Cmts_User, 1.00)

  add_rule_area(
    board,
    "DISPLAY_COMPONENT_KEEPOUT",
    DISPLAY_X,
    DISPLAY_Y,
    DISPLAY_W,
    DISPLAY_H,
    [pcbnew.F_Cu],
    block_footprints=True,
    block_copper=False,
  )
  add_rule_area(
    board,
    "BATTERY_COMPONENT_KEEPOUT",
    BATTERY_X,
    BATTERY_Y,
    BATTERY_W,
    BATTERY_H,
    [pcbnew.B_Cu],
    block_footprints=True,
    block_copper=False,
  )
  add_rule_area(
    board,
    "ESP32_ANTENNA_KEEPOUT",
    17.50,
    0.20,
    19.00,
    7.20,
    [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu],
    block_footprints=False,
    block_copper=True,
  )
  add_zone_fill_keepout(
    board,
    "NFC_ANTENNA_PLANE_KEEPOUT",
    0.50,
    8.00,
    7.80,
    51.50,
  )


def generate() -> None:
  # KiCad assigns UUIDs as board items are created. A fixed generator seed keeps
  # this code-generated board byte-for-byte stable across identical runs.
  pcbnew.KIID.SeedGenerator(0x54484344)
  netlist = export_netlist()
  board = pcbnew.BOARD()
  board.SetFileName(str(OUTPUT))
  netclasses = configure_board(board)
  nets, pad_nets = add_nets(board, netlist, netclasses)
  add_footprints(board, netlist, nets, pad_nets)
  add_mechanics(board)

  route_board(board)

  for layer in [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.B_Cu]:
    add_ground_zone(board, nets["GND"], layer)
  add_power_zone(board, nets["+3V3"])

  board.BuildListOfNets()
  # Zone island removal depends on current pad/track connectivity. Building it
  # explicitly keeps headless generation deterministic; otherwise pcbnew can
  # serialize floating fill fragments depending on internal cache state.
  board.BuildConnectivity()
  pcbnew.ZONE_FILLER(board).Fill(board.Zones())
  sync_schematic_fields(board, netlist)
  pcbnew.SaveBoard(str(OUTPUT), board)
  add_layer_reference_views(OUTPUT)
  print(f"wrote {OUTPUT.name}")
  print(
    f"footprints={len(list(board.GetFootprints()))} "
    f"nets={board.GetNetCount()} layers={board.GetCopperLayerCount()}"
  )


def _rasterize_svg(svg_path: Path, png_path: Path) -> None:
  """Rasterize a KiCad SVG plot without starting a GUI application."""
  import wx
  import wx.svg

  svg = wx.svg.SVGimage.CreateFromFile(str(svg_path))
  scale = LAYER_REFERENCE_RASTER_WIDTH / svg.width
  height = round(svg.height * scale)
  bitmap = svg.ConvertToBitmap(
    scale=scale,
    width=LAYER_REFERENCE_RASTER_WIDTH,
    height=height,
  )
  if not bitmap.SaveFile(str(png_path), wx.BITMAP_TYPE_PNG):
    raise RuntimeError(f"unable to rasterize {svg_path.name}")


def _reference_image_block(
  png_path: Path,
  x: float,
  y: float,
  image_uuid: str,
) -> str:
  encoded = base64.b64encode(png_path.read_bytes()).decode("ascii")
  data_lines = "\n".join(f'\t\t\t"{chunk}"' for chunk in textwrap.wrap(encoded, 76))
  return (
    "\t(image\n"
    f"\t\t(at {x:.2f} {y:.2f})\n"
    f"\t\t(scale {LAYER_REFERENCE_SCALE:.2f})\n"
    "\t\t(layer \"Cmts.User\")\n"
    f"\t\t(data\n{data_lines}\n\t\t)\n"
    f"\t\t(uuid \"{image_uuid}\")\n"
    "\t)\n"
  )


def add_layer_reference_views(board_path: Path) -> None:
  """Embed four non-physical copper-layer views beside the generated board."""
  with tempfile.TemporaryDirectory(prefix="the-card-layer-views-") as directory:
    output_dir = Path(directory)
    blocks: list[str] = []
    for layer, _, x, y, image_uuid in LAYER_REFERENCE_VIEWS:
      svg_path = output_dir / f"{layer.lower().replace('.', '-')}.svg"
      png_path = svg_path.with_suffix(".png")
      subprocess.run(
        [
          str(KICAD_CLI),
          "pcb",
          "export",
          "svg",
          "--mode-single",
          "--layers",
          f"{layer},Edge.Cuts",
          "--page-size-mode",
          "2",
          "--exclude-drawing-sheet",
          "--output",
          str(svg_path),
          str(board_path),
        ],
        check=True,
      )
      _rasterize_svg(svg_path, png_path)
      blocks.append(_reference_image_block(png_path, x, y, image_uuid))

  contents = board_path.read_text()
  closing = contents.rfind("\n)")
  if closing < 0:
    raise RuntimeError(f"invalid KiCad board file: {board_path}")
  board_path.write_text(contents[:closing] + "\n" + "".join(blocks) + contents[closing:])


if __name__ == "__main__":
  generate()
