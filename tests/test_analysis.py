from routecraft.analysis import analyze, validate
from routecraft.io import load


def test_example_is_valid() -> None:
    topology = load("examples/metro.yaml")
    assert validate(topology) == []


def test_failure_keeps_prefix_reachable_via_backup() -> None:
    topology = load("examples/metro.yaml")
    result = analyze(topology, frozenset(("core-a", "core-b")))
    assert result["10.10.0.0/16"]["reachable"] is True
    assert result["10.10.0.0/16"]["path"] == ["core-a", "dc-dub-1"]


def test_unknown_peer_is_reported() -> None:
    topology = load("examples/metro.yaml")
    topology.bgp_peers.append(("edge-dub", "missing"))
    assert any("unknown node" in error for error in validate(topology))
