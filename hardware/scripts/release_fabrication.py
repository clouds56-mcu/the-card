#!/usr/bin/env python3
"""Build a checked fabrication and first-assembly release for the-card."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Iterable
import xml.etree.ElementTree as ET
import zipfile

import yaml


HARDWARE = Path(__file__).resolve().parents[1]
REPOSITORY = HARDWARE.parent
BOARD = HARDWARE / "the-card.kicad_pcb"
PROJECT = HARDWARE / "the-card.kicad_pro"
SCHEMATIC = HARDWARE / "the-card.kicad_sch"
PARTS = HARDWARE / "parts.yaml"
CIRCUIT = HARDWARE / "circuit.py"
SCHEMATIC_GENERATOR = HARDWARE / "gen_hierarchical_schematic.py"
PCB_GENERATOR = HARDWARE / "gen_pcb.py"
PCB_ROUTER = HARDWARE / "pcb_router.py"
PYPROJECT = HARDWARE / "pyproject.toml"
UV_LOCK = HARDWARE / "uv.lock"
FP_LIB_TABLE = HARDWARE / "fp-lib-table"
SYM_LIB_TABLE = HARDWARE / "sym-lib-table"
LIBRARIES = HARDWARE / "libraries"
SYMBOL_LIBRARIES = (
  LIBRARIES / "the-card.kicad_sym",
  LIBRARIES / "passives.kicad_sym",
)
KICAD_CLI = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
KICAD_PYTHON = Path(
  "/Applications/KiCad/KiCad.app/Contents/Frameworks/"
  "Python.framework/Versions/3.9/bin/python3"
)
RASTERIZE_SVG = HARDWARE / "scripts" / "rasterize_svg.py"
VERIFY_SCHEMATIC = HARDWARE / "verify_schematic.py"
RELEASE_SCRIPT = Path(__file__).resolve()
FETCH_LIBRARIES = HARDWARE / "scripts" / "fetch_libs.sh"
NORMALIZE_LIBRARIES = HARDWARE / "scripts" / "normalize_libraries.py"

RELEASE_INPUT_FILES = (
  BOARD,
  PROJECT,
  SCHEMATIC,
  PARTS,
)
VERIFICATION_INPUT_FILES = (
  CIRCUIT,
  VERIFY_SCHEMATIC,
  *SYMBOL_LIBRARIES,
)
RELEASE_TOOL_FILES = (
  RELEASE_SCRIPT,
  RASTERIZE_SVG,
  PYPROJECT,
  UV_LOCK,
  FP_LIB_TABLE,
  SYM_LIB_TABLE,
)
DESIGN_GENERATOR_FILES = (
  SCHEMATIC_GENERATOR,
  PCB_GENERATOR,
  PCB_ROUTER,
  FETCH_LIBRARIES,
  NORMALIZE_LIBRARIES,
)

GERBER_LAYERS = (
  "F.Cu",
  "In1.Cu",
  "In2.Cu",
  "B.Cu",
  "F.Paste",
  "B.Paste",
  "F.Silkscreen",
  "B.Silkscreen",
  "F.Mask",
  "B.Mask",
  "Edge.Cuts",
)
REVIEW_LAYERS = (
  ("01-f-cu", "F.Cu", False),
  ("02-in1-cu", "In1.Cu", False),
  ("03-in2-cu", "In2.Cu", False),
  ("04-b-cu-bottom-view", "B.Cu", True),
  ("05-f-mask", "F.Mask", False),
  ("06-b-mask-bottom-view", "B.Mask", True),
  ("07-f-silkscreen", "F.Silkscreen", False),
  ("08-b-silkscreen-bottom-view", "B.Silkscreen", True),
  ("09-edge-cuts", "Edge.Cuts", False),
)
EXPECTED_RULES = {
  "min_through_hole_diameter": 0.25,
  "min_track_width": 0.15,
}
BOARD_SPEC = {
  "width_mm": 53.98,
  "height_mm": 85.60,
  "copper_layers": 4,
  "finished_thickness_mm": 0.80,
}


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
    "--output",
    required=True,
    type=Path,
    help="New release directory; the command refuses to overwrite it.",
  )
  parser.add_argument(
    "--revision",
    default="rev-a",
    help="Revision label recorded in the manifest and archive name.",
  )
  return parser.parse_args()


def run(command: list[str], *, cwd: Path = HARDWARE) -> None:
  print("+", " ".join(command), flush=True)
  subprocess.run(command, cwd=cwd, check=True)


def sha256(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as source:
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def local_model_files() -> tuple[Path, ...]:
  relative_paths = set(re.findall(
    r'\(model "\$\{KIPRJMOD\}/([^"\n]+)"',
    BOARD.read_text(),
  ))
  models = tuple(sorted(HARDWARE / path for path in relative_paths))
  missing = [path for path in models if not path.is_file()]
  if missing:
    raise FileNotFoundError(
      "board-local 3D models missing: " + ", ".join(map(str, missing))
    )
  return models


def release_source_groups() -> dict[str, tuple[Path, ...]]:
  return {
    "release_inputs": RELEASE_INPUT_FILES,
    "verification_inputs": VERIFICATION_INPUT_FILES,
    "release_tools": RELEASE_TOOL_FILES,
    "design_generators": DESIGN_GENERATOR_FILES,
    "library_assets": local_model_files(),
  }


def flatten_source_groups(
  groups: dict[str, tuple[Path, ...]],
) -> tuple[Path, ...]:
  return tuple(sorted({path for paths in groups.values() for path in paths}))


def capture_source_hashes(files: tuple[Path, ...]) -> dict[Path, str]:
  return {path: sha256(path) for path in files}


def assert_source_hashes_unchanged(initial: dict[Path, str]) -> None:
  current = capture_source_hashes(tuple(initial))
  changed = [
    path.relative_to(REPOSITORY)
    for path, digest in initial.items()
    if current[path] != digest
  ]
  if changed:
    raise RuntimeError(
      "release inputs changed during generation: "
      + ", ".join(map(str, changed))
    )


def package_version(distribution: str) -> str:
  try:
    return importlib.metadata.version(distribution)
  except importlib.metadata.PackageNotFoundError:
    return "not installed"


def natural_reference_key(reference: str) -> tuple[str, int]:
  match = re.fullmatch(r"([A-Za-z]+)(\d+)", reference)
  if not match:
    return reference, 0
  return match.group(1), int(match.group(2))


def expand_reference_expression(expression: str, quantity: int | None = None) -> list[str]:
  range_match = re.fullmatch(r"([A-Za-z]+)(\d+)-([A-Za-z]+)?(\d+)", expression)
  if range_match:
    first_prefix, first_number, last_prefix, last_number = range_match.groups()
    last_prefix = last_prefix or first_prefix
    if first_prefix != last_prefix:
      raise ValueError(f"mixed reference prefixes are unsupported: {expression}")
    return [
      f"{first_prefix}{number}"
      for number in range(int(first_number), int(last_number) + 1)
    ]

  reference_match = re.fullmatch(r"([A-Za-z]+)(\d+)", expression)
  if quantity and quantity > 1:
    if reference_match:
      prefix, first_number = reference_match.groups()
      start = int(first_number)
    else:
      prefix = expression
      start = 1
    return [f"{prefix}{number}" for number in range(start, start + quantity)]
  return [expression]


def expand_part_references(part: dict[str, Any]) -> list[str]:
  expressions = part.get("refs", part.get("ref"))
  if expressions is None:
    raise ValueError(f"part has no ref or refs: {part}")
  if isinstance(expressions, str):
    expressions = [expressions]

  references: list[str] = []
  for expression in expressions:
    quantity = part.get("qty") if len(expressions) == 1 else None
    references.extend(expand_reference_expression(expression, quantity))
  return references


def assign_sourcing(
  sourcing: dict[str, dict[str, str]],
  references: Iterable[str],
  metadata: dict[str, str],
) -> None:
  for reference in references:
    if reference in sourcing:
      raise ValueError(f"duplicate sourcing assignment for {reference}")
    sourcing[reference] = metadata


def load_sourcing() -> dict[str, dict[str, str]]:
  manifest = yaml.safe_load(PARTS.read_text())
  library_sourcing: dict[str, dict[str, str]] = {}
  assembly_sourcing: dict[str, dict[str, str]] = {}

  for part in manifest.get("lcsc_parts", []):
    lcsc = str(part.get("lcsc", ""))
    assigned = bool(re.fullmatch(r"C\d+", lcsc))
    default_source_hint = "JLCPCB/LCSC" if assigned else lcsc or "distributor"
    metadata = {
      "description": str(part.get("role", "")),
      "lcsc_part_number": lcsc if assigned else "",
      "sourcing_status": "assigned" if assigned else "distributor",
      "source_hint": str(part.get("source_hint", default_source_hint)),
      "notes": str(part.get("note", "")),
    }
    assign_sourcing(library_sourcing, expand_part_references(part), metadata)

  for part in manifest.get("assembly_parts", []):
    lcsc = str(part.get("lcsc", ""))
    if not re.fullmatch(r"C\d+", lcsc):
      raise ValueError(f"assembly part has invalid LCSC number: {part}")
    metadata = {
      "description": str(part.get("role", "")),
      "lcsc_part_number": lcsc,
      "sourcing_status": "assigned",
      "source_hint": str(part.get("source_hint", "JLCPCB/LCSC")),
      "notes": str(part.get("note", "")),
    }
    assign_sourcing(assembly_sourcing, expand_part_references(part), metadata)

  # An explicit assembly pick may reuse a symbol/footprint fetched for a
  # pin-compatible library part. In that case, the assembly selection is the
  # authoritative procurement record for the generated BOM.
  sourcing = library_sourcing | assembly_sourcing

  for part in manifest.get("standard_parts", []):
    metadata = {
      "description": str(part.get("role", "")),
      "lcsc_part_number": "",
      "sourcing_status": "needs_sourcing",
      "source_hint": "distributor",
      "notes": str(part.get("note", "")),
    }
    assign_sourcing(sourcing, expand_part_references(part), metadata)

  return sourcing


def assert_inputs() -> None:
  required = (
    *RELEASE_INPUT_FILES,
    *VERIFICATION_INPUT_FILES,
    *RELEASE_TOOL_FILES,
    *DESIGN_GENERATOR_FILES,
    LIBRARIES,
    KICAD_CLI,
    KICAD_PYTHON,
  )
  missing = [path for path in required if not path.exists()]
  if missing:
    raise FileNotFoundError(f"release inputs missing: {', '.join(map(str, missing))}")

  project = json.loads(PROJECT.read_text())
  rules = project["board"]["design_settings"]["rules"]
  mismatches = {
    name: {"expected": expected, "actual": rules.get(name)}
    for name, expected in EXPECTED_RULES.items()
    if rules.get(name) != expected
  }
  if mismatches:
    raise ValueError(f"project fabrication rules do not match the generator: {mismatches}")


def verify_schematic_connectivity() -> None:
  run([
    sys.executable,
    str(VERIFY_SCHEMATIC),
    str(SCHEMATIC),
    "--kicad-cli",
    str(KICAD_CLI),
  ])


def export_reports(root: Path) -> dict[str, Any]:
  reports = root / "reports"
  reports.mkdir(parents=True)
  drc = reports / "drc.json"
  erc = reports / "erc.json"

  run([
    str(KICAD_CLI),
    "pcb",
    "drc",
    "--output",
    str(drc),
    "--format",
    "json",
    "--severity-all",
    "--schematic-parity",
    "--exit-code-violations",
    str(BOARD),
  ])
  run([
    str(KICAD_CLI),
    "sch",
    "erc",
    "--output",
    str(erc),
    "--format",
    "json",
    "--severity-all",
    "--exit-code-violations",
    str(SCHEMATIC),
  ])

  drc_data = json.loads(drc.read_text())
  erc_data = json.loads(erc.read_text())
  return {
    "drc_violations": len(drc_data.get("violations", [])),
    "unconnected_items": len(drc_data.get("unconnected_items", [])),
    "schematic_parity_violations": len(drc_data.get("schematic_parity", [])),
    "erc_violations": len(erc_data.get("violations", [])),
  }


def export_fabrication(root: Path) -> tuple[list[Path], dict[str, float | int]]:
  fabrication = root / "fabrication"
  gerbers = fabrication / "gerbers"
  drill = fabrication / "drill"
  gerbers.mkdir(parents=True)
  drill.mkdir(parents=True)

  # gen_pcb.py fills every copper zone before saving, and the full DRC gate
  # above validates the resulting geometry. KiCad 10.0.5 on macOS aborts in
  # the CLI's redundant --check-zones export path for this otherwise clean
  # board, so release plotting intentionally relies on those two prior checks.
  run([
    str(KICAD_CLI),
    "pcb",
    "export",
    "gerbers",
    "--output",
    str(gerbers),
    "--layers",
    ",".join(GERBER_LAYERS),
    "--subtract-soldermask",
    str(BOARD),
  ])
  run([
    str(KICAD_CLI),
    "pcb",
    "export",
    "drill",
    "--output",
    str(drill),
    "--format",
    "excellon",
    "--excellon-units",
    "mm",
    "--excellon-zeros-format",
    "decimal",
    "--excellon-oval-format",
    "route",
    "--excellon-separate-th",
    "--generate-map",
    "--map-format",
    "gerberx2",
    "--generate-report",
    "--report-path",
    str(root / "reports" / "drill-report.txt"),
    str(BOARD),
  ])

  review_drill = root / "review" / "drill"
  review_drill.mkdir(parents=True)
  for map_path in drill.glob("*map*.gbr"):
    shutil.move(str(map_path), review_drill / map_path.name)

  gerber_files = sorted(path for path in gerbers.iterdir() if path.is_file())
  layer_gerbers = [path for path in gerber_files if path.suffix != ".gbrjob"]
  gerber_jobs = [path for path in gerber_files if path.suffix == ".gbrjob"]
  drill_files = sorted(drill.glob("*.drl"))
  if len(layer_gerbers) != len(GERBER_LAYERS) or len(gerber_jobs) != 1:
    raise RuntimeError(
      f"expected {len(GERBER_LAYERS)} layer Gerbers and one job file, "
      f"found {len(layer_gerbers)} layers and {len(gerber_jobs)} jobs"
    )
  if len(drill_files) < 2:
    raise RuntimeError(f"expected separate PTH and NPTH drill files, found {len(drill_files)}")

  gerber_job = json.loads(gerber_jobs[0].read_text())["GeneralSpecs"]
  plotted_size = gerber_job["Size"]
  if (
    abs(plotted_size["X"] - BOARD_SPEC["width_mm"]) > 0.10
    or abs(plotted_size["Y"] - BOARD_SPEC["height_mm"]) > 0.10
    or gerber_job["LayerNumber"] != BOARD_SPEC["copper_layers"]
    or gerber_job["BoardThickness"] != BOARD_SPEC["finished_thickness_mm"]
  ):
    raise RuntimeError(f"Gerber job does not match the expected board specification: {gerber_job}")
  plot_checks = {
    "gerber_job_width_mm": plotted_size["X"],
    "gerber_job_height_mm": plotted_size["Y"],
    "gerber_job_copper_layers": gerber_job["LayerNumber"],
    "gerber_job_thickness_mm": gerber_job["BoardThickness"],
  }
  return gerber_files + drill_files, plot_checks


def export_component_details() -> dict[str, dict[str, str | int]]:
  with tempfile.NamedTemporaryFile(suffix=".xml") as raw:
    run([
      str(KICAD_CLI),
      "sch",
      "export",
      "netlist",
      "--format",
      "kicadxml",
      "--output",
      raw.name,
      str(SCHEMATIC),
    ])
    netlist = ET.parse(raw.name).getroot()

  details: dict[str, dict[str, str | int]] = {}
  for component in netlist.findall("./components/comp"):
    libsource = component.find("libsource")
    pin_numbers = {
      pin.attrib["num"]
      for pin in component.findall("./units/unit/pins/pin")
    }
    details[component.attrib["ref"]] = {
      "description": (
        "" if libsource is None else libsource.attrib.get("description", "")
      ),
      "lib_ref": "" if libsource is None else libsource.attrib.get("part", ""),
      "pins": len(pin_numbers),
    }
  return details


def jlc_footprint(identifier: str) -> str:
  """Return the package name without KiCad's library prefix."""
  return identifier.split(":", 1)[-1]


