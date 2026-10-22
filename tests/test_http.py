# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""Origins as the bindings compare them (CONTRACT-006, CONTRACT-009): scheme, host and port, with
the default port and case normalized, and an IPv6 literal kept in its brackets."""

from __future__ import annotations

import pytest

from arras.http import origin_in, parse_origin, post_origin_ok, same_host


@pytest.mark.parametrize(
    "text,parsed",
    [
        ("http://[::1]:8000", ("http", "[::1]", 8000)),
        ("http://[::1]", ("http", "[::1]", 80)),
        ("https://[::1]", ("https", "[::1]", 443)),
        ("http://[2001:DB8::1]:9", ("http", "[2001:db8::1]", 9)),
        ("http://127.0.0.1:8000", ("http", "127.0.0.1", 8000)),
        ("HTTPS://App.Example", ("https", "app.example", 443)),
        ("http://localhost:", ("http", "localhost", 80)),
    ],
)
def test_an_origin_is_scheme_host_and_port(text: str, parsed: tuple) -> None:
    assert parse_origin(text) == parsed


@pytest.mark.parametrize(
    "text",
    [
        "null",
        "",
        "app.example",
        "ftp://app.example",
        "http://app.example/path",
        "http://user@app.example",
        "http://::1",  # IPv6 without brackets
        "http://[::1",
        "http://[::1]x",
        "http://[::1]:x",
        "http://app.example:http",
        "http://app.example:²",  # a superscript digit is not a port
        "http://a.example, http://b.example",  # two origins folded into one header
        "http://a b",
        "http://",
    ],
)
def test_anything_else_is_not_an_origin(text: str) -> None:
    assert parse_origin(text) is None


def test_default_ports_and_brackets_compare_equal() -> None:
    assert parse_origin("http://[::1]") == parse_origin("http://[::1]:80")
    assert parse_origin("http://[::1]:8000") != parse_origin("http://[::1]:8001")
    assert parse_origin("http://[::1]:8000") != parse_origin("http://[::2]:8000")
    allowed = {parse_origin("http://[::1]:8000")}
    assert origin_in("http://[::1]:8000", allowed)  # type: ignore[arg-type]
    assert not origin_in("http://[::1]", allowed)  # type: ignore[arg-type]
    assert same_host("http://[::1]:8000", "[::1]:8000")
    assert same_host("http://[::1]", "[::1]:80") and same_host("http://[::1]:80", "[::1]")
    assert not same_host("http://[::1]:8000", "[::1]:8001")
    assert not same_host("http://[::1]:8000", "127.0.0.1:8000")


LISTED = {("https", "app.example", 443)}


@pytest.mark.parametrize("lenient", [False, True])
def test_post_origin_ok_trusts_the_browsers_same_origin_word(lenient: bool) -> None:
    h = {"origin": "https://other.example", "sec-fetch-site": "same-origin"}
    assert post_origin_ok(h, set(), set(), browser_or_host=lenient)
    assert post_origin_ok({"sec-fetch-site": "same-origin"}, set(), set(), browser_or_host=lenient)
    for bad in ("null", "https://x.example/p", "https://a.example, https://b.example"):
        assert not post_origin_ok({**h, "origin": bad}, set(), set(), browser_or_host=lenient)
    for site in ("same-site", "cross-site", "none", ""):
        assert not post_origin_ok(
            {**h, "sec-fetch-site": site}, set(), set(), browser_or_host=lenient
        )


@pytest.mark.parametrize("lenient", [False, True])
def test_post_origin_ok_refuses_a_repeated_origin_or_fetch_site(lenient: bool) -> None:
    h = {"origin": "https://app.example", "sec-fetch-site": "same-origin"}
    for name in ("origin", "sec-fetch-site"):
        assert not post_origin_ok(h, {name}, LISTED, browser_or_host=lenient)


def test_post_origin_ok_strict_wants_proof_and_lenient_passes_a_non_browser() -> None:
    assert not post_origin_ok({}, set(), set())
    assert post_origin_ok({}, set(), set(), browser_or_host=True)
    assert post_origin_ok({"origin": "https://app.example"}, set(), LISTED)
