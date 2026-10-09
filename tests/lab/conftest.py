"""Fixtures for tests that run against the live lab (`docker compose up -d --wait`)."""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterator

import pytest

from labkit import compose, node_exec


@pytest.fixture(scope="session", autouse=True)
def lab_running() -> None:
    if shutil.which("docker") is None:
        pytest.fail("docker is not installed; the lab tests need a running lab")
    running = compose("ps", "--status", "running", "--services", check=False).stdout.split()
    expected = {"edge", "core-a", "core-b", "dc"}
    if not expected <= set(running):
        pytest.fail(
            f"lab is not running (running: {running or 'none'}). "
            "Start it with: docker compose up -d --wait"
        )


@pytest.fixture
def link_control() -> Iterator[tuple[Callable[[str, str], None], Callable[[], None]]]:
    """Return (fail, restore) for taking a link down on both ends.

    Whatever the test does, every link it failed is brought back up afterwards.
    """
    taken_down: list[tuple[str, str]] = []

    def fail(left: str, right: str) -> None:
        for node, peer in ((left, right), (right, left)):
            node_exec(node, "ip", "link", "set", f"to-{peer}", "down")
            taken_down.append((node, peer))

    def restore() -> None:
        while taken_down:
            node, peer = taken_down.pop()
            node_exec(node, "ip", "link", "set", f"to-{peer}", "up", check=False)

    yield fail, restore
    restore()
