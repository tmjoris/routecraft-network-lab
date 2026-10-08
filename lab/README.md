# Live FRRouting lab

This topology runs real FRRouting daemons in four containers:

```text
edge (eBGP) -- core-a (OSPF) -- core-b (OSPF) -- dc
                    \------------- OSPF --------/
```

Start it with:

```bash
docker compose up -d
docker compose exec core-a vtysh -c 'show ip ospf neighbor'
docker compose exec edge vtysh -c 'show ip bgp summary'
docker compose exec dc vtysh -c 'show ip route ospf'
```

To simulate a real link failure, stop the core-a/core-b network:

```bash
docker network disconnect routecraft_core_a_core_b core-a
docker compose exec core-a vtysh -c 'show ip route'
docker compose exec dc vtysh -c 'show ip route 10.10.0.1/32'
```

Restore it with `docker compose up -d`. The lab is intentionally isolated to
Docker networks and does not alter the host routing table.
