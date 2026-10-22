# SPDX-License-Identifier: MIT OR Apache-2.0
"""What registering a module's document checks of the host, shared by the administrator's
`Registry` and the person's `Schema` (CONTRACT-002): the placement the host gave it, the backends
that placement names, and the modules a relationship reaches. It holds no authority check: each
caller decides who may ask. `Arras` is imported for types only, so `core` can import this."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from arras.errors import Invalid, Violation
from arras.model import ModuleInfo
from arras.types import Revision
from arras.umf import parse_module

if TYPE_CHECKING:
    from arras.core import Arras


def as_revision(r: Revision | Mapping[str, Any]) -> Revision:
    """A caller's revision as the wire states it (`{"memory": 3}`) or as a `Revision`."""
    if isinstance(r, Revision):
        return r
    try:
        return Revision.from_wire(r)
    except ValueError as e:
        raise Invalid([Violation("expected_revision", "type", str(e))]) from None


def placed(h: Arras, document: bytes | str) -> tuple[bytes, ModuleInfo]:
    """The document's bytes and its module as the host placed it; `Invalid` when it does not parse
    or the host placed no such module."""
    raw = document.encode() if isinstance(document, str) else document
    mod = parse_module(raw)
    placement = h.placement_of(mod.name)
    if placement is None:
        raise Invalid(
            [Violation("placement", "invalid_placement", f"the host placed no {mod.name!r}")]
        )
    return raw, replace(mod, placement=placement)


def host_violations(h: Arras, mod: ModuleInfo, readable: Collection[str]) -> list[Violation]:
    """What the host's configuration and the modules the caller may read say against `mod`."""
    bad: list[Violation] = []
    backends = h.backends
    named = (*mod.placement.readers, *mod.placement.providers.values())
    for n in dict.fromkeys(named):
        if n not in backends:
            bad.append(Violation("placement", "invalid_placement", f"{n!r} is not configured"))
    if len(set(mod.placement.readers)) != len(mod.placement.readers):
        bad.append(Violation("placement", "invalid_placement", "a reader is named once"))
    for n in mod.placement.readers:
        if n in backends and not backends[n].describe().reads:
            bad.append(Violation("placement", "invalid_placement", f"{n!r} is not a reader"))
    for action, n in mod.placement.providers.items():
        if action.partition(".")[0] != mod.name:
            bad.append(
                Violation("placement", "invalid_placement", f"{action!r} is not {mod.name}'s")
            )
        if n in backends and not backends[n].describe().provides:
            bad.append(Violation("placement", "invalid_placement", f"{n!r} is not a provider"))
    for r in mod.relationships:
        for e in (*r.source, *r.target):
            other = e.split(".", 1)[0]
            if other != mod.name and other not in readable:
                bad.append(
                    Violation(
                        f"relationships.{r.name}", "unreadable_module", f"cannot read {other!r}"
                    )
                )
    return bad


def check_document(
    h: Arras, document: bytes | str, readable: Collection[str]
) -> tuple[bytes, ModuleInfo]:
    """`placed`, then every host violation raised together as one `Invalid`."""
    raw, mod = placed(h, document)
    bad = host_violations(h, mod, readable)
    if bad:
        raise Invalid(bad)
    return raw, mod
