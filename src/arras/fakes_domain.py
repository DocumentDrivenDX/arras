# SPDX-License-Identifier: MIT OR Apache-2.0
"""The numeric domains of a module's fields, as the memory adapter reads them (W-011).

`ModuleInfo` carries a field's scalar family, not its facets, so the memory adapter reads a
decimal's `precision` and `scale` and an integer's `integerWidth` from the registered document
itself. Weft holds a literal or a parameter to its field's domain (`WFT-NUMERIC-DOMAIN`), and a
backend's column holds what it stores to it; the memory adapter does both: `fault` says why a
value falls outside a domain, and `stored` gives the value a field holds (a decimal at its scale).
An integer field with no width is a signed 64-bit integer; a decimal with no precision and scale has
no domain the memory adapter can serve.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Any


@dataclass(frozen=True)
class Domain:
    family: str  # `integer` or `decimal`
    precision: int | None = None
    scale: int | None = None
    bits: int = 64
    signed: bool = True

    @property
    def served(self) -> bool:
        """Whether the domain is complete: a decimal names its precision and scale."""
        return self.family != "decimal" or (self.precision is not None and self.scale is not None)


Domains = Mapping[tuple[str, str, str], Domain]  # (module, record, field)


@lru_cache(maxsize=64)
def _parse(document: bytes) -> dict[tuple[str, str, str], Domain]:
    out: dict[tuple[str, str, str], Domain] = {}
    try:
        doc = json.loads(document)
    except ValueError:
        return out
    for module in doc.get("modules", []):
        for e in module.get("elements", []):
            if e.get("kind") != "field" or "." not in str(e.get("id", "")):
                continue
            owner, name = str(e["id"]).split(".", 1)
            facets: dict[str, Any] = e.get("facets") or {}
            if e.get("scalarType") == "decimal":
                p, s = facets.get("precision"), facets.get("scale")
                out[(module["id"], owner, name)] = Domain(
                    "decimal",
                    p if isinstance(p, int) else None,
                    s if isinstance(s, int) else None,
                )
            elif e.get("scalarType") == "integer":
                w: dict[str, Any] = facets.get("integerWidth") or {}
                raw_bits = w.get("bits")
                bits = raw_bits if isinstance(raw_bits, int) else 64
                out[(module["id"], owner, name)] = Domain(
                    "integer", bits=bits, signed=w.get("signed", True) is not False
                )
    return out


def domains(document: bytes | None) -> Domains:
    """The numeric domains a registered document declares; none for no document."""
    return _parse(document) if document is not None else {}


def fault(d: Domain, v: int | Decimal) -> str | None:
    """Why a value falls outside the domain, or `None`."""
    if d.family == "integer":
        lo, hi = (-(2 ** (d.bits - 1)), 2 ** (d.bits - 1) - 1) if d.signed else (0, 2**d.bits - 1)
        return None if lo <= v <= hi else f"an integer outside {d.bits}-bit range"
    if d.precision is None or d.scale is None:
        return None
    t = Decimal(v).normalize().as_tuple()
    exponent = t.exponent if isinstance(t.exponent, int) else 0
    scale = max(0, -exponent)
    whole = max(0, len(t.digits) + exponent) if any(t.digits) else 0
    if scale > d.scale:
        return f"a decimal with more than {d.scale} places"
    if whole > d.precision - d.scale:
        return f"a decimal with more than {d.precision - d.scale} digits before the point"
    return None


def stored(d: Domain, v: Any) -> Any:
    """The value a field of this domain holds: a decimal at its scale. `ValueError` with the
    reason when it falls outside the domain."""
    if isinstance(v, bool) or not isinstance(v, int | Decimal):
        return v
    why = fault(d, v)
    if why is not None:
        raise ValueError(why)
    if d.family == "decimal" and d.scale is not None:
        return Decimal(v).quantize(Decimal(1).scaleb(-d.scale))
    return v


def stored_props(
    found: Domains, module: str, record: str, props: Mapping[str, Any]
) -> dict[str, Any]:
    """`props` as the record's fields hold them; `ValueError((name, reason))` for the first value
    outside its field's domain."""
    out = dict(props)
    for name, v in props.items():
        d = found.get((module, record, name))
        if d is None:
            continue
        try:
            out[name] = stored(d, v)
        except ValueError as e:
            raise ValueError(name, str(e)) from None
    return out
