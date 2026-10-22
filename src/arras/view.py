# SPDX-License-Identifier: MIT OR Apache-2.0
"""The `arras.view` vocabulary: how a module's types are presented (CONTRACT-010, section A and B).

A module declares presentation in the closed vocabulary `arras.view` 0.1.0, in the `extensions`
of its UMF document. This module holds the closed sets, the types for what is declared and for
what is resolved, the template grammar, the checks that run at registration (`parse_view`) and the
resolution that merges a declaration with the defaults (`resolve`). A view is presentation only: it
never changes a type, a property, a relationship or an action, and it carries no entity data.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import lru_cache
from typing import Any, cast

from arras.errors import Violation
from arras.model import EntityTypeInfo, ModuleInfo, PropertyInfo

VOCABULARY = "arras.view"
VERSION = "0.1.0"

ICONS = (
    "box",
    "package",
    "puzzle",
    "file-text",
    "folder",
    "user",
    "users",
    "building",
    "tag",
    "flag",
    "alert",
    "check-circle",
    "clock",
    "calendar",
    "link",
    "globe",
    "wrench",
    "scale",
    "book",
    "chart",
    "shield",
    "star",
    "bolt",
    "circle",
)
TONES = ("slate", "blue", "teal", "green", "amber", "red", "violet", "rose")
FORMATS = (
    "text",
    "prose",
    "code",
    "link",
    "badge",
    "tags",
    "date",
    "datetime",
    "number",
    "boolean",
    "json",
)

MODULE_TERMS = ("title", "description")
RECORD_TERMS = ("label", "pluralLabel", "icon", "tone", "title", "summary", "sections", "search")
FIELD_TERMS = ("label", "format", "hideWhenEmpty", "tones")
RELATIONSHIP_TERMS = ("label", "inverseLabel", "hideWhenEmpty", "order")
SECTION_TERMS = ("label", "properties", "collapsed")
# A term that only a relationship has, found elsewhere, is a relationship term in the wrong place.
_RELATIONSHIP_ONLY = ("inverseLabel", "order")

MAX_MODULE_TITLE = 80
MAX_MODULE_DESCRIPTION = 280
MAX_LABEL = 60
MAX_TEMPLATE = 200
MAX_SECTIONS = 8
MAX_SECTION_PROPERTIES = 24
MAX_SEARCH = 8
MAX_TONES = 24
MAX_RECORD_BYTES = 16 * 1024
MAX_DOCUMENT_BYTES = 128 * 1024

_TITLE_NAMES = ("name", "title", "label")
_SUMMARY_NAMES = ("summary", "description", "statement", "problem", "notes")
_SEARCH_TAIL = ("description", "statement", "problem", "notes")
_PROSE = frozenset(
    "summary description statement problem notes prompt workflow caveat rationale".split()
)
_BADGE = frozenset("status state kind level".split())
_LINK_SUFFIXES = ("url", "uri", "link")

# -- declared and resolved views ---------------------------------------------------------------


@dataclass(frozen=True)
class DeclaredSection:
    label: str
    properties: tuple[str, ...]
    collapsed: bool = False


@dataclass(frozen=True)
class RecordTerms:
    """What a document declared for a record; `None` is not declared."""

    label: str | None = None
    plural_label: str | None = None
    icon: str | None = None
    tone: str | None = None
    title: str | None = None
    summary: str | None = None
    sections: tuple[DeclaredSection, ...] | None = None
    search: tuple[str, ...] | None = None


@dataclass(frozen=True)
class FieldTerms:
    label: str | None = None
    format: str | None = None
    hide_when_empty: bool | None = None
    tones: Mapping[str, str] | None = None


@dataclass(frozen=True)
class RelationshipTerms:
    label: str | None = None
    inverse_label: str | None = None
    hide_when_empty: bool | None = None
    order: int | None = None


@dataclass(frozen=True)
class DeclaredView:
    """The `arras.view` terms of one document, by local type name, `(type, property)` and
    relationship name. Empty when the document declares none."""

    title: str | None = None
    description: str | None = None
    records: Mapping[str, RecordTerms] = field(default_factory=dict[str, RecordTerms])
    fields: Mapping[tuple[str, str], FieldTerms] = field(
        default_factory=dict[tuple[str, str], FieldTerms]
    )
    relationships: Mapping[str, RelationshipTerms] = field(
        default_factory=dict[str, RelationshipTerms]
    )


@dataclass(frozen=True)
class ResolvedModuleView:
    title: str
    description: str | None


@dataclass(frozen=True)
class ViewSection:
    label: str
    properties: tuple[str, ...]
    collapsed: bool


@dataclass(frozen=True)
class FieldView:
    property: str
    label: str
    format: str
    hide_when_empty: bool
    tones: Mapping[str, str] | None


@dataclass(frozen=True)
class RelationshipView:
    field: str
    label: str
    hide_when_empty: bool
    order: int


@dataclass(frozen=True)
class ResolvedView:
    """A type's view as a client draws it: the declaration merged with the defaults."""

    declared: bool
    label: str
    plural_label: str
    icon: str
    tone: str
    title: str
    summary: str | None
    sections: tuple[ViewSection, ...]
    search: tuple[str, ...]
    fields: tuple[FieldView, ...]
    relationships: tuple[RelationshipView, ...]


