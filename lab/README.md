# RouteCraft live FRRouting lab

This directory describes the intended live part of RouteCraft. It uses the
`docker-compose.yml` file in the repository root and FRRouting containers to
form control-plane adjacencies when the configuration is started and verified
on a Docker-capable host.

## What the lab is intended to demonstrate

- eBGP between `edge` (AS 65001) and `core-a` (AS 65000);
- OSPF inside AS 65000;
- a directly connected loopback prefix on `dc`;
- route propagation through the core;
- the effect of removing one Docker network from the topology.

It is not a traffic generator, a hardware emulator, or a production
configuration. The lab is small so that a person can inspect every interface,
neighbor, and route. Docker is unavailable in the development environment,
so the live convergence commands below are a verification procedure rather
than a claim that live adjacencies have already been observed.

## Before starting

Install Docker Engine and the Docker Compose plugin. Confirm both commands
work:

```bash
docker version
docker compose version
```

The first run downloads `quay.io/frrouting/frr:10.2.1`. Image availability,
container privileges, and FRR startup behavior depend on the local Docker
installation. None of those conditions can be inferred from the repository
files alone.

## Start and inspect

From the repository root:

```bash
docker compose up -d
docker compose ps
```

Check that the daemons started:

```bash
docker compose logs edge
docker compose logs core-a
docker compose exec edge vtysh -c 'show version'
```

Check the intended control plane:

```bash
docker compose exec core-a vtysh -c 'show ip ospf neighbor'
docker compose exec core-b vtysh -c 'show ip ospf neighbor'
docker compose exec edge vtysh -c 'show ip bgp summary'
docker compose exec dc vtysh -c 'show ip route ospf'
```

For each command, compare the result with the expected topology. Do not infer
that an adjacency exists merely because the container is running.

## Troubleshooting interface names

The FRR configuration refers to `eth0`, `eth1`, and `eth2`. Docker normally
assigns interfaces in network declaration order, but that is an operational
assumption that must be checked:

```bash
docker compose exec core-a ip -br addr
docker compose exec core-b ip -br addr
docker compose exec dc ip -br addr
```

The expected addresses are:

| Node | Interface | Address |
|---|---|---|
| edge | eth0 | `172.30.1.1/30` |
| core-a | eth0 | `172.30.1.2/30` |
| core-a | eth1 | `172.30.2.1/30` |
| core-a | eth2 | `172.30.4.1/30` |
| core-b | eth0 | `172.30.2.2/30` |
| core-b | eth1 | `172.30.3.1/30` |
| dc | eth0 | `172.30.3.2/30` |
| dc | eth1 | `172.30.4.2/30` |

If the addresses do not match, stop and correct the container configuration
before interpreting routing output.

## Failure experiment

The direct `core-a` to `core-b` link is a Docker network. Compose usually
prefixes its name with the project name, so discover it instead of guessing:

```bash
docker network ls --format '{{.Name}}' | grep core_a_core_b
```

Inspect membership before changing it:

```bash
docker network inspect <network-name>
```

Disconnect both endpoints:

```bash
docker network disconnect <network-name> core-a
docker network disconnect <network-name> core-b
```

Then inspect the resulting state:

```bash
docker compose exec core-a vtysh -c 'show ip ospf neighbor'
docker compose exec core-a vtysh -c 'show ip route'
docker compose exec dc vtysh -c 'show ip route 10.10.0.1/32'
```

The expected learning outcome is that the OSPF adjacency over the disconnected
link disappears and the remaining path is evaluated. The exact convergence
timing and route output must be observed on the running lab; they are not
guaranteed by this document.

Reset rather than manually guessing how to reconnect:

```bash
docker compose down
docker compose up -d
```

## Cleanup

```bash
docker compose down
```

The Compose networks use private `172.30.0.0/16` subnets and are intended to
remain isolated from the host network. Review `docker network inspect` if the
environment has overlapping private address ranges.
