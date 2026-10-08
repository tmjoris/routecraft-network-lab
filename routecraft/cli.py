import argparse
import json

from .analysis import analyze, validate
from .io import load


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and analyze routing topologies")
    sub = parser.add_subparsers(dest="command", required=True)
    validate_cmd = sub.add_parser("validate")
    validate_cmd.add_argument("topology")
    failure_cmd = sub.add_parser("simulate-failure")
    failure_cmd.add_argument("topology")
    failure_cmd.add_argument("--link", required=True, help="failed link as node-a,node-b")
    args = parser.parse_args()
    topology = load(args.topology)
    errors = validate(topology)
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, indent=2))
        raise SystemExit(1)
    if args.command == "validate":
        print(json.dumps({"valid": True, "nodes": len(topology.nodes),
                          "links": len(topology.links)}, indent=2))
    else:
        left, right = (part.strip() for part in args.link.split(",", maxsplit=1))
        print(json.dumps(analyze(topology, frozenset((left, right))), indent=2))