@dataclass(frozen=True)
class ResolvedModule:
    module: ResolvedModuleView
    types: Mapping[str, ResolvedView]  # by local type name

    def of(self, type_name: str) -> ResolvedView | None:
        """A type's view by its qualified (`catalog.UseCase`) or local name."""
        return self.types.get(type_name.rpartition(".")[2])

    def view(self, type_name: str) -> ResolvedView:
        """A type's view; `KeyError` for a name that is not one of the module's types."""
        return self.types[type_name.rpartition(".")[2]]


# -- templates ---------------------------------------------------------------------------------


class TemplateError(ValueError):
    """A template that is malformed."""


@dataclass(frozen=True)
class Placeholder:
    name: str


@dataclass(frozen=True)
class OptionalGroup:
    """`[ ... ]`: shown only if every placeholder inside it has a value."""

    nodes: tuple[Node, ...]


Node = str | Placeholder | OptionalGroup
Template = tuple[Node, ...]

_ESCAPABLE = "{}[]\\"
_PLACEHOLDER = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


@lru_cache(maxsize=2048)
def parse_template(text: str) -> Template:
    """The template grammar of CONTRACT-010: `{name}`, `[` optional group `]` and escapes
    `\\{ \\} \\[ \\] \\\\`. Raises `TemplateError` for anything unescaped that is not one of those
    forms."""
    nodes, end = _parse(text, 0, nested=False)
    assert end == len(text)
    return nodes


def _parse(text: str, i: int, *, nested: bool) -> tuple[Template, int]:
    nodes: list[Node] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            nodes.append("".join(buf))
            buf.clear()

    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text) and text[i + 1] in _ESCAPABLE:
            buf.append(text[i + 1])
            i += 2
        elif c == "{":
            end = text.find("}", i)
            name = text[i + 1 : end] if end > 0 else ""
            if not _PLACEHOLDER.fullmatch(name):
                raise TemplateError("a { starts a {name} placeholder; write \\{ for a brace")
            flush()
            nodes.append(Placeholder(name))
            i = end + 1
        elif c == "[":
            flush()
            inner, i = _parse(text, i + 1, nested=True)
            nodes.append(OptionalGroup(inner))
        elif c == "]":
            if not nested:
                raise TemplateError("a ] closes no [; write \\] for a bracket")
            flush()
            return tuple(nodes), i + 1
        elif c == "}":
            raise TemplateError("a } closes no {; write \\} for a brace")
        else:
            buf.append(c)
            i += 1
    if nested:
        raise TemplateError("a [ is never closed; write \\[ for a bracket")
    flush()
    return tuple(nodes), i


