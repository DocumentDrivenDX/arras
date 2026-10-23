# SPDX-License-Identifier: MIT OR Apache-2.0
"""Strict JSON and cursor primitives for the selected native feed carrier."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from _lakebase_managed_common import Blocked as _Blocked

_MAX_FEED_PAGES = 64
_MAX_PAGE_BYTES = 8 * 1024 * 1024
_MAX_TOTAL_FEED_BYTES = 32 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_XID = re.compile(r"(?:0|[1-9][0-9]{0,19})\Z")
_FEED_FIELDS = {
    "interfaceVersion",
    "prior",
    "next",
    "writerXid",
    "configuration",
    "catalogPrerequisites",
    "revisions",
    "changes",
    "sources",
    "reservations",
}
_CURSOR_FIELDS = {
    "profile",
    "installationId",
    "sourceEpoch",
    "consumerId",
    "registrationId",
    "nextXid",
}
_CANONICALIZATION_PROFILE = {
    "identity": "truss-pg18-jsonb-text",
    "version": "0.1",
    "sha256": "e5eec0aa3dfd5195250bb2e781626c6229f645d71a5c21095ee3d10008aadc97",
}
_TRUSS_RELEASE_ID = "truss-catalog-runtime/0.74-candidate"
_TRUSS_RELEASE_SHA256 = "288801f7177338328441b5d3ce9328af31740ebf513f04ea45e30ae316a9f3a4"
_TRUSS_LAYOUT_PROFILE = {
    "identity": "truss-layout",
    "sha256": "cf417e0af5d37dd61fa5f39f818d2e7282a29e6c6c6ab7fc0b26dcdde99e7dec",
    "version": "1.0",
}


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _json_bytes(raw: bytes, code: str) -> Any:
    if type(raw) is not bytes or not raw or len(raw) > _MAX_PAGE_BYTES:
        raise _Blocked(code)
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_object,
            parse_float=lambda _value: (_ for _ in ()).throw(ValueError("fractional JSON number")),
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non-JSON constant")),
        )
    except (UnicodeError, ValueError, json.JSONDecodeError):
        raise _Blocked(code) from None


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise _Blocked("feed_semantic_encoding_invalid") from None


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _checked_cursor(raw: bytes) -> dict[str, Any]:
    cursor = _json_bytes(raw, "feed_cursor_invalid")
    if type(cursor) is not dict or set(cursor) != _CURSOR_FIELDS:
        raise _Blocked("feed_cursor_profile_unknown")
    if (
        cursor["profile"] != "truss-caller-asserted-feed/0.1"
        or any(
            type(cursor[key]) is not str or not cursor[key]
            for key in ("installationId", "sourceEpoch", "consumerId", "registrationId")
        )
        or type(cursor["nextXid"]) is not str
        or _XID.fullmatch(cursor["nextXid"]) is None
    ):
        raise _Blocked("feed_cursor_profile_unknown")
    return cursor


def _bytea(value: Any, code: str) -> bytes:
    if type(value) is not str or not value.startswith("\\x"):
        raise _Blocked(code)
    try:
        return bytes.fromhex(value[2:])
    except ValueError:
        raise _Blocked(code) from None


def _validate_configuration(value: Any) -> None:
    if type(value) is not dict or set(value) != {
        "releaseId",
        "releaseSha256",
        "layoutProfile",
        "preparationConfiguration",
        "settings",
    }:
        raise _Blocked("feed_configuration_profile_unknown")
    if (
        value["releaseId"] != _TRUSS_RELEASE_ID
        or value["releaseSha256"] != _TRUSS_RELEASE_SHA256
        or value["layoutProfile"] != _TRUSS_LAYOUT_PROFILE
        or type(value["preparationConfiguration"]) is not dict
        or type(value["settings"]) is not dict
    ):
        raise _Blocked("feed_configuration_profile_unknown")
