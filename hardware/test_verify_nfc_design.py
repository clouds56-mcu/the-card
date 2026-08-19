#!/usr/bin/env python3
"""Focused tests for the v0.2.0 NFC design verifier."""

from __future__ import annotations

from itertools import pairwise
import unittest
import xml.etree.ElementTree as ET

from nfc_antenna import RULE_AREA_NAME, TRACK_WIDTH_MM, spiral_points
from verify_nfc_design import board_problems, schematic_problems


VALID_COMPONENTS = {
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
    "properties": ("dnp",),
  },
  "L2": {
    "value": "PCB NFC antenna",
    "footprint": "NetTie:NetTie-2_SMD_Pad0.5mm",
    "properties": ("exclude_from_bom",),
  },
}


def netlist_xml(
  *nets: tuple[str, tuple[tuple[str, str], ...]],
  components: dict[str, dict[str, object]] | None = None,
) -> ET.Element:
  root = ET.Element("export")
  component_root = ET.SubElement(root, "components")
  for reference, metadata in (components or VALID_COMPONENTS).items():
    component = ET.SubElement(component_root, "comp", ref=reference)
    for field in ("value", "footprint", "datasheet"):
      if field in metadata:
        ET.SubElement(component, field).text = str(metadata[field])
    for name in metadata.get("properties", ()):
      ET.SubElement(component, "property", name=str(name))

  net_root = ET.SubElement(root, "nets")
  for code, (name, nodes) in enumerate(nets, start=1):
    net = ET.SubElement(net_root, "net", code=str(code), name=name)
    for reference, pin in nodes:
      ET.SubElement(net, "node", ref=reference, pin=pin)
  return root


def valid_netlist() -> ET.Element:
  return netlist_xml(
    ("+3V3", (("R17", "1"), ("U2", "8"))),
    ("NFC_IRQ", (("R17", "2"), ("U1", "23"), ("U2", "7"))),
    ("NFC_AC0", (("C29", "1"), ("L2", "1"), ("U2", "2"))),
    ("NFC_AC1", (("C29", "2"), ("L2", "2"), ("U2", "3"))),
    ("unconnected-(U1-IO3-Pad15)", (("U1", "15"),)),
  )


def rule_area(layer: str) -> str:
  return f"""
    (zone
      (layer "{layer}")
      (name "{RULE_AREA_NAME}")
      (keepout
        (footprints not_allowed)
        (copperpour not_allowed)
      )
      (polygon
        (pts
          (xy 20.35 27.5)
          (xy 29.5 27.5)
          (xy 29.5 78.0)
          (xy 20.35 78.0)
        )
      )
    )
  """


