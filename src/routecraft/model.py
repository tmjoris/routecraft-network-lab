"""Topology data structures."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

PROTOCOLS: frozenset[str] = frozenset({"OSPF", "ISIS", "BGP", "GRE", "IPINIP"})


@dataclass(frozen=True)
class Link:
    left: str
    right: str
    protocol: str
    cost: int = 10

    def endpoints(self) -> frozenset[str]:
        return frozenset((self.left, self.right))

    def other(self, node: str) -> str:
        return self.right if node == self.left else self.left

    def __str__(self) -> str:
        return f"{self.left},{self.right}"


@dataclass
class Topology:
    nodes: set[str]
    links: list[Link]
    prefixes: dict[str, str]
    bgp_peers: list[tuple[str, str]] = field(default_factory=list)

    def neighbors(
        self, node: str, protocols: Iterable[str] | None = None
    ) -> Iterator[tuple[str, int]]:
        allowed = frozenset(protocols) if protocols is not None else None
        for link in self.links:
            if node not in link.endpoints() or (
                allowed is not None and link.protocol not in allowed
            ):
                continue
            yield link.other(node), link.cost

    def find_link(self, left: str, right: str) -> Link | None:
        wanted = frozenset((left, right))
        return next((link for link in self.links if link.endpoints() == wanted), None)

    def without(self, links: Iterable[Link] = (), nodes: Iterable[str] = ()) -> Topology:
        """Return a copy with the given links and nodes (and their links) removed."""
        failed_links = set(links)
        failed_nodes = set(nodes)
        return Topology(
            nodes=self.nodes - failed_nodes,
            links=[
                link
                for link in self.links
                if link not in failed_links and not (link.endpoints() & failed_nodes)
            ],
            prefixes=dict(self.prefixes),
            bgp_peers=[peer for peer in self.bgp_peers if not (set(peer) & failed_nodes)],
        )
