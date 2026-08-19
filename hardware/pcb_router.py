"""Deterministic routing helpers for the-card PCB.

The router is intentionally board-specific. It uses a coarse three-layer maze
search for low-speed nets. In1.Cu remains the primary ground plane, with only
the NFC keepout and short power/ground feeders crossing its void. Critical
local connections and the NFC loop are added explicitly below.
"""

from __future__ import annotations

from dataclasses import dataclass
import heapq
import math
from typing import Iterable

import pcbnew

from nfc_antenna import (
  ANTENNA_NETS,
  QUIET_AREA,
  TRACK_WIDTH_MM as NFC_TRACK_WIDTH_MM,
  global_rectangle,
  spiral_points,
)


BOARD_X = 20.0
BOARD_Y = 20.0
BOARD_W = 53.98
BOARD_H = 85.60
GRID = 0.20
EDGE_MARGIN = 0.80

ROUTING_LAYERS = (pcbnew.B_Cu, pcbnew.In2_Cu, pcbnew.F_Cu)
LAYER_INDEX = {layer: index for index, layer in enumerate(ROUTING_LAYERS)}

POWER_NETS = {
  "+BAT",
  "AUX_3V3",
  "EPD_VCI",
  "EPD_VDD_CORE",
  "VBUS",
}
EPD_HV_NETS = {
  "EPD_PUMP",
  "EPD_SW",
  "EPD_VCOM",
  "EPD_VGH",
  "EPD_VGL",
  "EPD_VSH1",
  "EPD_VSH2",
  "EPD_VSL",
}
USB_NETS = {
  "USB_DP",
  "USB_DM",
  "Net-(J1-CC1)",
  "Net-(J1-CC2)",
  "Net-(J1-DP1)",
  "Net-(J1-DN1)",
}


def mm(value: float) -> int:
  return pcbnew.FromMM(value)


def to_mm(value: int) -> float:
  return pcbnew.ToMM(value)


def point(x: float, y: float) -> pcbnew.VECTOR2I:
  return pcbnew.VECTOR2I(mm(x), mm(y))


@dataclass(frozen=True)
class Pad:
  ref: str
  number: str
  net: str
  x: float
  y: float
  layer: int
  left: float
  top: float
  right: float
  bottom: float
  through_hole: bool
  center_x: float
  center_y: float


@dataclass(frozen=True)
class Segment:
  net: str
  layer: int
  width: float
  x1: float
  y1: float
  x2: float
  y2: float


@dataclass(frozen=True)
class Via:
  net: str
  x: float
  y: float
  diameter: float


def track_width(net: str) -> float:
  if net == "VBUS":
    # U10's 0.95 mm pin pitch requires a short neck-down at the device.
    return 0.30
  if net in {"EPD_VCI", "EPD_VDD_CORE"}:
    return 0.25
  if net in EPD_HV_NETS:
    # The 0.5 mm-pitch FPC requires a short neck-down at J2.
    return 0.20
  if net == "+BAT":
    return 0.30
  if net in POWER_NETS:
    return 0.50
  if net in USB_NETS:
    return 0.18
  return 0.20


def via_geometry(net: str) -> tuple[float, float]:
  if net in ANTENNA_NETS:
    return 0.60, 0.30
  if net in POWER_NETS:
    return 0.70, 0.35
  if net in USB_NETS:
    return 0.50, 0.25
  return 0.60, 0.30


def pad_layer(pad: pcbnew.PAD, footprint: pcbnew.FOOTPRINT) -> int:
  on_front = pad.IsOnLayer(pcbnew.F_Cu)
  on_back = pad.IsOnLayer(pcbnew.B_Cu)
  if on_front and not on_back:
    return pcbnew.F_Cu
  if on_back and not on_front:
    return pcbnew.B_Cu
  return footprint.GetLayer()


def collect_pads(board: pcbnew.BOARD) -> list[Pad]:
  result = []
  for footprint in board.GetFootprints():
    footprint_position = footprint.GetPosition()
    center_x = to_mm(footprint_position.x)
    center_y = to_mm(footprint_position.y)
    for source in footprint.Pads():
      net = source.GetNetname() or f"__NO_NET__:{footprint.GetReference()}.{source.GetNumber()}"
      position = source.GetPosition()
      bounds = source.GetBoundingBox()
      result.append(
        Pad(
          footprint.GetReference(),
          source.GetNumber(),
          net,
          to_mm(position.x),
          to_mm(position.y),
          pad_layer(source, footprint),
          to_mm(bounds.GetLeft()),
          to_mm(bounds.GetTop()),
          to_mm(bounds.GetRight()),
          to_mm(bounds.GetBottom()),
          source.GetAttribute() == pcbnew.PAD_ATTRIB_PTH,
          center_x,
          center_y,
        )
      )
  return result


def add_track(
  board: pcbnew.BOARD,
  net: pcbnew.NETINFO_ITEM,
  layer: int,
  width: float,
  start: tuple[float, float],
  end: tuple[float, float],
) -> None:
  if start == end:
    return
  track = pcbnew.PCB_TRACK(board)
  track.SetNet(net)
  track.SetLayer(layer)
  track.SetWidth(mm(width))
  track.SetStart(point(*start))
  track.SetEnd(point(*end))
  board.Add(track)


def add_via(
  board: pcbnew.BOARD,
  net: pcbnew.NETINFO_ITEM,
  position: tuple[float, float],
  diameter: float,
  drill: float,
) -> None:
  via = pcbnew.PCB_VIA(board)
  via.SetNet(net)
  via.SetPosition(point(*position))
  via.SetWidth(mm(diameter))
  via.SetDrill(mm(drill))
  via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
  board.Add(via)


