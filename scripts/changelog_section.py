# SPDX-License-Identifier: MIT OR Apache-2.0
"""Print the CHANGELOG.md section for a version: `changelog_section.py v0.8.2` (or `0.8.2`)."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    version = sys.argv[1].removeprefix("v")
    text = Path(__file__).resolve().parent.parent.joinpath("CHANGELOG.md").read_text("utf-8")
    match = re.search(rf"^## {re.escape(version)}\b.*?(?=^## |\Z)", text, re.M | re.S)
    if match is None:
        print(f"no CHANGELOG.md section for {version}", file=sys.stderr)
        return 1
    print(match.group(0).rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