def placeholders(template: str | Template) -> list[str]:
    """The property names a template names, in order of first appearance."""
    nodes = parse_template(template) if isinstance(template, str) else template
    found: list[str] = []
    for n in nodes:
        names = (
            [n.name]
            if isinstance(n, Placeholder)
            else placeholders(n.nodes)
            if isinstance(n, OptionalGroup)
            else []
        )
        found.extend(x for x in names if x not in found)
    return found


def as_text(value: Any) -> str:
    """A property's value as the text a template shows."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, list | tuple):
        return ", ".join(as_text(v) for v in cast(Sequence[Any], value))
    return str(value)


def _eval(nodes: Template, row: Mapping[str, Any]) -> tuple[str, bool]:
    """The text and whether every placeholder in it had a value."""
    out: list[str] = []
    filled = True
    for n in nodes:
        if isinstance(n, str):
            out.append(n)
        elif isinstance(n, Placeholder):
            text = as_text(row.get(n.name))
            if not text.strip():
                filled = False
            else:
                out.append(text)
        else:
            text, ok = _eval(n.nodes, row)
            filled = filled and ok
            if ok:
                out.append(text)
    return "".join(out), filled


def evaluate(template: str | Template, row: Mapping[str, Any]) -> str:
    """The template over an entity's properties. A placeholder with no value, and an optional
    group with any, produce no text; the result is text, never markup."""
    nodes = parse_template(template) if isinstance(template, str) else template
    return _eval(nodes, row)[0]


def title_of(view: ResolvedView, row: Mapping[str, Any], key: str) -> str:
    """An entity's title: its template over the row, or its key when that is empty."""
    return evaluate(view.title, row).strip() or key


# -- words and defaults ------------------------------------------------------------------------

_WORDS = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+[0-9]*|[A-Z]+[0-9]*|[0-9]+")


def split_words(name: str) -> str:
    """`UseCase` is `Use case`, `workArea` is `Work area`, `HTTPServer` is `HTTP server`."""
    words = _WORDS.findall(name.replace("_", " ").replace("-", " "))
    if not words:
        return name
    out = [w if len(w) > 1 and w.isupper() else w.lower() for w in words]
    out[0] = out[0][:1].upper() + out[0][1:]
    return " ".join(out)


def pluralize(label: str) -> str:
    """A label in the plural, by English rules, for where it names a collection: `Use case` is
    `Use cases`, `Category` is `Categories`, `Address` is `Addresses`. Only the last word changes
    and the label's capitalisation is kept."""
    head, space, last = label.rpartition(" ")
    lower = last.lower()
    if len(lower) > 1 and lower.endswith("y") and lower[-2] not in "aeiou":
        plural = last[:-1] + "ies"
    elif lower.endswith(("s", "x", "z", "ch", "sh")):
        plural = last + "es"
    else:
        plural = last + "s"
    return head + space + plural


def default_format(p: PropertyInfo) -> str:
    """The format a property shows in when none is declared (CONTRACT-010, Defaults)."""
    if not p.scalar:
        return "json"
    if p.cardinality == "many":
        return "tags" if p.type == "string" else "json"
    if p.type == "string":
        lower = p.name.lower()
        if lower.endswith(_LINK_SUFFIXES):
            return "link"
        if p.name in _PROSE:
            return "prose"
        return "badge" if p.name in _BADGE else "text"
    return {
        "timestamp": "datetime",
        "integer": "number",
        "decimal": "number",
        "boolean": "boolean",
        "binary": "binary",
    }.get(p.type, "json")


def format_suits(p: PropertyInfo, fmt: str) -> bool:
    """Whether `fmt` can show the property's type."""
    if not p.scalar:
        return fmt == "json"
    if p.cardinality == "many":
        return fmt == "tags" if p.type == "string" else fmt == "json"
    suits = {
        "string": ("text", "prose", "code", "link", "badge"),
        "timestamp": ("date", "datetime"),
        "integer": ("number",),
        "decimal": ("number",),
        "boolean": ("boolean",),
    }
    return fmt in suits.get(p.type, ())


