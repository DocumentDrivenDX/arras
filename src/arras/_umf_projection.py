# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bounded projection from the official UMF core typed snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from arras.model import SCALAR_FAMILIES, Cardinality
from arras.names import MODULE_NAME, check_name

_IssueCode = Literal[
    "invalid_name", "missing_key", "incomplete_interpretation", "unsupported_projection"
]
_ELEMENT_KEYS = {
    "id",
    "name",
    "description",
    "scalarType",
    "extensions",
    "references",
    "kind",
    "nullability",
    "cardinality",
    "itemType",
    "facets",
    "members",
    "keys",
    "title",
    "aliases",
    "examples",
    "allowedValues",
    "default",
    "rules",
    "semanticTypes",
}


@dataclass(frozen=True, slots=True)
class _Issue:
    path: str
    code: _IssueCode
    message: str


@dataclass(frozen=True, slots=True)
class _Property:
    name: str
    scalar_type: str
    cardinality: Cardinality


@dataclass(frozen=True, slots=True)
class _Projection:
    module_name: str | None
    type_name: str | None
    key_name: str | None
    properties: tuple[_Property, ...]
    issues: tuple[_Issue, ...]


def project_snapshot(snapshot: object) -> _Projection:
    """Inspect only supported core fields; input is a private SDK model dump."""
    issues: list[_Issue] = []
    module_name, module = _select_module(snapshot, issues)
    if module is None:
        return _finish(None, None, None, (), issues)
    elements = _as_list(module.get("elements"))
    if elements is None:
        issues.append(_unsupported("/modules/0/elements", "elements are not an ordered list"))
        return _finish(module_name, None, None, (), issues)
    records, fields = _inventory(elements, issues)
    _check_name_collisions(elements, issues)
    if len(records) != 1:
        issues.append(
            _unsupported("/modules/0/elements", "the profile requires exactly one record")
        )
        return _finish(module_name, None, None, (), issues)
    record_index, record = records[0]
    record_path = f"/modules/0/elements/{record_index}"
    record_id = _record_name(record, record_path, issues)
    member_ids = _record_members(record, record_path, module_name, fields, issues)
    properties = _properties(member_ids, fields, issues)
    key_name = _primary_key(record, record_path, module_name, member_ids, fields, issues)
    _check_key_carrier(key_name, record_path, fields, issues)
    type_name = f"{module_name}.{record_id}" if module_name and record_id else None
    return _finish(module_name, type_name, key_name, tuple(properties), issues)


def _select_module(
    snapshot: object, issues: list[_Issue]
) -> tuple[str | None, dict[str, object] | None]:
    root = _mapping(snapshot)
    if root is None:
        issues.append(_unsupported("/", "the typed document has no supported object shape"))
        return None, None
    _empty_slot(root, "vocabularies", "/vocabularies", issues)
    _empty_slot(root, "extensions", "/extensions", issues)
    _unknown_keys(
        root, {"umf", "id", "vocabularies", "modules", "extensions", "title", "aliases"}, "", issues
    )
    modules = _as_list(root.get("modules"))
    if modules is None or len(modules) != 1:
        issues.append(_unsupported("/modules", "the profile requires exactly one module"))
        return None, None
    module = _mapping(modules[0])
    if module is None:
        issues.append(_unsupported("/modules/0", "the module has no supported object shape"))
        return None, None
    module_name = _string(module.get("id"))
    if module_name is None or MODULE_NAME.fullmatch(module_name) is None:
        issues.append(
            _issue("/modules/0/id", "invalid_name", "the module identifier is not supported")
        )
    _empty_slot(module, "extensions", "/modules/0/extensions", issues)
    _empty_array_slot(module, "relationships", "/modules/0/relationships", issues)
    if "actions" in module:
        issues.append(_unsupported("/modules/0/actions", "actions are outside this profile"))
    _unknown_keys(
        module,
        {
            "id",
            "namespace",
            "elements",
            "extensions",
            "relationships",
            "actions",
            "title",
            "aliases",
        },
        "/modules/0",
        issues,
    )
    return module_name, module


