"""Static checks that docker-compose.yml, lab/frr/*/frr.conf and lab/topology.yaml agree.

These run without Docker, so drift between the three is caught in every CI run.
"""

import ipaddress
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from routecraft.io import load
from routecraft.model import Topology

ROOT = Path(__file__).resolve().parent.parent


def _compose() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    return data


def _frr_interfaces(node: str) -> dict[str, list[str]]:
    """Map interface name -> its config lines from a node's frr.conf."""
    interfaces: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in (ROOT / "lab" / "frr" / node / "frr.conf").read_text().splitlines():
        if match := re.match(r"^interface (\S+)", line):
            current = interfaces.setdefault(match.group(1), [])
        elif line.startswith(" ") and current is not None:
            current.append(line.strip())
        else:
            current = None
    return interfaces


@pytest.fixture(scope="module")
def topology() -> Topology:
    return load(ROOT / "lab" / "topology.yaml")


def _attachments() -> dict[str, list[tuple[str, dict[str, Any]]]]:
    """Map compose network -> [(service, attachment settings)]."""
    result: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for service, spec in _compose()["services"].items():
        for network, settings in spec["networks"].items():
            result.setdefault(network, []).append((service, settings))
    return result


def test_services_match_model_nodes(topology: Topology) -> None:
    assert set(_compose()["services"]) == topology.nodes


def test_every_service_pins_the_same_image() -> None:
    images = {spec["image"] for spec in _compose()["services"].values()}
    assert len(images) == 1
    (image,) = images
    assert re.search(r":\d+\.\d+\.\d+$", image), f"image must be pinned to a release: {image}"


def test_each_network_is_one_modeled_point_to_point_link(topology: Topology) -> None:
    networks = _compose()["networks"]
    attachments = _attachments()
    assert set(networks) == set(attachments)
    modeled = {link.endpoints() for link in topology.links}
    for name, spec in networks.items():
        members = attachments[name]
        assert len(members) == 2, f"{name} must connect exactly two nodes"
        assert frozenset(service for service, _ in members) in modeled, f"{name} is not modeled"
        assert spec["internal"] is True
        (subnet,) = (ipaddress.ip_network(cfg["subnet"]) for cfg in spec["ipam"]["config"])
        assert subnet.prefixlen == 31, f"{name} should be a /31 point-to-point link"
        for _, settings in members:
            assert ipaddress.ip_address(settings["ipv4_address"]) in subnet
    assert len(networks) == len(topology.links)


def test_interface_names_and_addresses_match_frr_config() -> None:
    for network, members in _attachments().items():
        prefixlen = ipaddress.ip_network(
            _compose()["networks"][network]["ipam"]["config"][0]["subnet"]
        ).prefixlen
        for service, settings in members:
            (peer,) = (other for other, _ in members if other != service)
            interface = settings["interface_name"]
            assert interface == f"to-{peer}", f"{service} on {network}: name by peer"
            config = _frr_interfaces(service)
            assert interface in config, f"{service}/frr.conf has no 'interface {interface}'"
            expected = f"ip address {settings['ipv4_address']}/{prefixlen}"
            assert expected in config[interface], f"{service} {interface}: want {expected}"


def test_ospf_costs_match_model(topology: Topology) -> None:
    for link in topology.links:
        if link.protocol != "OSPF":
            continue
        for node in (link.left, link.right):
            lines = _frr_interfaces(node)[f"to-{link.other(node)}"]
            assert f"ip ospf cost {link.cost}" in lines, f"{node} to-{link.other(node)}"
            assert "ip ospf network point-to-point" in lines
            assert "ip ospf bfd" in lines


def test_prefix_origins_originate_in_bgp(topology: Topology) -> None:
    for prefix, origin in topology.prefixes.items():
        config = (ROOT / "lab" / "frr" / origin / "frr.conf").read_text()
        assert f"network {prefix}\n" in config, f"{origin} must originate {prefix}"
        assert f"ip route {prefix} blackhole" in config, f"{origin} needs an anchor route"


def test_ebgp_sessions_have_policy_in_both_directions(topology: Topology) -> None:
    """RFC 8212: eBGP must not exchange routes without explicit policy."""
    for local, remote in topology.bgp_peers:
        for node in (local, remote):
            config = (ROOT / "lab" / "frr" / node / "frr.conf").read_text()
            for direction in ("in", "out"):
                assert re.search(rf"neighbor \S+ route-map \S+ {direction}\n", config), (
                    f"{node} has no {direction}bound eBGP policy"
                )