def export_bom(root: Path) -> dict[str, int]:
  assembly = root / "assembly"
  assembly.mkdir(parents=True)
  sourcing = load_sourcing()
  component_details = export_component_details()

  with tempfile.NamedTemporaryFile(suffix=".csv") as raw:
    run([
      str(KICAD_CLI),
      "sch",
      "export",
      "bom",
      "--output",
      raw.name,
      "--fields",
      "Reference,Value,Footprint,QUANTITY,DNP,Related To,Function",
      "--labels",
      "reference,value,footprint,quantity,dnp,related_to,function",
      "--sort-field",
      "Reference",
      "--exclude-dnp",
      str(SCHEMATIC),
    ])
    with Path(raw.name).open(newline="") as source:
      rows = list(csv.DictReader(source))

  grouped: dict[tuple[str, ...], list[str]] = defaultdict(list)
  jlc_grouped: dict[tuple[str, ...], list[str]] = defaultdict(list)
  relationships: dict[str, str] = {}
  functions: dict[str, str] = {}
  component_counts: dict[str, int] = defaultdict(int)
  for row in rows:
    reference = row["reference"]
    if reference.startswith("TP"):
      continue
    metadata = sourcing.get(reference, {
      "description": "",
      "lcsc_part_number": "",
      "sourcing_status": "needs_sourcing",
      "source_hint": "",
      "notes": "Exact purchasable part is not assigned in parts.yaml.",
    })
    key = (
      row["value"],
      row["footprint"],
      metadata["lcsc_part_number"],
      metadata["sourcing_status"],
      metadata["source_hint"],
      metadata["notes"],
    )
    grouped[key].append(reference)
    relationships[reference] = row.get("related_to", "")
    functions[reference] = row.get("function", "")
    details = component_details[reference]
    jlc_key = (
      row["value"],
      metadata["description"] or str(details["description"]),
      jlc_footprint(row["footprint"]),
      str(details["lib_ref"]),
      str(details["pins"]),
      metadata["lcsc_part_number"],
    )
    jlc_grouped[jlc_key].append(reference)
    component_counts[metadata["sourcing_status"]] += 1

  bom_path = assembly / "the-card-assembly-bom.csv"
  with bom_path.open("w", newline="") as output:
    writer = csv.writer(output)
    writer.writerow([
      "designators",
      "quantity",
      "value",
      "footprint",
      "lcsc_part_number",
      "sourcing_status",
      "source_hint",
      "related_to",
      "functions",
      "notes",
    ])
    for key, references in sorted(
      grouped.items(),
      key=lambda item: natural_reference_key(item[1][0]),
    ):
      value, footprint, lcsc, status, source_hint, notes = key
      references.sort(key=natural_reference_key)
      related_to = "; ".join(
        f"{reference}: {relationships[reference]}"
        for reference in references
        if relationships[reference]
      )
      component_functions = "; ".join(
        f"{reference}: {functions[reference]}"
        for reference in references
        if functions[reference]
      )
      writer.writerow([
        ",".join(references),
        len(references),
        value,
        footprint,
        lcsc,
        status,
        source_hint,
        related_to,
        component_functions,
        notes,
      ])

  jlc_bom_path = assembly / "the-card-jlc-bom.csv"
  with jlc_bom_path.open("w", newline="", encoding="utf-8") as output:
    writer = csv.writer(output)
    writer.writerow([
      "Comment",
      "Description",
      "Designator",
      "Footprint",
      "LibRef",
      "Pins",
      "Quantity",
      "JLCPCB Part #",
    ])
    for key, references in sorted(
      jlc_grouped.items(),
      key=lambda item: natural_reference_key(item[1][0]),
    ):
      comment, description, footprint, lib_ref, pins, lcsc = key
      references.sort(key=natural_reference_key)
      writer.writerow([
        comment,
        description,
        ",".join(references),
        footprint,
        lib_ref,
        pins,
        len(references),
        lcsc,
      ])

  return {
    "bom_lines": len(grouped),
    "jlc_bom_lines": len(jlc_grouped),
    "placed_components": sum(component_counts.values()),
    "components_with_assigned_lcsc": component_counts["assigned"],
    "distributor_components": component_counts["distributor"],
    "components_needing_sourcing": component_counts["needs_sourcing"],
  }