def _inventory(
    elements: list[object], issues: list[_Issue]
) -> tuple[list[tuple[int, dict[str, object]]], dict[str, tuple[int, dict[str, object]]]]:
    records: list[tuple[int, dict[str, object]]] = []
    fields: dict[str, tuple[int, dict[str, object]]] = {}
    for index, value in enumerate(elements):
        path = f"/modules/0/elements/{index}"
        element = _mapping(value)
        if element is None:
            issues.append(_unsupported(path, "an element has no supported object shape"))
            continue
        if element.get("kind") == "record":
            records.append((index, element))
        elif element.get("kind") == "field":
            field_id = _string(element.get("id"))
            if field_id is None:
                issues.append(_unsupported(f"{path}/id", "a field identifier is missing"))
            elif field_id in fields:
                issues.append(_unsupported(f"{path}/id", "field identifiers are duplicated"))
            else:
                fields[field_id] = (index, element)
        else:
            issues.append(_unsupported(f"{path}/kind", "element kind is outside this profile"))
        _inspect_element(element, path, issues)
    return records, fields


def _check_name_collisions(elements: list[object], issues: list[_Issue]) -> None:
    seen: set[str] = set()
    for index, value in enumerate(elements):
        element = _mapping(value)
        element_id = _string(element.get("id")) if element is not None else None
        if element_id is None:
            continue
        folded = element_id.casefold()
        if folded in seen:
            issues.append(
                _issue(
                    f"/modules/0/elements/{index}/id",
                    "invalid_name",
                    "record and field identifiers must be unique without regard to case",
                )
            )
        seen.add(folded)


def _record_name(record: dict[str, object], path: str, issues: list[_Issue]) -> str | None:
    record_id = _string(record.get("id"))
    if record_id is None or check_name(record_id, path, entity_type=True) is not None:
        issues.append(
            _issue(f"{path}/id", "invalid_name", "the record identifier is not supported")
        )
        return None
    return record_id


def _record_members(
    record: dict[str, object],
    path: str,
    module_name: str | None,
    fields: dict[str, tuple[int, dict[str, object]]],
    issues: list[_Issue],
) -> list[str]:
    members = _as_list(record.get("members"))
    member_ids: list[str] = []
    if members is None:
        issues.append(_unsupported(f"{path}/members", "record members are required"))
    else:
        for index, value in enumerate(members):
            member = _mapping(value)
            member_path = f"{path}/members/{index}"
            if member is None or member.get("module") != module_name:
                issues.append(_unsupported(member_path, "members must reference this module"))
                continue
            _unknown_keys(member, {"module", "element"}, member_path, issues)
            member_id = _string(member.get("element"))
            if member_id is None or member_id not in fields:
                issues.append(_unsupported(member_path, "members must reference direct fields"))
            elif member_id in member_ids:
                issues.append(_unsupported(member_path, "member references must be unique"))
            else:
                member_ids.append(member_id)
    if set(member_ids) != set(fields):
        issues.append(
            _unsupported(f"{path}/members", "every field element must be a record member")
        )
    return member_ids


def _properties(
    member_ids: list[str],
    fields: dict[str, tuple[int, dict[str, object]]],
    issues: list[_Issue],
) -> list[_Property]:
    properties: list[_Property] = []
    for field_id in member_ids:
        index, data = fields[field_id]
        path = f"/modules/0/elements/{index}"
        scalar, cardinality, nullability = (
            data.get("scalarType"),
            data.get("cardinality"),
            data.get("nullability"),
        )
        if (
            not isinstance(scalar, str)
            or scalar not in SCALAR_FAMILIES
            or cardinality != "one"
            or nullability not in ("required", "absent-allowed")
        ):
            issues.append(_unsupported(path, "field shape is outside the scalar profile"))
            continue
        if check_name(field_id, f"{path}/id") is not None:
            issues.append(
                _issue(f"{path}/id", "invalid_name", "the field identifier is not supported")
            )
            continue
        properties.append(
            _Property(field_id, scalar, "one" if nullability == "required" else "optional")
        )
    return properties


def _check_key_carrier(
    key_name: str | None,
    record_path: str,
    fields: dict[str, tuple[int, dict[str, object]]],
    issues: list[_Issue],
) -> None:
    if key_name is None:
        return
    key_field = fields.get(key_name)
    if key_field is None:
        issues.append(
            _unsupported(f"{record_path}/keys/0/fields/0", "the key target is not a direct field")
        )
        return
    index, data = key_field
    if (
        data.get("scalarType") != "string"
        or data.get("cardinality") != "one"
        or data.get("nullability") != "required"
    ):
        issues.append(
            _unsupported(
                f"/modules/0/elements/{index}",
                "the primary key field must be a required scalar string",
            )
        )