def valid_board(*extra: str) -> str:
  areas = "".join(
    rule_area(layer)
    for layer in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
  )
  coil = "".join(
    f"""
      (segment
        (start {start[0]} {start[1]})
        (end {end[0]} {end[1]})
        (width {TRACK_WIDTH_MM})
        (layer "F.Cu")
        (net "NFC_AC0")
      )
    """
    for start, end in pairwise(spiral_points())
  )
  coil_start = spiral_points()[0]
  inner_x, inner_y = spiral_points()[-1]
  reviewed_feeds = f"""
    (segment
      (start 28.5 27.4)
      (end {coil_start[0]} 27.4)
      (width {TRACK_WIDTH_MM})
      (layer "F.Cu")
      (net "NFC_AC0")
    )
    (segment
      (start {coil_start[0]} 27.4)
      (end {coil_start[0]} {coil_start[1]})
      (width {TRACK_WIDTH_MM})
      (layer "F.Cu")
      (net "NFC_AC0")
    )
    (segment
      (start 30.45 24.43)
      (end 28.8 24.28)
      (width {TRACK_WIDTH_MM})
      (layer "B.Cu")
      (net "NFC_AC0")
    )
    (segment
      (start 28.8 24.28)
      (end 28.5 25.2)
      (width {TRACK_WIDTH_MM})
      (layer "B.Cu")
      (net "NFC_AC0")
    )
    (segment
      (start 28.5 25.2)
      (end 28.5 27.4)
      (width {TRACK_WIDTH_MM})
      (layer "B.Cu")
      (net "NFC_AC0")
    )
    (segment
      (start {inner_x} {inner_y})
      (end {inner_x} 25.8)
      (width {TRACK_WIDTH_MM})
      (layer "B.Cu")
      (net "NFC_AC0")
    )
    (segment
      (start {inner_x} 25.8)
      (end 26 25.8)
      (width {TRACK_WIDTH_MM})
      (layer "B.Cu")
      (net "NFC_AC0")
    )
    (segment
      (start 26 25.8)
      (end 26 23.3)
      (width {TRACK_WIDTH_MM})
      (layer "B.Cu")
      (net "NFC_AC0")
    )
    (segment
      (start 30.45 23.17)
      (end 28.8 23.32)
      (width {TRACK_WIDTH_MM})
      (layer "B.Cu")
      (net "NFC_AC1")
    )
    (segment
      (start 28.8 23.32)
      (end 27 23.3)
      (width {TRACK_WIDTH_MM})
      (layer "B.Cu")
      (net "NFC_AC1")
    )
  """
  component_footprints = """
    (footprint "the-card:SO-8_L4.9-W3.9-P1.27-LS6.0-BL"
      (layer "B.Cu")
      (at 40 20)
      (property "Reference" "U2")
      (property "Value" "ST25DV04KC-IE8S3")
      (attr smd)
    )
    (footprint "Resistor_SMD:R_0402_1005Metric"
      (layer "B.Cu")
      (at 42 20)
      (property "Reference" "R17")
      (property "Value" "10k")
      (attr smd)
    )
    (footprint "Capacitor_SMD:C_0402_1005Metric"
      (layer "B.Cu")
      (at 44 20)
      (property "Reference" "C29")
      (property "Value" "DNP 0-22pF C0G/NP0")
      (property "Datasheet" "")
      (attr smd dnp)
    )
    (footprint "NetTie:NetTie-2_SMD_Pad0.5mm"
      (layer "B.Cu")
      (at 46 20)
      (property "Reference" "L2")
      (property "Value" "PCB NFC antenna")
      (attr exclude_from_pos_files exclude_from_bom allow_missing_courtyard)
      (net_tie_pad_groups "1, 2")
      (fp_poly
        (pts
          (xy -0.5 0.25)
          (xy 0.5 0.25)
          (xy 0.5 -0.25)
          (xy -0.5 -0.25)
        )
        (stroke (width 0) (type solid))
        (fill yes)
        (layer "B.Cu")
      )
    )
  """
  return f"""
    (kicad_pcb
      {areas}
      {component_footprints}
      {coil}
      {reviewed_feeds}
      (via
        (at {inner_x} {inner_y})
        (size 0.6)
        (drill 0.3)
        (layers "F.Cu" "B.Cu")
        (net "NFC_AC0")
      )
      (via
        (at 28.5 27.4)
        (size 0.6)
        (drill 0.3)
        (layers "F.Cu" "B.Cu")
        (net "NFC_AC0")
      )
      {''.join(extra)}
    )
  """


class NfcSchematicTests(unittest.TestCase):
  def test_reviewed_connectivity_passes(self) -> None:
    self.assertEqual(schematic_problems(valid_netlist()), [])

  def test_irq_must_use_gpio21_and_external_pull_up(self) -> None:
    root = netlist_xml(
      ("+3V3", (("U2", "8"),)),
      ("NFC_IRQ", (("U1", "15"), ("U2", "7"))),
      ("NFC_AC0", (("C29", "1"), ("L2", "1"), ("U2", "2"))),
      ("NFC_AC1", (("C29", "2"), ("L2", "2"), ("U2", "3"))),
    )

    problems = schematic_problems(root)

    self.assertTrue(any(problem.startswith("NFC_IRQ:") for problem in problems))
    self.assertIn(
      "R17.1 must connect the NFC GPO pull-up to +3V3",
      problems,
    )
    self.assertIn(
      "U1.15 / GPIO3 must remain unconnected, found ['NFC_IRQ']",
      problems,
    )

  def test_ac0_and_ac1_must_stay_distinct(self) -> None:
    root = netlist_xml(
      ("+3V3", (("R17", "1"),)),
      ("NFC_IRQ", (("R17", "2"), ("U1", "23"), ("U2", "7"))),
      (
        "NFC_AC0",
        (
          ("C29", "1"),
          ("C29", "2"),
          ("L2", "1"),
          ("L2", "2"),
          ("U2", "2"),
          ("U2", "3"),
        ),
      ),
      ("unconnected-(U1-IO3-Pad15)", (("U1", "15"),)),
    )

    problems = schematic_problems(root)

    self.assertTrue(any(problem.startswith("NFC_AC0:") for problem in problems))
    self.assertTrue(any(problem.startswith("NFC_AC1:") for problem in problems))

  def test_exact_nfc_component_metadata_is_required(self) -> None:
    mutations = {
      "U2 variant": ("U2", "value", "ST25DV04K"),
      "R17 value": ("R17", "value", "100k"),
      "C29 value": ("C29", "value", "4.7pF"),
      "C29 datasheet": ("C29", "datasheet", "selected-part.pdf"),
      "L2 footprint": ("L2", "footprint", "Inductor_SMD:L_0402"),
    }
    for label, (reference, field, value) in mutations.items():
      with self.subTest(label=label):
        components = {
          ref: dict(metadata)
          for ref, metadata in VALID_COMPONENTS.items()
        }
        components[reference][field] = value
        problems = schematic_problems(netlist_xml(components=components))
        self.assertTrue(
          any(
            problem.startswith(f"{reference}: expected {field}=")
            for problem in problems
          ),
          problems,
        )

  def test_c29_dnp_and_l2_bom_exclusion_are_required(self) -> None:
    for reference, expected_property in (
      ("C29", "dnp"),
      ("L2", "exclude_from_bom"),
    ):
      with self.subTest(reference=reference):
        components = {
          ref: dict(metadata)
          for ref, metadata in VALID_COMPONENTS.items()
        }
        components[reference]["properties"] = ()
        problems = schematic_problems(netlist_xml(components=components))
        self.assertIn(
          f"{reference}: missing properties=['{expected_property}']",
          problems,
        )


