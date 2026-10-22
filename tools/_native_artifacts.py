"""Validate pinned package URLs and the selected local find-links index."""

from __future__ import annotations

import hashlib
import html.parser
import re
import urllib.parse
from pathlib import Path
from typing import Any

_SHA = re.compile(r"^[0-9a-f]{64}$")


class ArtifactError(ValueError):
    """A selected artifact reference is malformed or unverified."""


def https_url(value: str) -> urllib.parse.SplitResult:
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ArtifactError("native wheel URLs must be HTTPS without userinfo, query, or fragment")
    return parsed


class _Links(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self.hrefs.extend(value for key, value in attrs if key.lower() == "href" and value)


def verify_find_links(path: Path, expected_sha256: str, wheels: list[dict[str, Any]]) -> bytes:
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ArtifactError(f"cannot read verified find-links page: {exc}") from exc
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ArtifactError("find-links page SHA-256 differs from cohort")
    parser = _Links()
    try:
        parser.feed(content.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ArtifactError(f"find-links page is not valid UTF-8 HTML: {exc}") from exc
    anchors: set[tuple[str, str]] = set()
    for href in parser.hrefs:
        parsed = urllib.parse.urlsplit(href)
        if parsed.scheme != "https" or not parsed.hostname or parsed.query:
            continue
        fragment = urllib.parse.parse_qs(parsed.fragment, strict_parsing=False)
        digests = fragment.get("sha256", [])
        if len(digests) == 1 and _SHA.fullmatch(digests[0]):
            anchors.add((urllib.parse.urlunsplit(parsed._replace(fragment="")), digests[0]))
    for wheel in wheels:
        if (wheel["url"], wheel["sha256"]) not in anchors:
            raise ArtifactError(
                f"find-links page does not contain the selected URL and digest for {wheel['filename']}"
            )
    return content
