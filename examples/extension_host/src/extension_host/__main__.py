"""Command-line entry point for the installed downstream example."""

from __future__ import annotations

import argparse
import json

from extension_host.app import run
from extension_host.configuration import settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the neutral Arras extension-host example")
    parser.add_argument("--resource", choices=("seed.json", "graph.json"), required=True)
    args = parser.parse_args()
    resource = args.resource
    print(json.dumps(run(settings(resource=resource)), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
