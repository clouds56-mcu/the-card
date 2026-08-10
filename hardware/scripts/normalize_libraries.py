#!/usr/bin/env python3
"""Apply project-reviewed corrections to regenerated third-party footprints."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


HARDWARE = Path(__file__).resolve().parents[1]
USB_C_FOOTPRINT = (
  HARDWARE
  / "libraries"
  / "the-card.pretty"
  / "USB-C_SMD-TYPE-C-31-M-12_1.kicad_mod"
)
TRACKED_CUSTOM_FOOTPRINTS = {
  "Hirose_FH12-24S-0.5SH_1x24-2MP_P0.50mm_Horizontal.kicad_mod",
}
KICAD_APP = Path("/Applications/KiCad/KiCad.app/Contents")
KICAD_CLI = KICAD_APP / "MacOS" / "kicad-cli"
KICAD_PYTHON = (
  KICAD_APP
  / "Frameworks"
  / "Python.framework"
  / "Versions"
  / "3.9"
  / "bin"
  / "python3"
)


def normalize_with_pcbnew() -> None:
  import pcbnew

  footprint_io = pcbnew.PCB_IO_KICAD_SEXPR()
  footprint = footprint_io.FootprintLoad(
    str(USB_C_FOOTPRINT.parent),
    USB_C_FOOTPRINT.stem,
  )
  if footprint is None:
    raise FileNotFoundError(f"unable to load {USB_C_FOOTPRINT}")

  footprint.SetAttributes(pcbnew.FP_THROUGH_HOLE)
  for pad in footprint.Pads():
    if pad.GetNumber():
      pad.SetLocalClearance(pcbnew.FromMM(0.10))
    else:
      pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
  footprint_io.FootprintSave(str(USB_C_FOOTPRINT.parent), footprint)


def normalize_usb_c() -> None:
  with tempfile.TemporaryDirectory(prefix="the-card-footprints-") as temp:
    upgraded = Path(temp) / "the-card.pretty"
    subprocess.run([
      str(KICAD_CLI),
      "fp",
      "upgrade",
      "--force",
      "--output",
      str(upgraded),
      str(USB_C_FOOTPRINT.parent),
    ], check=True)
    for footprint_path in sorted(upgraded.glob("*.kicad_mod")):
      if footprint_path.name in TRACKED_CUSTOM_FOOTPRINTS:
        continue
      shutil.copy2(footprint_path, USB_C_FOOTPRINT.parent / footprint_path.name)
  subprocess.run([str(KICAD_PYTHON), str(Path(__file__).resolve()), "--pcbnew"], check=True)


if __name__ == "__main__":
  if sys.argv[1:] == ["--pcbnew"]:
    normalize_with_pcbnew()
  elif sys.argv[1:]:
    raise SystemExit(f"unexpected arguments: {sys.argv[1:]}")
  else:
    normalize_usb_c()
    print(f"normalized {USB_C_FOOTPRINT.relative_to(HARDWARE)}")
