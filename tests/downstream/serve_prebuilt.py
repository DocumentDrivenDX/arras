# SPDX-License-Identifier: MIT OR Apache-2.0
"""Local-only ASGI fixture for the prebuilt page + inert downstream theme route."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from arras import ui
from arras.sandbox import Sandbox


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--static", type=Path, required=True)
    parser.add_argument("--theme", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    box = Sandbox().seed()
    app = ui.create_app(
        box.arras,
        principal_for_request=lambda _request: box.principal("alice"),
        authorize_operator=lambda _principal: True,
        authorize_schema=lambda _principal, _module: True,
        base_path="",
        public_origin=f"http://127.0.0.1:{args.port}",
        static_dir=args.static,
        theme_manifest=args.theme,
        brand=ui.Brand(name="Neutral Prebuilt", logo="theme"),
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