def is_searchable_type(p: PropertyInfo) -> bool:
    """A single-valued string: what a search can match."""
    return p.scalar and p.type == "string" and p.cardinality != "many"


def _non_key(t: EntityTypeInfo) -> list[PropertyInfo]:
    return [p for p in t.properties if p.name != t.key]


def _default_title(t: EntityTypeInfo) -> str:
    for n in _TITLE_NAMES:
        p = t.property(n)
        if p is not None and p.name != t.key:
            return "{" + n + "}"
    first = next((p for p in _non_key(t) if is_searchable_type(p)), None)
    return "{" + (first.name if first else t.key) + "}"


def _default_summary(t: EntityTypeInfo, title: str) -> str | None:
    used = placeholders(title)
    for n in _SUMMARY_NAMES:
        if t.property(n) is not None and n not in used and n != t.key:
            return "{" + n + "}"
    return None


def _default_search(t: EntityTypeInfo, title: str, summary: str | None) -> tuple[str, ...]:
    chosen: list[str] = []

    def add(name: str) -> None:
        p = t.property(name)
        if p is not None and is_searchable_type(p) and name not in chosen:
            chosen.append(name)

    for n in placeholders(title):
        add(n)
    add(t.key)
    for n in placeholders(summary or ""):
        add(n)
    for n in _SEARCH_TAIL:
        add(n)
    return tuple(chosen[:MAX_SEARCH])


def _sections(
    t: EntityTypeInfo, declared: tuple[DeclaredSection, ...] | None, used: list[str]
) -> tuple[ViewSection, ...]:
    if declared is None:
        rest = [p.name for p in _non_key(t) if p.name not in used]
        return (ViewSection("Details", tuple(rest), False),) if rest else ()
    placed = {p for s in declared for p in s.properties}
    out = [ViewSection(s.label, s.properties, s.collapsed) for s in declared]
    more = [p.name for p in _non_key(t) if p.name not in placed and p.name not in used]
    if more:
        out.append(ViewSection("More", tuple(more), False))
    return tuple(out)


def _field_view(t: str, p: PropertyInfo, terms: Mapping[tuple[str, str], FieldTerms]) -> FieldView:
    ft = terms.get((t, p.name), FieldTerms())
    fmt = ft.format or default_format(p)
    tones = dict(ft.tones) if ft.tones is not None and fmt == "badge" else None
    return FieldView(p.name, ft.label or split_words(p.name), fmt, bool(ft.hide_when_empty), tones)


def _relationship_views(
    mod: ModuleInfo, t: EntityTypeInfo, terms: Mapping[str, RelationshipTerms]
) -> tuple[RelationshipView, ...]:
    out: list[RelationshipView] = []
    for r in mod.relationships:
        rt = terms.get(r.name, RelationshipTerms())
        order, hide = rt.order if rt.order is not None else 50, bool(rt.hide_when_empty)
        if t.name in r.source:
            out.append(RelationshipView(r.name, rt.label or split_words(r.name), hide, order))
        if r.inverse and t.name in r.target:
            label = rt.inverse_label or split_words(r.inverse)
            out.append(RelationshipView(r.inverse, label, hide, order))
    return tuple(out)


def _resolve_type(
    mod: ModuleInfo, t: EntityTypeInfo, position: int, declared: DeclaredView
) -> ResolvedView:
    rt = declared.records.get(t.local_name, RecordTerms())
    title = rt.title if rt.title is not None else _default_title(t)
    summary = rt.summary if rt.summary is not None else _default_summary(t, title)
    used = [*placeholders(title), *placeholders(summary or "")]
    search = rt.search if rt.search is not None else _default_search(t, title, summary)
    any_declared = rt != RecordTerms() or any(k[0] == t.local_name for k in declared.fields)
    label = rt.label or split_words(t.local_name)
    return ResolvedView(
        declared=any_declared,
        label=label,
        plural_label=rt.plural_label or pluralize(label),
        icon=rt.icon or "circle",
        tone=rt.tone or TONES[position % len(TONES)],
        title=title,
        summary=summary,
        sections=_sections(t, rt.sections, used),
        search=tuple(search),
        fields=tuple(_field_view(t.local_name, p, declared.fields) for p in t.properties),
        relationships=_relationship_views(mod, t, declared.relationships),
    )


