# SPDX-License-Identifier: MIT OR Apache-2.0
"""Build the inert synthetic theme bundle used by downstream host qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
THEME_PACKAGE = HERE.parent / "theme-package"


def build(output: Path, ui_version: str, package_dir: Path = THEME_PACKAGE) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict[str, str | int]] = {}
    for name, mime in (("theme.css", "text/css"), ("favicon.svg", "image/svg+xml")):
        source_name = "theme.css" if name == "theme.css" else "favicon.svg"
        source = package_dir / "src" / source_name
        target_name = name
        target = output / target_name
        shutil.copyfile(source, target)
        body = target.read_bytes()
        files[target_name] = {
            "sha256": hashlib.sha256(body).hexdigest(),
            "size": len(body),
            "mime": mime,
        }
    package = json.loads((package_dir / "package.json").read_text(encoding="utf-8"))
    manifest = {
        "format": "arras.ui.assets",
        "version": 1,
        "kind": "theme",
        "package": {"name": package["name"], "version": package["version"]},
        "contracts": {"console": 2, "operate": 2, "schema": 1, "browser": 1},
        "ui_versions": [ui_version],
        "entry": {"stylesheet": "theme.css", "favicon": "favicon.svg"},
        "files": files,
    }
    result = output / "theme-manifest.json"
    result.write_text(f"{json.dumps(manifest, indent=2)}\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--ui-version", required=True)
    parser.add_argument("--package-dir", type=Path, default=THEME_PACKAGE)
    args = parser.parse_args()
    print(build(args.output, args.ui_version, args.package_dir))
