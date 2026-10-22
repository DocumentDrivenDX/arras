# SPDX-License-Identifier: MIT OR Apache-2.0
"""Plain data for JSON from the interface's types; shared by the bindings."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from arras.errors import ArrasError, PolicyRefused
from arras.types import Revision


def jsonable(v: Any, *, tag: bool = True) -> Any:
    """Plain data for JSON: dataclasses, mappings, sequences, decimals and timestamps."""
    if isinstance(v, Revision):  # on the wire it is its object keyed by backend name
        return dict(v.by_backend)
    if is_dataclass(v) and not isinstance(v, type):
        body = {f.name: jsonable(getattr(v, f.name), tag=tag) for f in fields(v)}
        return {"_type": type(v).__name__, **body} if tag else body
    if isinstance(v, Mapping):
        return {str(k): jsonable(x, tag=tag) for k, x in v.items()}  # type: ignore[reportUnknownVariableType]
    if isinstance(v, list | tuple | set | frozenset):
        return [jsonable(x, tag=tag) for x in v]  # type: ignore[reportUnknownVariableType]
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, bytes):
        return base64.b64encode(v).decode()
    if isinstance(v, ArrasError):
        return error_body(v)
    return v


def error_body(e: ArrasError) -> dict[str, Any]:
    error_type = "Refused" if isinstance(e, PolicyRefused) else type(e).__name__
    body: dict[str, Any] = {"type": error_type, "message": str(e)}
    for name in (
        "violations",
        "failures",
        "backend",
        "operation",
        "reason",
        "detail",
        "token",
        "construct",
        "supported",
    ):
        if hasattr(e, name):
            body[name] = jsonable(getattr(e, name))
    if isinstance(e, PolicyRefused):
        body["policy_code"] = e.policy_code
    notes = getattr(e, "__notes__", None)
    if notes:
        body["notes"] = list(notes)
    return body