def resolve(mod: ModuleInfo, declared: DeclaredView | None = None) -> ResolvedModule:
    """The module's resolved view: every type's declared terms merged with the defaults. With no
    declaration it is all defaults."""
    d = declared or DeclaredView()
    types = {t.local_name: _resolve_type(mod, t, i, d) for i, t in enumerate(mod.entity_types)}
    return ResolvedModule(ResolvedModuleView(d.title or mod.name, d.description), types)


def declared_from_text(text: str, mod: ModuleInfo) -> DeclaredView:
    """The view a registered document declares, or an empty one when it declares none or is
    not JSON (a document the registry accepted has passed `parse_view`)."""
    try:
        root = json.loads(text)
    except ValueError:
        return DeclaredView()
    if not isinstance(root, dict):
        return DeclaredView()
    declared, faults = parse_view(cast(dict[str, Any], root), mod)
    return DeclaredView() if faults else declared


# -- the checks at registration ----------------------------------------------------------------

Obj = dict[str, Any]


def _obj(v: Any) -> Obj:
    return cast(Obj, v) if isinstance(v, dict) else {}


def _list(v: Any) -> list[Any]:
    return cast(list[Any], v) if isinstance(v, list) else []


class _Checker:
    """Reads one document's `arras.view` terms and reports each fault with its document path."""

    def __init__(self, mod: ModuleInfo) -> None:
        self.mod = mod
        self.out: list[Violation] = []

    def fault(self, path: str, code: str, message: str) -> None:
        self.out.append(Violation(path, code, message))

    # -- values
    def text(
        self, v: Any, path: str, high: int, *, low: int = 1, over: str = "view_too_large"
    ) -> str | None:
        if not isinstance(v, str):
            self.fault(path, "view_bad_template", "a text value is required")
            return None
        if not low <= len(v) <= high:
            code = over if len(v) > high else "view_bad_template"
            self.fault(path, code, f"text of {low} to {high} characters is required")
            return None
        return v

    def flag(self, v: Any, path: str) -> bool | None:
        if not isinstance(v, bool):
            self.fault(path, "view_bad_template", "true or false is required")
            return None
        return v

    def named(
        self, v: Any, path: str, allowed: tuple[str, ...], code: str, what: str
    ) -> str | None:
        if isinstance(v, str) and v in allowed:
            return v
        self.fault(path, code, f"{what} is one of {', '.join(allowed)}")
        return None

    def terms(self, ext: Any, path: str, allowed: tuple[str, ...]) -> Obj:
        """The object at `path` with only the terms of `allowed`; every other one is a fault."""
        if not isinstance(ext, dict):
            self.fault(path, "view_unknown_term", "a view is an object of terms")
            return {}
        for k in cast(Obj, ext):
            if k in allowed:
                continue
            if k in _RELATIONSHIP_ONLY:
                code, why = "view_unknown_relationship", "is a term of a relationship"
            else:
                code, why = "view_unknown_term", "is not a term here"
            self.fault(f"{path}.{k}", code, f"{k!r} {why}")
        return {k: v for k, v in cast(Obj, ext).items() if k in allowed}

    def template(self, v: Any, path: str, t: EntityTypeInfo) -> str | None:
        text = self.text(v, path, MAX_TEMPLATE, over="view_bad_template")
        if text is None:
            return None
        try:
            names = placeholders(text)
        except TemplateError as e:
            self.fault(path, "view_bad_template", str(e))
            return None
        for n in names:
            if t.property(n) is None:
                self.fault(path, "view_unknown_property", f"{t.local_name} has no property {n!r}")
        return text

    # -- the places a term may be
    def module_terms(self, ext: Any, path: str) -> tuple[str | None, str | None]:
        found = self.terms(ext, path, MODULE_TERMS)
        title = description = None
        if "title" in found:
            title = self.text(found["title"], f"{path}.title", MAX_MODULE_TITLE)
        if "description" in found:
            description = self.text(
                found["description"], f"{path}.description", MAX_MODULE_DESCRIPTION, low=0
            )
        return title, description

    def record_terms(self, ext: Any, path: str, t: EntityTypeInfo) -> RecordTerms:
        found = self.terms(ext, path, RECORD_TERMS)
        label = plural = icon = tone = title = summary = None
        if "label" in found:
            label = self.text(found["label"], f"{path}.label", MAX_LABEL)
        if "pluralLabel" in found:
            plural = self.text(found["pluralLabel"], f"{path}.pluralLabel", MAX_LABEL)
        if "icon" in found:
            icon = self.named(found["icon"], f"{path}.icon", ICONS, "view_unknown_icon", "an icon")
        if "tone" in found:
            tone = self.named(found["tone"], f"{path}.tone", TONES, "view_unknown_tone", "a tone")
        if "title" in found:
            title = self.template(found["title"], f"{path}.title", t)
        if "summary" in found:
            summary = self.template(found["summary"], f"{path}.summary", t)
        sections = (
            self.sections(found["sections"], f"{path}.sections", t) if "sections" in found else None
        )
        search = self.search(found["search"], f"{path}.search", t) if "search" in found else None
        return RecordTerms(label, plural, icon, tone, title, summary, sections, search)

    def sections(self, v: Any, path: str, t: EntityTypeInfo) -> tuple[DeclaredSection, ...] | None:
        if not isinstance(v, list):
            self.fault(path, "view_bad_template", "sections is a list")
            return None
        items = cast(list[Any], v)
        if len(items) > MAX_SECTIONS:
            self.fault(path, "view_too_large", f"at most {MAX_SECTIONS} sections")
        placed: set[str] = set()
        out = [self.section(s, f"{path}[{i}]", t, placed) for i, s in enumerate(items)]
        return tuple(s for s in out if s is not None)

    def section(
        self, v: Any, path: str, t: EntityTypeInfo, placed: set[str]
    ) -> DeclaredSection | None:
        found = self.terms(v, path, SECTION_TERMS)
        label = self.text(found.get("label"), f"{path}.label", MAX_LABEL)
        props = _list(found.get("properties"))
        if not props or len(props) > MAX_SECTION_PROPERTIES:
            code = "view_too_large" if props else "view_bad_template"
            self.fault(f"{path}.properties", code, f"1 to {MAX_SECTION_PROPERTIES} properties")
        names: list[str] = []
        for i, p in enumerate(props):
            ppath = f"{path}.properties[{i}]"
            if not isinstance(p, str) or t.property(p) is None:
                self.fault(ppath, "view_unknown_property", f"{t.local_name} has no property {p!r}")
            elif p in placed:
                self.fault(ppath, "view_duplicate", f"{p!r} is in more than one section")
            else:
                placed.add(p)
                names.append(p)
        collapsed = False
        if "collapsed" in found:
            collapsed = bool(self.flag(found["collapsed"], f"{path}.collapsed"))
        return DeclaredSection(label or "", tuple(names), collapsed) if label else None

    def search(self, v: Any, path: str, t: EntityTypeInfo) -> tuple[str, ...] | None:
        if not isinstance(v, list):
            self.fault(path, "view_bad_template", "search is a list of property names")
            return None
        items = cast(list[Any], v)
        if len(items) > MAX_SEARCH:
            self.fault(path, "view_too_large", f"at most {MAX_SEARCH} search properties")
        chosen: list[str] = []
        for i, name in enumerate(items):
            p = t.property(name) if isinstance(name, str) else None
            if p is None:
                self.fault(f"{path}[{i}]", "view_unknown_property", f"no property {name!r}")
            elif not is_searchable_type(p):
                self.fault(f"{path}[{i}]", "view_bad_template", f"{name!r} is not a string")
            elif name in chosen:
                self.fault(f"{path}[{i}]", "view_duplicate", f"{name!r} is listed twice")
            else:
                chosen.append(name)
        return tuple(chosen)

    def field_terms(self, ext: Any, path: str, p: PropertyInfo) -> FieldTerms:
        found = self.terms(ext, path, FIELD_TERMS)
        label = fmt = hide = tones = None
        if "label" in found:
            label = self.text(found["label"], f"{path}.label", MAX_LABEL)
        if "format" in found:
            fmt = self.format(found["format"], f"{path}.format", p)
        if "hideWhenEmpty" in found:
            hide = self.flag(found["hideWhenEmpty"], f"{path}.hideWhenEmpty")
        if "tones" in found:
            tones = self.tones(found["tones"], f"{path}.tones", (fmt or default_format(p)))
        return FieldTerms(label, fmt, hide, tones)

    def format(self, v: Any, path: str, p: PropertyInfo) -> str | None:
        if not isinstance(v, str) or v not in FORMATS or not format_suits(p, v):
            self.fault(
                path, "view_format_mismatch", f"{p.name} ({p.type}) cannot be shown as {v!r}"
            )
            return None
        return v

    def tones(self, v: Any, path: str, fmt: str) -> dict[str, str] | None:
        if fmt != "badge":
            self.fault(path, "view_format_mismatch", "tones belong to the badge format")
            return None
        if not isinstance(v, dict):
            self.fault(path, "view_bad_template", "tones is an object of value to tone")
            return None
        items = cast(Obj, v)
        if len(items) > MAX_TONES:
            self.fault(path, "view_too_large", f"at most {MAX_TONES} tones")
        out: dict[str, str] = {}
        for k, tone in items.items():
            if (
                c := self.named(tone, f"{path}.{k}", TONES, "view_unknown_tone", "a tone")
            ) is not None:
                out[k] = c
        return out

    def relationship_terms(self, ext: Any, path: str, has_inverse: bool) -> RelationshipTerms:
        found = self.terms(ext, path, RELATIONSHIP_TERMS)
        label = inverse = hide = order = None
        if "label" in found:
            label = self.text(found["label"], f"{path}.label", MAX_LABEL)
        if "inverseLabel" in found:
            if has_inverse:
                inverse = self.text(found["inverseLabel"], f"{path}.inverseLabel", MAX_LABEL)
            else:
                self.fault(f"{path}.inverseLabel", "view_unknown_relationship", "no inverse")
        if "hideWhenEmpty" in found:
            hide = self.flag(found["hideWhenEmpty"], f"{path}.hideWhenEmpty")
        if "order" in found:
            n = found["order"]
            if isinstance(n, int) and not isinstance(n, bool) and 0 <= n <= 99:
                order = n
            else:
                self.fault(f"{path}.order", "view_bad_template", "order is an integer 0 to 99")
        return RelationshipTerms(label, inverse, hide, order)


