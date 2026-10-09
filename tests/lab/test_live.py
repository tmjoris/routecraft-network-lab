"""End-to-end checks against the running FRRouting lab.

Run with: docker compose up -d --wait && pytest -m lab
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import pytest

from routecraft.analysis import shortest_path
from routecraft.io import load
from routecraft.model import Topology

from labkit import ROOT, address_owners, eventually, node_exec, vtysh_json

pytestmark = pytest.mark.lab

SERVICE_ADDRESSES = {"10.10.0.0/16": ("dc", "10.10.0.1"), "192.0.2.0/24": ("edge", "192.0.2.1")}
LOOPBACKS = {"core-a": "10.255.0.2", "core-b": "10.255.0.3", "dc": "10.255.0.4"}


@pytest.fixture(scope="module")
def topology() -> Topology:
    return load(ROOT / "lab" / "topology.yaml")


def live_path(source: str, prefix: str) -> list[str]:
    """Traceroute between service addresses and translate each hop to a node name."""
    target_node, target = SERVICE_ADDRESSES[prefix]
    (_, source_address), *_ = (v for v in SERVICE_ADDRESSES.values() if v[0] == source)
    owners = address_owners() | {addr: node for node, addr in SERVICE_ADDRESSES.values()}
    output = node_exec(
        source, "traceroute", "-n", "-q", "1", "-w", "1", "-m", "8", "-s", source_address, target
    )
    hops = re.findall(r"^\s*\d+\s+(\S+)", output, flags=re.MULTILINE)
    path = [source, *(owners.get(hop, hop) for hop in hops)]
    assert path[-1] == target_node, f"traceroute did not reach {target}:\n{output}"
    return path


def model_path(topology: Topology, source: str, prefix: str) -> list[str]:
    result = shortest_path(topology, source, topology.prefixes[prefix])
    assert result is not None
    return result[1]


FLOWS = (("edge", "10.10.0.0/16"), ("dc", "192.0.2.0/24"))


def assert_live_paths_follow(model: Topology, timeout: float) -> None:
    """Wait until both directions of traffic take the path the model predicts."""
    for source, prefix in FLOWS:
        expected = model_path(model, source, prefix)

        def matches(
            source: str = source, prefix: str = prefix, expected: list[str] = expected
        ) -> bool:
            live = live_path(source, prefix)
            assert live == expected, f"{source} -> {prefix}: live {live}, model {expected}"
            return True

        eventually(matches, timeout=timeout)


def test_interfaces_have_fixed_names_and_addresses() -> None:
    expected: dict[str, set[str]] = {}
    for address, node in address_owners().items():
        expected.setdefault(node, set()).add(address)
    for node, addresses in expected.items():
        live = set(re.findall(r"inet (\S+)/31", node_exec(node, "ip", "-4", "addr")))
        assert live == addresses, node


def test_ospf_adjacencies_are_full(topology: Topology) -> None:
    for link in (link for link in topology.links if link.protocol == "OSPF"):
        for node in (link.left, link.right):
            peer_id = LOOPBACKS[link.other(node)]

            def full(node: str = node, peer_id: str = peer_id) -> bool:
                neighbors = vtysh_json(node, "show ip ospf neighbor")["neighbors"]
                states = [n["nbrState"] for n in neighbors.get(peer_id, [])]
                assert any(s.startswith("Full") for s in states), f"{node}->{peer_id}: {states}"
                return True

            eventually(full)


def test_bgp_sessions_are_established() -> None:
    sessions = {
        "edge": ["172.30.0.1"],
        "core-a": ["172.30.0.0", "10.255.0.3", "10.255.0.4"],
        "core-b": ["10.255.0.2", "10.255.0.4"],
        "dc": ["10.255.0.2", "10.255.0.3"],
    }
    for node, peers in sessions.items():

        def established(node: str = node, peers: list[str] = peers) -> bool:
            summary = vtysh_json(node, "show bgp ipv4 unicast summary")["peers"]
            for peer in peers:
                assert summary.get(peer, {}).get("state") == "Established", (node, peer)
            return True

        eventually(established)


def test_bfd_protects_every_adjacency() -> None:
    for node in ("edge", "core-a", "core-b", "dc"):
        peers = vtysh_json(node, "show bfd peers")
        assert peers, f"{node} has no BFD sessions"
        for peer in peers:
            assert peer["status"] == "up", (node, peer["peer"])
            assert peer["multihop"] is False, (node, peer["peer"])


def received(node: str, neighbor: str) -> set[str]:
    routes: dict[str, Any] = vtysh_json(
        node, f"show bgp ipv4 unicast neighbors {neighbor} routes"
    ).get("routes", {})
    return set(routes)


def test_ebgp_policy_only_exchanges_intended_prefixes() -> None:
    assert eventually(lambda: received("edge", "172.30.0.1")) == {"10.10.0.0/16"}
    assert eventually(lambda: received("core-a", "172.30.0.0")) == {"192.0.2.0/24"}


def test_infrastructure_is_not_reachable_from_outside() -> None:
    routes = vtysh_json("edge", "show ip route")
    assert not [prefix for prefix in routes if prefix.startswith("10.255.0.")]


def test_end_to_end_forwarding() -> None:
    output = node_exec("edge", "ping", "-c", "3", "-W", "1", "-I", "192.0.2.1", "10.10.0.1")
    assert " 0% packet loss" in output


def test_live_paths_match_model(topology: Topology) -> None:
    assert_live_paths_follow(topology, timeout=60)


def test_link_failure_matches_model_and_recovers(
    topology: Topology,
    link_control: tuple[Callable[[str, str], None], Callable[[], None]],
) -> None:
    fail, restore = link_control
    link = topology.find_link("core-a", "core-b")
    assert link is not None
    reduced = topology.without(links=[link])
    assert model_path(reduced, "edge", "10.10.0.0/16") == ["edge", "core-a", "dc"]

    fail("core-a", "core-b")
    assert_live_paths_follow(reduced, timeout=15)
    test_end_to_end_forwarding()

    restore()
    assert_live_paths_follow(topology, timeout=60)