class MazeRouter:
  """Route low-speed nets on a fixed grid without disturbing placement."""

  def __init__(self, board: pcbnew.BOARD, pads: list[Pad]) -> None:
    self.board = board
    self.pads = pads
    self.obstacle_pads = list(pads)
    self.segments: list[Segment] = []
    self.vias: list[Via] = []
    self.min_ix = math.ceil((BOARD_X + EDGE_MARGIN) / GRID)
    self.max_ix = math.floor((BOARD_X + BOARD_W - EDGE_MARGIN) / GRID)
    self.min_iy = math.ceil((BOARD_Y + EDGE_MARGIN) / GRID)
    self.max_iy = math.floor((BOARD_Y + BOARD_H - EDGE_MARGIN) / GRID)

  def grid(self, value: float) -> int:
    return round(value / GRID)

  def coordinate(self, index: int) -> float:
    return index * GRID

  def raster_rectangle(
    self,
    blocked: set[tuple[int, int]],
    left: float,
    top: float,
    right: float,
    bottom: float,
    margin: float,
  ) -> None:
    for ix in range(
      math.floor((left - margin) / GRID),
      math.ceil((right + margin) / GRID) + 1,
    ):
      for iy in range(
        math.floor((top - margin) / GRID),
        math.ceil((bottom + margin) / GRID) + 1,
      ):
        x = self.coordinate(ix)
        y = self.coordinate(iy)
        if (
          left - margin <= x <= right + margin
          and top - margin <= y <= bottom + margin
        ):
          blocked.add((ix, iy))

  def raster_disk(
    self,
    blocked: set[tuple[int, int]],
    x: float,
    y: float,
    radius: float,
  ) -> None:
    first_x = math.floor((x - radius) / GRID)
    last_x = math.ceil((x + radius) / GRID)
    first_y = math.floor((y - radius) / GRID)
    last_y = math.ceil((y + radius) / GRID)
    radius_sq = radius ** 2
    for ix in range(first_x, last_x + 1):
      for iy in range(first_y, last_y + 1):
        dx = self.coordinate(ix) - x
        dy = self.coordinate(iy) - y
        if dx * dx + dy * dy <= radius_sq:
          blocked.add((ix, iy))

  def raster_segment(
    self,
    blocked: set[tuple[int, int]],
    segment: Segment,
    radius: float,
  ) -> None:
    length = math.hypot(segment.x2 - segment.x1, segment.y2 - segment.y1)
    steps = max(1, math.ceil(length / (GRID * 0.45)))
    for index in range(steps + 1):
      ratio = index / steps
      x = segment.x1 + (segment.x2 - segment.x1) * ratio
      y = segment.y1 + (segment.y2 - segment.y1) * ratio
      self.raster_disk(blocked, x, y, radius)

  def obstacles(
    self,
    net: str,
    width: float,
    clearance_override: float | None = None,
  ) -> tuple[list[set[tuple[int, int]]], set[tuple[int, int]]]:
    clearance = clearance_override or (0.30 if net in EPD_HV_NETS else 0.20)
    blocked = [set() for _layer in ROUTING_LAYERS]
    via_blocked: set[tuple[int, int]] = set()

    for pad in self.obstacle_pads:
      if pad.net == net:
        continue
      margin = clearance + width / 2 + 0.04
      layers = (
        range(len(ROUTING_LAYERS))
        if pad.through_hole or pad.layer not in LAYER_INDEX
        else [LAYER_INDEX[pad.layer]]
      )
      for layer_index in layers:
        self.raster_rectangle(
          blocked[layer_index],
          pad.left,
          pad.top,
          pad.right,
          pad.bottom,
          margin,
        )
      via_diameter, _drill = via_geometry(net)
      via_margin = clearance + via_diameter / 2
      self.raster_rectangle(
        via_blocked,
        pad.left,
        pad.top,
        pad.right,
        pad.bottom,
        via_margin,
      )

    for segment in self.segments:
      if segment.net == net:
        continue
      radius = clearance + width / 2 + segment.width / 2 + 0.04
      if segment.layer in LAYER_INDEX:
        self.raster_segment(blocked[LAYER_INDEX[segment.layer]], segment, radius)
      via_diameter, _drill = via_geometry(net)
      self.raster_segment(
        via_blocked,
        segment,
        clearance + via_diameter / 2 + segment.width / 2 + 0.04,
      )

    via_diameter, _drill = via_geometry(net)
    for via in self.vias:
      radius = clearance + via_diameter / 2 + via.diameter / 2
      if via.net != net:
        for layer_blocked in blocked:
          self.raster_disk(layer_blocked, via.x, via.y, radius)
      # Same-net vias may share copper, but their drilled holes still need the
      # fabrication minimum separation.
      self.raster_disk(via_blocked, via.x, via.y, radius)

    # The ESP32 antenna end must be clear of copper on every layer.
    track_radius = width / 2
    for layer_blocked in blocked:
      self.raster_rectangle(
        layer_blocked,
        37.50 - track_radius,
        20.20 - track_radius,
        56.50 + track_radius,
        27.40 + track_radius,
        0.0,
      )
    via_diameter, _drill = via_geometry(net)
    via_radius = via_diameter / 2
    self.raster_rectangle(
      via_blocked,
      37.50 - via_radius,
      20.20 - via_radius,
      56.50 + via_radius,
      27.40 + via_radius,
      0.0,
    )
    if net not in ANTENNA_NETS:
      quiet_area = global_rectangle(QUIET_AREA)
      for layer_blocked in blocked:
        self.raster_rectangle(
          layer_blocked,
          quiet_area.x - track_radius,
          quiet_area.y - track_radius,
          quiet_area.x + quiet_area.width + track_radius,
          quiet_area.y + quiet_area.height + track_radius,
          0.0,
        )
      self.raster_rectangle(
        via_blocked,
        quiet_area.x - via_radius,
        quiet_area.y - via_radius,
        quiet_area.x + quiet_area.width + via_radius,
        quiet_area.y + quiet_area.height + via_radius,
        0.0,
      )
    return blocked, via_blocked

  def in_bounds(self, ix: int, iy: int) -> bool:
    return (
      self.min_ix <= ix <= self.max_ix
      and self.min_iy <= iy <= self.max_iy
    )

  def search(self, start: Pad, goal: Pad) -> list[tuple[int, int, int]]:
    width = track_width(start.net)
    blocked, via_blocked = self.obstacles(start.net, width)
    start_state = (self.grid(start.x), self.grid(start.y), LAYER_INDEX[start.layer])
    goal_state = (self.grid(goal.x), self.grid(goal.y), LAYER_INDEX[goal.layer])
    # Fine-pitch connector pads can sit in a channel narrower than the routing
    # grid.  Open only the immediate escape cells; the exact endpoint segment
    # is still checked later by KiCad's full-resolution DRC.
    for endpoint in (start_state, goal_state):
      for dx, dy in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
        blocked[endpoint[2]].discard((endpoint[0] + dx, endpoint[1] + dy))

    def heuristic(state: tuple[int, int, int]) -> int:
      dx = abs(goal_state[0] - state[0])
      dy = abs(goal_state[1] - state[1])
      diagonal = min(dx, dy)
      straight = max(dx, dy) - diagonal
      layer = 45 if state[2] != goal_state[2] else 0
      return diagonal * 14 + straight * 10 + layer

    queue: list[tuple[int, int, tuple[int, int, int]]] = []
    serial = 0
    heapq.heappush(queue, (heuristic(start_state), serial, start_state))
    costs = {start_state: 0}
    previous: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    moves = (
      (-1, 0, 10),
      (1, 0, 10),
      (0, -1, 10),
      (0, 1, 10),
      (-1, -1, 14),
      (-1, 1, 14),
      (1, -1, 14),
      (1, 1, 14),
    )

    while queue:
      _priority, _serial, current = heapq.heappop(queue)
      if current == goal_state:
        path = [current]
        while current in previous:
          current = previous[current]
          path.append(current)
        path.reverse()
        return path

      current_cost = costs[current]
      ix, iy, layer_index = current
      for dx, dy, move_cost in moves:
        next_state = (ix + dx, iy + dy, layer_index)
        if not self.in_bounds(next_state[0], next_state[1]):
          continue
        if next_state[:2] in blocked[layer_index] and next_state != goal_state:
          continue
        # Do not cut diagonally through a blocked corner.
        if dx and dy:
          if (ix + dx, iy) in blocked[layer_index]:
            continue
          if (ix, iy + dy) in blocked[layer_index]:
            continue
        layer_penalty = 0 if layer_index == 0 else (1 if layer_index == 1 else 3)
        candidate_cost = current_cost + move_cost + layer_penalty
        if candidate_cost >= costs.get(next_state, 1 << 60):
          continue
        costs[next_state] = candidate_cost
        previous[next_state] = current
        serial += 1
        heapq.heappush(
          queue,
          (candidate_cost + heuristic(next_state), serial, next_state),
        )

      if (ix, iy) in via_blocked:
        continue
      for next_layer in range(len(ROUTING_LAYERS)):
        if next_layer == layer_index or (ix, iy) in blocked[next_layer]:
          continue
        next_state = (ix, iy, next_layer)
        candidate_cost = current_cost + 60 + abs(next_layer - layer_index) * 5
        if candidate_cost >= costs.get(next_state, 1 << 60):
          continue
        costs[next_state] = candidate_cost
        previous[next_state] = current
        serial += 1
        heapq.heappush(
          queue,
          (candidate_cost + heuristic(next_state), serial, next_state),
        )

    raise RuntimeError(
      f"unable to route {start.net}: {start.ref}.{start.number} -> "
      f"{goal.ref}.{goal.number}"
    )

  @staticmethod
  def simplify(path: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    if len(path) < 3:
      return path
    result = [path[0]]
    previous_direction = None
    for index in range(1, len(path)):
      before = path[index - 1]
      current = path[index]
      direction = (
        current[0] - before[0],
        current[1] - before[1],
        current[2] - before[2],
      )
      if previous_direction is not None and direction != previous_direction:
        result.append(before)
      previous_direction = direction
    result.append(path[-1])
    return result

  def commit_path(self, start: Pad, goal: Pad, path: list[tuple[int, int, int]]) -> None:
    net = self.board.FindNet(start.net)
    width = track_width(start.net)
    diameter, drill = via_geometry(start.net)
    simplified = self.simplify(path)
    first = simplified[0]
    first_point = (self.coordinate(first[0]), self.coordinate(first[1]))
    add_track(self.board, net, ROUTING_LAYERS[first[2]], width, (start.x, start.y), first_point)
    if (start.x, start.y) != first_point:
      self.segments.append(
        Segment(start.net, ROUTING_LAYERS[first[2]], width, start.x, start.y, *first_point)
      )

    for before, current in zip(simplified, simplified[1:]):
      position = (self.coordinate(before[0]), self.coordinate(before[1]))
      if before[2] != current[2]:
        add_via(self.board, net, position, diameter, drill)
        self.vias.append(Via(start.net, *position, diameter))
        continue
      end = (self.coordinate(current[0]), self.coordinate(current[1]))
      add_track(self.board, net, ROUTING_LAYERS[before[2]], width, position, end)
      self.segments.append(
        Segment(start.net, ROUTING_LAYERS[before[2]], width, *position, *end)
      )

    last = simplified[-1]
    last_point = (self.coordinate(last[0]), self.coordinate(last[1]))
    add_track(self.board, net, ROUTING_LAYERS[last[2]], width, last_point, (goal.x, goal.y))
    if last_point != (goal.x, goal.y):
      self.segments.append(
        Segment(start.net, ROUTING_LAYERS[last[2]], width, *last_point, goal.x, goal.y)
      )

  @staticmethod
  def minimum_spanning_edges(pads: list[Pad]) -> list[tuple[Pad, Pad]]:
    connected = [pads[0]]
    remaining = pads[1:]
    edges = []
    while remaining:
      distance, source, target = min(
        (
          ((left.x - right.x) ** 2 + (left.y - right.y) ** 2, left, right)
          for left in connected
          for right in remaining
        ),
        key=lambda item: item[0],
      )
      del distance
      edges.append((source, target))
      connected.append(target)
      remaining.remove(target)
    return edges

  def route_net(self, net: str) -> None:
    pads = [pad for pad in self.pads if pad.net == net]
    if len(pads) < 2:
      return
    for start, goal in self.minimum_spanning_edges(pads):
      path = self.search(start, goal)
      self.commit_path(start, goal, path)

  def route_between_points(
    self,
    net: str,
    start: tuple[float, float],
    goal: tuple[float, float],
    layer: int,
  ) -> None:
    """Connect two existing same-net access points through routed copper."""
    def endpoint(label: str, position: tuple[float, float]) -> Pad:
      return Pad(
        label,
        "",
        net,
        *position,
        layer,
        position[0] - 0.02,
        position[1] - 0.02,
        position[0] + 0.02,
        position[1] + 0.02,
        False,
        *position,
      )

    start_pad = endpoint("__BRIDGE_START__", start)
    goal_pad = endpoint("__BRIDGE_GOAL__", goal)
    self.commit_path(start_pad, goal_pad, self.search(start_pad, goal_pad))

  def manual_polyline(
    self,
    net_name: str,
    layer: int,
    points: list[tuple[float, float]],
    width: float | None = None,
  ) -> None:
    net = self.board.FindNet(net_name)
    route_width = width or track_width(net_name)
    for start, end in zip(points, points[1:]):
      add_track(self.board, net, layer, route_width, start, end)
      self.segments.append(
        Segment(net_name, layer, route_width, *start, *end)
      )

  def manual_via(self, net_name: str, position: tuple[float, float]) -> None:
    net = self.board.FindNet(net_name)
    diameter, drill = via_geometry(net_name)
    add_via(self.board, net, position, diameter, drill)
    self.vias.append(Via(net_name, *position, diameter))

  def manual_via_geometry(
    self,
    net_name: str,
    position: tuple[float, float],
    diameter: float,
    drill: float,
  ) -> None:
    net = self.board.FindNet(net_name)
    add_via(self.board, net, position, diameter, drill)
    self.vias.append(Via(net_name, *position, diameter))

  def fanout_pad_to_via(
    self,
    ref: str,
    number: str,
    via_position: tuple[float, float],
  ) -> None:
    """Replace a dense connector pad with an accessible In2.Cu endpoint."""
    index, pad = next(
      (index, pad)
      for index, pad in enumerate(self.pads)
      if pad.ref == ref and pad.number == number
    )
    neck_y = 97.20
    self.manual_polyline(
      pad.net,
      pcbnew.B_Cu,
      [(pad.x, pad.y), (pad.x, neck_y), via_position],
    )
    self.manual_via(pad.net, via_position)
    diameter, _drill = via_geometry(pad.net)
    radius = diameter / 2
    self.pads[index] = Pad(
      ref,
      number,
      pad.net,
      *via_position,
      pcbnew.In2_Cu,
      via_position[0] - radius,
      via_position[1] - radius,
      via_position[0] + radius,
      via_position[1] + radius,
      False,
      via_position[0],
      via_position[1],
    )

  def fanout_dense_pad(self, index: int, distance: float = 0.55) -> None:
    pad = self.pads[index]
    if pad.ref == "U1":
      distance = 0.25
    elif pad.ref == "U9" and pad.net == "+BAT":
      distance = 0.95
    elif pad.ref in {"U3", "U4", "U5"}:
      # These sensors sit beside the NFC quiet-area boundary. Push their
      # escapes beyond the neighboring fine-pitch pads so the bus can use the
      # narrow service channel without cutting through a package courtyard.
      # The SDA escape is longer so the two bus traces leave each package in
      # separate lanes instead of trapping one another against adjacent pads.
      if pad.net == "I2C_SDA":
        distance = 2.40
      elif pad.net == "I2C_SCL":
        distance = 1.00
    elif pad.ref in {"R13", "R14"}:
      distance = 1.00
    dx = pad.x - pad.center_x
    dy = pad.y - pad.center_y
    if abs(dx) >= abs(dy):
      direction = (1.0 if dx >= 0 else -1.0, 0.0)
      half_size = (pad.right - pad.left) / 2
    else:
      direction = (0.0, 1.0 if dy >= 0 else -1.0)
      half_size = (pad.bottom - pad.top) / 2
    access = (
      pad.x + direction[0] * (half_size + distance),
      pad.y + direction[1] * (half_size + distance),
    )
    self.manual_polyline(pad.net, pad.layer, [(pad.x, pad.y), access])
    self.pads[index] = Pad(
      pad.ref,
      pad.number,
      pad.net,
      *access,
      pad.layer,
      access[0] - 0.02,
      access[1] - 0.02,
      access[0] + 0.02,
      access[1] + 0.02,
      False,
      *access,
    )

  def fanout_pad_to_point(
    self,
    ref: str,
    number: str,
    access: tuple[float, float],
  ) -> None:
    index, pad = next(
      (index, pad)
      for index, pad in enumerate(self.pads)
      if pad.ref == ref and pad.number == number
    )
    self.manual_polyline(pad.net, pad.layer, [(pad.x, pad.y), access])
    self.pads[index] = Pad(
      pad.ref,
      pad.number,
      pad.net,
      *access,
      pad.layer,
      access[0] - 0.02,
      access[1] - 0.02,
      access[0] + 0.02,
      access[1] + 0.02,
      False,
      *access,
    )

  def fanout_power_pad(self, pad: Pad) -> None:
    dense = pad.ref in {"U3", "U5", "U9"}
    width = 0.15 if dense else 0.30
    if pad.ref == "U9" and pad.number == "5":
      candidate = (34.20, pad.y)
      self.manual_polyline(pad.net, pad.layer, [(pad.x, pad.y), candidate], width)
      self.manual_via(pad.net, candidate)
      return
    blocked, via_blocked = self.obstacles(
      pad.net,
      width,
      clearance_override=0.10 if dense else None,
    )
    layer_index = LAYER_INDEX[pad.layer]
    dx = pad.x - pad.center_x
    dy = pad.y - pad.center_y
    if abs(dx) >= abs(dy):
      primary = (1.0 if dx >= 0 else -1.0, 0.0)
    else:
      primary = (0.0, 1.0 if dy >= 0 else -1.0)
    directions = (
      primary,
      (0.0, -1.0),
      (0.0, 1.0),
      (-1.0, 0.0),
      (1.0, 0.0),
      (-0.707, -0.707),
      (0.707, -0.707),
      (-0.707, 0.707),
      (0.707, 0.707),
    )
    for distance in (0.90, 1.10, 1.30, 1.50, 1.80):
      for direction in directions:
        candidate = (
          round((pad.x + direction[0] * distance) / GRID) * GRID,
          round((pad.y + direction[1] * distance) / GRID) * GRID,
        )
        cell = (self.grid(candidate[0]), self.grid(candidate[1]))
        if not self.in_bounds(*cell) or cell in via_blocked:
          continue
        steps = max(2, math.ceil(math.dist((pad.x, pad.y), candidate) / 0.10))
        if any(
          (
            self.grid(pad.x + (candidate[0] - pad.x) * step / steps),
            self.grid(pad.y + (candidate[1] - pad.y) * step / steps),
          ) in blocked[layer_index]
          for step in range(1, steps + 1)
        ):
          continue
        self.manual_polyline(pad.net, pad.layer, [(pad.x, pad.y), candidate], width)
        self.manual_via(pad.net, candidate)
        return
    raise RuntimeError(f"unable to fan out power pad {pad.ref}.{pad.number}")

  def route_nets(self, nets: Iterable[str]) -> None:
    for net in nets:
      self.route_net(net)


def route_usb_front_end(router: MazeRouter) -> None:
  """Escape the interleaved USB-C contacts into the protection device."""
  # Configuration-channel resistors.
  router.manual_polyline(
    "Net-(J1-CC1)",
    pcbnew.B_Cu,
    [(24.75, 102.97), (24.75, 100.20)],
    0.18,
  )
  router.manual_via("Net-(J1-CC1)", (24.75, 100.20))
  router.manual_polyline(
    "Net-(J1-CC1)",
    pcbnew.In2_Cu,
    [(24.75, 100.20), (25.50, 99.45), (25.50, 96.60), (31.60, 96.60)],
    0.18,
  )
  router.manual_via("Net-(J1-CC1)", (31.60, 96.60))
  router.manual_polyline(
    "Net-(J1-CC1)",
    pcbnew.B_Cu,
    [(31.60, 96.60), (32.00, 97.00), (32.50, 97.01)],
    0.18,
  )
  router.manual_polyline(
    "Net-(J1-CC2)",
    pcbnew.B_Cu,
    [(27.75, 102.97), (27.75, 100.20)],
    0.18,
  )
  router.manual_via("Net-(J1-CC2)", (27.75, 100.20))
  router.manual_polyline(
    "Net-(J1-CC2)",
    pcbnew.In2_Cu,
    [(27.75, 100.20), (29.00, 99.40), (35.40, 99.40), (35.40, 97.00)],
    0.18,
  )
  router.manual_via("Net-(J1-CC2)", (35.40, 97.00))
  router.manual_polyline(
    "Net-(J1-CC2)",
    pcbnew.B_Cu,
    [(35.40, 97.00), (34.50, 97.01)],
    0.18,
  )

  # D- escapes above the receptacle.  The two mirrored contacts join before
  # the protection device, as required for a USB-C USB 2.0 receptacle.
  router.manual_polyline(
    "Net-(J1-DN1)",
    pcbnew.B_Cu,
    [(25.25, 102.97), (25.25, 101.50), (26.25, 101.50), (26.25, 102.97)],
  )
  router.manual_polyline(
    "Net-(J1-DN1)",
    pcbnew.B_Cu,
    [
      (26.25, 101.50),
      (26.25, 99.55),
      (31.55, 99.55),
      (31.80, 99.80),
      (31.80, 101.95),
      (33.35, 101.95),
    ],
  )

  # D+ escapes below the receptacle and changes layer after clearing the
  # shield tabs, avoiding a crossover with D-.
  router.manual_polyline(
    "Net-(J1-DP1)",
    pcbnew.B_Cu,
    [(25.75, 102.97), (25.75, 104.35), (26.75, 104.35), (26.75, 102.97)],
  )
  router.manual_polyline(
    "Net-(J1-DP1)",
    pcbnew.B_Cu,
    [(26.75, 104.35), (31.80, 104.35)],
  )
  router.manual_via("Net-(J1-DP1)", (31.80, 104.35))
  router.manual_polyline(
    "Net-(J1-DP1)",
    pcbnew.In2_Cu,
    [(31.80, 104.35), (32.40, 103.75), (32.40, 100.05)],
  )
  router.manual_via("Net-(J1-DP1)", (32.40, 100.05))
  router.manual_polyline(
    "Net-(J1-DP1)",
    pcbnew.B_Cu,
    [(32.40, 100.05), (33.35, 100.05)],
  )

  # VBUS uses the second inner layer as a short distribution trunk.  The
  # 0.30 mm neck-downs at J1 and U10 expand into the plane immediately.
  vbus_fanouts = (
    ((35.65, 101.00), (36.40, 101.00)),
    ((36.50, 97.275), (37.40, 97.275)),
    ((28.91, 93.41), (28.91, 94.40)),
    ((23.09, 89.59), (22.20, 89.59)),
  )
  for start, end in vbus_fanouts:
    router.manual_polyline("VBUS", pcbnew.B_Cu, [start, end], 0.30)
    router.manual_via("VBUS", end)
  router.manual_polyline(
    "VBUS",
    pcbnew.B_Cu,
    [(23.60, 102.97), (23.60, 104.20)],
    0.30,
  )
  router.manual_via("VBUS", (23.60, 104.20))
  router.manual_polyline(
    "VBUS",
    pcbnew.B_Cu,
    [(28.40, 102.97), (28.40, 103.60)],
    0.30,
  )
  router.manual_via("VBUS", (28.40, 103.60))
  router.manual_polyline(
    "VBUS",
    pcbnew.In2_Cu,
    [(22.20, 89.59), (22.20, 95.50), (37.00, 95.50)],
    0.50,
  )
  router.manual_polyline(
    "VBUS",
    pcbnew.In2_Cu,
    [(23.60, 104.20), (23.90, 103.90), (23.90, 95.50)],
    0.50,
  )
  router.manual_polyline(
    "VBUS",
    pcbnew.In2_Cu,
    [(37.00, 95.50), (37.80, 95.50)],
    0.50,
  )
  router.manual_via("VBUS", (37.80, 95.50))
  router.manual_polyline(
    "VBUS",
    pcbnew.F_Cu,
    [
      (28.40, 103.60),
      (28.46, 103.66),
      (31.00, 103.66),
      (31.40, 103.26),
      (37.80, 103.26),
      (37.80, 95.50),
    ],
    0.50,
  )
  router.manual_polyline(
    "VBUS",
    pcbnew.In2_Cu,
    [(28.91, 94.40), (28.91, 95.50)],
    0.50,
  )
  router.manual_polyline(
    "VBUS",
    pcbnew.In2_Cu,
    [(36.40, 101.00), (37.00, 100.40), (37.00, 95.50)],
    0.50,
  )
  router.manual_polyline(
    "VBUS",
    pcbnew.In2_Cu,
    [(37.40, 97.275), (37.00, 96.875), (37.00, 95.50)],
    0.50,
  )


def route_usb_data_pair(router: MazeRouter) -> None:
  """Route the protected USB data nets as a length-matched pair."""
  # The display footprint is component-only, so the clear front copper beneath
  # it provides a much cleaner reference-plane corridor than the crowded rear.
  # The short D+ trombone equalizes the full protection-device-to-MCU paths.
  router.manual_polyline(
    "USB_DP",
    pcbnew.B_Cu,
    [(35.65, 100.05), (35.65, 98.50), (33.70, 98.50)],
  )
  router.manual_via("USB_DP", (33.70, 98.50))
  router.manual_polyline(
    "USB_DP",
    pcbnew.F_Cu,
    [
      (33.70, 98.50),
      (34.00, 98.20),
      (34.00, 90.00),
      (43.50, 80.50),
      (43.50, 76.00),
      (40.88, 76.00),
      (40.88, 74.00),
      (43.50, 74.00),
      (43.50, 65.00),
      (54.30, 54.20),
      (54.30, 50.00),
      (57.20, 47.10),
    ],
  )
  router.manual_via("USB_DP", (57.20, 47.10))
  router.manual_polyline(
    "USB_DP",
    pcbnew.B_Cu,
    [
      (57.20, 47.10),
      (56.20, 46.10),
      (55.75, 44.52),
    ],
  )

  router.manual_polyline(
    "USB_DM",
    pcbnew.B_Cu,
    [(35.65, 101.95), (36.20, 102.40)],
  )
  router.manual_via("USB_DM", (36.20, 102.40))
  router.manual_polyline(
    "USB_DM",
    pcbnew.F_Cu,
    [
      (36.20, 102.40),
      (34.50, 101.00),
      (34.50, 90.50),
      (44.00, 81.00),
      (44.00, 65.50),
      (54.80, 54.70),
      (54.80, 50.50),
      (57.70, 47.60),
    ],
  )
  router.manual_via("USB_DM", (57.70, 47.60))
  router.manual_polyline(
    "USB_DM",
    pcbnew.B_Cu,
    [
      (57.70, 47.60),
      (58.20, 47.10),
      (58.20, 43.25),
      (55.75, 43.25),
    ],
  )


def fanout_display_connector(router: MazeRouter) -> None:
  """Spread J2's 0.5 mm contacts to a DRC-safe 1.0 mm via pitch."""
  connected_pins = (
    "2",
    "3",
    "5",
    "9",
    "10",
    "11",
    "12",
    "13",
    "14",
    "15",
    "16",
    "18",
    "20",
    "21",
    "22",
    "23",
    "24",
  )
  for index, pin in enumerate(connected_pins):
    router.fanout_pad_to_via("J2", pin, (39.60 + index, 92.00))


def fanout_dense_components(router: MazeRouter, excluded: set[str]) -> None:
  dense_refs = {
    "L1", "R13", "R14", "U1", "U2", "U3", "U4", "U5", "U6", "U7",
    "U8", "U9", "U10",
  }
  for index in reversed(range(len(router.pads))):
    pad = router.pads[index]
    if (
      pad.ref not in dense_refs
      or pad.net in excluded
      or pad.net.startswith("unconnected-")
      or pad.net.startswith("__NO_NET__:")
      or pad.ref == "J2"
      or (pad.ref == "U5" and pad.net == "+BAT")
    ):
      continue
    router.fanout_dense_pad(index)


def join_u5_battery_pins(router: MazeRouter) -> None:
  indexed = [
    (index, pad)
    for index, pad in enumerate(router.pads)
    if pad.ref == "U5" and pad.net == "+BAT"
  ]
  if len(indexed) != 2:
    raise RuntimeError(f"expected two U5 +BAT pads, found {len(indexed)}")
  indexed.sort(key=lambda item: item[1].y)
  (upper_index, upper), (lower_index, lower) = indexed
  access = (30.30, upper.y)
  router.manual_polyline(
    "+BAT",
    upper.layer,
    [(lower.x, lower.y), (upper.x, upper.y), access],
  )
  router.manual_via("+BAT", access)
  diameter, _drill = via_geometry("+BAT")
  radius = diameter / 2
  router.pads[upper_index] = Pad(
    upper.ref,
    upper.number,
    upper.net,
    access[0],
    access[1],
    pcbnew.In2_Cu,
    access[0] - radius,
    access[1] - radius,
    access[0] + radius,
    access[1] + radius,
    False,
    access[0],
    access[1],
  )
  del router.pads[lower_index]


def connect_u5_decoupling(router: MazeRouter) -> None:
  """Join the fuel-gauge supply to C10 without crowding the I2C fanout."""
  u5_index, u5 = next(
    (index, pad)
    for index, pad in enumerate(router.pads)
    if pad.ref == "U5" and pad.net == "+BAT"
  )
  c10_index, c10 = next(
    (index, pad)
    for index, pad in enumerate(router.pads)
    if pad.ref == "C10" and pad.net == "+BAT"
  )
  capacitor_access = (33.70, c10.y)
  route_access = (36.50, c10.y)
  router.manual_polyline(
    "+BAT",
    c10.layer,
    [(c10.x, c10.y), capacitor_access],
  )
  router.manual_via("+BAT", capacitor_access)
  router.manual_polyline(
    "+BAT",
    pcbnew.F_Cu,
    [
      (u5.x, u5.y),
      (u5.x, 77.40),
      (route_access[0], 77.40),
      route_access,
      capacitor_access,
    ],
  )
  router.manual_via("+BAT", route_access)
  diameter, _drill = via_geometry("+BAT")
  radius = diameter / 2
  router.pads[u5_index] = Pad(
    u5.ref,
    u5.number,
    u5.net,
    route_access[0],
    route_access[1],
    pcbnew.In2_Cu,
    route_access[0] - radius,
    route_access[1] - radius,
    route_access[0] + radius,
    route_access[1] + radius,
    False,
    route_access[0],
    route_access[1],
  )
  del router.pads[c10_index]


def join_u9_battery_enable(router: MazeRouter) -> None:
  """Join the LDO VIN/CE pads without routing around its intervening GND pad."""
  indexed = [
    (index, pad)
    for index, pad in enumerate(router.pads)
    if pad.ref == "U9" and pad.net == "+BAT"
  ]
  if len(indexed) != 2:
    raise RuntimeError(f"expected two U9 +BAT pads, found {len(indexed)}")
  indexed.sort(key=lambda item: item[1].y)
  (lower_index, lower), (upper_index, upper) = indexed
  for pad in (lower, upper):
    router.manual_via("+BAT", (pad.x, pad.y))
  router.manual_polyline(
    "+BAT",
    pcbnew.In2_Cu,
    [(lower.x, lower.y), (upper.x, upper.y)],
  )
  diameter, _drill = via_geometry("+BAT")
  radius = diameter / 2
  router.pads[upper_index] = Pad(
    upper.ref,
    upper.number,
    upper.net,
    upper.x,
    upper.y,
    pcbnew.In2_Cu,
    upper.x - radius,
    upper.y - radius,
    upper.x + radius,
    upper.y + radius,
    False,
    upper.x,
    upper.y,
  )
  del router.pads[lower_index]


def connect_u9_ground(router: MazeRouter) -> None:
  pad = next(
    pad for pad in router.pads
    if pad.ref == "U9" and pad.number == "2" and pad.net == "GND"
  )
  access = (29.80, pad.y)
  router.manual_polyline("GND", pad.layer, [(pad.x, pad.y), access], 0.20)
  router.manual_via_geometry("GND", access, 0.50, 0.25)


def fanout_battery_connector(router: MazeRouter) -> None:
  router.fanout_pad_to_point("J3", "1", (70.80, 44.00))
  router.fanout_pad_to_point("J3", "2", (70.80, 42.00))


def route_aux_power(router: MazeRouter) -> None:
  """Carry the switched LED rail through a clear front/back transition."""
  router.manual_polyline(
    "AUX_3V3",
    pcbnew.B_Cu,
    [(29.00, 88.10), (28.30, 87.40), (27.00, 87.00)],
    0.25,
  )
  router.manual_via("AUX_3V3", (27.00, 87.00))
  router.manual_polyline(
    "AUX_3V3",
    pcbnew.F_Cu,
    [(27.00, 87.00), (27.50, 86.50), (28.80, 86.50), (28.80, 85.28), (28.00, 84.48)],
    0.25,
  )
  router.manual_polyline(
    "AUX_3V3",
    pcbnew.F_Cu,
    [(27.50, 86.50), (21.80, 86.50), (21.80, 83.11), (23.06, 83.11)],
    0.25,
  )


def route_nfc_antenna(router: MazeRouter) -> None:
  """Route the reviewed nine-turn spiral and its short rear crossover."""
  pads = {
    (pad.ref, pad.number): pad
    for pad in router.pads
    if pad.ref in {"U2", "C29", "L2"}
  }
  u2_ac0 = pads[("U2", "2")]
  u2_ac1 = pads[("U2", "3")]
  c29_ac0 = next(
    pad for pad in pads.values()
    if pad.ref == "C29" and pad.net == "NFC_AC0"
  )
  c29_ac1 = next(
    pad for pad in pads.values()
    if pad.ref == "C29" and pad.net == "NFC_AC1"
  )
  l2_ac0 = next(
    pad for pad in pads.values()
    if pad.ref == "L2" and pad.net == "NFC_AC0"
  )
  l2_ac1 = next(
    pad for pad in pads.values()
    if pad.ref == "L2" and pad.net == "NFC_AC1"
  )
  coil = spiral_points()
  feed_via = (28.50, 27.40)
  inner_via = coil[-1]

  router.manual_polyline(
    "NFC_AC0",
    pcbnew.B_Cu,
    [
      (u2_ac0.x, u2_ac0.y),
      (c29_ac0.x, c29_ac0.y),
      (feed_via[0], 25.20),
      feed_via,
    ],
    NFC_TRACK_WIDTH_MM,
  )
  router.manual_via("NFC_AC0", feed_via)
  router.manual_polyline(
    "NFC_AC0",
    pcbnew.F_Cu,
    [feed_via, (coil[0][0], feed_via[1]), *coil],
    NFC_TRACK_WIDTH_MM,
  )
  router.manual_via("NFC_AC0", inner_via)
  router.manual_polyline(
    "NFC_AC0",
    pcbnew.B_Cu,
    [
      inner_via,
      (inner_via[0], 25.80),
      (l2_ac0.x, 25.80),
      (l2_ac0.x, l2_ac0.y),
    ],
    NFC_TRACK_WIDTH_MM,
  )
  router.manual_polyline(
    "NFC_AC1",
    pcbnew.B_Cu,
    [
      (u2_ac1.x, u2_ac1.y),
      (c29_ac1.x, c29_ac1.y),
      (l2_ac1.x, l2_ac1.y),
    ],
    NFC_TRACK_WIDTH_MM,
  )


def connect_3v3_plane(router: MazeRouter) -> None:
  for pad in [pad for pad in router.pads if pad.net == "+3V3"]:
    router.fanout_power_pad(pad)


def connect_3v3_islands(router: MazeRouter) -> None:
  """Bridge the two In2.Cu pours split by the dense left-side routing."""
  router.route_between_points(
    "+3V3",
    (34.20, 81.95),
    (30.60, 69.40),
    pcbnew.In2_Cu,
  )


def add_ground_stitching(router: MazeRouter) -> None:
  positions = [
    (72.80, 30.00),
    (72.80, 35.00),
    (30.00, 21.20),
    (64.00, 21.20),
    (58.00, 104.40),
  ]
  for position in positions:
    router.manual_via("GND", position)


def add_ground_stitching_grid(router: MazeRouter) -> None:
  """Connect isolated outer-pour pockets to the continuous ground plane."""
  _blocked, via_blocked = router.obstacles("GND", 0.20)
  for x in range(25, 71, 5):
    for y in range(30, 101, 5):
      if x < 30 and 27 <= y <= 79:
        continue
      cell = (router.grid(float(x)), router.grid(float(y)))
      if cell in via_blocked:
        continue
      router.manual_via("GND", (float(x), float(y)))


def add_ground_island_connections(router: MazeRouter) -> None:
  """Tie cramped pad-connected pour pockets to the inner ground plane."""
  for position in (
    (32.01, 89.50),
    (63.00, 80.00),
    (61.00, 83.00),
    (30.20, 67.00),
    (32.50, 53.50),
    (34.00, 33.19),
    (35.00, 30.00),
  ):
    router.manual_via_geometry("GND", position, 0.50, 0.25)


def route_board(board: pcbnew.BOARD) -> None:
  pads = collect_pads(board)
  by_net = {
    pad.net
    for pad in pads
    if not pad.net.startswith("unconnected-")
    and not pad.net.startswith("__NO_NET__:")
  }
  excluded = {
    "GND",
    "+3V3",
    "NFC_AC0",
    "NFC_AC1",
    "AUX_3V3",
    "Net-(J1-CC1)",
    "Net-(J1-CC2)",
    "Net-(J1-DN1)",
    "Net-(J1-DP1)",
    "USB_DM",
    "USB_DP",
    "VBUS",
  }
  preferred_order = [
    "Net-(U6-PROG)",
    "AUX_3V3",
    "PWR_AUX",
    "LED_DIN",
    "BTN_MENU",
    "BTN_SEL",
    "BTN_DOWN",
    "BTN_UP",
    "I2C_SDA",
    "I2C_SCL",
    "IMU_INT",
    "NFC_IRQ",
    "MCU_EN",
    "MCU_BOOT",
    "Net-(U1-IO1)",
    "~CHRG",
    "EPD_PWR_EN",
    "+BAT",
    "EPD_VGL",
    "EPD_VCOM",
    "EPD_VGH",
    "EPD_VSL",
    "EPD_VSH1",
    "EPD_VSH2",
    "EPD_VDD_CORE",
    "EPD_VCI",
    "EPD_GDR",
    "EPD_RESE",
    "EPD_SW",
    "EPD_PUMP",
    "EPD_BUSY",
    "EPD_RST",
    "EPD_DC",
    "EPD_CS",
    "EPD_SCLK",
    "EPD_SDA",
    "FET_DRAIN",
    "BAT_NEG",
    "Net-(U7-COUT)",
    "Net-(U7-DOUT)",
    "Net-(U7-VDD)",
    "Net-(U7-VM)",
  ]
  remaining = sorted(by_net - excluded - set(preferred_order))
  router = MazeRouter(board, pads)
  add_ground_stitching(router)
  route_nfc_antenna(router)
  route_aux_power(router)
  route_usb_front_end(router)
  route_usb_data_pair(router)
  fanout_display_connector(router)
  fanout_dense_components(router, excluded)
  join_u5_battery_pins(router)
  join_u9_battery_enable(router)
  connect_u9_ground(router)
  fanout_battery_connector(router)
  connect_3v3_plane(router)
  router.manual_polyline(
    "+3V3",
    pcbnew.In2_Cu,
    [(36.20, 25.60), (35.80, 30.20)],
    0.30,
  )
  add_ground_island_connections(router)
  early_order = ("EPD_BUSY", "I2C_SDA", "I2C_SCL")
  early_nets = set(early_order)
  router.route_nets(net for net in early_order if net in by_net)
  connect_u5_decoupling(router)
  for net in preferred_order:
    if net not in by_net or net in early_nets:
      continue
    router.route_net(net)
  router.route_nets(remaining)
  connect_3v3_islands(router)
  add_ground_stitching_grid(router)
