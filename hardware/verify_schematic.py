#!/usr/bin/env python3
"""Verify that a generated KiCad schematic preserves the SKiDL connectivity."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_SCHEMATIC = HERE / "the-card.kicad_sch"
MACOS_KICAD_CLI = Path(
  "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
)

Node = tuple[str, str]
NetNames = dict[Node, str]


def find_kicad_cli(explicit: Path | None = None) -> str:
  if explicit is not None:
    executable = explicit.expanduser().resolve()
    if executable.is_file():
      return str(executable)
    raise FileNotFoundError(f"kicad-cli was not found at {executable}")
  executable = shutil.which("kicad-cli")
  if executable:
    return executable
  if MACOS_KICAD_CLI.is_file():
    return str(MACOS_KICAD_CLI)
  raise FileNotFoundError("kicad-cli was not found")


def expected_connectivity() -> tuple[
  set[str],
  dict[Node, frozenset[Node]],
  NetNames,
]:
  # Keep the pure comparison helpers importable in lightweight CI jobs. The
  # electrical model and its generated symbol libraries are only required when
  # verifying a real schematic.
  import circuit

  design = circuit.nfc.circuit
  design.merge_net_names()
  design.merge_nets()
  refs = {part.ref for part in design.parts}
  peers: dict[Node, frozenset[Node]] = {}
  net_names: NetNames = {}
  for net in design.nets:
    nodes = frozenset(
      (pin.part.ref, str(pin.num))
      for pin in net.pins
      if pin.part.ref in refs
    )
    for node in nodes:
      peers[node] = nodes
      if net.name != "__NOCONNECT" and not net.is_implicit():
        net_names[node] = str(net.name)
  for part in design.parts:
    for pin in part.pins:
      node = part.ref, str(pin.num)
      peers.setdefault(node, frozenset({node}))
  return refs, peers, net_names


def exported_connectivity(
  schematic: Path,
  kicad_cli: Path | None = None,
) -> tuple[set[str], dict[Node, frozenset[Node]], NetNames]:
  executable = find_kicad_cli(kicad_cli)
  with tempfile.TemporaryDirectory(prefix="the-card-netlist-") as temp_dir:
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
    root = ET.parse(xml_path).getroot()

  exported_refs = {
    component.attrib["ref"]
    for component in root.findall("./components/comp")
  }
  peers: dict[Node, frozenset[Node]] = {}
  net_names: NetNames = {}
  for net in root.findall("./nets/net"):
    nodes = frozenset(
      (node.attrib["ref"], node.attrib["pin"])
      for node in net.findall("node")
    )
    for node in nodes:
      peers[node] = nodes
      net_names[node] = net.attrib["name"]
  return exported_refs, peers, net_names


def connectivity_problems(
  expected_refs: set[str],
  expected_peers: dict[Node, frozenset[Node]],
  expected_net_names: NetNames,
  exported_refs: set[str],
  exported_peers: dict[Node, frozenset[Node]],
  exported_net_names: NetNames,
) -> list[str]:
  problems: list[str] = []
  if exported_refs != expected_refs:
    problems.append(
      "component mismatch: "
      f"missing={sorted(expected_refs - exported_refs)}, "
      f"extra={sorted(exported_refs - expected_refs)}"
    )

  expected_nodes = set(expected_peers)
  exported_nodes = set(exported_peers)
  if exported_nodes != expected_nodes:
    problems.append(
      "pin mismatch: "
      f"missing={sorted(expected_nodes - exported_nodes)}, "
      f"extra={sorted(exported_nodes - expected_nodes)}"
    )

  for node in sorted(expected_nodes & exported_nodes):
    expected = expected_peers[node]
    exported = exported_peers[node]
    if exported != expected:
      problems.append(
        f"{node[0]}.{node[1]}: "
        f"expected={sorted(expected)}, exported={sorted(exported)}"
      )
  for node in sorted(set(expected_net_names) & exported_nodes):
    expected_name = expected_net_names[node]
    exported_name = exported_net_names[node]
    if exported_name != expected_name:
      problems.append(
        f"{node[0]}.{node[1]}: expected net name={expected_name!r}, "
        f"exported={exported_name!r}"
      )
  return problems


def verify(schematic: Path, kicad_cli: Path | None = None) -> None:
  expected_refs, expected_peers, expected_net_names = expected_connectivity()
  exported_refs, exported_peers, exported_net_names = exported_connectivity(
    schematic,
    kicad_cli,
  )
  problems = connectivity_problems(
    expected_refs,
    expected_peers,
    expected_net_names,
    exported_refs,
    exported_peers,
    exported_net_names,
  )
  if problems:
    raise RuntimeError(
      "Schematic connectivity differs from circuit.py:\n  - "
      + "\n  - ".join(problems)
    )
  print(
    f"connectivity OK: components={len(expected_refs)} "
    f"pins={len(expected_peers)} "
    f"named_nets={len(set(expected_net_names.values()))} "
    f"schematic={schematic.name}"
  )


def main() -> None:
  parser = argparse.ArgumentParser()
  parser.add_argument(
    "schematic",
    nargs="?",
    type=Path,
    default=DEFAULT_SCHEMATIC,
  )
  parser.add_argument(
    "--kicad-cli",
    type=Path,
    help="Exact kicad-cli executable to use instead of PATH discovery.",
  )
  args = parser.parse_args()
  verify(args.schematic.resolve(), args.kicad_cli)


if __name__ == "__main__":
  main()
