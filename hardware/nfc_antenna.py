"""Reviewed geometry and first-order bounds for the etched NFC antenna.

The ST25DV04KC contains a nominal 28.5 pF tuning capacitance. ST AN2972's
modified-Wheeler expression is useful for square coils but is optimistic when
the same expression is reduced to this design's long, narrow rectangle. Rev B
therefore records that square-equivalent heuristic alongside an independent
rectangular-coil bracket from NXP AN11276. Neither estimate includes the final
display/battery loading or replaces ST eDesignSuite and physical measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


BOARD_X = 20.0
BOARD_Y = 20.0


@dataclass(frozen=True)
class Rectangle:
  x: float
  y: float
  width: float
  height: float


QUIET_AREA = Rectangle(0.35, 7.50, 9.15, 50.50)
COIL_ENVELOPE = Rectangle(0.75, 8.50, 7.25, 48.50)
COIL_TURNS = 9
TRACK_WIDTH_MM = 0.20
TURN_GAP_MM = 0.15
TURN_PITCH_MM = TRACK_WIDTH_MM + TURN_GAP_MM
COPPER_THICKNESS_UM = 35.0
ST25_TUNING_CAPACITANCE_PF = 28.5
OPERATING_FREQUENCY_MHZ = 13.56
C29_MAX_TRIM_PF = 22.0
RECTANGULAR_TURN_EXPONENT_RANGE = (1.75, 1.85)
ANTENNA_NETS = frozenset({"NFC_AC0", "NFC_AC1"})
RULE_AREA_NAME = "NFC_ANTENNA_QUIET_AREA"


def global_point(x: float, y: float) -> tuple[float, float]:
  return BOARD_X + x, BOARD_Y + y


def global_rectangle(rectangle: Rectangle) -> Rectangle:
  return Rectangle(
    BOARD_X + rectangle.x,
    BOARD_Y + rectangle.y,
    rectangle.width,
    rectangle.height,
  )


def spiral_points() -> list[tuple[float, float]]:
  """Return a clockwise outer-to-inner F.Cu rectangular spiral centerline."""
  half_width = TRACK_WIDTH_MM / 2
  left = COIL_ENVELOPE.x + half_width
  top = COIL_ENVELOPE.y + half_width
  right = COIL_ENVELOPE.x + COIL_ENVELOPE.width - half_width
  bottom = COIL_ENVELOPE.y + COIL_ENVELOPE.height - half_width
  points = [global_point(right, top)]

  for turn in range(COIL_TURNS):
    points.extend((
      global_point(right, bottom),
      global_point(left, bottom),
      global_point(left, top),
    ))
    if turn == COIL_TURNS - 1:
      break
    next_left = left + TURN_PITCH_MM
    next_top = top + TURN_PITCH_MM
    right -= TURN_PITCH_MM
    bottom -= TURN_PITCH_MM
    points.extend((
      global_point(left, next_top),
      global_point(next_left, next_top),
      global_point(right, next_top),
    ))
    left = next_left
    top = next_top

  return points


def centerline_dimensions_mm() -> tuple[float, float, float, float]:
  outer_width = COIL_ENVELOPE.width - TRACK_WIDTH_MM
  outer_height = COIL_ENVELOPE.height - TRACK_WIDTH_MM
  winding_inset = 2 * (COIL_TURNS - 1) * TURN_PITCH_MM
  return (
    outer_width,
    outer_height,
    outer_width - winding_inset,
    outer_height - winding_inset,
  )


def estimated_square_equivalent_inductance_uh() -> float:
  """Apply ST AN2972's square-coil expression as an optimistic heuristic.

  The long rectangle is reduced to mean outer and inner diameters. The result
  is retained as an upper sanity check, not as the predicted Rev B inductance.
  """
  outer_width, outer_height, inner_width, inner_height = (
    centerline_dimensions_mm()
  )
  outer_diameter_m = (outer_width + outer_height) / 2 / 1000
  inner_diameter_m = (inner_width + inner_height) / 2 / 1000
  average_diameter_m = (outer_diameter_m + inner_diameter_m) / 2
  fill_ratio = (
    (outer_diameter_m - inner_diameter_m)
    / (outer_diameter_m + inner_diameter_m)
  )
  permeability = 4 * math.pi * 1e-7
  inductance_h = (
    2.34
    * permeability
    * COIL_TURNS**2
    * average_diameter_m
    / (1 + 2.75 * fill_ratio)
  )
  return inductance_h * 1e6


def estimated_rectangular_inductance_uh(turn_exponent: float) -> float:
  """Estimate inductance with NXP AN11276 §4.3.1.1's rectangle model.

  AN11276 §4.4.1.4 gives 1.75–1.85 as the empirical turn exponent for etched
  coils. Dimensions are centerline-envelope inputs in SI units.
  """
  outer_length_m = COIL_ENVELOPE.height / 1000
  outer_width_m = COIL_ENVELOPE.width / 1000
  trace_width_m = TRACK_WIDTH_MM / 1000
  trace_gap_m = TURN_GAP_MM / 1000
  copper_thickness_m = COPPER_THICKNESS_UM * 1e-6
  conductor_diameter_m = (
    2 * (trace_width_m + copper_thickness_m) / math.pi
  )
  average_length_m = outer_length_m - COIL_TURNS * (
    trace_gap_m + trace_width_m
  )
  average_width_m = outer_width_m - COIL_TURNS * (
    trace_gap_m + trace_width_m
  )
  diagonal_m = math.hypot(average_length_m, average_width_m)
  x1 = average_length_m * math.log(
    2 * average_length_m * average_width_m
    / (conductor_diameter_m * (average_length_m + diagonal_m))
  )
  x2 = average_width_m * math.log(
    2 * average_length_m * average_width_m
    / (conductor_diameter_m * (average_width_m + diagonal_m))
  )
  x3 = 2 * (average_length_m + average_width_m - diagonal_m)
  x4 = (average_length_m + average_width_m) / 4
  permeability = 4 * math.pi * 1e-7
  inductance_h = (
    permeability
    / math.pi
    * (x1 + x2 - x3 + x4)
    * COIL_TURNS**turn_exponent
  )
  return inductance_h * 1e6


def estimated_rectangular_inductance_range_uh() -> tuple[float, float]:
  low_exponent, high_exponent = RECTANGULAR_TURN_EXPONENT_RANGE
  return (
    estimated_rectangular_inductance_uh(low_exponent),
    estimated_rectangular_inductance_uh(high_exponent),
  )


def estimated_resonance_mhz(
  inductance_uh: float,
  capacitance_pf: float,
) -> float:
  inductance_h = inductance_uh * 1e-6
  capacitance_f = capacitance_pf * 1e-12
  return 1 / (2 * math.pi * math.sqrt(inductance_h * capacitance_f)) / 1e6


def required_parallel_trim_pf(inductance_uh: float) -> float:
  inductance_h = inductance_uh * 1e-6
  angular_frequency = 2 * math.pi * OPERATING_FREQUENCY_MHZ * 1e6
  target_capacitance_f = 1 / (inductance_h * angular_frequency**2)
  return target_capacitance_f * 1e12 - ST25_TUNING_CAPACITANCE_PF


def estimated_parallel_trim_range_pf() -> tuple[float, float]:
  low_inductance_uh, high_inductance_uh = (
    estimated_rectangular_inductance_range_uh()
  )
  return (
    required_parallel_trim_pf(high_inductance_uh),
    required_parallel_trim_pf(low_inductance_uh),
  )