def export_positions(root: Path) -> int:
  assembly = root / "assembly"
  position_path = assembly / "the-card-positions.csv"
  run([
    str(KICAD_CLI),
    "pcb",
    "export",
    "pos",
    "--output",
    str(position_path),
    "--side",
    "both",
    "--format",
    "csv",
    "--units",
    "mm",
    "--exclude-dnp",
    str(BOARD),
  ])
  with position_path.open(newline="") as source:
    rows = list(csv.DictReader(source))

  with (assembly / "the-card-jlc-bom.csv").open(newline="") as source:
    bom_references = {
      reference
      for row in csv.DictReader(source)
      for reference in row["Designator"].split(",")
    }
  position_references = {row["Ref"] for row in rows}
  if len(position_references) != len(rows):
    raise ValueError("JLC position export contains duplicate designators")
  if position_references != bom_references:
    raise ValueError(
      "JLC BOM/position designator mismatch: "
      f"missing={sorted(bom_references - position_references)}, "
      f"extra={sorted(position_references - bom_references)}"
    )

  jlc_position_path = assembly / "the-card-jlc-positions.csv"
  with jlc_position_path.open("w", newline="", encoding="utf-8") as output:
    writer = csv.writer(output)
    writer.writerow(["Designator", "Mid X", "Mid Y", "Rotation", "Layer"])
    for row in rows:
      side = row["Side"].capitalize()
      if side not in {"Top", "Bottom"}:
        raise ValueError(
          f"unexpected placement side for {row['Ref']}: {row['Side']}"
        )
      writer.writerow([
        row["Ref"],
        row["PosX"],
        row["PosY"],
        row["Rot"],
        side,
      ])
  return len(rows)


