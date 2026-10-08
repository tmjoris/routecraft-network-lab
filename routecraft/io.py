from pathlib import Path

import yaml

from .model import Link, Topology


def load(path: str | Path) -> Topology:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    nodes = {node["name"] for node in data.get("nodes", [])}
    links = [Link(item["left"], item["right"], item["protocol"].upper(), int(item.get("cost", 10)))
             for item in data.get("links", [])]
    prefixes = {item["prefix"]: item["origin"] for item in data.get("prefixes", [])}
    peers = [(peer["local"], peer["remote"]) for peer in data.get("bgp_peers", [])]
    return Topology(nodes, links, prefixes, peers)

