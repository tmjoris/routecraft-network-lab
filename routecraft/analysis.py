import heapq

from .model import Topology


def validate(topology: Topology) -> list[str]:
    errors: list[str] = []
    seen: set[frozenset[str]] = set()
    for link in topology.links:
        if link.left not in topology.nodes or link.right not in topology.nodes:
            errors.append(f"link references unknown node: {link.left}-{link.right}")
        if link.left == link.right:
            errors.append(f"self-link is not valid: {link.left}")
        if link.cost <= 0:
            errors.append(f"link cost must be positive: {link.left}-{link.right}")
        if link.endpoints() in seen:
            errors.append(f"duplicate link: {link.left}-{link.right}")
        seen.add(link.endpoints())
        if link.protocol not in {"OSPF", "ISIS", "BGP", "GRE", "IPINIP"}:
            errors.append(f"unsupported protocol: {link.protocol}")
    for local, remote in topology.bgp_peers:
        if local not in topology.nodes or remote not in topology.nodes:
            errors.append(f"BGP peer references unknown node: {local}-{remote}")
    for prefix, origin in topology.prefixes.items():
        if origin not in topology.nodes:
            errors.append(f"prefix {prefix} has unknown origin {origin}")
    return errors


def shortest_path(topology: Topology, source: str, destination: str,
                  excluded: frozenset[str] | None = None) -> tuple[int, list[str]] | None:
    excluded = excluded or frozenset()
    queue: list[tuple[int, str, list[str]]] = [(0, source, [source])]
    best: dict[str, int] = {}
    while queue:
        cost, node, path = heapq.heappop(queue)
        if node in excluded or cost > best.get(node, float("inf")):
            continue
        best[node] = cost
        if node == destination:
            return cost, path
        for neighbor, edge_cost in topology.neighbors(node, {"OSPF", "ISIS", "BGP", "GRE", "IPINIP"}):
            if neighbor not in path:
                heapq.heappush(queue, (cost + edge_cost, neighbor, path + [neighbor]))
    return None


def analyze(topology: Topology, failed_link: frozenset[str] | None = None) -> dict[str, object]:
    links = [link for link in topology.links if not failed_link or link.endpoints() != failed_link]
    reduced = Topology(topology.nodes, links, topology.prefixes, topology.bgp_peers)
    results = {}
    for prefix, origin in topology.prefixes.items():
        source = sorted(topology.nodes - {origin})[0]
        path = shortest_path(reduced, source, origin)
        results[prefix] = {"origin": origin, "reachable": path is not None,
                           "path": path[1] if path else None}
    return results