def _size(*parts: Any) -> int:
    return len(json.dumps(parts, separators=(",", ":"), ensure_ascii=False).encode())


def _view_of(carrier: Any) -> Any:
    return _obj(_obj(carrier).get("extensions")).get(VOCABULARY)


def _has_view(carrier: Any) -> bool:
    return VOCABULARY in _obj(_obj(carrier).get("extensions"))


def parse_view(root: Mapping[str, Any], mod: ModuleInfo) -> tuple[DeclaredView, list[Violation]]:
    """Check and read the document's `arras.view` terms against the module's types.

    `mod` is the module the document defines (`umf.parse_module`'s reading of it). The terms are
    examined only when the document declares the vocabulary; a version this release does not
    support is the one fault then. Every fault carries its document path."""
    vocab = _obj(root.get("vocabularies")).get(VOCABULARY)
    if vocab is None:
        return DeclaredView(), []
    if _obj(vocab).get("version") != VERSION:
        path = f"vocabularies.{VOCABULARY}.version"
        v = Violation(path, "view_unsupported_version", f"arras.view {VERSION} is supported")
        return DeclaredView(), [v]
    c = _Checker(mod)
    module = _obj((_list(root.get("modules")) or [None])[0])
    declared = _read_module(c, root, module)
    total = _size(
        declared.title,
        declared.description,
        [_view_of(e) for e in _list(module.get("elements"))],
        [_view_of(r) for r in _list(module.get("relationships"))],
    )
    if total > MAX_DOCUMENT_BYTES:
        c.fault(
            "modules[0].extensions.arras.view",
            "view_too_large",
            "a document's views are at most 128 KiB",
        )
    return declared, c.out


