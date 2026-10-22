# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The dev host's page for a route of the app carries the brand's title and the meta tag the UI reads
(SD-013, Branding), independent of whether the UI has been built in this checkout."""

from __future__ import annotations

import json
from html import unescape

from arras.devhost import DevHost, seed_demo
from arras.sandbox import Sandbox


def test_index_fallback_carries_title_and_brand_meta(tmp_path) -> None:
    (tmp_path / "index.html").write_text(
        "<!doctype html><html><head><title>Placeholder</title></head><body></body></html>"
    )
    host = DevHost(seed_demo(Sandbox().seed()), port=0, ui_dir=tmp_path)
    status, ctype, body = host.static("/browse/catalog")
    page = body.decode()
    assert status == 200 and ctype.startswith("text/html")
    assert "<title>Arras</title>" in page
    marker = '<meta name="arras-brand" content="'
    start = page.index(marker) + len(marker)
    content = unescape(page[start : page.index('"', start)])
    assert json.loads(content) == {"name": "Arras"}
