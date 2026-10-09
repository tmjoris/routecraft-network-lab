"""Helpers for driving the live lab from tests."""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import yaml

ROOT = Path(__file__).resolve().parents[2]
T = TypeVar("T")


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=check,
        timeout=60,
    )


def node_exec(node: str, *command: str, check: bool = True) -> str:
    return compose("exec", "-T", node, *command, check=check).stdout


def vtysh_json(node: str, command: str) -> Any:
    return json.loads(node_exec(node, "vtysh", "-c", f"{command} json"))


def eventually(probe: Callable[[], T], timeout: float = 60.0, interval: float = 1.0) -> T:
    """Retry probe until it returns a truthy value and stops raising AssertionError."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            result = probe()
            if result:
                return result
            error: Exception = AssertionError(f"{probe.__name__} returned {result!r}")
        except AssertionError as exc:
            error = exc
        if time.monotonic() > deadline:
            raise error
        time.sleep(interval)


def address_owners() -> dict[str, str]:
    """Map every lab interface address to the node that owns it."""
    spec = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    return {
        settings["ipv4_address"]: service
        for service, service_spec in spec["services"].items()
        for settings in service_spec["networks"].values()
    }
