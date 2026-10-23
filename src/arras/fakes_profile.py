# SPDX-License-Identifier: MIT OR Apache-2.0
"""The raw-document semantic subset the in-memory writer can enforce.

This is deliberately a profile check, not an evaluator for UMF facets. It examines only declared
semantic slots on fields, modules, and elements, and refuses the module as a whole when the memory
writer cannot honor one of those declarations.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, NoReturn, cast

from arras.errors import Unsupported


def require_supported_write_profile(
    document: bytes | None,
    module_name: str,
    metadata_profile: str = "legacy-arras/1",
) -> None:
    """Refuse writes when a registered raw document declares semantics memory does not serve.

    A metadata-only profile refuses writes regardless of its source bytes. A missing legacy
    document is the explicit baseline for hand-built ModuleInfo fixtures. Present legacy source
    is checked at known semantic locations only; arbitrary extension content is not searched for
    similarly named keys.
    """
    if metadata_profile == "umf-core-metadata/1":
        raise Unsupported(
            f"writes to {module_name} with a metadata-only profile",
            ["the selected metadata profile supports schema registration and reads only"],
        )
    if metadata_profile != "legacy-arras/1":
        raise Unsupported(
            f"writes to {module_name} with an unsupported metadata profile",
            ["the selected metadata profile is not recognized by the memory writer"],
        )
    _require_legacy_document_profile(document, module_name)


def _require_legacy_document_profile(document: bytes | None, module_name: str) -> None:
    if document is None:
        return
    try:
        decoded = json.loads(document)
    except (UnicodeDecodeError, ValueError):
        _refuse(module_name, ["document: registered source is not valid JSON"])
    if not isinstance(decoded, dict):
        _refuse(module_name, ["document: registered source is not an object"])
    root = cast(dict[str, Any], decoded)
    modules = root.get("modules")
    if not isinstance(modules, list):
        _refuse(module_name, ["modules: registered source has no module list"])
    module_items = cast(list[Any], modules)
    raw_module = next(
        (
            cast(dict[str, Any], item)
            for item in module_items
            if isinstance(item, dict) and cast(dict[str, Any], item).get("id") == module_name
        ),
        None,
    )
    if not isinstance(raw_module, dict):
        _refuse(module_name, [f"modules.{module_name}: registered source module is missing"])

    unsupported: list[str] = []
    _rule_slot(raw_module, f"modules.{module_name}.rules", unsupported)
    elements = raw_module.get("elements")
    if not isinstance(elements, list):
        unsupported.append(f"modules.{module_name}.elements: registered source has no element list")
        element_items: list[Any] = []
    else:
        element_items = cast(list[Any], elements)
    for index, unknown_item in enumerate(element_items):
        if not isinstance(unknown_item, dict):
            continue
        item = cast(dict[str, Any], unknown_item)
        ident = item.get("id")
        path = f"modules.{module_name}.elements[{index}]"
        _rule_slot(item, f"{path}.rules", unsupported)
        if item.get("kind") != "field":
            continue
        field_path = f"{module_name}.{ident}" if isinstance(ident, str) else path
        for key in ("default", "allowedValues"):
            if key in item:
                unsupported.append(f"{field_path}.{key}: declared field {key} is not enforced")
        semantic_types = item.get("semanticTypes")
        if "semanticTypes" in item and semantic_types != []:
            unsupported.append(
                f"{field_path}.semanticTypes: declared semantic types are not enforced"
            )

        if "facets" not in item or item.get("facets") == {}:
            continue
        _check_facets(item, field_path, unsupported)

    if unsupported:
        _refuse(module_name, unsupported)


def _refuse(module_name: str, reasons: list[str]) -> NoReturn:
    raise Unsupported(
        f"writes to {module_name} with unserved document semantics", sorted(set(reasons))
    )


def _rule_slot(value: Mapping[str, Any], path: str, out: list[str]) -> None:
    if "rules" in value:
        out.append(f"{path}: declared rules are not evaluated")


def _check_facets(item: Mapping[str, Any], path: str, out: list[str]) -> None:
    facets = item.get("facets")
    if not isinstance(facets, dict):
        out.append(f"{path}.facets: malformed facets are not supported")
        return
    facets = cast(dict[str, Any], facets)
    scalar = item.get("scalarType")
    direct_scalar = (
        isinstance(scalar, str)
        and scalar in {"string", "integer", "decimal", "boolean", "timestamp", "binary"}
        and item.get("cardinality", "one") == "one"
        and "." in str(item.get("id", ""))
        and "itemType" not in item
        and "type" not in item
    )
    if not direct_scalar:
        out.append(f"{path}.facets: facets on non-direct scalar fields are not supported")
        return
    if scalar == "integer" and set(facets) == {"integerWidth"}:
        width = facets.get("integerWidth")
        if not isinstance(width, dict):
            out.append(f"{path}.facets.integerWidth: unsupported integer width shape")
            return
        width = cast(dict[str, Any], width)
        if width.keys() - {"bits", "signed"}:
            out.append(f"{path}.facets.integerWidth: unsupported integer width shape")
            return
        bits = width.get("bits", 64)
        signed = width.get("signed", True)
        if isinstance(bits, bool) or not isinstance(bits, int) or bits <= 0:
            out.append(f"{path}.facets.integerWidth.bits: expected a positive integer")
        if not isinstance(signed, bool):
            out.append(f"{path}.facets.integerWidth.signed: expected a boolean")
        return
    if scalar == "decimal" and set(facets) == {"precision", "scale"}:
        precision, scale = facets.get("precision"), facets.get("scale")
        if isinstance(precision, bool) or not isinstance(precision, int) or precision < 1:
            out.append(f"{path}.facets.precision: expected a positive integer")
        if (
            isinstance(scale, bool)
            or not isinstance(scale, int)
            or not isinstance(precision, int)
            or isinstance(precision, bool)
            or not 0 <= scale <= precision
        ):
            out.append(f"{path}.facets.scale: expected an integer from zero through precision")
        return
    out.append(f"{path}.facets: declared facet shape is not enforced")
