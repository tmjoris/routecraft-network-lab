# RouteCraft

## What problem this solves

Network engineers need to answer two different questions:

1. Is the intended topology and protocol configuration internally consistent?
2. What happens to reachability when a link or device fails?

RouteCraft provides both a deterministic analysis model and an optional
containerized FRRouting lab. The Python model is fast and reproducible. The
FRRouting lab is where real routing daemons form adjacencies and calculate
routes.

The project is organized as:

```text
topology data -> validation -> path/failure analysis
                                  |
                                  +-> optional FRRouting containers
```

## Part 1: deterministic Python model

Install and run:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
routecraft validate examples/metro.yaml
routecraft simulate-failure examples/metro.yaml --link core-a,core-b
```

The example topology has four nodes:

```text
edge-dub -- core-a -- core-b -- dc-dub-1
                         \------/
```

It models:

- an external BGP relationship between `edge-dub` and `core-a`;
- OSPF-style internal links;
- link costs;
- one destination prefix originated by `dc-dub-1`;
- a more expensive direct backup link from `core-a` to `dc-dub-1`.

`validate` checks for unknown nodes, duplicate links, invalid costs,
unsupported protocols, unknown BGP peers, and prefixes with unknown origins.

`simulate-failure` removes one modeled link and recomputes reachability. It
does not change a real interface, send packets, or start a routing daemon.

## Part 2: live FRRouting lab

The repository also contains a Docker Compose topology using FRRouting:

```text
edge (AS 65001)
   |
core-a (AS 65000) ---- OSPF ---- core-b (AS 65000)
   |                                  |
   +------------- OSPF ---------------+
                                      |
                                     dc
```

The daemons are isolated in Docker networks. They are not connected to the
host's physical interfaces or routing table.

Start the lab:

```bash
docker compose up -d
docker compose ps
```

Inspect the control plane:

```bash
docker compose exec core-a vtysh -c 'show ip ospf neighbor'
docker compose exec edge vtysh -c 'show ip bgp summary'
docker compose exec dc vtysh -c 'show ip route ospf'
```

Inspect interfaces and routes when debugging:

```bash
docker compose exec core-a ip addr
docker compose exec core-a ip route
docker compose logs core-a
```

The FRRouting containers are configured with static addresses on the Compose
networks. The configuration files assume the Docker interfaces appear as
`eth0`, `eth1`, and `eth2` in the same order as the service's `networks`
section. Always inspect `ip addr` before treating a protocol result as valid;
container interface ordering is an environment-dependent detail.

To stop the direct core link for a failure experiment, first discover the
actual Compose network name:

```bash
docker network ls --filter name=core_a_core_b
```

Then disconnect `core-a` and `core-b` from that network:

```bash
docker network disconnect <project>_core_a_core_b core-a
docker network disconnect <project>_core_a_core_b core-b
docker compose exec dc vtysh -c 'show ip route'
```

Restore the lab with:

```bash
docker compose down
docker compose up -d
```

This is a real FRRouting control-plane experiment, but it is still a small
four-node lab. It does not reproduce Meta's scale, hardware, route policies,
failure domains, or production change controls.

## Repository map

| Path | Responsibility |
|---|---|
| `routecraft/model.py` | topology and link data structures |
| `routecraft/io.py` | YAML topology loading |
| `routecraft/analysis.py` | validation, shortest paths, failure analysis |
| `routecraft/cli.py` | command-line interface |
| `examples/metro.yaml` | deterministic sample topology |
| `docker-compose.yml` | FRRouting container topology |
| `lab/frr/*/frr.conf` | per-node BGP/OSPF configuration |
| `lab/README.md` | live-lab walkthrough |
| `docs/ARCHITECTURE.md` | detailed design and limitations |

## What has and has not been verified

Verified in the development environment:

- the Python model compiles;
- the YAML topology parses;
- the deterministic validator and failure analysis run;
- the Compose YAML and FRR configuration files pass structural smoke checks.

Not verified in the development environment:

- pulling the FRRouting image;
- starting Docker containers;
- forming live OSPF adjacencies;
- establishing live BGP state;
- observing a real route withdrawal after network disconnection.

Docker was not available in the development environment. The live protocol
claims therefore remain documented instructions until someone runs the lab on a
machine with Docker.
