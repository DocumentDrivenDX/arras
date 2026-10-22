# SPDX-License-Identifier: MIT OR Apache-2.0
"""Validated brand values shared by embedding hosts without importing a UI runtime."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:\S")
_IMAGE_URL = re.compile(r"^https://[^\s;,'\"]+$")
BRAND_CAPS = {"name": 80, "title": 120, "wordmark": 2048, "tagline": 200}
_PAGE_CSP = (
    "default-src 'none'; base-uri 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "frame-src 'self' about:; connect-src 'self'; frame-ancestors 'self'"
)


def _length(text: str) -> int:
    """UTF-16 code units of the trimmed text, which is how the browser counts."""
    return len(text.strip().encode("utf-16-le")) // 2


@dataclass(frozen=True)
class Brand:
    """What the console is called. `title` is the page title (default `name`); `wordmark` is text or an
    `https://` URL; `tagline` is a line under the name;
    `logo` is `"theme"` to show the theme's mark before the name."""

    name: str = "Arras"
    title: str | None = None
    wordmark: str | None = None
    tagline: str | None = None
    logo: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("a brand needs a name")
        for field_name, cap in BRAND_CAPS.items():
            value = getattr(self, field_name)
            if value is not None and _length(value) > cap:
                raise ValueError(f"a brand's {field_name} is at most {cap} characters")
        w = self.wordmark
        if w is not None and _SCHEME.match(w) and not w.startswith("https://"):
            raise ValueError("a wordmark is text or an https:// URL")
        if (
            w is not None
            and w.startswith("https://")
            and not (_IMAGE_URL.match(w) and self.image_origin)
        ):
            raise ValueError("a wordmark is text or an https:// URL")
        if self.logo is not None and self.logo != "theme":
            raise ValueError('a logo is "theme"')

    @property
    def image_origin(self) -> str | None:
        """The origin of an `https://` image wordmark, else None (text, or no wordmark)."""
        w = self.wordmark
        if w is None or not w.startswith("https://"):
            return None
        try:
            parts = urlsplit(w)
            host = parts.hostname
            port = parts.port
        except ValueError:
            return None
        if not host or host == "*" or parts.username is not None or parts.password is not None:
            return None
        if parts.netloc.endswith(":"):  # an empty port
            return None
        shown = f"[{host}]" if ":" in host else host
        return f"https://{shown}" if port is None else f"https://{shown}:{port}"

    def csp(self) -> str:
        """The default page policy with this brand image origin admitted to `img-src`."""
        origin = self.image_origin
        return (
            _PAGE_CSP
            if origin is None
            else _PAGE_CSP.replace("img-src 'self'", f"img-src 'self' {origin}")
        )

    def meta(self) -> str:
        """The brand as JSON, the fields that are set."""
        fields = {
            "name": self.name,
            "title": self.title,
            "wordmark": self.wordmark,
            "tagline": self.tagline,
            "logo": self.logo,
        }
        return json.dumps({k: v for k, v in fields.items() if v is not None})
