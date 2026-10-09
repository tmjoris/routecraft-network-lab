"""Validation, shortest-path and failure analysis over a Topology."""

from __future__ import annotations

import heapq
import ipaddress
from collections.abc import Iterable
from typing import Any

from .model import PROTOCOLS, Link, Topology


def validate(topology: Topology) -> list[str]:
    """Return semantic errors; an empty list means the topology is usable."""
    return [*_link_errors(topology), *_peer_errors(topology), *_prefix_errors(topology)]


def _link_errors(topology: Topology) -> list[str]:
    errors: list[str] = []
    seen: set[frozenset[str]] = set()
    for link in topology.links:
        errors.extend(
            f"link {link} references unknown node {node!r}"
            for node in (link.left, link.right)
            if node not in topology.nodes
        )
        if link.left == link.right:
            errors.append(f"self-link is not valid: {link.left}")
        if link.cost <= 0:
            errors.append(f"link {link} cost must be positive, got {link.cost}")
        if link.endpoints() in seen:
            errors.append(f"duplicate link: {link}")
        seen.add(link.endpoints())
        if link.protocol not in PROTOCOLS:
            errors.append(
                f"link {link} uses unsupported protocol {link.protocol!r} "
                f"(supported: {', '.join(sorted(PROTOCOLS))})"
            )
    return errors


def _peer_errors(topology: Topology) -> list[str]:
    errors: list[str] = []
    peerings: set[frozenset[str]] = set()
    for local, remote in topology.bgp_peers:
        errors.extend(
            f"BGP peer {local},{remote} references unknown node {node!r}"
            for node in (local, remote)
            if node not in topology.nodes
        )
        if local == remote:
            errors.append(f"BGP peer cannot peer with itself: {local}")
        if frozenset((local, remote)) in peerings:
            errors.append(f"duplicate BGP peering: {local},{remote}")
        peerings.add(frozenset((local, remote)))
    errors.extend(
        f"BGP link {link} has no matching bgp_peers entry"
        for link in topology.links
        if link.protocol == "BGP" and link.endpoints() not in peerings
    )
    return errors


def _prefix_errors(topology: Topology) -> list[str]:
    errors: list[str] = []
    for prefix, origin in topology.prefixes.items():
        try:
            ipaddress.ip_network(prefix)
        except ValueError:
            errors.append(f"prefix {prefix!r} is not a valid network in CIDR notation")
        if origin not in topology.nodes:
            errors.append(f"prefix {prefix} has unknown origin {origin!r}")
    return errors


def shortest_path(
    topology: Topology,
    source: str,
    destination: str,
    excluded: frozenset[str] | None = None,
) -> tuple[int, list[str]] | None:
    """Dijkstra over modeled links.

    Equal-cost paths are broken by comparing the node sequence, so the result
    is deterministic regardless of link order in the file.
    """
    excluded = excluded or frozenset()
    if source in excluded or destination in excluded:
        return None
    queue: list[tuple[int, list[str]]] = [(0, [source])]
    settled: set[str] = set()
    while queue:
        cost, path = heapq.heappop(queue)
        node = path[-1]
        if node in settled:
            continue
        settled.add(node)
        if node == destination:
            return cost, path
        for neighbor, edge_cost in topology.neighbors(node, PROTOCOLS):
            if neighbor not in settled and neighbor not in excluded:
                heapq.heappush(queue, (cost + edge_cost, [*path, neighbor]))
    return None


def analyze(
    topology: Topology,
    failed_links: Iterable[Link] = (),
    failed_nodes: Iterable[str] = (),
) -> dict[str, Any]:
    """Compare reachability of every prefix from every node before and after failures."""
    failed_links = sorted(set(failed_links), key=str)
    failed_nodes = sorted(set(failed_nodes))
    reduced = topology.without(failed_links, failed_nodes)
    summary = {"unreachable": 0, "rerouted": 0, "unchanged": 0}
    prefixes: dict[str, Any] = {}
    for prefix, origin in sorted(topology.prefixes.items()):
        sources: dict[str, Any] = {}
        for source in sorted(reduced.nodes - {origin}):
            before = shortest_path(topology, source, origin)
            after = shortest_path(reduced, source, origin)
            if after is None:
                status = "unreachable"
            elif before is not None and before[1] == after[1]:
                status = "unchanged"
            else:
                status = "rerouted"
            summary[status] += 1
            sources[source] = {
                "status": status,
                "cost": after[0] if after else None,
                "path": after[1] if after else None,
                "baseline_path": before[1] if before else None,
            }
        prefixes[prefix] = {
            "origin": origin,
            "origin_failed": origin in failed_nodes,
            "sources": sources,
        }
    return {
        "failed": {"links": [str(link) for link in failed_links], "nodes": failed_nodes},
        "prefixes": prefixes,
        "summary": summary,
    }


def resilience(topology: Topology) -> dict[str, Any]:
    """Fail every link and every node in turn (N-1) and report reachability loss."""
    scenarios = []
    for kind, failure in [("link", link) for link in topology.links] + [
        ("node", node) for node in sorted(topology.nodes)
    ]:
        if isinstance(failure, Link):
            result = analyze(topology, failed_links=[failure])
        else:
            result = analyze(topology, failed_nodes=[failure])
        lost_origins = [
            prefix for prefix, entry in result["prefixes"].items() if entry["origin_failed"]
        ]
        lost = [
            {"prefix": prefix, "source": source}
            for prefix, entry in result["prefixes"].items()
            if not entry["origin_failed"]
            for source, outcome in entry["sources"].items()
            if outcome["status"] == "unreachable"
        ]
        scenarios.append(
            {
                "failure": f"{kind} {failure}",
                "lost_reachability": lost,
                "lost_origins": lost_origins,
                "rerouted": result["summary"]["rerouted"],
            }
        )
    single_points = [s["failure"] for s in scenarios if s["lost_reachability"] or s["lost_origins"]]
    return {
        "resilient": not single_points,
        "single_points_of_failure": single_points,
        "scenarios": scenarios,
    }
