# SPDX-License-Identifier: MIT OR Apache-2.0
"""`python -m arras.ui npm-package [--copy DIR]`: where the wheel's npm tarball is, or a copy of it."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from arras.ui import npm_package


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m arras.ui")
    sub = parser.add_subparsers(dest="command", required=True)
    pkg = sub.add_parser(
        "npm-package", help="print the path of the @documentdrivendx/arras-ui npm tarball"
    )
    pkg.add_argument("--copy", metavar="DIR", help="copy it into DIR and print the copy's path")
    args = parser.parse_args(argv)
    path = npm_package()
    if args.copy:
        target = Path(args.copy)
        target.mkdir(parents=True, exist_ok=True)
        path = Path(shutil.copy2(path, target / path.name))
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
