# RouteCraft

[![CI](https://github.com/tmjoris/routecraft-network-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/tmjoris/routecraft-network-lab/actions/workflows/ci.yml)

## What problem this solves

Network engineers need to answer two different questions:

1. Is the intended topology and protocol configuration internally consistent?
2. What happens to reachability when a link or device fails?

RouteCraft answers both with two layers that check each other:

- a **deterministic Python model** that validates a topology file and predicts
  paths before and after failures, fast enough to run on every commit;
- a **live FRRouting lab** in Docker, where real OSPF, BGP and BFD daemons form
  adjacencies, forward packets and reconverge when a link is cut.

The lab's end-to-end tests compare the paths packets actually take (by
traceroute) with the paths the model predicts, both before and after a failure.

```text
topology YAML -> validate -> path / failure / N-1 analysis   (routecraft CLI)
      |                                 |
      |                       predictions must match
      v                                 v
docker-compose.yml + frr.conf -> FRRouting lab -> live paths  (pytest -m lab)
```

## Quick start

Requirements:

- **Python 3.11+** with `venv`. On Debian or Ubuntu that means `sudo apt install python3-venv`.
- **For the live lab:** Docker Engine 28.1+ (tested on 29.8) with the Compose plugin v2.36+,
  on Linux. Your user must be able to run `docker` without `sudo`.

```bash
git clone https://github.com/tmjoris/routecraft-network-lab.git
cd routecraft-network-lab
make install                 # creates .venv and installs routecraft with dev tools
. .venv/bin/activate

routecraft validate examples/metro.yaml
routecraft simulate-failure examples/metro.yaml --link core-a,core-b

lab/labctl up                # checks prerequisites, starts 4 routers, waits for convergence
lab/labctl path              # where traffic goes now
lab/labctl fail-link core-a core-b
lab/labctl path              # where it goes after the failure
lab/labctl restore-link core-a core-b
make lab-test                # automated end-to-end verification
lab/labctl down
```

No `make`? Run `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'` instead.

## Part 1: deterministic Python model

A topology file lists nodes, links (protocol and cost), BGP peerings and the
prefixes each node originates. See [`examples/metro.yaml`](examples/metro.yaml):

```text
edge-dub --BGP 5-- core-a --10-- core-b --10-- dc-dub-1
                      \------------30----------/
```

### Commands

| Command | What it does |
|---|---|
| `routecraft validate FILE` | schema and semantic checks |
| `routecraft simulate-failure FILE --link A,B --node N` | recompute reachability after failures (both options repeatable) |
| `routecraft resilience FILE [--fail-on-loss]` | fail every link and node in turn (N-1) and report losses |

Every command accepts `--format json` for machine-readable output. Exit codes:
`0` success, `1` invalid topology (or loss with `--fail-on-loss`), `2` usage error.

```console
$ routecraft simulate-failure examples/metro.yaml --link core-a,core-b
Failure: core-a,core-b
10.10.0.0/16 from origin dc-dub-1
  core-a       rerouted    core-a -> dc-dub-1 (cost 30)
  core-b       unchanged   core-b -> dc-dub-1 (cost 10)
  edge-dub     rerouted    edge-dub -> core-a -> dc-dub-1 (cost 35)
Summary: 1 unchanged, 2 rerouted, 0 unreachable

$ routecraft resilience examples/metro.yaml
LOSS  link edge-dub,core-a
        edge-dub cannot reach 10.10.0.0/16
ok    link core-a,core-b
...
Not resilient: 3 single point(s) of failure
```

`resilience --fail-on-loss` can be used as a CI gate: a change that introduces
a new single point of failure fails the build.

### What validation catches

The loader rejects structural problems with the file and position, such as
`links[2]: missing required field 'right'`. That includes misspelled keys,
wrong types, and duplicate nodes or prefixes that a plain mapping would
otherwise silently drop.

`validate` then reports semantic errors:
- unknown nodes;
- self-links and duplicate links;
- non-positive costs;
- unsupported protocols;
- BGP links with no peering;
- duplicate or unknown BGP peers;
- invalid CIDR prefixes;
- unknown prefix origins.

The model is not a routing daemon. It runs a weighted shortest-path search
(Dijkstra with deterministic tie-breaking) over the modeled links, and does not
implement BGP path selection or OSPF areas.

## Part 2: live FRRouting lab

```text
                 edge  AS 65001   lo 192.0.2.1 (announces 192.0.2.0/24)
                   | eBGP + BFD, TCP-MD5, prefix-list policy both ways
                 core-a ---------- 10 ---------- core-b
  AS 65000         \                               | 10
  OSPF area 0       \------------- 30 ------------ dc   lo 10.10.0.1
  iBGP full mesh                          (announces 10.10.0.0/16)
```

### Addressing plan

| Link | Network | Addresses |
|---|---|---|
| edge – core-a | `172.30.0.0/31` | edge `.0`, core-a `.1` |
| core-a – core-b | `172.30.0.2/31` | core-a `.2`, core-b `.3` |
| core-b – dc | `172.30.0.4/31` | core-b `.4`, dc `.5` |
| core-a – dc | `172.30.0.6/31` | core-a `.6`, dc `.7` |

Router IDs and iBGP endpoints are loopbacks: core-a `10.255.0.2`, core-b
`10.255.0.3`, dc `10.255.0.4` (edge `10.255.1.1`). On each router the
interface facing a peer is named `to-<peer>`, for example `to-core-b`.

### Design choices

| Practice | How the lab does it |
|---|---|
| Point-to-point links (RFC 3021) | `/31` per link, OSPF `network point-to-point` (no DR/BDR election) |
| Lab isolated from host | links are `internal` Docker networks with no host gateway address and no default route |
| Predictable interfaces | Compose `interface_name`, not Docker's `ethN` ordering |
| IGP carries infrastructure only | OSPF has loopbacks and links; service prefixes ride iBGP |
| Loopback iBGP | `update-source lo`, so iBGP survives any single core link loss |
| `next-hop-self` | core-a rewrites eBGP next hops for iBGP peers |
| eBGP default-deny (RFC 8212) | explicit import/export route-maps on both sides, `maximum-prefix` |
| Fast failure detection | BFD on every OSPF adjacency and the eBGP session (900 ms detection) |
| Control-plane authentication | OSPF HMAC-SHA-256 key chain, TCP-MD5 on eBGP |
| Reproducible images | FRR pinned to `10.7.1`, config mounted read-only from git |
| Least privilege | specific capabilities instead of `--privileged` |

The passwords in `lab/frr/*/frr.conf` are lab values, committed on purpose.
Never reuse them on a real network.

### Driving the lab

`lab/labctl` wraps the common operations and works from any directory:

```console
$ lab/labctl up
==> Docker 29.8.2, Compose 2.36.1: ready
==> starting the lab (first run downloads the FRR image)
==> waiting for OSPF, BGP and forwarding to converge ............. done in 25s
==> lab is up. Next: lab/labctl status, lab/labctl path

$ lab/labctl path
==> edge (192.0.2.1) -> dc service (10.10.0.1)
  1   172.30.0.1   core-a
  2   172.30.0.3   core-b
  3   10.10.0.1    dc

$ lab/labctl fail-link core-a core-b
==> link core-a <-> core-b is down

$ lab/labctl path
==> edge (192.0.2.1) -> dc service (10.10.0.1)
  1   172.30.0.1   core-a
  2   10.10.0.1    dc
```

This is the same reroute the model predicts with `routecraft simulate-failure
lab/topology.yaml --link core-a,core-b`. `restore-link` brings the link back
and waits until OSPF has re-formed the adjacency and every forwarding table is
stable. Traffic is then back on core-b.

Other commands: `check`, `status` (OSPF, BGP and BFD on every router),
`shell <router>` (interactive `vtysh`), `logs [router]`, `wait`, `down`. Run
`lab/labctl help` for details.

`check`, which `up` runs first, catches the usual reasons a lab fails to start:
- Docker is not installed, or the daemon is not running;
- no permission to use the Docker socket;
- Docker Engine or Compose is too old for fixed interface names;
- the Docker Engine lacks isolated networks;
- another Docker network, VPN or route already uses `172.30.0.0/24`.

Plain `docker compose up -d --wait` also works, but `--wait` only means the
daemons answer. Routing needs about another 20 s: OSPF hellos run every 10 s,
and SPF and BGP best-path runs follow. Run `lab/labctl wait` before testing
reachability. It returns once every adjacency and session is up and the
forwarding tables have stopped changing.
[`lab/README.md`](lab/README.md) has a manual `vtysh` walkthrough.

## Model vs reality: the tests

| Suite | Needs Docker | Checks |
|---|---|---|
| `tests/test_io.py`, `test_analysis.py`, `test_cli.py` | no | loader, analysis and CLI behavior |
| `tests/test_lab_config.py` | no | `docker-compose.yml`, `lab/frr/*/frr.conf` and `lab/topology.yaml` agree (addresses, interface names, OSPF costs, BFD, eBGP policy) |
| `tests/lab/test_live.py` (`pytest -m lab`) | yes, lab running | interfaces, OSPF Full, BGP Established, single-hop BFD up, policy exchanges only intended prefixes, infrastructure not exposed, ping, **traceroute paths equal model paths before, during and after a link failure** |

CI runs the first two suites on Python 3.11–3.13, then boots the real lab on
a GitHub runner and runs the live suite.

## Development

```bash
make install    # .venv with ruff, mypy, pytest
make check      # lint + strict typecheck + tests with coverage
make lab-up lab-test lab-down
pre-commit install   # optional: run ruff and shellcheck on every commit
```

## Repository map

| Path | Responsibility |
|---|---|
| `src/routecraft/model.py` | topology and link data structures |
| `src/routecraft/io.py` | YAML loading and structural validation |
| `src/routecraft/analysis.py` | semantic validation, shortest paths, failure and N-1 analysis |
| `src/routecraft/cli.py` | command-line interface |
| `examples/metro.yaml` | sample topology |
| `lab/topology.yaml` | model of the live lab, kept in sync by tests |
| `docker-compose.yml` | FRRouting lab topology |
| `lab/frr/` | per-router `frr.conf`, shared `daemons` and `vtysh.conf` |
| `lab/labctl` | lab lifecycle, failure injection and inspection |
| `lab/README.md` | manual lab walkthrough |
| `docs/ARCHITECTURE.md` | design and limitations |

## What has been verified

Verified on Linux with Docker Engine 29.8.2, Compose 2.36.1, FRR 10.7.1 and
Python 3.12, starting from a fresh clone:
- the steps in *Quick start*;
- the unit and config tests;
- the live suite, run repeatedly, including:
  - OSPF, BGP and BFD state;
  - policy filtering;
  - forwarding;
  - BFD-driven reroute on link failure;
  - recovery.

The same live suite also passes in CI on a GitHub-hosted Ubuntu runner.

Not verified yet:
- Docker Desktop on macOS or Windows;
- rootless Docker;
- Podman.

## Limitations

This is a four-router control-plane lab. It does not reproduce production
scale, hardware forwarding, failure domains, traffic engineering or change
control. Containers share the host kernel, so BFD and convergence timings
reflect a lightly loaded Linux host, not router hardware.