class NfcBoardTests(unittest.TestCase):
  def test_reviewed_quiet_area_passes(self) -> None:
    self.assertEqual(board_problems(valid_board()), [])

  def test_foreign_track_crossing_quiet_area_fails(self) -> None:
    board = valid_board("""
      (segment
        (start 18.0 40.0)
        (end 32.0 40.0)
        (width 0.2)
        (layer "B.Cu")
        (net "GND")
      )
    """)

    self.assertIn(
      "foreign segment on GND enters NFC quiet area",
      board_problems(board),
    )

  def test_board_must_contain_the_modeled_spiral(self) -> None:
    board = valid_board()
    first_start, first_end = next(pairwise(spiral_points()))
    first_segment = f"""
      (segment
        (start {first_start[0]} {first_start[1]})
        (end {first_end[0]} {first_end[1]})
        (width {TRACK_WIDTH_MM})
        (layer "F.Cu")
        (net "NFC_AC0")
      )
    """

    problems = board_problems(board.replace(first_segment, "", 1))

    self.assertIn(
      "etched NFC antenna is missing 1 reviewed track segments",
      problems,
    )

  def test_extra_antenna_net_copper_and_vias_fail(self) -> None:
    board = valid_board("""
      (segment
        (start 27.9 40)
        (end 27.55 40)
        (width 0.2)
        (layer "F.Cu")
        (net "NFC_AC0")
      )
      (via
        (at 24 50)
        (size 0.6)
        (drill 0.3)
        (layers "F.Cu" "B.Cu")
        (net "NFC_AC1")
      )
    """)

    problems = board_problems(board)

    self.assertIn(
      "etched NFC antenna has 1 unreviewed track segments",
      problems,
    )
    self.assertIn("etched NFC antenna has 1 unreviewed vias", problems)

  def test_duplicate_reviewed_antenna_segment_fails(self) -> None:
    start, end = next(pairwise(spiral_points()))
    board = valid_board(f"""
      (segment
        (start {start[0]} {start[1]})
        (end {end[0]} {end[1]})
        (width {TRACK_WIDTH_MM})
        (layer "F.Cu")
        (net "NFC_AC0")
      )
    """)

    self.assertIn(
      "etched NFC antenna has 1 unreviewed track segments",
      board_problems(board),
    )

  def test_foreign_via_and_rotated_back_pad_fail(self) -> None:
    board = valid_board("""
      (via
        (at 24.0 50.0)
        (size 0.6)
        (layers "F.Cu" "B.Cu")
        (net "+3V3")
      )
      (footprint "Test:Part"
        (layer "B.Cu")
        (at 30.0 40.0 90)
        (property "Reference" "U99")
        (pad "1" smd rect
          (at 0 -5)
          (size 1 1)
          (layers "B.Cu" "B.Mask")
          (net "GND")
        )
      )
    """)

    problems = board_problems(board)

    self.assertIn(
      "foreign via on +3V3 enters NFC quiet area",
      problems,
    )
    self.assertIn(
      "foreign pad U99.1 on GND enters NFC quiet area",
      problems,
    )

  def test_foreign_filled_zone_fails(self) -> None:
    board = valid_board("""
      (zone
        (net "GND")
        (layer "In1.Cu")
        (filled_polygon
          (layer "In1.Cu")
          (pts
            (xy 22 35) (xy 28 35) (xy 28 45) (xy 22 45)
          )
        )
      )
    """)

    self.assertIn(
      "foreign zone fill on GND / In1.Cu enters NFC quiet area",
      board_problems(board),
    )

  def test_foreign_copper_graphic_fails(self) -> None:
    board = valid_board("""
      (gr_line
        (start 18 60)
        (end 24 60)
        (stroke (width 0.3) (type solid))
        (layer "F.Cu")
      )
    """)

    self.assertIn(
      "foreign copper graphic gr_line on F.Cu enters NFC quiet area",
      board_problems(board),
    )

  def test_copper_text_and_text_box_fail(self) -> None:
    board = valid_board("""
      (gr_text "X"
        (at 24 40)
        (layer "F.Cu")
        (effects (font (size 1 1) (thickness 0.15)))
      )
      (gr_text_box "X"
        (start 23 45)
        (end 25 47)
        (layer "B.Cu")
        (effects (font (size 1 1) (thickness 0.15)))
      )
    """)

    problems = board_problems(board)

    self.assertIn(
      "foreign copper graphic gr_text on F.Cu enters NFC quiet area",
      problems,
    )
    self.assertIn(
      "foreign copper graphic gr_text_box on B.Cu enters NFC quiet area",
      problems,
    )

  def test_custom_pad_primitive_reaching_into_quiet_area_fails(self) -> None:
    board = valid_board("""
      (footprint "Test:Custom"
        (layer "F.Cu")
        (at 30 50)
        (property "Reference" "U99")
        (pad "1" smd custom
          (at 0 0)
          (size 0.1 0.1)
          (layers "F.Cu" "F.Mask")
          (net "GND")
          (primitives
            (gr_line
              (start -8 0)
              (end 0 0)
              (width 0.2)
            )
          )
        )
      )
    """)

    self.assertIn(
      "custom-pad copper U99.1 on GND enters NFC quiet area",
      board_problems(board),
    )

  def test_pcb_nfc_metadata_and_assembly_attributes_are_required(self) -> None:
    mutations = {
      "U2 value": (
        '"ST25DV04KC-IE8S3"',
        '"wrong-U2"',
        "U2: expected PCB value='ST25DV04KC-IE8S3'",
      ),
      "U2 footprint": (
        '"the-card:SO-8_L4.9-W3.9-P1.27-LS6.0-BL"',
        '"Package_SO:SO-8_3.9x4.9mm_P1.27mm"',
        "U2: expected PCB footprint=",
      ),
      "R17 value": (
        '(property "Value" "10k")',
        '(property "Value" "100k")',
        "R17: expected PCB value='10k'",
      ),
      "R17 footprint": (
        '"Resistor_SMD:R_0402_1005Metric"',
        '"Resistor_SMD:R_0603_1608Metric"',
        "R17: expected PCB footprint=",
      ),
      "C29 value": (
        '"DNP 0-22pF C0G/NP0"',
        '"4.7pF"',
        "C29: expected PCB value='DNP 0-22pF C0G/NP0'",
      ),
      "C29 footprint": (
        '"Capacitor_SMD:C_0402_1005Metric"',
        '"Capacitor_SMD:C_0603_1608Metric"',
        "C29: expected PCB footprint=",
      ),
      "C29 datasheet intent": (
        '(property "Datasheet" "")',
        '(property "Datasheet" "selected-part.pdf")',
        "C29: expected PCB Datasheet=''",
      ),
      "C29 DNP": (
        "(attr smd dnp)",
        "(attr smd)",
        "C29: missing PCB attributes=['dnp']",
      ),
      "L2 assembly exclusions": (
        "(attr exclude_from_pos_files exclude_from_bom allow_missing_courtyard)",
        "(attr allow_missing_courtyard)",
        "L2: missing PCB attributes=['exclude_from_bom', 'exclude_from_pos_files']",
      ),
      "L2 footprint": (
        '"NetTie:NetTie-2_SMD_Pad0.5mm"',
        '"Inductor_SMD:L_0402_1005Metric"',
        "L2: expected PCB footprint=",
      ),
      "L2 net-tie semantics": (
        '(net_tie_pad_groups "1, 2")',
        '(net_tie_pad_groups "")',
        "L2: expected net_tie_pad_groups='1, 2'",
      ),
    }
    for label, (old, new, expected) in mutations.items():
      with self.subTest(label=label):
        problems = board_problems(valid_board().replace(old, new, 1))
        self.assertTrue(
          any(problem.startswith(expected) for problem in problems),
          problems,
        )

  def test_l2_must_contain_the_physical_net_tie_bridge(self) -> None:
    board = valid_board().replace(
      "(fill yes)\n        (layer \"B.Cu\")",
      "(fill no)\n        (layer \"B.Cu\")",
      1,
    )

    self.assertIn(
      "L2: expected one exact filled B.Cu net-tie bridge between pads 1 and 2",
      board_problems(board),
    )

  def test_all_four_copper_layer_keepouts_are_required(self) -> None:
    board = valid_board().replace(rule_area("B.Cu"), "")

    self.assertIn(
      f"{RULE_AREA_NAME} layers: missing=['B.Cu'], extra=[]",
      board_problems(board),
    )

  def test_rule_area_must_block_footprint_bodies(self) -> None:
    board = valid_board().replace(
      "(footprints not_allowed)",
      "(footprints allowed)",
      1,
    )

    self.assertIn(
      f"{RULE_AREA_NAME} on F.Cu does not block footprints",
      board_problems(board),
    )


if __name__ == "__main__":
  unittest.main()