def export_review(root: Path) -> None:
  layers = root / "review" / "layers"
  renders = root / "review" / "3d"
  layers.mkdir(parents=True)
  renders.mkdir(parents=True)

  for filename, layer, mirror in REVIEW_LAYERS:
    plotted_layers = layer if layer == "Edge.Cuts" else f"{layer},Edge.Cuts"
    command = [
      str(KICAD_CLI),
      "pcb",
      "export",
      "svg",
      "--output",
      str(layers / f"{filename}.svg"),
      "--layers",
      plotted_layers,
      "--mode-single",
      "--page-size-mode",
      "2",
      "--exclude-drawing-sheet",
      "--drill-shape-opt",
      "2",
    ]
    if mirror:
      command.append("--mirror")
    command.append(str(BOARD))
    run(command)
    run([
      str(KICAD_PYTHON),
      str(RASTERIZE_SVG),
      str(layers / f"{filename}.svg"),
      str(layers / f"{filename}.png"),
      "1600",
    ])

  for side in ("top", "bottom"):
    run([
      str(KICAD_CLI),
      "pcb",
      "render",
      "--output",
      str(renders / f"the-card-{side}.png"),
      "--width",
      "1200",
      "--height",
      "1600",
      "--side",
      side,
      "--background",
      "opaque",
      "--quality",
      "high",
      "--preset",
      "follow_plot_settings",
      str(BOARD),
    ])


