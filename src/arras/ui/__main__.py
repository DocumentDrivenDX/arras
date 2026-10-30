# SPDX-License-Identifier: MIT OR Apache-2.0
"""`python -m arras.ui`: `npm-package [--copy DIR]` names the wheel's npm tarball or copies it, and
`theme-manifest --css FILE --out DIR` builds a runtime theme bundle for `create_app`."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from arras.ui import npm_package
from arras.ui.assets import build_theme_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m arras.ui")
    sub = parser.add_subparsers(dest="command", required=True)
    pkg = sub.add_parser(
        "npm-package", help="print the path of the @documentdrivendx/arras-ui npm tarball"
    )
    pkg.add_argument("--copy", metavar="DIR", help="copy it into DIR and print the copy's path")
    theme = sub.add_parser(
        "theme-manifest",
        help="copy a stylesheet, favicon and fonts into a directory and write their theme manifest",
    )
    theme.add_argument("--css", required=True, type=Path, help="the theme stylesheet")
    theme.add_argument("--out", required=True, type=Path, help="the bundle directory")
    theme.add_argument("--favicon", type=Path, help="an svg, png, jpeg, webp or ico image")
    theme.add_argument(
        "--font", action="append", default=[], type=Path, help="a woff or woff2 font"
    )
    theme.add_argument("--package-name", default="theme", help="the theme's own name")
    theme.add_argument("--package-version", default="1", help="the theme's own version")
    theme.add_argument(
        "--ui-version",
        action="append",
        help="a page version the theme supports (repeatable; default: the installed Arras)",
    )
    args = parser.parse_args(argv)
    if args.command == "theme-manifest":
        try:
            print(
                build_theme_manifest(
                    args.out,
                    stylesheet=args.css,
                    favicon=args.favicon,
                    fonts=args.font,
                    package_name=args.package_name,
                    package_version=args.package_version,
                    ui_versions=args.ui_version,
                )
            )
        except ValueError as error:
            parser.exit(2, f"{parser.prog}: {error}\n")
        return 0
    path = npm_package()
    if args.copy:
        target = Path(args.copy)
        target.mkdir(parents=True, exist_ok=True)
        path = Path(shutil.copy2(path, target / path.name))
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