def _read_module(c: _Checker, root: Mapping[str, Any], module: Obj) -> DeclaredView:
    if _has_view(root):
        c.fault(f"extensions.{VOCABULARY}", "view_unknown_term", "a view belongs to a module")
    title = description = None
    if _has_view(module):
        title, description = c.module_terms(_view_of(module), f"modules[0].extensions.{VOCABULARY}")
    for i, action in enumerate(_list(module.get("actions"))):
        if _has_view(action):
            c.fault(
                f"modules[0].actions[{i}].extensions.{VOCABULARY}",
                "view_unknown_term",
                "an action has no view",
            )
    records, fields = _read_elements(c, _list(module.get("elements")))
    rels = _read_relationships(c, _list(module.get("relationships")))
    return DeclaredView(title, description, records, fields, rels)


def _read_elements(
    c: _Checker, elements: list[Any]
) -> tuple[dict[str, RecordTerms], dict[tuple[str, str], FieldTerms]]:
    records: dict[str, RecordTerms] = {}
    fields: dict[tuple[str, str], FieldTerms] = {}
    for i, el in enumerate(_obj(e) for e in elements):
        if not _has_view(el):
            continue
        path = f"modules[0].elements[{i}].extensions.{VOCABULARY}"
        eid = str(el.get("id", ""))
        if el.get("kind") == "record":
            t = c.mod.entity_type(eid)
            if t is None:
                c.fault(path, "view_unknown_term", "only an entity record has a view")
                continue
            records[eid] = c.record_terms(_view_of(el), path, t)
        elif el.get("kind") == "field":
            type_name, _, prop = eid.partition(".")
            t = c.mod.entity_type(type_name)
            p = t.property(prop) if t else None
            if p is None:
                c.fault(path, "view_unknown_term", "only the field of an entity record has a view")
                continue
            fields[(type_name, prop)] = c.field_terms(_view_of(el), path, p)
        else:
            c.fault(path, "view_unknown_term", "only a record or a field has a view")
    _check_record_sizes(c, elements)
    return records, fields


