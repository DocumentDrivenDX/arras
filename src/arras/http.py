# SPDX-License-Identifier: MIT OR Apache-2.0
"""What an ASGI binding shares: the request a host's `principal_for_request` looks at, and the
ASGI types (CONTRACT-006, CONTRACT-009)."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]
Response = tuple[int, list[tuple[str, str]], bytes]


@dataclass(frozen=True)
class Request:
    """What `principal_for_request` may look at to tell who is asking."""

    method: str
    path: str
    headers: Mapping[str, str]
    query: Mapping[str, str]
    scope: Mapping[str, Any]


_DEFAULT_PORTS = {"http": 80, "https": 443}
_HOST = re.compile(r"[A-Za-z0-9.-]+|\[[0-9A-Fa-f:.]+\]")  # a name, IPv4, or a bracketed IPv6


def parse_origin(value: str) -> tuple[str, str, int] | None:
    """`scheme://host[:port]` as (scheme, lower-case host, port with the scheme's default), or
    None for anything else (`null`, a path, no scheme)."""
    scheme, sep, rest = value.strip().partition("://")
    scheme = scheme.lower()
    if not sep or scheme not in _DEFAULT_PORTS or "/" in rest or "@" in rest or not rest:
        return None
    if rest.startswith("["):  # an IPv6 literal keeps its brackets: `[::1]` or `[::1]:8000`
        host, bracket, after = rest.partition("]")
        host += bracket
        if not bracket or (after and not after.startswith(":")):
            return None
        port = after[1:]
    elif rest.count(":") > 1:  # an IPv6 address without brackets is not an origin
        return None
    else:
        host, _, port = rest.partition(":")
    if not _HOST.fullmatch(host) or (port and not (port.isascii() and port.isdigit())):
        return None
    return scheme, host.lower(), int(port) if port else _DEFAULT_PORTS[scheme]


def origin_in(origin: str | None, allowed: set[tuple[str, str, int]]) -> bool:
    parsed = parse_origin(origin) if origin else None
    return parsed is not None and parsed in allowed


def same_host(origin: str, host: str | None) -> bool:
    """Whether `origin` names the host the request asked, ports and case normalized. Behind a
    proxy that rewrites `Host`, a host names its origin instead (`public_origin`)."""
    parsed, asked = (
        parse_origin(origin),
        parse_origin(f"{(parse_origin(origin) or ('http',))[0]}://{host}") if host else None,
    )
    return parsed is not None and asked is not None and parsed == asked


def post_origin_ok(
    headers: Mapping[str, str],
    repeated: set[str],
    allowed: set[tuple[str, str, int]],
    *,
    browser_or_host: bool = False,
) -> bool:
    """CONTRACT-006 and CONTRACT-009: whether a POST proves its origin. An `Origin` that is
    `public_origin` or in `allowed_origins` passes, and so does the browser's own word that the
    request is same-origin (`Sec-Fetch-Site: same-origin`); with that word an `Origin`, if sent,
    need not be listed (behind a proxy a host may not know its public origin) but must be one
    well-formed origin. A repeated `Origin` or `Sec-Fetch-Site` is refused, never read as its
    first or last value. `headers` are lower-cased names; `repeated` names those sent twice.

    `browser_or_host` is the console's added leniency: a caller that sends neither header (not a
    browser) passes, and when the host named no origins an `Origin` equal to the `Host` asked
    passes. A `Sec-Fetch-Site` of `cross-site` is refused there whatever the `Origin`."""
    if repeated & {"origin", "sec-fetch-site"}:
        return False
    origin = headers.get("origin")
    site = headers.get("sec-fetch-site", "").strip().lower()
    if browser_or_host and site == "cross-site":
        return False
    if browser_or_host and origin is None:
        return True
    if origin_in(origin, allowed):
        return True
    if site == "same-origin":
        return origin is None or parse_origin(origin) is not None
    if browser_or_host and not allowed and origin is not None:
        return same_host(origin, headers.get("host"))
    return False
