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
import mimetypes
import os
from pathlib import Path
import platform
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Iterable
import xml.etree.ElementTree as ET
import zipfile

import yaml

if __package__:
  from .export_design_review import (
    assert_pdfs_passive,
    check_rasterizer,
    export_pcb,
    export_schematic,
    sanitize_pdf,
  )
  from .release_manifest import (
    ArtifactSpec,
    SEMANTIC_VERSION,
  )
  from .release_manifest import write_release_manifest
else:
  from export_design_review import (
    assert_pdfs_passive,
    check_rasterizer,
    export_pcb,
    export_schematic,
    sanitize_pdf,
  )
  from release_manifest import (
    ArtifactSpec,
    SEMANTIC_VERSION,
  )
  from release_manifest import write_release_manifest


HARDWARE = Path(__file__).resolve().parents[1]
REPOSITORY = HARDWARE.parent
CI_WORKFLOW = REPOSITORY / ".github" / "workflows" / "ci.yml"
HARDWARE_OUTPUT_WORKFLOW = (
  REPOSITORY / ".github" / "workflows" / "hardware-output.yml"
)
BOARD = HARDWARE / "the-card.kicad_pcb"
PROJECT = HARDWARE / "the-card.kicad_pro"
SCHEMATIC = HARDWARE / "the-card.kicad_sch"
PARTS = HARDWARE / "parts.yaml"
DESIGN_METADATA = HARDWARE / "design_metadata.py"
CIRCUIT = HARDWARE / "circuit.py"
SCHEMATIC_GENERATOR = HARDWARE / "gen_hierarchical_schematic.py"
PCB_GENERATOR = HARDWARE / "gen_pcb.py"
PCB_ROUTER = HARDWARE / "pcb_router.py"
NFC_ANTENNA = HARDWARE / "nfc_antenna.py"
DESIGN_RULES = HARDWARE / "the-card.kicad_dru"
PYPROJECT = HARDWARE / "pyproject.toml"
UV_LOCK = HARDWARE / "uv.lock"
FP_LIB_TABLE = HARDWARE / "fp-lib-table"
SYM_LIB_TABLE = HARDWARE / "sym-lib-table"
LIBRARIES = HARDWARE / "libraries"
SYMBOL_LIBRARIES = (
  LIBRARIES / "the-card.kicad_sym",
  LIBRARIES / "passives.kicad_sym",
)
FOOTPRINT_LIBRARIES = tuple(sorted(
  (LIBRARIES / "the-card.pretty").glob("*.kicad_mod")
))
RASTERIZE_SVG = HARDWARE / "scripts" / "rasterize_svg.py"
VERIFY_SCHEMATIC = HARDWARE / "verify_schematic.py"
VERIFY_NFC_DESIGN = HARDWARE / "verify_nfc_design.py"
RELEASE_SCRIPT = Path(__file__).resolve()
FETCH_LIBRARIES = HARDWARE / "scripts" / "fetch_libs.sh"
NORMALIZE_LIBRARIES = HARDWARE / "scripts" / "normalize_libraries.py"
DESIGN_REVIEW_EXPORTER = HARDWARE / "scripts" / "export_design_review.py"
RELEASE_MANIFEST = HARDWARE / "scripts" / "release_manifest.py"
FABRICATION_NOTES = HARDWARE / "FABRICATION.md"

