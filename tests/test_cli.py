import json
from pathlib import Path

import pytest

from routecraft.cli import main


@pytest.fixture
def metro(root: Path) -> str:
    return str(root / "examples" / "metro.yaml")


def test_validate_text(metro: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", metro]) == 0
    assert capsys.readouterr().out.strip() == "OK: 4 nodes, 4 links"


def test_validate_json(metro: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", metro, "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"valid": True, "nodes": 4, "links": 4}


def test_invalid_topology_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "t.yaml"
    path.write_text("links: [{left: a, right: b, protocol: OSPF}]\n", encoding="utf-8")
    assert main(["validate", str(path)]) == 1
    assert "unknown node 'a'" in capsys.readouterr().out


def test_unreadable_file_exits_1_with_message(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", "does-not-exist.yaml"]) == 1
    assert "cannot read file" in capsys.readouterr().err


def test_simulate_link_failure(metro: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["simulate-failure", metro, "--link", "core-b, core-a"]) == 0
    out = capsys.readouterr().out
    assert "edge-dub     rerouted    edge-dub -> core-a -> dc-dub-1 (cost 35)" in out
    assert "0 unreachable" in out


def test_simulate_node_failure_json(metro: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["simulate-failure", metro, "--node", "core-b", "--format", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["failed"] == {"links": [], "nodes": ["core-b"]}


@pytest.mark.parametrize(
    "args",
    [
        ["--link", "core-a"],
        ["--link", "core-a,nowhere"],
        ["--node", "nowhere"],
        [],
    ],
)
def test_bad_failure_arguments_are_usage_errors(metro: str, args: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["simulate-failure", metro, *args])
    assert exc.value.code == 2


def test_resilience_gate(metro: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["resilience", metro]) == 0
    assert main(["resilience", metro, "--fail-on-loss"]) == 1
    assert "LOSS  link edge-dub,core-a" in capsys.readouterr().out


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--version"])
    assert capsys.readouterr().out.startswith("routecraft ")
