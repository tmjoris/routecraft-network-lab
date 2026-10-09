# RouteCraft architecture

RouteCraft has two deliberately separate layers that are checked against each
other by tests.

## Deterministic analysis layer

`routecraft.io` loads a YAML topology into `Topology` and `Link` objects. It
rejects structural problems: wrong types, missing or unknown keys, and
duplicate nodes or prefixes. Each error names its position in the file.
`routecraft.analysis.validate` then reports semantic errors as a list, so every
problem is shown at once rather than one per run.

Path analysis is Dijkstra over modeled links. Equal-cost paths are broken by
comparing node sequences, so results never depend on link order in the file.
Failure analysis removes links and/or nodes. It then evaluates every
(source, prefix) pair against the unfailed baseline and labels each one
`unchanged`, `rerouted` or `unreachable`. `resilience` repeats that for every
single link and node (N-1).

This layer is useful for:

- fast checks in CI and pre-commit;
- reproducible examples;
- explaining a failure without containers;
- gating changes that add a single point of failure (`--fail-on-loss`).

It is not a routing daemon. It does not implement the BGP decision process,
OSPF areas, ECMP or policy. A BGP link is treated as one more weighted edge.

## Live protocol layer

`docker-compose.yml` runs one FRRouting container per router. Each link is its
own Docker bridge network:

- **`/31` subnet**, so exactly two routers share it, with no broadcast domain to reason about.
- **`internal: true`**: no NAT and no default route out of the lab.
- **`gateway_mode_ipv4: isolated`**: the host bridge carries no IP address, so
  the host is not a hidden third router on the link and Docker does not
  reserve one of the two `/31` addresses.
- **`interface_name: to-<peer>`**: FRR config refers to stable names instead
  of Docker's `ethN` order, which is not guaranteed.

```text
Docker network    Subnet          Protocols
edge_core_a       172.30.0.0/31   eBGP + BFD
core_a_core_b     172.30.0.2/31   OSPF (cost 10) + BFD
core_b_dc         172.30.0.4/31   OSPF (cost 10) + BFD
core_a_dc         172.30.0.6/31   OSPF (cost 30) + BFD
```

### Routing design

- **OSPF (area 0)** runs inside AS 65000 and carries only loopbacks and link
  subnets. Each link uses point-to-point network type, HMAC-SHA-256
  authentication and BFD.
- **iBGP** is a full mesh between loopbacks (`update-source lo`). It carries the
  service prefixes. The sessions stay up through the loss of any single core
  link, because OSPF re-routes the loopbacks underneath them. Three routers do
  not need route reflectors; a larger design would add them.
- **eBGP** connects edge (AS 65001) and core-a. FRR enforces RFC 8212 by
  default, which means an eBGP session with no policy exchanges nothing. Both
  sides therefore carry explicit route-maps: core-a accepts only
  `192.0.2.0/24` and announces only `10.10.0.0/16`. Edge mirrors this.
  `maximum-prefix` caps what each side will accept.
- **Origination:** each service prefix is originated with a BGP `network`
  statement, anchored by a blackhole static route so it is always in the RIB.
  This is the usual alternative to redistributing the IGP into BGP, which leaks
  infrastructure routes.

### Trade-offs

- **GTSM (`ttl-security`) is not used on eBGP.** In FRR it switches the BGP BFD
  session to multihop mode, which is wrong for a directly connected peer.
  Single-hop BFD was kept and the session is protected with TCP-MD5 instead.
- **Capabilities:** FRR daemons request `NET_ADMIN`, `NET_RAW`,
  `NET_BIND_SERVICE` and `SYS_ADMIN` at startup and exit without them. This is
  the minimum that works, and still narrower than `--privileged`.
- **Timers:** OSPF keeps the standard 10 s hello. BFD provides sub-second
  failure detection, so faster hellos would only make the lab less
  representative. The cost is that initial convergence and re-adjacency after
  a restore take roughly 20–25 s.

### Live layer and the CLI

The Python CLI never starts or touches containers. This keeps the analysis
deterministic and keeps container lifecycle, privileges and convergence
visible to the person running the experiment. `lab/labctl` is the operator
interface to the lab.

The two layers meet in two places:

- `tests/test_lab_config.py` statically checks that Compose, `frr.conf` and
  `lab/topology.yaml` describe the same topology.
- `tests/lab/test_live.py` checks that traceroute paths through the running
  lab equal the model's predicted paths, before, during and after a link
  failure.

## Not included

The lab demonstrates protocol behavior, not a complete production design. It
does not include:

- IPv6;
- route reflectors;
- graceful restart;
- ECMP policy;
- RPKI;
- telemetry export;
- automated rollback.
