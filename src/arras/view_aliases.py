# SPDX-License-Identifier: MIT OR Apache-2.0
"""Select one declared vocabulary name for reading a module's view extensions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from arras._legacy_aliases import validate_alias_tuple
from arras.errors import Violation


def _object(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _array(value: Any) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def select_view_vocabulary(
    root: Mapping[str, Any], aliases: tuple[str, ...], canonical: str
) -> tuple[str | None, Violation | None]:
    selected = validate_alias_tuple(aliases, "view_vocabulary_aliases", canonical)
    names = (canonical, *selected)
    vocabularies = _object(root.get("vocabularies"))
    declarations = [(name, f"vocabularies.{name}") for name in names if name in vocabularies]
    module = _object((_array(root.get("modules")) or [None])[0])
    carriers = (
        (root, "extensions"),
        (module, "modules[0].extensions"),
        *tuple(
            (_object(action), f"modules[0].actions[{i}].extensions")
            for i, action in enumerate(_array(module.get("actions")))
        ),
        *tuple(
            (_object(element), f"modules[0].elements[{i}].extensions")
            for i, element in enumerate(_array(module.get("elements")))
        ),
        *tuple(
            (_object(relationship), f"modules[0].relationships[{i}].extensions")
            for i, relationship in enumerate(_array(module.get("relationships")))
        ),
    )
    extensions = [
        (name, f"{path}.{name}")
        for carrier, path in carriers
        for name in names
        if name in _object(carrier.get("extensions"))
    ]
    occurrences = [*declarations, *extensions]
    selected_name = occurrences[0][0] if occurrences else None
    conflict = next((entry for entry in occurrences[1:] if entry[0] != selected_name), None)
    if conflict is not None:
        return None, Violation(
            conflict[1],
            "view_ambiguous_vocabulary",
            "select one view vocabulary name per document",
        )
    if declarations:
        return declarations[0][0], None
    alias_extension = next((entry for entry in extensions if entry[0] in selected), None)
    if alias_extension is not None:
        return None, Violation(
            alias_extension[1],
            "view_unknown_term",
            "the matching vocabulary must be declared",
        )
    return None, None
