# SPDX-License-Identifier: MIT OR Apache-2.0
"""Rewrite ui/openapi.json from arras.operate (the UI's client is generated from it):

uv run python tests/regen_openapi.py
"""

import json
from pathlib import Path

from arras.operate import openapi_document

path = Path(__file__).resolve().parent.parent / "ui" / "openapi.json"
path.write_text(json.dumps(openapi_document(), indent=2) + "\n")
