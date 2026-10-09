# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-10-09

### Fixed
- The live lab did not start. Docker reserves the first address of every
  subnet as its bridge gateway, and the routers were configured with those
  same addresses (`Address already in use`).
- eBGP exchanged no routes. FRR enforces RFC 8212, so an eBGP session needs an
  explicit policy, and none was configured.
- `core-b` configured an `eth2` address on a network that did not exist.
- Interface names depended on Docker's `ethN` ordering, which is not guaranteed.
- Commands in the documentation used container names (`core-a`) that Compose
  never creates, and assumed the repository directory name.
- The `dc` router had no route back to `edge`, because OSPF was redistributed
  into BGP in one direction only.
- `simulate-failure` analysed one alphabetically chosen source node instead of
  every node.
- `simulate-failure` accepted a link that does not exist, and crashed on a
  `--link` without a comma.
- Malformed topology files produced Python tracebacks, and duplicate nodes or
  prefixes were silently dropped.
- Build artifacts (`routecraft.egg-info/`) were committed.

### Changed
- Lab redesigned:
  - `/31` point-to-point links, isolated from the host;
  - loopback-based iBGP full mesh with OSPF for infrastructure only;
  - BFD everywhere;
  - OSPF HMAC-SHA-256 and eBGP TCP-MD5 authentication;
  - prefix-list policy in both directions;
  - FRR pinned to 10.7.1;
  - configs mounted read-only.
- The CLI defaults to human-readable output. Use `--format json` for the
  previous style.
- The package moved to a `src/` layout.

### Added
- `simulate-failure --node` and repeatable `--link`.
- `resilience` command: N-1 analysis with an optional `--fail-on-loss` gate.
- `lab/labctl`: preflight checks, convergence wait, failure injection and
  annotated traceroutes.
- End-to-end tests against the live lab, including model-vs-live path
  comparison through a link failure.
- Static consistency tests between Compose, FRR configs and the lab model.
- Tooling: ruff, mypy (strict), coverage gate, pre-commit, Dependabot, and a
  CI matrix that also boots the live lab.

## [0.1.0]

- Initial topology model, CLI and FRRouting lab.