def _check_record_sizes(c: _Checker, elements: list[Any]) -> None:
    """A record's view, with those of its fields, at most 16 KiB; the fault is at the first
    element of the record that declares a view."""
    sizes: dict[str, int] = {}
    first: dict[str, int] = {}
    for i, el in enumerate(_obj(e) for e in elements):
        eid = str(el.get("id", ""))
        owner = eid.partition(".")[0] if el.get("kind") == "field" else eid
        if _has_view(el):
            sizes[owner] = sizes.get(owner, 0) + _size(_view_of(el))
            first.setdefault(owner, i)
    for owner, n in sizes.items():
        if n > MAX_RECORD_BYTES:
            path = f"modules[0].elements[{first[owner]}].extensions.{VOCABULARY}"
            c.fault(path, "view_too_large", f"{owner}'s view is at most 16 KiB")


def _read_relationships(c: _Checker, rels: list[Any]) -> dict[str, RelationshipTerms]:
    out: dict[str, RelationshipTerms] = {}
    for i, rel in enumerate(_obj(r) for r in rels):
        if not _has_view(rel):
            continue
        path = f"modules[0].relationships[{i}].extensions.{VOCABULARY}"
        name = str(rel.get("name", ""))
        if _size(_view_of(rel)) > MAX_RECORD_BYTES:
            c.fault(path, "view_too_large", "a relationship's view is at most 16 KiB")
        out[name] = c.relationship_terms(_view_of(rel), path, bool(rel.get("inverse")))
    return out
