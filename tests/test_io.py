from pathlib import Path
from typing import Any

import pytest

from routecraft.io import TopologyFormatError, load, parse

MINIMAL: dict[str, Any] = {
    "nodes": [{"name": "a"}, {"name": "b"}],
    "links": [{"left": "a", "right": "b", "protocol": "ospf"}],
}


def test_parse_normalizes_protocol_and_defaults_cost() -> None:
    topology = parse(MINIMAL)
    assert topology.nodes == {"a", "b"}
    assert topology.links[0].protocol == "OSPF"
    assert topology.links[0].cost == 10


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ([], "top level must be a mapping"),
        ({"nodes": "a"}, "'nodes' must be a list"),
        ({"nodes": ["a"]}, r"nodes\[0\]: must be a mapping"),
        ({"nodes": [{"name": "a"}, {"name": "a"}]}, "duplicate node 'a'"),
        ({"links": [{"left": "a", "protocol": "OSPF"}]}, "missing required field 'right'"),
        ({"links": [{"left": "a", "right": "b", "protocol": "OSPF", "cost": "5"}]}, "integer"),
        ({"links": [{"left": "a", "right": "b", "protocol": "OSPF", "cost": True}]}, "integer"),
        ({"links": [{"left": "a", "right": "b", "protocol": "OSPF", "cots": 5}]}, "cots"),
        ({"nodes": [{"name": ""}]}, "non-empty string"),
        ({"routers": []}, "unknown field"),
        (
            {"prefixes": [{"prefix": "10.0.0.0/8", "origin": "a"}] * 2},
            "duplicate prefix",
        ),
    ],
)
def test_parse_rejects_malformed_input(data: Any, message: str) -> None:
    with pytest.raises(TopologyFormatError, match=message):
        parse(data)


def test_load_reports_path_on_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("nodes: [", encoding="utf-8")
    with pytest.raises(TopologyFormatError, match=r"bad\.yaml: invalid YAML"):
        load(path)


def test_load_missing_file(tmp_path: Path) -> None:
    with pytest.raises(TopologyFormatError, match="cannot read file"):
        load(tmp_path / "missing.yaml")


def test_empty_file_is_an_empty_topology(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("{}\n", encoding="utf-8")
    assert load(path).nodes == set()
