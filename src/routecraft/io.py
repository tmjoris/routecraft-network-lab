"""Load topology files.

Loading checks the *shape* of the file (types, required and unknown keys,
duplicates that a mapping would otherwise hide) and raises TopologyFormatError.
Semantic checks such as unknown node references live in analysis.validate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .model import Link, Topology


class TopologyFormatError(ValueError):
    """The topology file is not structurally valid."""


def load(path: str | Path) -> Topology:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TopologyFormatError(f"{path}: cannot read file: {exc.strerror}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise TopologyFormatError(f"{path}: invalid YAML: {exc}") from exc
    try:
        return parse(data)
    except TopologyFormatError as exc:
        raise TopologyFormatError(f"{path}: {exc}") from None


def parse(data: Any) -> Topology:
    if not isinstance(data, dict):
        raise TopologyFormatError("top level must be a mapping")
    _reject_unknown(data, {"nodes", "links", "prefixes", "bgp_peers"}, "top level")

    nodes: set[str] = set()
    for where, item in _items(data, "nodes"):
        _reject_unknown(item, {"name"}, where)
        name = _string(item, "name", where)
        if name in nodes:
            raise TopologyFormatError(f"{where}: duplicate node {name!r}")
        nodes.add(name)

    links = []
    for where, item in _items(data, "links"):
        _reject_unknown(item, {"left", "right", "protocol", "cost"}, where)
        cost = item.get("cost", 10)
        if isinstance(cost, bool) or not isinstance(cost, int):
            raise TopologyFormatError(f"{where}: 'cost' must be an integer")
        links.append(
            Link(
                _string(item, "left", where),
                _string(item, "right", where),
                _string(item, "protocol", where).upper(),
                cost,
            )
        )

    prefixes: dict[str, str] = {}
    for where, item in _items(data, "prefixes"):
        _reject_unknown(item, {"prefix", "origin"}, where)
        prefix = _string(item, "prefix", where)
        if prefix in prefixes:
            raise TopologyFormatError(f"{where}: duplicate prefix {prefix!r}")
        prefixes[prefix] = _string(item, "origin", where)

    peers = []
    for where, item in _items(data, "bgp_peers"):
        _reject_unknown(item, {"local", "remote"}, where)
        peers.append((_string(item, "local", where), _string(item, "remote", where)))

    return Topology(nodes, links, prefixes, peers)


def _items(data: dict[str, Any], key: str) -> list[tuple[str, dict[str, Any]]]:
    value = data.get(key) or []
    if not isinstance(value, list):
        raise TopologyFormatError(f"'{key}' must be a list")
    result = []
    for index, item in enumerate(value):
        where = f"{key}[{index}]"
        if not isinstance(item, dict):
            raise TopologyFormatError(f"{where}: must be a mapping")
        result.append((where, item))
    return result


def _string(item: dict[str, Any], key: str, where: str) -> str:
    if key not in item:
        raise TopologyFormatError(f"{where}: missing required field '{key}'")
    value = item[key]
    if not isinstance(value, str) or not value.strip():
        raise TopologyFormatError(f"{where}: '{key}' must be a non-empty string")
    return value.strip()


def _reject_unknown(item: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = sorted(set(item) - allowed)
    if unknown:
        raise TopologyFormatError(f"{where}: unknown field(s): {', '.join(map(str, unknown))}")
