# RouteCraft

RouteCraft is a deterministic routing-design and failure-analysis lab. It
loads a small multi-area topology, validates BGP/OSPF adjacency intent, finds
shortest paths, and identifies prefixes that become unreachable after a link
failure. It is designed to make routing tradeoffs inspectable in code rather
than hiding them in a vendor simulator.

## Quick start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
routecraft validate examples/metro.yaml
routecraft simulate-failure examples/metro.yaml --link core-a,core-b
pytest
```

The model includes external BGP edges, OSPF internal links, administrative
costs, loopback reachability, and a failure simulation. The validator rejects
unknown neighbors, duplicate links, invalid costs, and references to
nonexistent devices.

For real routing protocol behavior, the repository also contains an isolated
FRRouting lab. See [`lab/README.md`](lab/README.md) and run:

```bash
docker compose -f docker-compose.yml up -d
docker compose exec core-a vtysh -c 'show ip ospf neighbor'
docker compose exec edge vtysh -c 'show ip bgp summary'
```

## Why this matters

At production scale, a routing event is not just "is the protocol up?" The
engine checks whether the intended control-plane relationships produce a
usable forwarding path and explains the first broken prefix after a failure.
The same model can later be backed by NetBox, vendor APIs, or streaming
telemetry without changing the reasoning layer. The FRRouting lab now provides
that live protocol layer for local experiments.