RELEASE_INPUT_FILES = (
  BOARD,
  PROJECT,
  SCHEMATIC,
  PARTS,
  DESIGN_METADATA,
  DESIGN_RULES,
)
VERIFICATION_INPUT_FILES = (
  CIRCUIT,
  VERIFY_SCHEMATIC,
  VERIFY_NFC_DESIGN,
  *SYMBOL_LIBRARIES,
)
RELEASE_TOOL_FILES = (
  RELEASE_SCRIPT,
  DESIGN_REVIEW_EXPORTER,
  RELEASE_MANIFEST,
  RASTERIZE_SVG,
  FABRICATION_NOTES,
  CI_WORKFLOW,
  HARDWARE_OUTPUT_WORKFLOW,
  PYPROJECT,
  UV_LOCK,
  FP_LIB_TABLE,
  SYM_LIB_TABLE,
)
DESIGN_GENERATOR_FILES = (
  SCHEMATIC_GENERATOR,
  PCB_GENERATOR,
  PCB_ROUTER,
  NFC_ANTENNA,
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
  ("05-f-paste", "F.Paste", False),
  ("06-b-paste-bottom-view", "B.Paste", True),
  ("07-f-mask", "F.Mask", False),
  ("08-b-mask-bottom-view", "B.Mask", True),
  ("09-f-silkscreen", "F.Silkscreen", False),
  ("10-b-silkscreen-bottom-view", "B.Silkscreen", True),
  ("11-edge-cuts", "Edge.Cuts", False),
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
EXPECTED_KICAD_VERSION = "10.0.5"
MANUAL_RELEASE_GATES = (
  "Confirm display FPC pin 1, contact side, and fold direction with the physical panel.",
  "Confirm battery connector polarity with a multimeter.",
  "Confirm bare versus protected cell choice before populating the on-board protector.",
  "Inspect U8 orientation and protection-path continuity before connecting a cell.",
  "Import the assembly files and verify stock, package, side, rotation, pin 1, "
  "and polarized-part orientation.",
  "With C29 DNP, measure NFC resonance and Q on the assembled prototype; "
  "fit the smallest measured C0G trim only if needed, then verify read/write "
  "range with multiple phones and retest in the final enclosure. Treat more "
  "than about 15-18 pF, poor Q, or inadequate range as a respin signal.",
)


def find_executable(
  environment_name: str,
  *candidates: str | Path,
) -> Path:
  configured = os.environ.get(environment_name)
  if configured:
    return Path(configured).expanduser().resolve()
  for candidate in candidates:
    path = Path(candidate).expanduser()
    if path.is_absolute() and path.is_file():
      return path.resolve()
    discovered = shutil.which(str(candidate))
    if discovered:
      return Path(discovered).resolve()
  return Path(candidates[0])


KICAD_CLI = find_executable(
  "KICAD_CLI",
  "kicad-cli",
  Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"),
)
KICAD_PYTHON = find_executable(
  "KICAD_PYTHON",
  Path(
    "/Applications/KiCad/KiCad.app/Contents/Frameworks/"
    "Python.framework/Versions/3.9/bin/python3"
  ),
  "python3",
)


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
    "--output",
    required=True,
    type=Path,
    help="New release directory; the command refuses to overwrite it.",
  )
  parser.add_argument(
    "--include-3d",
    action="store_true",
    help="Include optional 3D renders; requires every referenced model.",
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


def release_source_groups(
  include_3d: bool,
) -> dict[str, tuple[Path, ...]]:
  library_assets = (*SYMBOL_LIBRARIES, *FOOTPRINT_LIBRARIES)
  if include_3d:
    library_assets = (*library_assets, *local_model_files())
  return {
    "release_inputs": RELEASE_INPUT_FILES,
    "verification_inputs": VERIFICATION_INPUT_FILES,
    "release_tools": RELEASE_TOOL_FILES,
    "design_generators": DESIGN_GENERATOR_FILES,
    "library_assets": library_assets,
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


def load_design_metadata() -> dict[str, str]:
  namespace = runpy.run_path(str(DESIGN_METADATA))
  metadata = {
    "project_name": namespace.get("PROJECT_NAME"),
    "design_version": namespace.get("DESIGN_VERSION"),
  }
  invalid = {
    name: value
    for name, value in metadata.items()
    if not isinstance(value, str) or not value
  }
  if invalid:
    raise ValueError(f"invalid design_metadata.py values: {invalid}")
  return metadata


def excluded_assembly_references() -> frozenset[str]:
  namespace = runpy.run_path(str(DESIGN_METADATA))
  references: set[str] = set()
  for name in ("DNP_REFERENCES", "NON_ASSEMBLY_REFERENCES"):
    value = namespace.get(name, frozenset())
    if not isinstance(value, (set, frozenset)) \
        or any(not isinstance(reference, str) for reference in value):
      raise ValueError(f"invalid design_metadata.py {name}: {value!r}")
    references.update(value)
  return frozenset(references)


def assert_no_excluded_assembly_references(
  references: Iterable[str],
  context: str,
) -> None:
  unexpected = sorted(
    set(references) & excluded_assembly_references(),
    key=natural_reference_key,
  )
  if unexpected:
    raise ValueError(
      f"{context} contains DNP/non-assembly references: {unexpected}"
    )


def configured_design_version() -> str:
  design_version = load_design_metadata()["design_version"]
  if not SEMANTIC_VERSION.fullmatch(design_version):
    raise ValueError(
      f"design_metadata.py DESIGN_VERSION is not semantic: {design_version!r}"
    )
  return design_version


def design_series(design_version: str) -> str:
  return ".".join(design_version.split(".")[:2])


def title_block_revision(path: Path) -> str:
  contents = path.read_text(encoding="utf-8")
  title_block = contents.partition("(title_block")[2].partition("\n\t)")[0]
  match = re.search(r'\(rev\s+"([^"]+)"\)', title_block)
  if not match:
    raise ValueError(f"missing title-block revision in {path}")
  return match.group(1)


def assert_design_identity(design_version: str) -> None:
  revisions = {
    SCHEMATIC.name: title_block_revision(SCHEMATIC),
    BOARD.name: title_block_revision(BOARD),
  }
  mismatches = {
    name: revision
    for name, revision in revisions.items()
    if revision != design_version
  }
  if mismatches:
    raise ValueError(
      "generated title-block versions do not match DESIGN_VERSION: "
      f"expected={design_version!r}, actual={mismatches}"
    )

  board_text = BOARD.read_text(encoding="utf-8")
  expected = f"HW {design_series(design_version)} - 4L / 0.8 mm"
  marker = f'(gr_text "{expected}"'
  if board_text.count(marker) != 1:
    raise ValueError(
      f"expected exactly one PCB silkscreen identity {expected!r}"
    )
  marker_block = board_text.split(marker, 1)[1][:500]
  if '(layer "B.SilkS")' not in marker_block or '(hide yes)' in marker_block:
    raise ValueError(
      "PCB identity must be visible on B.SilkS: " + expected
    )
  stale_markers = sorted(set(re.findall(r'REV\s+[A-Z0-9._-]+', board_text)))
  if stale_markers:
    raise ValueError(f"stale PCB revision markers remain: {stale_markers}")


def assert_inputs() -> None:
  required = (
    *RELEASE_INPUT_FILES,
    *VERIFICATION_INPUT_FILES,
    *RELEASE_TOOL_FILES,
    *DESIGN_GENERATOR_FILES,
    *FOOTPRINT_LIBRARIES,
    LIBRARIES,
    KICAD_CLI,
    KICAD_PYTHON,
  )
  missing = [path for path in required if not path.exists()]
  if missing:
    raise FileNotFoundError(f"release inputs missing: {', '.join(map(str, missing))}")

  design_version = configured_design_version()
  assert_design_identity(design_version)
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


def verify_nfc_design() -> None:
  run([
    sys.executable,
    str(VERIFY_NFC_DESIGN),
    "--schematic",
    str(SCHEMATIC),
    "--board",
    str(BOARD),
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
  erc_violations = sum(
    len(sheet.get("violations", []))
    for sheet in erc_data.get("sheets", [])
  )
  return {
    "drc_violations": len(drc_data.get("violations", [])),
    "unconnected_items": len(drc_data.get("unconnected_items", [])),
    "schematic_parity_violations": len(drc_data.get("schematic_parity", [])),
    "erc_violations": erc_violations,
  }


def validate_gerber_job(
  gerber_job: dict[str, Any],
  design_version: str,
) -> dict[str, float | int | str]:
  project_name = load_design_metadata()["project_name"]
  plotted_project = gerber_job["ProjectId"]["Name"]
  if plotted_project != project_name:
    raise RuntimeError(
      "Gerber project name does not match design_metadata.py: "
      f"configured={project_name!r}, plotted={plotted_project!r}"
    )
  plotted_revision = gerber_job["ProjectId"]["Revision"]
  if plotted_revision != design_version:
    raise RuntimeError(
      "design version does not match the PCB title block: "
      f"configured={design_version!r}, plotted={plotted_revision!r}"
    )

  plotted_size = gerber_job["Size"]
  if (
    abs(plotted_size["X"] - BOARD_SPEC["width_mm"]) > 0.10
    or abs(plotted_size["Y"] - BOARD_SPEC["height_mm"]) > 0.10
    or gerber_job["LayerNumber"] != BOARD_SPEC["copper_layers"]
    or gerber_job["BoardThickness"] != BOARD_SPEC["finished_thickness_mm"]
  ):
    raise RuntimeError(
      "Gerber job does not match the expected board specification: "
      f"{gerber_job}"
    )
  return {
    "gerber_job_width_mm": plotted_size["X"],
    "gerber_job_height_mm": plotted_size["Y"],
    "gerber_job_copper_layers": gerber_job["LayerNumber"],
    "gerber_job_thickness_mm": gerber_job["BoardThickness"],
    "gerber_job_project": plotted_project,
    "gerber_job_design_version": plotted_revision,
  }


def validate_gerber_headers(
  gerbers: Iterable[Path],
  project_name: str,
  design_version: str,
) -> None:
  expected = re.compile(
    r"%TF\.ProjectId,"
    + re.escape(project_name)
    + r",[^,\r\n]+,"
    + re.escape(design_version)
    + r"\*%"
  )
  for gerber in gerbers:
    contents = gerber.read_text(encoding="utf-8", errors="strict")
    if len(expected.findall(contents)) != 1:
      raise RuntimeError(
        f"Gerber X2 design identity mismatch in {gerber.name}"
      )


def export_fabrication(
  root: Path,
  design_version: str,
) -> tuple[list[Path], dict[str, float | int | str]]:
  fabrication = root / "fabrication"
  gerbers = fabrication / "gerbers"
  drill = fabrication / "drill"
  gerbers.mkdir(parents=True)
  drill.mkdir(parents=True)
  shutil.copy2(FABRICATION_NOTES, fabrication / "fabrication-notes.md")

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

  preview_drill = root / "preview" / "drill"
  preview_drill.mkdir(parents=True)
  for map_path in drill.glob("*map*.gbr"):
    shutil.move(str(map_path), preview_drill / map_path.name)

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
  plot_checks = validate_gerber_job(gerber_job, design_version)
  validate_gerber_headers(
    layer_gerbers,
    load_design_metadata()["project_name"],
    design_version,
  )
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


def write_json(path: Path, value: Any) -> None:
  path.write_text(
    json.dumps(value, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
  )


def export_bom(root: Path) -> dict[str, int]:
  assembly = root / "assembly"
  canonical = assembly / "canonical"
  jlcpcb = assembly / "jlcpcb"
  canonical.mkdir(parents=True)
  jlcpcb.mkdir()
  (assembly / "README.md").write_text(
    "# Assembly outputs\n\n"
    "`canonical/` contains vendor-neutral BOM, placement, and drawing data.\n"
    "`jlcpcb/` contains upload-ready BOM and position files derived from the "
    "canonical data. J2 is intentionally distributor-sourced and has no LCSC "
    "part number.\n",
    encoding="utf-8",
  )
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

  assert_no_excluded_assembly_references(
    (row["reference"] for row in rows),
    "schematic BOM export",
  )

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

  bom_path = canonical / "bom.csv"
  bom_records: list[dict[str, str | int]] = []
  bom_fields = (
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
  )
  with bom_path.open("w", newline="") as output:
    writer = csv.DictWriter(output, fieldnames=bom_fields)
    writer.writeheader()
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
      record: dict[str, str | int] = {
        "designators": ",".join(references),
        "quantity": len(references),
        "value": value,
        "footprint": footprint,
        "lcsc_part_number": lcsc,
        "sourcing_status": status,
        "source_hint": source_hint,
        "related_to": related_to,
        "functions": component_functions,
        "notes": notes,
      }
      writer.writerow(record)
      bom_records.append(record)
  write_json(canonical / "bom.json", bom_records)

  jlc_bom_path = jlcpcb / "bom.csv"
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
  canonical = assembly / "canonical"
  jlcpcb = assembly / "jlcpcb"
  with tempfile.NamedTemporaryFile(suffix=".csv") as raw:
    run([
      str(KICAD_CLI),
      "pcb",
      "export",
      "pos",
      "--output",
      raw.name,
      "--side",
      "both",
      "--format",
      "csv",
      "--units",
      "mm",
      "--exclude-dnp",
      str(BOARD),
    ])
    with Path(raw.name).open(newline="") as source:
      rows = list(csv.DictReader(source))

  assert_no_excluded_assembly_references(
    (row["Ref"] for row in rows),
    "PCB position export",
  )

  with (jlcpcb / "bom.csv").open(newline="") as source:
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

  placements = [
    {
      "designator": row["Ref"],
      "value": row["Val"],
      "footprint": row["Package"],
      "x_mm": float(row["PosX"]),
      "y_mm": float(row["PosY"]),
      "rotation_deg": float(row["Rot"]),
      "side": row["Side"].lower(),
    }
    for row in rows
  ]
  placement_fields = (
    "designator",
    "value",
    "footprint",
    "x_mm",
    "y_mm",
    "rotation_deg",
    "side",
  )
  placement_path = canonical / "placements.csv"
  with placement_path.open("w", newline="", encoding="utf-8") as output:
    writer = csv.DictWriter(output, fieldnames=placement_fields)
    writer.writeheader()
    writer.writerows(placements)
  write_json(canonical / "placements.json", placements)

  jlc_position_path = jlcpcb / "positions.csv"
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


def export_layer_previews(root: Path) -> None:
  layers = root / "preview" / "layers"
  layers.mkdir(parents=True)

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
      "1800",
    ])


def export_assembly_drawings(root: Path) -> None:
  canonical = root / "assembly" / "canonical"
  for side, layer, mirror in (
    ("front", "F.Fab", False),
    ("back", "B.Fab", True),
  ):
    pdf = canonical / f"assembly-{side}.pdf"
    pdf_command = [
      str(KICAD_CLI),
      "pcb",
      "export",
      "pdf",
      "--output",
      str(pdf),
      "--layers",
      f"{layer},Edge.Cuts",
      "--mode-single",
      "--black-and-white",
      "--exclude-value",
      "--include-border-title",
      "--sketch-pads-on-fab-layers",
      "--hide-DNP-footprints-on-fab-layers",
      "--drill-shape-opt",
      "2",
      "--scale",
      "1",
      "--no-property-popups",
    ]
    if mirror:
      pdf_command.append("--mirror")
    pdf_command.append(str(BOARD))
    run(pdf_command)
    sanitize_pdf(pdf)

    svg = canonical / f"assembly-{side}.svg"
    svg_command = [
      str(KICAD_CLI),
      "pcb",
      "export",
      "svg",
      "--output",
      str(svg),
      "--layers",
      f"{layer},Edge.Cuts",
      "--mode-single",
      "--page-size-mode",
      "2",
      "--exclude-drawing-sheet",
      "--black-and-white",
      "--sketch-pads-on-fab-layers",
      "--hide-DNP-footprints-on-fab-layers",
      "--drill-shape-opt",
      "2",
    ]
    if mirror:
      svg_command.append("--mirror")
    svg_command.append(str(BOARD))
    run(svg_command)
    run([
      str(KICAD_PYTHON),
      str(RASTERIZE_SVG),
      str(svg),
      str(canonical / f"assembly-{side}.png"),
      "1800",
    ])


def export_3d_renders(root: Path) -> None:
  renders = root / "preview" / "3d"
  renders.mkdir(parents=True)
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


def export_preview(root: Path, include_3d: bool) -> None:
  check_rasterizer(str(KICAD_PYTHON))
  preview = root / "preview"
  export_schematic(
    str(KICAD_CLI),
    str(KICAD_PYTHON),
    preview,
    3200,
    900,
  )
  export_pcb(
    str(KICAD_CLI),
    str(KICAD_PYTHON),
    preview,
    1800,
  )
  export_layer_previews(root)
  export_assembly_drawings(root)
  if include_3d:
    export_3d_renders(root)


def write_deterministic_archive(
  archive: Path,
  files: Iterable[Path],
  base: Path,
) -> Path:
  with zipfile.ZipFile(
    archive,
    "w",
    compression=zipfile.ZIP_DEFLATED,
    compresslevel=9,
  ) as output:
    for path in sorted(files):
      relative = path.relative_to(base)
      info = zipfile.ZipInfo.from_file(path, arcname=relative.as_posix())
      info.date_time = (1980, 1, 1, 0, 0, 0)
      info.external_attr = 0o100644 << 16
      with path.open("rb") as source:
        output.writestr(
          info,
          source.read(),
          compress_type=zipfile.ZIP_DEFLATED,
          compresslevel=9,
        )
  return archive


def write_category_archives(
  root: Path,
  design_version: str,
  fabrication_files: Iterable[Path],
) -> tuple[Path, Path, Path]:
  prefix = f"the-card-hardware-v{design_version}"
  fabrication = root / "fabrication"
  fabrication_archive = write_deterministic_archive(
    fabrication / f"{prefix}-fabrication.zip",
    fabrication_files,
    fabrication,
  )

  assembly = root / "assembly"
  assembly_files = sorted(path for path in assembly.rglob("*") if path.is_file())
  assembly_archive = write_deterministic_archive(
    assembly / f"{prefix}-assembly.zip",
    assembly_files,
    assembly,
  )

  preview = root / "preview"
  preview_files = sorted(path for path in preview.rglob("*") if path.is_file())
  preview_archive = write_deterministic_archive(
    preview / f"{prefix}-preview.zip",
    preview_files,
    preview,
  )
  return fabrication_archive, assembly_archive, preview_archive


def git_output(*arguments: str) -> str:
  result = subprocess.run(
    [
      "git",
      "-c",
      f"safe.directory={REPOSITORY}",
      *arguments,
    ],
    cwd=REPOSITORY,
    check=True,
    capture_output=True,
    text=True,
  )
  return result.stdout.strip()


def capture_git_state() -> dict[str, Any]:
  return {
    "commit": git_output("rev-parse", "HEAD"),
    "dirty_worktree": bool(git_output(
      "status",
      "--porcelain",
      "--untracked-files=normal",
    )),
  }


def capture_toolchain() -> dict[str, Any]:
  kicad_version = subprocess.run(
    [str(KICAD_CLI), "--version"],
    check=True,
    capture_output=True,
    text=True,
  ).stdout.strip()
  if kicad_version != EXPECTED_KICAD_VERSION:
    raise RuntimeError(
      f"release requires KiCad {EXPECTED_KICAD_VERSION}, found {kicad_version}"
    )
  return {
    "kicad_cli": {
      "path": str(KICAD_CLI),
      "version": kicad_version,
    },
    "python": {
      "executable": str(Path(sys.executable).resolve()),
      "version": platform.python_version(),
    },
    "rasterizer_python": str(KICAD_PYTHON),
    "python_packages": {
      "PyYAML": package_version("PyYAML"),
      "skidl": package_version("skidl"),
    },
  }


def artifact_id(path: Path) -> str:
  portable_path = path.as_posix()
  readable = re.sub(r"[^a-z0-9]+", "_", portable_path.lower()).strip("_")
  if not readable:
    raise ValueError(f"unable to derive artifact ID from {path}")
  # The readable form alone is ambiguous: for example, `pcb-front.png` and
  # `pcb/front.png` normalize to the same snake_case value. Keep it useful to
  # humans while adding a stable path digest so every distinct path stays
  # distinct in the website-facing manifest.
  path_digest = hashlib.sha256(portable_path.encode("utf-8")).hexdigest()[:12]
  return f"{readable}_{path_digest}"


def artifact_media_type(path: Path) -> str:
  overrides = {
    ".csv": "text/csv",
    ".drl": "application/octet-stream",
    ".gbr": "application/octet-stream",
    ".gbrjob": "application/json",
    ".md": "text/markdown",
    ".svg": "image/svg+xml",
  }
  return overrides.get(
    path.suffix.lower(),
    mimetypes.guess_type(path.name)[0] or "application/octet-stream",
  )


def artifact_spec(root: Path, path: Path) -> ArtifactSpec:
  relative = path.relative_to(root)
  category = relative.parts[0]
  profile: str | None = None
  if category == "reports":
    category = "report"
  elif category == "assembly":
    profile = (
      relative.parts[1]
      if len(relative.parts) > 2 and relative.parts[1] in {"canonical", "jlcpcb"}
      else "bundle"
    )
  if category not in {"assembly", "fabrication", "preview", "report"}:
    raise ValueError(f"artifact has no public category: {relative}")
  return ArtifactSpec(
    artifact_id(relative),
    category,
    relative,
    artifact_media_type(relative),
    profile=profile,
  )


def write_release_metadata(
  root: Path,
  design_version: str,
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

  artifact_files = sorted(
    path for path in root.rglob("*")
    if path.is_file() and path.name not in {"release.json", "SHA256SUMS"}
  )
  provenance = {
    "dirty_worktree": git_state["dirty_worktree"],
    "toolchain": toolchain,
    "source_file_groups": {
      name: [
        path.relative_to(REPOSITORY).as_posix()
        for path in paths
      ]
      for name, paths in source_groups.items()
    },
    "source_files": {
      path.relative_to(REPOSITORY).as_posix(): digest
      for path, digest in source_hashes.items()
    },
  }
  manifest_path = write_release_manifest(
    root,
    project=load_design_metadata()["project_name"],
    design_version=design_version,
    git_commit=git_state["commit"],
    generator="hardware/scripts/release_fabrication.py",
    kicad_version=toolchain["kicad_cli"]["version"],
    board=BOARD_SPEC,
    validation=checks,
    assembly={**assembly, "position_count": position_count},
    provenance=provenance,
    manual_approval_status="pending",
    manual_release_gates=MANUAL_RELEASE_GATES,
    artifacts=[artifact_spec(root, path) for path in artifact_files],
    generated_at=datetime.now(timezone.utc),
  )

  checksum_files = sorted(
    [*artifact_files, manifest_path],
    key=lambda path: path.relative_to(root).as_posix(),
  )
  checksum_path = root / "SHA256SUMS"
  checksum_path.write_text("".join(
    f"{sha256(path)}  {path.relative_to(root).as_posix()}\n"
    for path in checksum_files
  ), encoding="utf-8")


def build_release(
  output: Path,
  include_3d: bool,
) -> None:
  output = output.resolve()
  if output.exists():
    raise FileExistsError(f"refusing to overwrite existing release directory: {output}")
  assert_inputs()
  design_version = configured_design_version()
  output.parent.mkdir(parents=True, exist_ok=True)
  source_groups = release_source_groups(include_3d)
  source_hashes = capture_source_hashes(flatten_source_groups(source_groups))
  git_state = capture_git_state()
  if git_state["dirty_worktree"]:
    raise RuntimeError("refusing to release from a dirty worktree")
  toolchain = capture_toolchain()
  verify_schematic_connectivity()
  verify_nfc_design()

  with tempfile.TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temp:
    root = Path(temp) / output.name
    root.mkdir()
    checks = export_reports(root)
    checks["connectivity_verifier"] = True
    checks["nfc_design_verifier"] = True
    fabrication_files, plot_checks = export_fabrication(
      root,
      design_version,
    )
    checks.update(plot_checks)
    assembly = export_bom(root)
    position_count = export_positions(root)
    export_preview(root, include_3d)
    assert_pdfs_passive(root)
    write_category_archives(root, design_version, fabrication_files)
    write_release_metadata(
      root,
      design_version,
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
    "design_version": design_version,
    "checks": checks,
    "assembly": assembly,
    "position_count": position_count,
  }, indent=2))


if __name__ == "__main__":
  arguments = parse_args()
  build_release(
    arguments.output,
    arguments.include_3d,
  )
