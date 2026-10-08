from dataclasses import dataclass, field


@dataclass(frozen=True)
class Link:
    left: str
    right: str
    protocol: str
    cost: int = 10

    def endpoints(self) -> frozenset[str]:
        return frozenset((self.left, self.right))


@dataclass
class Topology:
    nodes: set[str]
    links: list[Link]
    prefixes: dict[str, str]
    bgp_peers: list[tuple[str, str]] = field(default_factory=list)

    def neighbors(self, node: str, protocols: set[str] | None = None) -> list[tuple[str, int]]:
        result = []
        for link in self.links:
            if node not in link.endpoints() or (protocols and link.protocol not in protocols):
                continue
            result.append((link.right if link.left == node else link.left, link.cost))
        return result

