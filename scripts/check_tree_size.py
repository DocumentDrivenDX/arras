# SPDX-License-Identifier: MIT OR Apache-2.0
"""Fail when the committed tree grows past its budget, so evidence and binaries cannot return.

Reads sizes from the committed tree (`git ls-tree -r -l HEAD`): no tracked file may exceed
MAX_FILE_BYTES unless it is allowlisted, and the whole tree may not exceed MAX_TREE_BYTES.
"""

from __future__ import annotations

import subprocess
import sys

MAX_FILE_BYTES = 1_000_000
MAX_TREE_BYTES = 26_000_000
ALLOWLIST = frozenset(
    {
        "tests/fixtures/umf-core-reference/current-conformance.json",
        "src/arras/conformance/read_cases.json",
    }
)


def main() -> int:
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "-l", "-z", "HEAD"], check=True, capture_output=True, text=True
    ).stdout
    total = 0
    problems: list[str] = []
    for entry in filter(None, listing.split("\0")):
        meta, path = entry.split("\t", 1)
        size_text = meta.split()[3]
        size = 0 if size_text == "-" else int(size_text)
        total += size
        if size > MAX_FILE_BYTES and path not in ALLOWLIST:
            problems.append(f"{path}: {size} bytes exceeds the {MAX_FILE_BYTES} byte file limit")
    if total > MAX_TREE_BYTES:
        problems.append(f"tree is {total} bytes, over the {MAX_TREE_BYTES} byte budget")
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f"tree size {total} bytes; {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
