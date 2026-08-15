#!/usr/bin/env python3
"""Regression tests for schematic connectivity comparison."""

from __future__ import annotations

import unittest

from verify_schematic import NetNames, Node, connectivity_problems


DATA_SOURCE: Node = ("U1", "1")
DATA_SINK: Node = ("U2", "1")
SINGLETON: Node = ("U1", "2")
EXPECTED_REFS = {"U1", "U2"}
EXPECTED_PEERS = {
  DATA_SOURCE: frozenset({DATA_SOURCE, DATA_SINK}),
  DATA_SINK: frozenset({DATA_SOURCE, DATA_SINK}),
  SINGLETON: frozenset({SINGLETON}),
}
EXPECTED_NET_NAMES: NetNames = {
  DATA_SOURCE: "DATA",
  DATA_SINK: "DATA",
}


class ConnectivityProblemsTests(unittest.TestCase):
  def problems(
    self,
    *,
    exported_refs: set[str] | None = None,
    exported_peers: dict[Node, frozenset[Node]] | None = None,
    exported_net_names: NetNames | None = None,
  ) -> list[str]:
    return connectivity_problems(
      EXPECTED_REFS,
      EXPECTED_PEERS,
      EXPECTED_NET_NAMES,
      set(EXPECTED_REFS) if exported_refs is None else exported_refs,
      dict(EXPECTED_PEERS) if exported_peers is None else exported_peers,
      dict(EXPECTED_NET_NAMES)
      if exported_net_names is None
      else exported_net_names,
    )

  def test_matching_connectivity_has_no_problems(self) -> None:
    self.assertEqual(self.problems(), [])

  def test_extra_component_and_pin_are_reported(self) -> None:
    extra_node: Node = ("U3", "1")
    exported_peers = dict(EXPECTED_PEERS)
    exported_peers[extra_node] = frozenset({extra_node})
    exported_net_names = dict(EXPECTED_NET_NAMES)
    exported_net_names[extra_node] = "EXTRA"

    self.assertEqual(
      self.problems(
        exported_refs={*EXPECTED_REFS, "U3"},
        exported_peers=exported_peers,
        exported_net_names=exported_net_names,
      ),
      [
        "component mismatch: missing=[], extra=['U3']",
        "pin mismatch: missing=[], extra=[('U3', '1')]",
      ],
    )

  def test_extra_component_without_net_nodes_is_reported(self) -> None:
    self.assertEqual(
      self.problems(exported_refs={*EXPECTED_REFS, "U3"}),
      ["component mismatch: missing=[], extra=['U3']"],
    )

  def test_missing_singleton_pin_is_reported(self) -> None:
    exported_peers = dict(EXPECTED_PEERS)
    del exported_peers[SINGLETON]

    self.assertEqual(
      self.problems(exported_peers=exported_peers),
      ["pin mismatch: missing=[('U1', '2')], extra=[]"],
    )

  def test_wrong_canonical_net_name_is_reported(self) -> None:
    exported_net_names = dict(EXPECTED_NET_NAMES)
    exported_net_names[DATA_SOURCE] = "Net-(U1-Pad1)"
    exported_net_names[DATA_SINK] = "Net-(U1-Pad1)"

    self.assertEqual(
      self.problems(exported_net_names=exported_net_names),
      [
        "U1.1: expected net name='DATA', exported='Net-(U1-Pad1)'",
        "U2.1: expected net name='DATA', exported='Net-(U1-Pad1)'",
      ],
    )

  def test_wrong_peer_topology_is_reported(self) -> None:
    exported_peers = dict(EXPECTED_PEERS)
    exported_peers[DATA_SOURCE] = frozenset({DATA_SOURCE})
    exported_peers[DATA_SINK] = frozenset({DATA_SINK})

    self.assertEqual(
      self.problems(exported_peers=exported_peers),
      [
        "U1.1: expected=[('U1', '1'), ('U2', '1')], "
        "exported=[('U1', '1')]",
        "U2.1: expected=[('U1', '1'), ('U2', '1')], "
        "exported=[('U2', '1')]",
      ],
    )

  def test_implicit_or_unconnected_net_names_are_ignored(self) -> None:
    exported_net_names = dict(EXPECTED_NET_NAMES)
    exported_net_names[SINGLETON] = "unconnected-(U1-Pad2)"

    self.assertEqual(
      self.problems(exported_net_names=exported_net_names),
      [],
    )


if __name__ == "__main__":
  unittest.main()