def write_fabrication_archive(root: Path, revision: str, files: Iterable[Path]) -> Path:
  archive = root / f"the-card-{revision}-fabrication.zip"
  with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
    for path in sorted(files):
      relative = path.relative_to(root / "fabrication")
      info = zipfile.ZipInfo.from_file(path, arcname=str(relative))
      info.date_time = (1980, 1, 1, 0, 0, 0)
      info.external_attr = 0o100644 << 16
      with path.open("rb") as source:
        output.writestr(info, source.read(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
  return archive


def git_output(*arguments: str) -> str:
  result = subprocess.run(
    ["git", *arguments],
    cwd=REPOSITORY,
    check=True,
    capture_output=True,
    text=True,
  )
  return result.stdout.strip()


def capture_git_state() -> dict[str, Any]:
  return {
    "commit": git_output("rev-parse", "HEAD"),
    "dirty_hardware_worktree": bool(git_output(
      "status",
      "--porcelain",
      "--untracked-files=normal",
      "--",
      "hardware",
    )),
  }


def capture_toolchain() -> dict[str, Any]:
  kicad_version = subprocess.run(
    [str(KICAD_CLI), "--version"],
    check=True,
    capture_output=True,
    text=True,
  ).stdout.strip()
  return {
    "kicad_cli": {
      "path": str(KICAD_CLI),
      "version": kicad_version,
    },
    "python": {
      "executable": str(Path(sys.executable).resolve()),
      "version": platform.python_version(),
    },
    "python_packages": {
      "PyYAML": package_version("PyYAML"),
      "skidl": package_version("skidl"),
    },
  }


def write_manifest(
  root: Path,
  revision: str,
  checks: dict[str, Any],
  assembly: dict[str, int],
  position_count: int,
  source_groups: dict[str, tuple[Path, ...]],
  source_hashes: dict[Path, str],
  git_state: dict[str, Any],
  toolchain: dict[str, Any],
) -> None:
  if position_count != assembly["placed_components"]:
    raise RuntimeError(
      "BOM/position count mismatch: "
      f"{assembly['placed_components']} BOM components vs {position_count} placements"
    )

  payload_files = sorted(
    path for path in root.rglob("*")
    if path.is_file() and path.name not in {"release-manifest.json", "SHA256SUMS"}
  )
  manifest = {
    "project": "the-card",
    "revision": revision,
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "generator": "hardware/scripts/release_fabrication.py",
    "kicad_version": toolchain["kicad_cli"]["version"],
    "git": git_state,
    "toolchain": toolchain,
    "board": BOARD_SPEC,
    "checks": checks,
    "assembly": assembly,
    "manual_release_gates": [
      "Confirm display FPC pin 1, contact side, and fold direction with the physical panel.",
      "Confirm battery connector polarity with a multimeter.",
      "Confirm bare versus protected cell choice before populating the on-board protector.",
      "Inspect U8 orientation and protection-path continuity before connecting a cell.",
      "Tune and range-test the NFC antenna on the first physical prototype.",
    ],
    "source_file_groups": {
      name: [
        str(path.relative_to(REPOSITORY))
        for path in paths
      ]
      for name, paths in source_groups.items()
    },
    "source_files": {
      str(path.relative_to(REPOSITORY)): digest
      for path, digest in source_hashes.items()
    },
    "payload_files": {
      str(path.relative_to(root)): {
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
      }
      for path in payload_files
    },
  }
  manifest_path = root / "release-manifest.json"
  manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

  checksum_files = sorted([*payload_files, manifest_path])
  checksum_path = root / "SHA256SUMS"
  checksum_path.write_text("".join(
    f"{sha256(path)}  {path.relative_to(root)}\n"
    for path in checksum_files
  ))


def build_release(output: Path, revision: str) -> None:
  if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", revision):
    raise ValueError(f"invalid revision label: {revision!r}")
  output = output.resolve()
  if output.exists():
    raise FileExistsError(f"refusing to overwrite existing release directory: {output}")
  assert_inputs()
  output.parent.mkdir(parents=True, exist_ok=True)
  source_groups = release_source_groups()
  source_hashes = capture_source_hashes(flatten_source_groups(source_groups))
  git_state = capture_git_state()
  toolchain = capture_toolchain()
  verify_schematic_connectivity()

  with tempfile.TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temp:
    root = Path(temp) / output.name
    root.mkdir()
    checks = export_reports(root)
    checks["connectivity_verifier"] = True
    fabrication_files, plot_checks = export_fabrication(root)
    checks.update(plot_checks)
    assembly = export_bom(root)
    position_count = export_positions(root)
    export_review(root)
    write_fabrication_archive(root, revision, fabrication_files)
    write_manifest(
      root,
      revision,
      checks,
      assembly,
      position_count,
      source_groups,
      source_hashes,
      git_state,
      toolchain,
    )
    assert_source_hashes_unchanged(source_hashes)
    root.rename(output)

  print(json.dumps({
    "release": str(output),
    "checks": checks,
    "assembly": assembly,
    "position_count": position_count,
  }, indent=2))


if __name__ == "__main__":
  arguments = parse_args()
  build_release(arguments.output, arguments.revision)
