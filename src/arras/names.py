# SPDX-License-Identifier: MIT OR Apache-2.0
"""The name rules of CONTRACT-002."""

from __future__ import annotations

import re

from arras.errors import Violation

MODULE_NAME = re.compile(r"[a-z][a-z0-9_]{0,40}")
BACKEND_NAME = (
    MODULE_NAME  # a name the host registers a backend under (CONTRACT-005): the same shape
)
NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
RESERVED_NAMES = frozenset(
    "Query Mutation Subscription Entity Page Ref Freshness Revision Module Status JSON DateTime "
    "BigInt Decimal Base64 String Int Float Boolean ID ref key type version revision freshness "
    "references Consistency".split()
)


def quoted(name: str) -> str:
    """`name` as a Weft quoted identifier (`"order"`, embedded quotes doubled), so a statement
    Arras writes reads every legal UMF name exactly, a Weft reserved word among them. Only for a
    name the rules above admitted (a module, type, property or relationship of a registered
    module); anything else is refused, so free input is never written into a statement."""
    if not (NAME.fullmatch(name) or MODULE_NAME.fullmatch(name)):
        raise ValueError(f"{name!r} is not a name the rules admit")
    return '"' + name.replace('"', '""') + '"'


def quoted_type(qualified: str) -> str:
    """A qualified type name, `module.Type`, as Weft quoted identifiers: `"module"."Type"`."""
    module, _, local = qualified.partition(".")
    return f"{quoted(module)}.{quoted(local)}" if local else quoted(module)


def check_name(name: str, path: str, *, entity_type: bool = False) -> Violation | None:
    """The name rules of CONTRACT-002; `None` when the name is allowed."""
    if not NAME.fullmatch(name):
        return Violation(path, "invalid_name", f"{name!r} must match [A-Za-z][A-Za-z0-9_]{{0,63}}")
    if name in RESERVED_NAMES:
        return Violation(path, "invalid_name", f"{name!r} is a reserved name")
    if entity_type and (name.endswith("Page") or name.endswith("List")):
        return Violation(path, "invalid_name", f"type name {name!r} must not end in Page or List")
    return None
