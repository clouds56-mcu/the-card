#!/usr/bin/env python3
"""Export portable schematic and PCB images for design review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


HARDWARE = Path(__file__).resolve().parents[1]
SCHEMATIC = HARDWARE / "the-card.kicad_sch"
BOARD = HARDWARE / "the-card.kicad_pcb"
RASTERIZER = HARDWARE / "scripts" / "rasterize_svg.py"
MACOS_KICAD_CLI = Path(
  "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
)
PCB_PREVIEWS = (
  (
    "front",
    "F.Cu,F.Mask,F.Silkscreen,Edge.Cuts",
    False,
  ),
  ("inner-1", "In1.Cu,Edge.Cuts", False),
  ("inner-2", "In2.Cu,Edge.Cuts", False),
  (
    "back",
    "B.Cu,B.Mask,B.Silkscreen,Edge.Cuts",
    True,
  ),
)
PCB_PDF_LAYERS = "F.Cu,In1.Cu,In2.Cu,B.Cu"
STABLE_ARTIFACTS = (
  "schematic.pdf",
  "schematic.svg",
  "schematic.png",
  "schematic-thumbnail.png",
  "pcb.pdf",
  "pcb-front.png",
  "pcb-inner-1.png",
  "pcb-inner-2.png",
  "pcb-back.png",
)


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
    "--output",
    type=Path,
    default=HARDWARE / "ci-design-review",
    help="New output directory; existing directories are not overwritten.",
  )
  parser.add_argument(
    "--kicad-cli",
    type=Path,
    help="Exact kicad-cli executable to use instead of PATH discovery.",
  )
  parser.add_argument(
    "--rasterizer-python",
    type=Path,
    help="Python with wx.svg support; defaults to the current interpreter.",
  )
  parser.add_argument(
    "--schematic-height",
    type=int,
    default=3200,
    help="Height in pixels for each schematic PNG page.",
  )
  parser.add_argument(
    "--schematic-thumbnail-height",
    type=int,
    default=900,
    help="Height in pixels for schematic-thumbnail.png.",
  )
  parser.add_argument(
    "--pcb-height",
    type=int,
    default=1800,
    help="Height in pixels for each PCB PNG preview.",
  )
  return parser.parse_args()


def find_kicad_cli(explicit: Path | None) -> str:
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


def find_python(explicit: Path | None) -> str:
  if explicit is None:
    return sys.executable
  executable = explicit.expanduser().resolve()
  if executable.is_file():
    return str(executable)
  raise FileNotFoundError(f"rasterizer Python was not found at {executable}")


def run(command: list[str]) -> None:
  print("+", " ".join(command), flush=True)
  subprocess.run(command, cwd=HARDWARE, check=True)


def check_rasterizer(python: str) -> None:
  run([
    python,
    "-c",
    "import wx, wx.svg; print(f'wxPython {wx.version()}')",
  ])


def require_nonempty(path: Path) -> None:
  if not path.is_file() or path.stat().st_size == 0:
    raise RuntimeError(f"expected a non-empty review artifact at {path}")


def copy_artifact(source: Path, destination: Path) -> None:
  shutil.copy2(source, destination)
  require_nonempty(destination)


def rasterize(
  python: str,
  source: Path,
  output: Path,
  height: int,
) -> None:
  run([
    python,
    str(RASTERIZER),
    str(source),
    str(output),
    str(height),
  ])
  require_nonempty(output)


def export_schematic(
  kicad_cli: str,
  python: str,
  output: Path,
  height: int,
  thumbnail_height: int,
) -> None:
  schematic = output / "schematic"
  svg = schematic / "svg"
  png = schematic / "png"
  svg.mkdir(parents=True)
  png.mkdir()

  pdf = schematic / "the-card-schematic.pdf"
  run([
    kicad_cli,
    "sch",
    "export",
    "pdf",
    "--output",
    str(pdf),
    str(SCHEMATIC),
  ])
  require_nonempty(pdf)
  copy_artifact(pdf, output / "schematic.pdf")

  run([
    kicad_cli,
    "sch",
    "export",
    "svg",
    "--output",
    str(svg),
    str(SCHEMATIC),
  ])
  svg_pages = sorted(svg.glob("*.svg"))
  if not svg_pages:
    raise RuntimeError("KiCad did not export any schematic SVG pages")
  for index, page in enumerate(svg_pages):
    require_nonempty(page)
    page_png = png / f"{page.stem}.png"
    rasterize(python, page, page_png, height)
    if index == 0:
      copy_artifact(page, output / "schematic.svg")
      copy_artifact(page_png, output / "schematic.png")
      rasterize(
        python,
        page,
        output / "schematic-thumbnail.png",
        thumbnail_height,
      )


def export_pcb(
  kicad_cli: str,
  python: str,
  output: Path,
  height: int,
) -> None:
  pcb = output / "pcb"
  pcb.mkdir(parents=True)
  for name, layers, mirror in PCB_PREVIEWS:
    svg = pcb / f"{name}.svg"
    command = [
      kicad_cli,
      "pcb",
      "export",
      "svg",
      "--output",
      str(svg),
      "--layers",
      layers,
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
    require_nonempty(svg)
    png = pcb / f"{name}.png"
    rasterize(python, svg, png, height)
    copy_artifact(png, output / f"pcb-{name}.png")

  pdf = output / "pcb.pdf"
  run([
    kicad_cli,
    "pcb",
    "export",
    "pdf",
    "--output",
    str(pdf),
    "--layers",
    PCB_PDF_LAYERS,
    "--common-layers",
    "Edge.Cuts",
    "--mode-multipage",
    "--drill-shape-opt",
    "2",
    "--scale",
    "0",
    str(BOARD),
  ])
  require_nonempty(pdf)


def sha256(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as source:
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def write_manifest(output: Path, kicad_cli: str) -> None:
  for relative in STABLE_ARTIFACTS:
    require_nonempty(output / relative)
  version = subprocess.run(
    [kicad_cli, "--version"],
    check=True,
    capture_output=True,
    text=True,
  ).stdout.strip()
  artifacts = sorted(
    path for path in output.rglob("*") if path.is_file()
  )
  manifest = {
    "generator": "hardware/scripts/export_design_review.py",
    "kicad_version": version,
    "artifacts": {
      str(path.relative_to(output)): {
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
      }
      for path in artifacts
    },
  }
  (output / "manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n"
  )


def main() -> None:
  args = parse_args()
  heights = (
    args.schematic_height,
    args.schematic_thumbnail_height,
    args.pcb_height,
  )
  if any(height <= 0 for height in heights):
    raise ValueError("PNG heights must be positive")
  output = args.output.expanduser().resolve()
  if output.exists():
    raise FileExistsError(
      f"refusing to overwrite existing review directory: {output}"
    )

  kicad_cli = find_kicad_cli(args.kicad_cli)
  python = find_python(args.rasterizer_python)
  check_rasterizer(python)
  output.mkdir(parents=True)
  export_schematic(
    kicad_cli,
    python,
    output,
    args.schematic_height,
    args.schematic_thumbnail_height,
  )
  export_pcb(kicad_cli, python, output, args.pcb_height)
  write_manifest(output, kicad_cli)
  print(f"design review written: {output}")


if __name__ == "__main__":
  main()
