# SPDX-License-Identifier: MIT OR Apache-2.0
"""Brand an HTML page while leaving unrelated source bytes untouched."""

from __future__ import annotations

import html
import json
from html.parser import HTMLParser

from arras._legacy_aliases import validate_alias_tuple
from arras.branding import Brand


class _BrandTokens(HTMLParser):
    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.line_starts = [0]
        self.line_starts.extend(index + 1 for index, char in enumerate(source) if char == "\n")
        self.brand_ranges: list[tuple[int, int]] = []
        self.graph_alias_ranges: list[tuple[int, int]] = []
        self.head_end: int | None = None
        self.title_start: int | None = None
        self.title_content_start: int | None = None
        self.title_content_end: int | None = None
        self.title_end: int | None = None
        self.rcdata_tag: str | None = None
        self.feed(source)
        self.close()

    def token_offset(self) -> int:
        line, column = self.getpos()
        return self.line_starts[line - 1] + column

    def _has_meta_name(self, attrs: list[tuple[str, str | None]], wanted: str) -> bool:
        seen: set[str] = set()
        for name, value in attrs:
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            if key == "name":
                return (value or "").casefold() == wanted
        return False

    def _tag_end(self, start: int) -> int:
        end = self.source.find(">", start)
        if end < 0:
            raise ValueError("HTMLParser returned an unterminated tag")
        return end + 1

    def _start_tag_text(self) -> str:
        raw = self.get_starttag_text()
        if raw is None:
            raise RuntimeError("HTMLParser did not retain the current start tag")
        return raw

    def _start(self, tag: str, attrs: list[tuple[str, str | None]], raw: str) -> None:
        if self.rcdata_tag is not None:
            return
        start = self.token_offset()
        lower = tag.lower()
        if lower == "meta":
            if self._has_meta_name(attrs, "arras-brand"):
                self.brand_ranges.append((start, start + len(raw)))
            if self._has_meta_name(attrs, "arras-graph-format-aliases"):
                self.graph_alias_ranges.append((start, start + len(raw)))
        if lower == "title" and self.title_start is None:
            self.title_start = start
            self.title_content_start = start + len(raw)
        if lower in {
            "script",
            "style",
            "textarea",
            "title",
            "xmp",
            "iframe",
            "noembed",
            "noframes",
            "plaintext",
        }:
            self.rcdata_tag = lower

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, self._start_tag_text())

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, self._start_tag_text())

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        start = self.token_offset()
        end = self._tag_end(start)
        if self.rcdata_tag is not None:
            if lower == self.rcdata_tag:
                if lower == "title" and self.title_content_end is None:
                    self.title_content_end = start
                    self.title_end = end
                self.rcdata_tag = None
            return
        if lower == "head" and self.head_end is None:
            self.head_end = start
        elif lower == "title" and self.title_content_end is None:
            self.title_content_end = start
            self.title_end = end


def branded(page: bytes, brand: Brand, *, graph_format_aliases: tuple[str, ...] = ()) -> bytes:
    """Brand head/title-anchored pages, preserving fragment-only input unchanged."""
    aliases = validate_alias_tuple(graph_format_aliases, "graph_format_aliases", "arras.graph")
    source = page.decode()
    tokens = _BrandTokens(source)
    if tokens.head_end is None and tokens.title_end is None:
        return page
    title = html.escape(brand.title or brand.name, quote=True)
    meta = f'<meta name="arras-brand" content="{html.escape(brand.meta(), quote=True)}">'
    graph_aliases = html.escape(json.dumps(aliases), quote=True)
    alias_meta = f'<meta name="arras-graph-format-aliases" content="{graph_aliases}">'

    edits: list[tuple[int, int, str]] = [
        (start, end, "") for start, end in (*tokens.brand_ranges, *tokens.graph_alias_ranges)
    ]
    if tokens.title_content_start is not None and tokens.title_content_end is not None:
        edits.append((tokens.title_content_start, tokens.title_content_end, title))

    if tokens.head_end is not None:
        insertion = tokens.head_end
    elif tokens.title_end is not None:
        insertion = tokens.title_end
    else:
        insertion = len(source)
    edits.append((insertion, insertion, meta + alias_meta))

    for start, end, replacement in sorted(edits, reverse=True):
        source = source[:start] + replacement + source[end:]
    return source.encode()
