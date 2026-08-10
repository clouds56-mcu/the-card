#!/usr/bin/env python3
"""Rasterize a KiCad SVG plot for visual release review."""

from pathlib import Path
import sys

import wx
import wx.svg


def rasterize(source: Path, output: Path, target_height: int) -> None:
  svg = wx.svg.SVGimage.CreateFromFile(str(source))
  scale = target_height / svg.height
  width = round(svg.width * scale)
  bitmap = svg.ConvertToBitmap(scale=scale, width=width, height=target_height)
  if not bitmap.SaveFile(str(output), wx.BITMAP_TYPE_PNG):
    raise RuntimeError(f"unable to rasterize {source}")


if __name__ == "__main__":
  if len(sys.argv) != 4:
    raise SystemExit("usage: rasterize_svg.py INPUT.svg OUTPUT.png HEIGHT_PX")
  rasterize(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]))
