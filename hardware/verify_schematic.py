#!/usr/bin/env python3
"""Verify that a generated KiCad schematic preserves the SKiDL connectivity."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import circuit


HERE = Path(__file__).resolve().parent
DEFAULT_SCHEMATIC = HERE / "the-card.kicad_sch"
MACOS_KICAD_CLI = Path(
  "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
)

Node = tuple[str, str]


def find_kicad_cli() -> str:
  executable = shutil.which("kicad-cli")
  if executable:
    return executable
  if MACOS_KICAD_CLI.is_file():
    return str(MACOS_KICAD_CLI)
  raise FileNotFoundError("kicad-cli was not found")


def expected_connectivity() -> tuple[set[str], dict[Node, frozenset[Node]]]:
  design = circuit.nfc.circuit
  design.merge_net_names()
  design.merge_nets()
  refs = {part.ref for part in design.parts}
  peers: dict[Node, frozenset[Node]] = {}
  for net in design.nets:
    nodes = frozenset(
      (pin.part.ref, str(pin.num))
      for pin in net.pins
      if pin.part.ref in refs
    )
    for node in nodes:
      peers[node] = nodes
  for part in design.parts:
    for pin in part.pins:
      node = part.ref, str(pin.num)
      peers.setdefault(node, frozenset({node}))
  return refs, peers


def exported_connectivity(
  schematic: Path,
  component_refs: set[str],
) -> tuple[set[str], dict[Node, frozenset[Node]]]:
  kicad_cli = find_kicad_cli()
  with tempfile.TemporaryDirectory(prefix="the-card-netlist-") as temp_dir:
    xml_path = Path(temp_dir) / "schematic.xml"
    subprocess.run(
      [
        kicad_cli,
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
    root = ET.parse(xml_path).getroot()

  exported_refs = {
    component.attrib["ref"]
    for component in root.findall("./components/comp")
    if component.attrib["ref"] in component_refs
  }
  peers: dict[Node, frozenset[Node]] = {}
  for net in root.findall("./nets/net"):
    nodes = frozenset(
      (node.attrib["ref"], node.attrib["pin"])
      for node in net.findall("node")
      if node.attrib["ref"] in component_refs
    )
    for node in nodes:
      peers[node] = nodes
  return exported_refs, peers


def verify(schematic: Path) -> None:
  expected_refs, expected_peers = expected_connectivity()
  exported_refs, exported_peers = exported_connectivity(schematic, expected_refs)
  problems: list[str] = []
  if exported_refs != expected_refs:
    problems.append(
      "component mismatch: "
      f"missing={sorted(expected_refs - exported_refs)}, "
      f"extra={sorted(exported_refs - expected_refs)}"
    )

  for node, expected in sorted(expected_peers.items()):
    exported = exported_peers.get(node, frozenset({node}))
    if exported != expected:
      problems.append(
        f"{node[0]}.{node[1]}: "
        f"expected={sorted(expected)}, exported={sorted(exported)}"
      )
  if problems:
    raise RuntimeError(
      "Schematic connectivity differs from circuit.py:\n  - "
      + "\n  - ".join(problems)
    )
  print(
    f"connectivity OK: components={len(expected_refs)} "
    f"pins={len(expected_peers)} schematic={schematic.name}"
  )


def main() -> None:
  parser = argparse.ArgumentParser()
  parser.add_argument(
    "schematic",
    nargs="?",
    type=Path,
    default=DEFAULT_SCHEMATIC,
  )
  args = parser.parse_args()
  verify(args.schematic.resolve())


if __name__ == "__main__":
  main()