def _primary_key(
    record: dict[str, object],
    path: str,
    module_name: str | None,
    member_ids: list[str],
    fields: dict[str, tuple[int, dict[str, object]]],
    issues: list[_Issue],
) -> str | None:
    keys = _as_list(record.get("keys"))
    if keys is None or not keys:
        issues.append(
            _issue(f"{path}/keys", "missing_key", "the record has no declared primary key")
        )
        return None
    if len(keys) != 1:
        issues.append(_unsupported(f"{path}/keys", "the profile permits exactly one key"))
        return None
    key = _mapping(keys[0])
    if key is None or key.get("primary") is not True:
        issues.append(
            _issue(f"{path}/keys/0/primary", "missing_key", "an explicit primary key is required")
        )
        return None
    _unknown_keys(
        key,
        {"fields", "id", "name", "primary", "description"},
        f"{path}/keys/0",
        issues,
    )
    refs = _as_list(key.get("fields"))
    if refs is None or len(refs) != 1:
        issues.append(
            _unsupported(f"{path}/keys/0/fields", "the primary key must reference one field")
        )
        return None
    ref = _mapping(refs[0])
    field_id = _string(ref.get("element")) if ref is not None else None
    if ref is not None:
        _unknown_keys(ref, {"module", "element"}, f"{path}/keys/0/fields/0", issues)
    if (
        ref is None
        or ref.get("module") != module_name
        or field_id is None
        or field_id not in fields
        or field_id not in member_ids
    ):
        issues.append(
            _unsupported(f"{path}/keys/0/fields/0", "the key must target a direct member field")
        )
        return None
    return field_id


def _inspect_element(element: dict[str, object], path: str, issues: list[_Issue]) -> None:
    _empty_slot(element, "extensions", f"{path}/extensions", issues)
    for slot in ("default", "allowedValues", "rules"):
        if slot in element:
            issues.append(
                _unsupported(f"{path}/{slot}", "value constraints are outside this profile")
            )
    for slot in ("facets", "semanticTypes"):
        value = element.get(slot)
        if value not in (None, {}, []):
            issues.append(
                _unsupported(
                    f"{path}/{slot}", "nonempty semantic constraints are outside this profile"
                )
            )
    for slot in ("references", "itemType"):
        value = element.get(slot)
        if value not in (None, [], {}):
            issues.append(
                _unsupported(
                    f"{path}/{slot}", "structured or reference fields are outside this profile"
                )
            )
    _unknown_keys(element, _ELEMENT_KEYS, path, issues)


def _empty_slot(value: dict[str, object], name: str, path: str, issues: list[_Issue]) -> None:
    if name in value and value[name] not in (None, {}):
        issues.append(_unsupported(path, "nonempty extensions are outside this profile"))


def _empty_array_slot(value: dict[str, object], name: str, path: str, issues: list[_Issue]) -> None:
    if name in value and value[name] not in ([], None):
        issues.append(_unsupported(path, "relationships are outside this profile"))


def _unknown_keys(
    value: dict[str, object], allowed: set[str], parent: str, issues: list[_Issue]
) -> None:
    for key in value:
        if key not in allowed:
            issues.append(_unsupported(f"{parent}/{_escape(key)}", "field is outside this profile"))


def _mapping(value: object) -> dict[str, object] | None:
    if type(value) is not dict:
        return None
    raw = cast(dict[object, object], value)
    if any(type(key) is not str for key in raw):
        return None
    return cast(dict[str, object], raw)


def _as_list(value: object) -> list[object] | None:
    if type(value) is not list:
        return None
    return cast(list[object], value)


def _string(value: object) -> str | None:
    return value if type(value) is str else None


def _escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _issue(path: str, code: _IssueCode, message: str) -> _Issue:
    return _Issue(path, code, message)


def _unsupported(path: str, message: str) -> _Issue:
    return _issue(path, "unsupported_projection", message)


def _finish(
    module_name: str | None,
    type_name: str | None,
    key_name: str | None,
    properties: tuple[_Property, ...],
    issues: list[_Issue],
) -> _Projection:
    return _Projection(module_name, type_name, key_name, properties, tuple(issues))
