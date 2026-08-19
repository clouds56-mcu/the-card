#!/usr/bin/env python3
"""Regression tests for the reviewed Rev B NFC antenna geometry."""

from __future__ import annotations

from itertools import pairwise
import unittest

import nfc_antenna as antenna


class NfcAntennaTests(unittest.TestCase):
  def test_spiral_is_a_nine_turn_orthogonal_centerline(self) -> None:
    points = antenna.spiral_points()

    self.assertEqual(len(points), 6 * antenna.COIL_TURNS - 2)
    for start, end in pairwise(points):
      self.assertNotEqual(start, end)
      self.assertTrue(
        start[0] == end[0] or start[1] == end[1],
        f"non-orthogonal antenna segment: {start} -> {end}",
      )

  def test_spiral_copper_stays_inside_the_quiet_area(self) -> None:
    points = antenna.spiral_points()
    coil = antenna.global_rectangle(antenna.COIL_ENVELOPE)
    quiet = antenna.global_rectangle(antenna.QUIET_AREA)
    half_width = antenna.TRACK_WIDTH_MM / 2

    for x, y in points:
      self.assertGreaterEqual(x - half_width, coil.x)
      self.assertLessEqual(x + half_width, coil.x + coil.width)
      self.assertGreaterEqual(y - half_width, coil.y)
      self.assertLessEqual(y + half_width, coil.y + coil.height)

    self.assertGreaterEqual(coil.x, quiet.x)
    self.assertLessEqual(coil.x + coil.width, quiet.x + quiet.width)
    self.assertGreaterEqual(coil.y, quiet.y)
    self.assertLessEqual(coil.y + coil.height, quiet.y + quiet.height)

  def test_turn_pitch_preserves_the_selected_track_and_gap(self) -> None:
    self.assertAlmostEqual(
      antenna.TURN_PITCH_MM,
      antenna.TRACK_WIDTH_MM + antenna.TURN_GAP_MM,
    )
    outer_width, outer_height, inner_width, inner_height = (
      antenna.centerline_dimensions_mm()
    )
    expected_inset = 2 * (antenna.COIL_TURNS - 1) * antenna.TURN_PITCH_MM

    self.assertAlmostEqual(outer_width - inner_width, expected_inset)
    self.assertAlmostEqual(outer_height - inner_height, expected_inset)
    self.assertGreater(inner_width, antenna.TRACK_WIDTH_MM)
    self.assertGreater(inner_height, antenna.TRACK_WIDTH_MM)

  def test_first_order_models_bound_the_prototype_tuning_range(self) -> None:
    square_equivalent_uh = (
      antenna.estimated_square_equivalent_inductance_uh()
    )
    rectangular_range_uh = antenna.estimated_rectangular_inductance_range_uh()
    trim_range_pf = antenna.estimated_parallel_trim_range_pf()

    self.assertAlmostEqual(square_equivalent_uh, 4.5243, places=3)
    self.assertAlmostEqual(rectangular_range_uh[0], 3.1918, places=3)
    self.assertAlmostEqual(rectangular_range_uh[1], 3.9761, places=3)
    self.assertLess(rectangular_range_uh[1], square_equivalent_uh)
    self.assertAlmostEqual(trim_range_pf[0], 6.1467, places=3)
    self.assertAlmostEqual(trim_range_pf[1], 14.6605, places=3)
    self.assertLess(trim_range_pf[1], antenna.C29_MAX_TRIM_PF)

  def test_only_the_two_rf_nets_are_allowed_in_the_quiet_area(self) -> None:
    self.assertEqual(
      antenna.ANTENNA_NETS,
      frozenset({"NFC_AC0", "NFC_AC1"}),
    )


if __name__ == "__main__":
  unittest.main()
