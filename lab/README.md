# RouteCraft live FRRouting lab: manual walkthrough

`lab/labctl` automates everything below. This page shows the raw commands, so
you can see what each step does and adapt it. Run them from the repository root.

## What the lab demonstrates

- eBGP between `edge` (AS 65001) and `core-a` (AS 65000), with policy in both
  directions;
- OSPF inside AS 65000 carrying loopbacks, plus iBGP between loopbacks carrying
  service prefixes;
- BFD-driven sub-second failure detection;
- traffic rerouting over the backup link when the core link fails, and
  returning when it is restored.

The lab is small, so you can inspect every interface, neighbor and route. It
is not a traffic generator, a hardware emulator or a production configuration.

## Start

```bash
lab/labctl check            # prerequisites; see "Troubleshooting" if this fails
docker compose up -d --wait # containers healthy = daemons answering
lab/labctl wait             # adjacencies up and forwarding tables stable (~20 s)
```

The first run downloads `quay.io/frrouting/frr:10.7.1`, about 190 MB.

## Inspect the control plane

```bash
docker compose exec core-a vtysh -c 'show ip ospf neighbor'
docker compose exec core-a vtysh -c 'show bgp ipv4 unicast summary'
docker compose exec core-a vtysh -c 'show bfd peers brief'
docker compose exec edge   vtysh -c 'show ip route bgp'
```

What you should see:

| Router | OSPF neighbors (Full) | BGP sessions (Established) |
|---|---|---|
| edge | none | 172.30.0.1 (core-a) |
| core-a | 10.255.0.3, 10.255.0.4 | 172.30.0.0 (edge), 10.255.0.3, 10.255.0.4 |
| core-b | 10.255.0.2, 10.255.0.4 | 10.255.0.2, 10.255.0.4 |
| dc | 10.255.0.2, 10.255.0.3 | 10.255.0.2, 10.255.0.3 |

`edge` should learn exactly one route, `10.10.0.0/16`. It should learn none of
the `10.255.0.x` loopbacks, because the export policy keeps infrastructure
private.

## Inspect interfaces

```bash
docker compose exec core-a ip -br addr
```

```text
lo               UNKNOWN        127.0.0.1/8 10.255.0.2/32 ...
to-core-b@if29   UP             172.30.0.2/31
to-dc@if32       UP             172.30.0.6/31
to-edge@if35     UP             172.30.0.1/31
```

Interface names are set by `interface_name` in `docker-compose.yml`, so they
are the same on every host.

## Data plane

```bash
docker compose exec edge ping -c 3 -I 192.0.2.1 10.10.0.1
docker compose exec edge traceroute -n -s 192.0.2.1 10.10.0.1
```

Always source traffic from `192.0.2.1`. The link address `172.30.0.0` is not
announced, so replies to it have no route back. That is intentional.

## Failure experiment

Take the core-a ↔ core-b link down on both ends, like a cut cable:

```bash
docker compose exec core-a ip link set to-core-b down
docker compose exec core-b ip link set to-core-a down
```

Then observe:

```bash
docker compose exec dc vtysh -c 'show ip route 192.0.2.0/24'   # next hop now via to-core-a
docker compose exec edge traceroute -n -s 192.0.2.1 10.10.0.1  # core-a -> dc directly
docker compose exec core-a vtysh -c 'show bgp ipv4 unicast summary'  # iBGP stayed up
```

The iBGP sessions do not flap, because they run between loopbacks and OSPF
re-routes the loopbacks over the backup link.

To take down only one end and watch BFD detect the failure on the other end,
run just the first command, then run `show ip ospf neighbor` on core-b. The
adjacency to core-a disappears within about a second. Without BFD it would
take the 40 s OSPF dead interval.

Restore:

```bash
docker compose exec core-a ip link set to-core-b up
docker compose exec core-b ip link set to-core-a up
```

OSPF re-forms the adjacency on the next hello, within about 10 s, and traffic
returns to core-b.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Pool overlaps with other one on this address space` | another Docker network uses `172.30.0.0/24`. `lab/labctl check` names it. |
| Compose rejects `interface_name` | Compose is older than 2.36. Upgrade the `docker-compose-plugin` package. `lab/labctl check` reports the version. |
| `permission denied ... docker.sock` | `sudo usermod -aG docker "$USER"`, then log out and back in |
| container `unhealthy` | `docker compose logs <router>`; an FRR config error is printed at startup |
| `Network unreachable`, or an unexpected path, right after start | routing has not converged yet. Run `lab/labctl wait`. |

## Cleanup

```bash
docker compose down
```
