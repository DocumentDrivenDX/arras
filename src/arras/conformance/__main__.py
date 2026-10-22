# SPDX-License-Identifier: MIT OR Apache-2.0
"""Run the packaged Arras corpus on one of its built-in memory backend shapes."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from typing import Any

from arras.conformance import run_corpus
from arras.conformance.fakes import MemoryReplicaHarness, MemoryStoreHarness

_FACTORIES = {
    "memory-store": MemoryStoreHarness,
    "memory-replica": MemoryReplicaHarness,
}


def _factory(kind: str) -> Any:
    if kind in _FACTORIES:
        return _FACTORIES[kind]
    if kind == "truss":
        from arras.conformance.truss import TrussHarness

        return TrussHarness
    raise ValueError("backend must be memory-store, memory-replica or truss")


def run(kind: str) -> tuple[dict[str, Any], int]:
    """Return the fixed-corpus report and the command's success/failure exit code."""
    report = run_corpus(_factory(kind))
    counts = Counter(result.status for result in report.results)
    payload: dict[str, Any] = {
        "backend": kind,
        "roles": list(report.roles),
        "corpus_version": report.corpus_version,
        "newer_corpus": report.newer_corpus,
        "counts": {
            status: counts.get(status, 0)
            for status in ("passed", "failed", "harness_error", "limit", "host_specific")
        },
        "results": [
            {"case": result.case, "status": result.status, "message": result.message}
            for result in report.results
        ],
        "skipped": list(report.skipped),
    }
    success = report.passed and bool(report.results) and not report.newer_corpus
    return payload, 0 if success else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Arras's packaged backend conformance corpus")
    parser.add_argument("--backend", choices=(*_FACTORIES, "truss"), required=True)
    args = parser.parse_args(argv)
    payload, status = run(args.backend)
    print(json.dumps(payload, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
