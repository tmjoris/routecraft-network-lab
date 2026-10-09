from pathlib import Path

import pytest

from routecraft.analysis import analyze, resilience, shortest_path, validate
from routecraft.io import load, parse
from routecraft.model import Link, Topology


@pytest.fixture
def metro(root: Path) -> Topology:
    return load(root / "examples" / "metro.yaml")


@pytest.mark.parametrize("name", ["examples/metro.yaml", "lab/topology.yaml"])
def test_shipped_topologies_are_valid(root: Path, name: str) -> None:
    assert validate(load(root / name)) == []


def test_primary_path_uses_lowest_cost(metro: Topology) -> None:
    assert shortest_path(metro, "edge-dub", "dc-dub-1") == (
        25,
        ["edge-dub", "core-a", "core-b", "dc-dub-1"],
    )


def test_core_link_failure_reroutes_over_backup(metro: Topology) -> None:
    link = metro.find_link("core-a", "core-b")
    assert link is not None
    result = analyze(metro, failed_links=[link])
    edge = result["prefixes"]["10.10.0.0/16"]["sources"]["edge-dub"]
    assert edge["status"] == "rerouted"
    assert edge["path"] == ["edge-dub", "core-a", "dc-dub-1"]
    assert edge["baseline_path"] == ["edge-dub", "core-a", "core-b", "dc-dub-1"]
    assert result["prefixes"]["10.10.0.0/16"]["sources"]["core-b"]["status"] == "unchanged"
    assert result["summary"]["unreachable"] == 0


def test_every_node_is_evaluated_not_just_one(metro: Topology) -> None:
    result = analyze(metro)
    assert set(result["prefixes"]["10.10.0.0/16"]["sources"]) == {"edge-dub", "core-a", "core-b"}


def test_node_failure_isolates_single_homed_edge(metro: Topology) -> None:
    result = analyze(metro, failed_nodes=["core-a"])
    sources = result["prefixes"]["10.10.0.0/16"]["sources"]
    assert "core-a" not in sources
    assert sources["edge-dub"]["status"] == "unreachable"
    assert sources["core-b"]["status"] == "unchanged"


def test_origin_failure_is_flagged(metro: Topology) -> None:
    result = analyze(metro, failed_nodes=["dc-dub-1"])
    assert result["prefixes"]["10.10.0.0/16"]["origin_failed"] is True


def test_resilience_finds_single_points_of_failure(metro: Topology) -> None:
    report = resilience(metro)
    assert report["resilient"] is False
    assert "link edge-dub,core-a" in report["single_points_of_failure"]
    assert "link core-a,core-b" not in report["single_points_of_failure"]
    dc_failure = next(s for s in report["scenarios"] if s["failure"] == "node dc-dub-1")
    assert dc_failure["lost_origins"] == ["10.10.0.0/16"]
    assert dc_failure["lost_reachability"] == []


def test_ring_is_resilient_to_link_failures() -> None:
    ring = parse(
        {
            "nodes": [{"name": n} for n in "abc"],
            "links": [
                {"left": "a", "right": "b", "protocol": "OSPF"},
                {"left": "b", "right": "c", "protocol": "OSPF"},
                {"left": "c", "right": "a", "protocol": "OSPF"},
            ],
            "prefixes": [{"prefix": "10.0.0.0/24", "origin": "a"}],
        }
    )
    report = resilience(ring)
    assert [s for s in report["single_points_of_failure"] if s.startswith("link")] == []


def test_equal_cost_tie_break_is_deterministic() -> None:
    links = [
        Link("s", "y", "OSPF"),
        Link("s", "x", "OSPF"),
        Link("y", "d", "OSPF"),
        Link("x", "d", "OSPF"),
    ]
    forward = Topology({"s", "x", "y", "d"}, links, {})
    backward = Topology({"s", "x", "y", "d"}, list(reversed(links)), {})
    assert (
        shortest_path(forward, "s", "d")
        == shortest_path(backward, "s", "d")
        == (
            20,
            ["s", "x", "d"],
        )
    )


def test_unreachable_returns_none() -> None:
    topology = Topology({"a", "b"}, [], {})
    assert shortest_path(topology, "a", "b") is None


def test_validate_reports_each_problem(metro: Topology) -> None:
    metro.links.append(Link("core-a", "core-a", "OSPF"))
    metro.links.append(Link("core-b", "ghost", "RIP", 0))
    metro.links.append(Link("core-b", "core-a", "OSPF"))
    metro.links.append(Link("core-b", "dc-dub-1", "BGP"))
    metro.bgp_peers.append(("edge-dub", "missing"))
    metro.bgp_peers.append(("core-a", "edge-dub"))
    metro.prefixes["10.10.0.0/33"] = "dc-dub-1"
    metro.prefixes["192.0.2.0/24"] = "nowhere"
    errors = "\n".join(validate(metro))
    for expected in [
        "self-link is not valid: core-a",
        "references unknown node 'ghost'",
        "cost must be positive",
        "unsupported protocol 'RIP'",
        "duplicate link: core-b,core-a",
        "BGP link core-b,dc-dub-1 has no matching bgp_peers entry",
        "BGP peer edge-dub,missing references unknown node 'missing'",
        "duplicate BGP peering: core-a,edge-dub",
        "'10.10.0.0/33' is not a valid network",
        "unknown origin 'nowhere'",
    ]:
        assert expected in errors
