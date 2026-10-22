# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""Wire values to the values the interface takes (CONTRACT-007, CONTRACT-009).

A binding that receives text (MCP, HTTP) converts it with `convert_inputs` before the library
sees a value; a value that does not convert is a violation at its path.
"""

from __future__ import annotations

import base64
import re
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from arras.actions import ActionInfo
from arras.errors import Violation
from arras.model import ModuleInfo

_INT_53 = 2**53

# The text a person types, as the UI checks it too (tests/vectors/inputs.json): ASCII digits only,
# no spaces, no `_` separators, no hexadecimal, no `NaN` or `Infinity`.
_INTEGER = re.compile(r"[+-]?[0-9]+")
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
# RFC 3339 date-time, with `t`/`z` in either case, a space for `T`, and seconds optional; an offset
# is required. The fields are range-checked by `datetime` itself (a calendar date, hour <= 23,
# minute and second <= 59).
_TIMESTAMP = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})[Tt ]([0-9]{2}):([0-9]{2})(?::([0-9]{2})(?:\.([0-9]+))?)?"
    r"(?:([Zz])|([+-])([0-9]{2}):([0-9]{2}))"
)


def parse_timestamp(text: str) -> datetime | None:
    """An RFC 3339 timestamp with its offset, or None for any other text."""
    m = _TIMESTAMP.fullmatch(text)
    if m is None:
        return None
    year, month, day, hour, minute, second, frac, z, sign, oh, om = m.groups()
    if z:
        tz = UTC
    else:
        if int(oh) > 23 or int(om) > 59:
            return None
        delta = timedelta(hours=int(oh), minutes=int(om))
        tz = timezone(-delta if sign == "-" else delta)
    try:
        return datetime(
            int(year),
            int(month),
            int(day),
            int(hour),
            int(minute),
            int(second or 0),
            int((frac or "0")[:6].ljust(6, "0")),
            tzinfo=tz,
        )
    except ValueError:  # not a calendar date, or a field out of range
        return None


# -- wire values to the values the interface takes ------------------------------------------


def to_python(
    spec_type: str, kind: str, value: Any, path: str, out: list[Violation], module: ModuleInfo
) -> Any:
    """Convert one JSON value as the schema above allows it; a fault is recorded, not raised."""

    def bad(msg: str) -> Any:
        out.append(Violation(path, "type", msg))
        return value

    if kind == "scalar":
        if spec_type == "integer" and isinstance(value, str):
            if not _INTEGER.fullmatch(value):
                return bad("an integer, or its decimal text")
            return int(value)
        if (
            spec_type == "integer"
            and isinstance(value, int)
            and abs(value) >= _INT_53
            and not isinstance(value, bool)
        ):
            return bad("an integer beyond 53 bits is sent as decimal text")
        if spec_type == "decimal" and isinstance(value, str):
            if not _DECIMAL.fullmatch(value):
                return bad("a finite decimal as text")
            try:
                return Decimal(value)
            except InvalidOperation:  # pragma: no cover - the pattern admits only decimals
                return bad("a finite decimal as text")
        if spec_type == "timestamp" and isinstance(value, str):
            dt = parse_timestamp(value)
            return dt if dt is not None else bad("an RFC 3339 timestamp with an offset")
        if spec_type == "binary" and isinstance(value, str):
            try:
                return base64.b64decode(value, validate=True)
            except ValueError:
                return bad("base64 text")
        return value
    if kind == "record" and isinstance(value, dict):
        vt = next((v for v in module.value_types if v.name == f"{module.name}.{spec_type}"), None)
        props = {p.name: p for p in (vt.properties if vt else ())}
        result: dict[str, Any] = {}
        for k, v in value.items():  # type: ignore[reportUnknownVariableType]
            p = props.get(k)
            if p is None:
                result[k] = v
            elif p.cardinality == "many" and isinstance(v, list):
                result[k] = [
                    to_python(
                        p.type,
                        "scalar" if p.scalar else "record",
                        x,
                        f"{path}.{k}[{i}]",
                        out,
                        module,
                    )
                    for i, x in enumerate(v)
                ]
            else:
                result[k] = to_python(
                    p.type, "scalar" if p.scalar else "record", v, f"{path}.{k}", out, module
                )
        return result
    return value


def convert_inputs(
    action: ActionInfo, module: ModuleInfo, inputs: dict[str, Any], prefix: str = "inputs"
) -> tuple[dict[str, Any], list[Violation]]:
    out: list[Violation] = []
    specs = {s.name: s for s in action.inputs}
    values: dict[str, Any] = {}
    for k, v in inputs.items():
        s = specs.get(k)
        if s is None:
            values[k] = v  # the interface reports an unknown input
        elif s.cardinality == "many" and isinstance(v, list):
            values[k] = [
                to_python(s.type, s.kind, x, f"{prefix}.{k}[{i}]", out, module)
                for i, x in enumerate(v)  # type: ignore[reportUnknownVariableType]
            ]
        else:
            values[k] = to_python(s.type, s.kind, v, f"{prefix}.{k}", out, module)
    return values, out
