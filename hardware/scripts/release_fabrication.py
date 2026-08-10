#!/usr/bin/env python3
"""Build a checked fabrication and first-assembly release for the-card."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Iterable
import zipfile

import yaml


HARDWARE = Path(__file__).resolve().parents[1]
REPOSITORY = HARDWARE.parent
BOARD = HARDWARE / "the-card.kicad_pcb"
PROJECT = HARDWARE / "the-card.kicad_pro"
SCHEMATIC = HARDWARE / "the-card.kicad_sch"
PARTS = HARDWARE / "parts.yaml"
KICAD_CLI = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
KICAD_PYTHON = Path(
  "/Applications/KiCad/KiCad.app/Contents/Frameworks/"
  "Python.framework/Versions/3.9/bin/python3"
)
RASTERIZE_SVG = HARDWARE / "scripts" / "rasterize_svg.py"

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


def load_sourcing() -> dict[str, dict[str, str]]:
  manifest = yaml.safe_load(PARTS.read_text())
  sourcing: dict[str, dict[str, str]] = {}

  for part in manifest.get("lcsc_parts", []):
    lcsc = str(part.get("lcsc", ""))
    assigned = bool(re.fullmatch(r"C\d+", lcsc))
    metadata = {
      "lcsc_part_number": lcsc if assigned else "",
      "sourcing_status": "assigned" if assigned else "distributor",
      "source_hint": "LCSC" if assigned else lcsc or "distributor",
      "notes": str(part.get("note", "")),
    }
    for reference in expand_reference_expression(part["ref"], part.get("qty")):
      sourcing[reference] = metadata

  for part in manifest.get("standard_parts", []):
    metadata = {
      "lcsc_part_number": "",
      "sourcing_status": "needs_sourcing",
      "source_hint": "distributor",
      "notes": str(part.get("note", "")),
    }
    for reference in expand_reference_expression(part["ref"], part.get("qty")):
      sourcing[reference] = metadata

  return sourcing


def assert_inputs() -> None:
  required = (
    BOARD,
    PROJECT,
    SCHEMATIC,
    PARTS,
    KICAD_CLI,
    KICAD_PYTHON,
    RASTERIZE_SVG,
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
    "--check-zones",
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


def export_bom(root: Path) -> dict[str, int]:
  assembly = root / "assembly"
  assembly.mkdir(parents=True)
  sourcing = load_sourcing()

  with tempfile.NamedTemporaryFile(suffix=".csv") as raw:
    run([
      str(KICAD_CLI),
      "sch",
      "export",
      "bom",
      "--output",
      raw.name,
      "--fields",
      "Reference,Value,Footprint,QUANTITY,DNP",
      "--labels",
      "reference,value,footprint,quantity,dnp",
      "--sort-field",
      "Reference",
      "--exclude-dnp",
      str(SCHEMATIC),
    ])
    with Path(raw.name).open(newline="") as source:
      rows = list(csv.DictReader(source))

  grouped: dict[tuple[str, ...], list[str]] = defaultdict(list)
  component_counts: dict[str, int] = defaultdict(int)
  for row in rows:
    reference = row["reference"]
    if reference.startswith("TP"):
      continue
    metadata = sourcing.get(reference, {
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
      "notes",
    ])
    for key, references in sorted(
      grouped.items(),
      key=lambda item: natural_reference_key(item[1][0]),
    ):
      value, footprint, lcsc, status, source_hint, notes = key
      references.sort(key=natural_reference_key)
      writer.writerow([
        ",".join(references),
        len(references),
        value,
        footprint,
        lcsc,
        status,
        source_hint,
        notes,
      ])

  return {
    "bom_lines": len(grouped),
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
    return sum(1 for _row in csv.DictReader(source))


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
      "--check-zones",
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


def write_manifest(
  root: Path,
  revision: str,
  checks: dict[str, Any],
  assembly: dict[str, int],
  position_count: int,
) -> None:
  if position_count != assembly["placed_components"]:
    raise RuntimeError(
      "BOM/position count mismatch: "
      f"{assembly['placed_components']} BOM components vs {position_count} placements"
    )

  source_files = (BOARD, PROJECT, SCHEMATIC, PARTS)
  payload_files = sorted(
    path for path in root.rglob("*")
    if path.is_file() and path.name not in {"release-manifest.json", "SHA256SUMS"}
  )
  dirty = bool(git_output("status", "--porcelain", "--untracked-files=no", "--", "hardware"))
  manifest = {
    "project": "the-card",
    "revision": revision,
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "generator": "hardware/scripts/release_fabrication.py",
    "kicad_version": subprocess.run(
      [str(KICAD_CLI), "--version"],
      check=True,
      capture_output=True,
      text=True,
    ).stdout.strip(),
    "git": {
      "commit": git_output("rev-parse", "HEAD"),
      "dirty_hardware_worktree": dirty,
    },
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
    "source_files": {
      str(path.relative_to(REPOSITORY)): sha256(path)
      for path in source_files
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
  assert_inputs()
  if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", revision):
    raise ValueError(f"invalid revision label: {revision!r}")
  output = output.resolve()
  if output.exists():
    raise FileExistsError(f"refusing to overwrite existing release directory: {output}")
  output.parent.mkdir(parents=True, exist_ok=True)

  with tempfile.TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temp:
    root = Path(temp) / output.name
    root.mkdir()
    checks = export_reports(root)
    fabrication_files, plot_checks = export_fabrication(root)
    checks.update(plot_checks)
    assembly = export_bom(root)
    position_count = export_positions(root)
    export_review(root)
    write_fabrication_archive(root, revision, fabrication_files)
    write_manifest(root, revision, checks, assembly, position_count)
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
