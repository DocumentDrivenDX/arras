# SPDX-License-Identifier: MIT OR Apache-2.0
"""Values and ids of a registered document, as a Truss group takes them (plan TR-07).

Truss stores and compares a number or a timestamp by the spelling of its token, and it does not
validate a property name or a key, so the adapter owns both: it writes every value in one canonical
spelling (a decimal at its field's declared scale, a timestamp in UTC with microseconds and `Z`, an
integer in plain digits, padded base64) so an equal value is an equal token, and it states a number
outside a field's numeric domain as `Invalid` before Truss is asked.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from arras.adapters.truss.wire import Wire
from arras.errors import Invalid, Unsupported, Violation


@dataclass(frozen=True)
class Domain:
    """A numeric field's facets as the registered document states them."""

    family: str  # `integer` or `decimal`
    precision: int | None = None
    scale: int | None = None
    bits: int = 64
    signed: bool = True


@dataclass(frozen=True)
class Ids:
    """What a group names that Arras's `ModuleInfo` does not carry: Truss's ids come from the
    registered document itself (the record id is the type's local name; a key and a relationship
    have their own ids, and the relationship's Arras name is the document's `name`)."""

    module_id: str
    keys: Mapping[str, str]  # record -> primary key id
    relationships: Mapping[str, str]  # relationship name -> relationship id
    domains: Mapping[tuple[str, str], Domain]  # (record, field) -> numeric facets


def _objects(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], x) for x in cast(list[Any], value) if isinstance(x, dict)]


def document_ids(content: bytes, module: str) -> Ids:
    """The ids of `module` in the registered document's bytes."""
    try:
        document = json.loads(content)
        modules = _objects(document.get("modules"))
    except (ValueError, AttributeError):
        raise Unsupported(
            "a registered document that is not JSON", ["JSON UMF documents"]
        ) from None
    mod = next((m for m in modules if m.get("id") == module), None)
    if mod is None:
        raise Unsupported(f"module {module} in its document", ["a registered module"])
    keys: dict[str, str] = {}
    domains: dict[tuple[str, str], Domain] = {}
    for e in _objects(mod.get("elements")):
        if e.get("kind") == "record":
            declared = _objects(e.get("keys"))
            chosen = next((k for k in declared if k.get("primary") is True), None) or (
                declared[0] if declared else None
            )
            if chosen is not None and isinstance(chosen.get("id"), str):
                keys[str(e["id"])] = chosen["id"]
        elif e.get("kind") == "field" and "." in str(e.get("id", "")):
            owner, name = str(e["id"]).split(".", 1)
            facets: dict[str, Any] = e.get("facets") or {}
            if e.get("scalarType") == "decimal":
                p, s = facets.get("precision"), facets.get("scale")
                domains[(owner, name)] = Domain(
                    "decimal", p if isinstance(p, int) else None, s if isinstance(s, int) else None
                )
            elif e.get("scalarType") == "integer":
                w: dict[str, Any] = facets.get("integerWidth") or {}
                bits = w.get("bits")
                domains[(owner, name)] = Domain(
                    "integer",
                    bits=bits if isinstance(bits, int) else 64,
                    signed=w.get("signed", True) is not False,
                )
    relationships = {
        str(r["name"]): str(r["id"])
        for r in _objects(mod.get("relationships"))
        if isinstance(r.get("name"), str) and isinstance(r.get("id"), str)
    }
    return Ids(module_id=module, keys=keys, relationships=relationships, domains=domains)


def _fault(d: Domain, v: int | Decimal) -> str | None:
    """Why a number falls outside its field's domain, or None."""
    if d.family == "integer":
        lo, hi = (-(2 ** (d.bits - 1)), 2 ** (d.bits - 1) - 1) if d.signed else (0, 2**d.bits - 1)
        return None if lo <= v <= hi else f"an integer outside {d.bits}-bit range"
    if d.precision is None or d.scale is None:
        return None
    t = Decimal(v).normalize().as_tuple()
    exponent = t.exponent if isinstance(t.exponent, int) else 0
    places = max(0, -exponent)
    whole = max(0, len(t.digits) + exponent) if any(t.digits) else 0
    if places > d.scale:
        return f"a decimal with more than {d.scale} places"
    if whole > d.precision - d.scale:
        return f"a decimal with more than {d.precision - d.scale} digits before the point"
    return None


def timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def encode(wire: Wire, family: str, domain: Domain | None, name: str, value: Any) -> Any:
    """`value` as a Truss value of its field's family, in the canonical spelling. `Invalid` for a
    number outside the field's domain."""
    if isinstance(value, bool):
        return wire.boolean(value)
    if isinstance(value, int | Decimal) and domain is not None:
        why = _fault(domain, value)
        if why is not None:
            raise Invalid([Violation(f"effects.{name}", "numeric_domain", why)])
    if family == "integer" or (family == "" and isinstance(value, int)):
        return wire.text("integer", str(int(value)))
    if family == "decimal" or (family == "" and isinstance(value, Decimal)):
        number = Decimal(value)
        if domain is not None and domain.scale is not None:
            number = number.quantize(Decimal(1).scaleb(-domain.scale))
        return wire.text("decimal", format(number, "f"))
    if isinstance(value, datetime):
        return wire.text("timestamp", timestamp(value))
    if isinstance(value, bytes):
        return wire.text("binary", base64.b64encode(value).decode("ascii"))
    return wire.text("string", str(value))
