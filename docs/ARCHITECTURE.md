# RouteCraft architecture

RouteCraft has two deliberately separate layers.

## Deterministic analysis layer

The Python package loads a YAML topology into `Topology` and `Link` objects.
Validation checks structural errors before analysis begins. The path analyzer
then uses weighted graph search over modeled links.

This layer is useful for:

- fast checks in CI;
- reproducible examples;
- explaining a failure without requiring containers;
- testing topology data and policy logic.

It is not a routing daemon. It does not implement the full BGP or OSPF
protocol state machines.

## Live protocol layer

The Compose lab runs FRRouting processes. Docker creates isolated L2 networks;
FRR configures routing processes on the container interfaces.

```text
Docker network         FRR process
172.30.1.0/30   --->   eBGP edge/core-a
172.30.2.0/30   --->   OSPF core-a/core-b
172.30.3.0/30   --->   OSPF core-b/dc
172.30.4.0/30   --->   OSPF core-a/dc
```

The live layer is intentionally not invoked by the Python CLI. This keeps
analysis deterministic and keeps container lifecycle, privileges, and
protocol convergence visible to the person running the experiment.

## Important configuration assumptions

The FRR files refer to Linux interface names assigned by Docker. The Compose
network declaration order is intended to produce the expected `ethN` mapping,
but the mapping must be inspected with `ip -br addr` on the running
containers. This is an operational check, not a guarantee encoded by Python.

The current live configuration also demonstrates protocol concepts rather than
a complete production design. It does not include authentication, route
maps, prefix filters, BFD, graceful restart, ECMP policy, telemetry export,
or automated rollback.

