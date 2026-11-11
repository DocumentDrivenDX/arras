# SPDX-License-Identifier: MIT OR Apache-2.0
"""The version of each contract this build implements."""

from __future__ import annotations

CONTRACT_VERSIONS = {
    "interface": 2,
    "actions": 2,
    "backend": 6,
    "lifecycle": 3,
    "console": 2,
    "operate": 2,
    "schema": 1,
    "mcp": 2,
    "browser": 1,
}


def version_in_range(found: str, low: str, high: str) -> bool:
    """Whether the release `found` satisfies `low <= found < high` (plain `N.N.N` releases).

    A version with a pre-release or local suffix, or a non-numeric part, is outside every range."""
    try:
        parts = tuple(int(p) for p in found.split("."))
        floor = tuple(int(p) for p in low.split("."))
        ceiling = tuple(int(p) for p in high.split("."))
    except ValueError:
        return False
    return floor <= parts < ceiling
