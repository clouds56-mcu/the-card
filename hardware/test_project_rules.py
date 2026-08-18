#!/usr/bin/env python3
"""Regression tests for fabrication-critical KiCad project rules."""

from __future__ import annotations

import json
from pathlib import Path
import unittest


PROJECT = Path(__file__).resolve().parent / "the-card.kicad_pro"
EXPECTED_RULES = {
  "min_through_hole_diameter": 0.25,
  "min_track_width": 0.15,
}


class ProjectRulesTests(unittest.TestCase):
  def test_fabrication_minimums_match_generated_board(self) -> None:
    project = json.loads(PROJECT.read_text())
    rules = project["board"]["design_settings"]["rules"]

    self.assertEqual(
      {name: rules.get(name) for name in EXPECTED_RULES},
      EXPECTED_RULES,
    )


if __name__ == "__main__":
  unittest.main()
