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
  bitmap = svg.ConvertToBitmap(
    scale=scale,
    width=width,
    height=target_height,
  )

  # KiCad SVG plots have a transparent canvas. Preserving that alpha makes
  # black assembly strokes disappear on dark website/image-viewer themes, so
  # publish an opaque white review image instead.
  image = bitmap.ConvertToImage()
  if image.HasAlpha():
    alpha = image.GetAlpha()
    rgb = bytearray(image.GetData())
    for pixel, opacity in enumerate(alpha):
      inverse = 255 - opacity
      offset = pixel * 3
      for channel in range(3):
        rgb[offset + channel] = (
          rgb[offset + channel] * opacity + 255 * inverse + 127
        ) // 255
    image.SetData(bytes(rgb))
    image.SetAlpha(bytes([255]) * (width * target_height))

  if not image.SaveFile(str(output), wx.BITMAP_TYPE_PNG):
    raise RuntimeError(f"unable to rasterize {source}")


if __name__ == "__main__":
  if len(sys.argv) != 4:
    raise SystemExit("usage: rasterize_svg.py INPUT.svg OUTPUT.png HEIGHT_PX")
  rasterize(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]))
