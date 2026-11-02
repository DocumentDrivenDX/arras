# SPDX-License-Identifier: MIT OR Apache-2.0
"""Public Arras and Truss operation constructors for managed cases."""

from __future__ import annotations

from typing import Any

from _lakebase_managed_common import MODULE as _MODULE
from _lakebase_managed_common import QUERY as _QUERY
from _lakebase_managed_common import Failed as _Failed


def _public_host(backend: Any, registrar: Any, module: str = _MODULE) -> Any:
    from arras.core import Arras
    from arras.model import Placement

    return Arras.start(
        {"truss": backend},
        expected=("truss",),
        admin=registrar,
        default_placement=Placement("truss"),
    )


def _insert_probe(host: Any, writer: Any, value: str, *, code: str, key: str) -> Any:
    return host.session(writer).invoke(
        f"{_MODULE}.CreateProbe",
        {"code": code, "value": value},
        idempotency_key=key,
    )


def _query_probe(backend: Any, principal: Any) -> tuple[dict[str, Any], ...]:
    from arras.types import Statement

    result = backend.query(principal, _MODULE, Statement(_QUERY), limit=100)
    rows = getattr(result, "rows", None)
    if type(rows) not in {tuple, list}:
        raise _Failed("public_query_result_unavailable")
    return tuple(dict(row) for row in rows)
