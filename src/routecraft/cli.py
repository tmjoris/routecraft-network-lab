"""Command-line interface.

Exit codes: 0 success, 1 invalid topology or (with --fail-on-loss) lost
reachability, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from . import __version__
from .analysis import analyze, resilience, validate
from .io import TopologyFormatError, load
from .model import Link, Topology


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="routecraft", description="Validate and analyze routing topologies"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("topology", help="path to a topology YAML file")
    common.add_argument(
        "--format", choices=("text", "json"), default="text", help="output format (default: text)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", parents=[common], help="check a topology for errors")
    failure = sub.add_parser(
        "simulate-failure", parents=[common], help="remove links/nodes and recompute reachability"
    )
    failure.add_argument(
        "--link", action="append", default=[], metavar="A,B", help="failed link (repeatable)"
    )
    failure.add_argument(
        "--node", action="append", default=[], metavar="NAME", help="failed node (repeatable)"
    )
    res = sub.add_parser(
        "resilience", parents=[common], help="fail every link and node in turn (N-1 analysis)"
    )
    res.add_argument(
        "--fail-on-loss",
        action="store_true",
        help="exit 1 if any single failure loses reachability",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        topology = load(args.topology)
    except TopologyFormatError as exc:
        print(f"routecraft: error: {exc}", file=sys.stderr)
        return 1

    errors = validate(topology)
    if errors:
        _emit(args.format, {"valid": False, "errors": errors}, _text_errors)
        return 1

    if args.command == "validate":
        report = {"valid": True, "nodes": len(topology.nodes), "links": len(topology.links)}
        _emit(args.format, report, _text_valid)
        return 0

    if args.command == "simulate-failure":
        if not args.link and not args.node:
            parser.error("simulate-failure needs at least one --link or --node")
        links = [_resolve_link(parser, topology, spec) for spec in args.link]
        for node in args.node:
            if node not in topology.nodes:
                parser.error(f"--node {node!r} is not in the topology")
        _emit(args.format, analyze(topology, links, args.node), _text_analysis)
        return 0

    report = resilience(topology)
    _emit(args.format, report, _text_resilience)
    return 1 if args.fail_on_loss and not report["resilient"] else 0


def _resolve_link(parser: argparse.ArgumentParser, topology: Topology, spec: str) -> Link:
    parts = [part.strip() for part in spec.split(",")]
    if len(parts) != 2 or not all(parts):
        parser.error(f"--link expects NODE_A,NODE_B, got {spec!r}")
    link = topology.find_link(parts[0], parts[1])
    if link is None:
        parser.error(f"--link {spec!r} does not match any link in the topology")
    return link


def _emit(fmt: str, report: dict[str, Any], render: Any) -> None:
    if fmt == "json":
        print(json.dumps(report, indent=2))
    else:
        print(render(report))


def _text_errors(report: dict[str, Any]) -> str:
    return "\n".join(["INVALID topology:", *(f"  - {error}" for error in report["errors"])])


def _text_valid(report: dict[str, Any]) -> str:
    return f"OK: {report['nodes']} nodes, {report['links']} links"


def _text_analysis(report: dict[str, Any]) -> str:
    failed = report["failed"]["links"] + report["failed"]["nodes"]
    lines = [f"Failure: {', '.join(failed)}"]
    for prefix, entry in report["prefixes"].items():
        note = " (origin failed)" if entry["origin_failed"] else ""
        lines.append(f"{prefix} from origin {entry['origin']}{note}")
        for source, outcome in entry["sources"].items():
            if outcome["path"]:
                detail = f"{' -> '.join(outcome['path'])} (cost {outcome['cost']})"
            else:
                detail = "no path"
            lines.append(f"  {source:<12} {outcome['status']:<11} {detail}")
    summary = report["summary"]
    lines.append(
        f"Summary: {summary['unchanged']} unchanged, {summary['rerouted']} rerouted, "
        f"{summary['unreachable']} unreachable"
    )
    return "\n".join(lines)


def _text_resilience(report: dict[str, Any]) -> str:
    lines = []
    for scenario in report["scenarios"]:
        problems = [
            f"{p['source']} cannot reach {p['prefix']}" for p in scenario["lost_reachability"]
        ]
        problems += [f"{prefix} has no origin" for prefix in scenario["lost_origins"]]
        status = "LOSS" if problems else "ok"
        lines.append(f"{status:<5} {scenario['failure']}")
        lines.extend(f"        {problem}" for problem in problems)
    if report["resilient"]:
        lines.append("Resilient: no single failure loses reachability")
    else:
        lines.append(
            f"Not resilient: {len(report['single_points_of_failure'])} single point(s) of failure"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
