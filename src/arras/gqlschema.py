# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""GraphQL schemas built from the registry (CONTRACT-006): one meta schema, one per module.

This module sits below `arras.core`, which builds a module's schema to refuse a registration the
console could not serve. It reaches the session only through the request context, so the one
`core` name it uses is a type.

Read-only: there is no Mutation and no Subscription. Every resolver reads through the interface
as the viewer's principal, and a type's relationship fields come from the same `alias.*` row as
its properties, never one query per entity.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from graphql import (
    GraphQLArgument,
    GraphQLBoolean,
    GraphQLEnumType,
    GraphQLError,
    GraphQLField,
    GraphQLInt,
    GraphQLInterfaceType,
    GraphQLList,
    GraphQLNonNull,
    GraphQLObjectType,
    GraphQLScalarType,
    GraphQLSchema,
    GraphQLString,
    validate_schema,
)

from arras.entityread import (
    FACT_FIELDS,  # noqa: F401
    MAX_RELATIONSHIP_KEYS,  # noqa: F401
    entity_rows,
    entity_sql,
    relationships_of,
    selected_fields,
)
from arras.errors import (
    ArrasError,
    Conflict,
    Invalid,
    NotYetCurrent,
    PolicyRefused,
    Refused,
    Unavailable,
    Unsupported,
    Violation,
)
from arras.model import EntityTypeInfo, ModuleInfo, PropertyInfo
from arras.names import quoted, quoted_type
from arras.searchplan import MAX_LIMIT as MAX_SEARCH_LIMIT
from arras.searchplan import SearchPage
from arras.serialize import jsonable
from arras.types import Freshness, Rows
from arras.view import ResolvedModule, ResolvedView

if TYPE_CHECKING:
    from arras.core import Ontology

MAX_LIMIT = 100
MAX_ENTITIES = 1000
MAX_TARGETS = 100

# --- scalars -------------------------------------------------------------------------------


def _passthrough(v: Any) -> Any:
    return jsonable(v, tag=False)


JSON = GraphQLScalarType("JSON", serialize=_passthrough, parse_value=lambda v: v)


def _datetime(v: Any) -> str:
    """RFC 3339 text with the offset as authored; a time with no offset is read as UTC."""
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=UTC)).isoformat()
    return str(v)


DateTime = GraphQLScalarType("DateTime", serialize=_datetime)
BigInt = GraphQLScalarType("BigInt", serialize=lambda v: str(v), parse_value=lambda v: int(v))
DecimalScalar = GraphQLScalarType(
    "Decimal", serialize=lambda v: str(v) if isinstance(v, Decimal | int) else str(v)
)
Base64 = GraphQLScalarType(
    "Base64",
    serialize=lambda v: base64.b64encode(v).decode() if isinstance(v, bytes) else str(v),
)
Consistency = GraphQLEnumType("Consistency", {"LATEST": "latest", "BULK": "bulk"})
_SCALARS = {
    "string": GraphQLString,
    "integer": BigInt,
    "decimal": DecimalScalar,
    "boolean": GraphQLBoolean,
    "binary": Base64,
    "timestamp": DateTime,
}

Freshness_ = GraphQLObjectType(
    "Freshness",
    lambda: {
        "backend": GraphQLField(GraphQLNonNull(GraphQLString), resolve=lambda f, i: f.backend),
        "asOf": GraphQLField(GraphQLNonNull(GraphQLString), resolve=lambda f, i: f.as_of.value),
        "at": GraphQLField(GraphQLNonNull(DateTime), resolve=lambda f, i: f.as_of.at),
        "consistency": GraphQLField(
            GraphQLNonNull(Consistency), resolve=lambda f, i: f.consistency
        ),
    },
)

# --- errors --------------------------------------------------------------------------------


def error_code(e: BaseException) -> tuple[str, dict[str, Any]]:
    """The `extensions.code` for an interface error, and what else to say about it."""
    if isinstance(e, Refused):
        more: dict[str, Any] = {"backend": e.backend, "reason": e.reason}
        if isinstance(e, PolicyRefused):
            more["policy_code"] = e.policy_code
        return "REFUSED", more
    if isinstance(e, Unavailable):
        return "UNAVAILABLE", {"backend": e.backend, "reason": e.reason}
    if isinstance(e, Unsupported):
        return "UNSUPPORTED", {"supported": e.supported}
    if isinstance(e, NotYetCurrent):
        return "NOT_YET_CURRENT", {"backend": e.backend, "token": e.token}
    if isinstance(e, Invalid):
        return "BAD_QUERY", {"violations": jsonable(e.violations)}
    return "INTERNAL_ERROR", {}


def gql_error(e: BaseException) -> GraphQLError:
    code, more = error_code(e)
    msg = str(e) if isinstance(e, ArrasError) else "internal error"  # no detail for a bug
    return GraphQLError(msg, extensions={"code": code, **more})


def coded(code: str, message: str) -> GraphQLError:
    return GraphQLError(message, extensions={"code": code})


# --- per-request state ---------------------------------------------------------------------


@dataclass
class RequestContext:
    """One request: the viewer's session, the one registry snapshot, and its entity budget."""

    ontology: Ontology
    module: ModuleInfo | None = None
    entities: int = 0
    targets: int = 0
    keys: dict[str, str | None] = field(default_factory=dict[str, str | None])
    revision: Mapping[str, Any] = field(default_factory=dict[str, Any])
    modules: dict[str, ModuleInfo] = field(default_factory=dict[str, ModuleInfo])  # as described
    views: dict[str, ResolvedModule] = field(default_factory=dict[str, ResolvedModule])

    def module_view(self, name: str) -> ResolvedModule:
        """A described module's resolved view (CONTRACT-010), resolved once per request."""
        if name not in self.views:
            self.views[name] = self.ontology.view_of(self.modules[name])
        return self.views[name]

    def type_view(self, qualified: str) -> ResolvedView:
        found = self.module_view(qualified.partition(".")[0]).of(qualified)
        if found is None:
            raise coded("INTERNAL_ERROR", "a type has no view")
        return found

    def reserve(self, n: int) -> None:
        """Set aside `n` entities before a query runs, so a request cannot read past its budget."""
        if self.entities + n > MAX_ENTITIES:
            raise coded("COST_EXCEEDED", f"a request resolves at most {MAX_ENTITIES} entities")
        self.entities += n

    def try_reserve(self, n: int) -> bool:
        """Like `reserve`, but a request that is full says so instead of failing (search names a
        type it could not afford as not searched)."""
        if self.entities + n > MAX_ENTITIES:
            return False
        self.entities += n
        return True

    def reserve_target(self) -> None:
        """A `Ref.target` is one by-key query of its own, so there are only so many of them."""
        if self.targets >= MAX_TARGETS:
            raise coded(
                "COST_EXCEEDED", f"a request opens at most {MAX_TARGETS} relationship targets"
            )
        self.reserve(1)
        self.targets += 1

    def settle(self, reserved: int, actual: int) -> None:
        self.entities -= reserved - actual

    def check_revision(self, rows: Rows) -> None:
        """Every resolver in a request runs under the one registry revision the request stated."""
        if self.module is not None and rows.revision != self.module.revision:
            raise coded(
                "REVISION_CHANGED",
                "the module's revision changed while the request ran; ask again",
            )


def _guard(fn: Callable[..., Any]) -> Callable[..., Any]:
    def run(*a: Any, **k: Any) -> Any:
        try:
            return fn(*a, **k)
        except GraphQLError:
            raise
        except ArrasError as e:
            raise gql_error(e) from e

    return run


# --- meta schema ---------------------------------------------------------------------------


def _resolver(getter: Callable[..., Any], with_info: bool) -> Callable[[Any, Any], Any]:
    return (lambda o, i: getter(o, i)) if with_info else (lambda o, i: getter(o))


def _rec(type_name: str, /, **fields_: tuple[Any, ...]) -> GraphQLObjectType:
    """An object type whose fields read the parent: `(type, getter)`, or `(type, getter, True)`
    for a getter that also takes the resolve info."""
    return GraphQLObjectType(
        type_name,
        lambda: {
            k: GraphQLField(spec[0], resolve=_resolver(spec[1], len(spec) > 2))
            for k, spec in fields_.items()
        },
    )


_NN = GraphQLNonNull
_S = _NN(GraphQLString)


def _list(t: Any) -> Any:
    return _NN(GraphQLList(_NN(t)))


def _mult(m: Any) -> str:
    return str(m)


PropertyInfoT = _rec(
    "PropertyInfo",
    name=(_S, lambda p: p.name),
    type=(_S, lambda p: p.type),
    required=(_NN(GraphQLBoolean), lambda p: p.required),
    cardinality=(_S, lambda p: p.cardinality),
)
BackendStatusT = _rec(
    "BackendStatus",
    backend=(_S, lambda s: s[0]),
    available=(_NN(GraphQLBoolean), lambda s: s[1].available),
    reason=(GraphQLString, lambda s: s[1].reason),
    detail=(GraphQLString, lambda s: s[1].detail or None),
    position=(GraphQLString, lambda s: s[1].position.value if s[1].position else None),
    lag=(GraphQLString, lambda s: None if s[1].lag is None else str(s[1].lag)),
)
ViewSectionT = _rec(
    "ViewSection",
    label=(_S, lambda s: s.label),
    properties=(_list(GraphQLString), lambda s: list(s.properties)),
    collapsed=(_NN(GraphQLBoolean), lambda s: s.collapsed),
)
FieldViewT = _rec(
    "FieldView",
    property=(_S, lambda f: f.property),
    label=(_S, lambda f: f.label),
    format=(_S, lambda f: f.format),
    hideWhenEmpty=(_NN(GraphQLBoolean), lambda f: f.hide_when_empty),
    tones=(JSON, lambda f: None if f.tones is None else dict(f.tones)),
)
RelationshipViewT = _rec(
    "RelationshipView",
    field=(_S, lambda r: r.field),
    label=(_S, lambda r: r.label),
    hideWhenEmpty=(_NN(GraphQLBoolean), lambda r: r.hide_when_empty),
    order=(_NN(GraphQLInt), lambda r: r.order),
)
ViewT = _rec(
    "View",
    declared=(_NN(GraphQLBoolean), lambda v: v.declared),
    label=(_S, lambda v: v.label),
    pluralLabel=(_S, lambda v: v.plural_label),
    icon=(_S, lambda v: v.icon),
    tone=(_S, lambda v: v.tone),
    title=(_S, lambda v: v.title),
    summary=(GraphQLString, lambda v: v.summary),
    sections=(_list(ViewSectionT), lambda v: list(v.sections)),
    search=(_list(GraphQLString), lambda v: list(v.search)),
    fields=(_list(FieldViewT), lambda v: list(v.fields)),
    relationships=(_list(RelationshipViewT), lambda v: list(v.relationships)),
)
ModuleViewT = _rec(
    "ModuleView",
    title=(_S, lambda v: v.title),
    description=(GraphQLString, lambda v: v.description),
)
EntityTypeInfoT = _rec(
    "EntityTypeInfo",
    name=(_S, lambda t: t.name),
    key=(_S, lambda t: t.key),
    properties=(_list(PropertyInfoT), lambda t: list(t.properties)),
    capabilities=(_NN(JSON), lambda t: dict(t.capabilities)),
    view=(_NN(ViewT), _guard(lambda t, info: info.context.request.type_view(t.name)), True),
)
RelationshipInfoT = _rec(
    "RelationshipInfo",
    name=(_S, lambda r: r.name),
    source=(_list(GraphQLString), lambda r: list(r.source)),
    target=(_list(GraphQLString), lambda r: list(r.target)),
    sourceMultiplicity=(_S, lambda r: _mult(r.source_multiplicity)),
    targetMultiplicity=(_S, lambda r: _mult(r.target_multiplicity)),
    lifecycle=(_S, lambda r: r.lifecycle),
    inverse=(GraphQLString, lambda r: r.inverse),
)
InputSpecT = _rec(
    "InputSpec",
    name=(_S, lambda s: s.name),
    type=(_S, lambda s: s.type),
    kind=(_S, lambda s: s.kind),
    cardinality=(_S, lambda s: s.cardinality),
)
ActionInfoT = _rec(
    "ActionInfo",
    name=(_S, lambda a: a.name),
    description=(_S, lambda a: a.description),
    inputs=(_NN(JSON), lambda a: a.inputs),
    inputSpecs=(_list(InputSpecT), lambda a: list(a.inputs)),
    preconditions=(_NN(JSON), lambda a: a.preconditions),
    effects=(_NN(JSON), lambda a: a.effects),
)
ModuleT = _rec(
    "Module",
    name=(_S, lambda m: m.name),
    record=(_S, lambda m: m.placement.record),
    replicas=(_list(GraphQLString), lambda m: list(m.placement.replicas)),
    providers=(_NN(JSON), lambda m: dict(m.placement.providers)),
    revision=(_NN(JSON), lambda m: m.revision),
    entityTypes=(_list(EntityTypeInfoT), lambda m: list(m.entity_types)),
    relationships=(_list(RelationshipInfoT), lambda m: list(m.relationships)),
    actions=(_list(ActionInfoT), lambda m: list(m.actions)),
    view=(
        _NN(ModuleViewT),
        _guard(lambda m, info: info.context.request.module_view(m.name).module),
        True,
    ),
)


def build_meta_schema() -> GraphQLSchema:
    def modules(_: Any, info: Any) -> Any:
        described = info.context.ontology.describe()
        info.context.request.modules.update({m.name: m for m in described})
        return described

    def status(_: Any, info: Any) -> Any:
        return list(info.context.arras.status().items())

    query = GraphQLObjectType(
        "Query",
        {
            "modules": GraphQLField(_list(ModuleT), resolve=_guard(modules)),
            "status": GraphQLField(_list(BackendStatusT), resolve=status),
        },
    )
    return GraphQLSchema(query=query)


# --- the search read (CONTRACT-010, section C) -----------------------------------------------

SegmentT = _rec(
    "_Segment",
    text=(_S, lambda s: s.text),
    mark=(_NN(GraphQLBoolean), lambda s: s.mark),
)
TypeCountT = _rec(
    "_TypeCount",
    type=(_S, lambda c: c.type),
    count=(_NN(GraphQLInt), lambda c: c.count),
    atLeast=(_NN(GraphQLBoolean), lambda c: c.at_least),
)
NotSearchedT = _rec(
    "_NotSearched",
    type=(_S, lambda n: n.type),
    reason=(_S, lambda n: n.reason),
    backend=(GraphQLString, lambda n: n.backend),
)


def _hit_entity(mod: ModuleInfo, hit: Any) -> dict[str, Any]:
    """The matched entity as `Query.<t>` returns it, from the row the search read."""
    t = mod.entity_type(hit.type)
    assert t is not None
    return _node(t, hit.row, hit.freshness)


def _search_types(mod: ModuleInfo, entity: GraphQLInterfaceType) -> list[GraphQLObjectType]:
    """`_SearchPage`, `_SearchHit` and the types they use; a hit's `entity` is the module's own."""
    hit = _rec(
        "_SearchHit",
        type=(_S, lambda h: h.type),
        key=(_S, lambda h: h.key),
        score=(_NN(GraphQLInt), lambda h: h.score),
        label=(_S, lambda h: h.label),
        excerpt=(GraphQLList(_NN(SegmentT)), lambda h: list(h.excerpt) if h.excerpt else None),
        matched=(_list(GraphQLString), lambda h: list(h.matched)),
        entity=(_NN(entity), lambda h: _hit_entity(mod, h)),
    )
    page = _rec(
        "_SearchPage",
        text=(_S, lambda p: p.text),
        hits=(_list(hit), lambda p: list(p.hits)),
        counts=(_list(TypeCountT), lambda p: list(p.counts)),
        notSearched=(_list(NotSearchedT), lambda p: list(p.not_searched)),
        truncated=(_NN(GraphQLBoolean), lambda p: p.truncated),
        freshness=(_list(Freshness_), lambda p: list(p.freshness)),
    )
    return [page, hit, SegmentT, TypeCountT, NotSearchedT]


def _fail_if_nothing_searched(page: SearchPage) -> None:
    """A search that searched no type is an error, by what stopped it (CONTRACT-010, Errors)."""
    if page.counts or not page.not_searched:
        return
    reasons = {n.reason for n in page.not_searched}
    if "unavailable" in reasons:
        down = next(n for n in page.not_searched if n.reason == "unavailable")
        raise Unavailable(down.backend or "arras", "unreachable")
    if "over_budget" in reasons:
        raise coded("COST_EXCEEDED", f"a request resolves at most {MAX_ENTITIES} entities")
    raise Unsupported("text search", ["a type is searched where its backend declares search"])


def _search_field(mod: ModuleInfo, page: GraphQLObjectType) -> GraphQLField:
    @_guard
    def resolve(
        _: Any,
        info: Any,
        text: str,
        types: list[str] | None = None,
        limit: int | None = 20,
        consistency: str = "latest",
        atLeast: str | None = None,
    ) -> Any:
        limit = 20 if limit is None else limit
        if not 1 <= limit <= MAX_SEARCH_LIMIT:
            raise coded("LIMIT_EXCEEDED", f"limit is 1 to {MAX_SEARCH_LIMIT}")
        ctx = info.context.request
        revision = ctx.module.revision if ctx.module is not None else None
        try:
            found = ctx.ontology.search(
                mod.name,
                text,
                types,
                limit,
                consistency,
                atLeast,
                budget=ctx,
                revision=revision,
            )
        except Conflict as e:
            if e.reason != "revision":
                raise
            raise coded(
                "REVISION_CHANGED", "the module's revision changed while the search ran; ask again"
            ) from None
        _fail_if_nothing_searched(found)
        return found

    return GraphQLField(
        _NN(page),
        args={
            "text": GraphQLArgument(_S),
            "types": GraphQLArgument(GraphQLList(_S)),
            "limit": GraphQLArgument(GraphQLInt, default_value=20),
            "consistency": GraphQLArgument(Consistency, default_value="latest"),
            "atLeast": GraphQLArgument(GraphQLString),
        },
        resolve=resolve,
    )


# --- the schema generated for one module ---------------------------------------------------


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:]


def _gql_type(p: PropertyInfo) -> Any:
    base = _SCALARS.get(p.type, JSON) if p.scalar else JSON
    if p.cardinality == "many":
        base = GraphQLList(_NN(base))
    return _NN(base) if p.required else base


def build_module_schema(mod: ModuleInfo) -> GraphQLSchema:
    """The schema for `mod` at its current revision; `Invalid` (`invalid_name`) if it cannot be."""
    for r in mod.relationships:
        if len(r.source) > 1 or len(r.target) > 1:  # a Ref names one type; v1 serves one end each
            raise Invalid(
                [
                    Violation(
                        f"relationships.{r.name}",
                        "invalid_name",
                        "the console serves one type per end",
                    )
                ]
            )
    entity = GraphQLInterfaceType(
        "Entity",
        lambda: {
            "key": GraphQLField(_S),
            "type": GraphQLField(_S),
            "version": GraphQLField(BigInt),
            "freshness": GraphQLField(_NN(Freshness_)),
            **{k: GraphQLField(t) for k, (t, _col) in _ATTRIBUTION.items()},
        },
        resolve_type=lambda value, info, _t: value["__type__"],
    )
    ref = _ref_type(mod, entity)
    foreign = GraphQLObjectType(
        FOREIGN,
        {
            "key": GraphQLField(_S, resolve=lambda n, i: n["__key__"]),
            "type": GraphQLField(_S, resolve=lambda n, i: n["__qualified__"]),
            "version": GraphQLField(BigInt, resolve=lambda n, i: n.get("_version")),
            "freshness": GraphQLField(_NN(Freshness_), resolve=lambda n, i: n["__freshness__"]),
            **_attribution_fields(),  # null: another module's entity is read from its own endpoint
        },
        interfaces=[entity],
    )
    objects: dict[str, GraphQLObjectType] = {}
    pages: dict[str, GraphQLObjectType] = {}
    for t in mod.entity_types:
        objects[t.name] = _entity_type(mod, t, entity, ref)
        pages[t.name] = _page_type(t, objects[t.name])
    query_fields: dict[str, GraphQLField] = {}
    for t in mod.entity_types:
        lf = _lower_first(t.local_name)
        query_fields[lf] = _by_key(mod, t, objects[t.name])
        query_fields[lf + "List"] = _list_field(mod, t, pages[t.name])
    search_types = _search_types(mod, entity)
    query_fields["_search"] = _search_field(mod, search_types[0])
    try:
        schema = GraphQLSchema(
            query=GraphQLObjectType("Query", query_fields),
            types=[*objects.values(), *pages.values(), foreign, ref, Freshness_, *search_types],
        )
    except TypeError as e:  # two types of one name, and the like
        raise Invalid([Violation("module", "invalid_name", str(e))]) from None
    errors = validate_schema(schema)
    if errors:
        raise Invalid([Violation("module", "invalid_name", e.message) for e in errors])
    return schema


# Who created and last changed an entity: the `_created_*` and `_updated_*` columns of `alias.*`.
_ATTRIBUTION: dict[str, tuple[Any, str]] = {
    "createdBy": (GraphQLString, "_created_by"),
    "createdAt": (DateTime, "_created_at"),
    "updatedBy": (GraphQLString, "_updated_by"),
    "updatedAt": (DateTime, "_updated_at"),
}


def _attribution_fields() -> dict[str, GraphQLField]:
    return {
        k: GraphQLField(t, resolve=lambda n, i, col=col: n.get(col))
        for k, (t, col) in _ATTRIBUTION.items()
    }


FOREIGN = "ForeignEntity"  # the `Entity` a relationship target of another module comes back as


def _ref_type(mod: ModuleInfo, entity: GraphQLInterfaceType) -> GraphQLObjectType:
    """`Ref`: who is on the other end, and `target` to open it (one by-key query, budgeted)."""

    @_guard
    def target(r: Mapping[str, Any], info: Any) -> Any:
        ctx = info.context.request
        module, _, local = r["type"].partition(".")
        own = module == mod.name
        key_prop = _key_property(ctx, mod if own else None, module, local)
        if key_prop is None:  # another module the viewer cannot read, or a type it no longer has
            return None
        ctx.reserve_target()
        try:
            where = f" WHERE x.{quoted(key_prop)} = :key"
            t_own = mod.entity_type(local) if own else None
            if t_own:
                rows = _entities(
                    info, mod, t_own, where, {"key": r["key"]}, 1, selected_fields(info), limit=1
                )
            else:
                sql = (
                    f"SELECT x.* FROM {quoted_type(r['type'])} x{where}"
                    f" ORDER BY x.{quoted(key_prop)} LIMIT 1"
                )
                rows = _rows(info, module, sql, {"key": r["key"]}, limit=1)
        except (Refused, Invalid):
            ctx.settle(1, 0)
            return None
        ctx.settle(1, len(rows.rows))
        if own:
            ctx.check_revision(rows)
        if not rows.rows:
            return None
        row = rows.rows[0]
        if own:
            return _node(mod.entity_type(local), row, rows.freshness)  # type: ignore[arg-type]
        return {
            "__type__": FOREIGN,
            "__qualified__": r["type"],
            "__key__": r["key"],
            "__freshness__": rows.freshness,
            "_version": row.get("_version"),
        }

    return GraphQLObjectType(
        "Ref",
        lambda: {
            "module": GraphQLField(_S, resolve=lambda r, i: r["type"].partition(".")[0]),
            "type": GraphQLField(_S, resolve=lambda r, i: r["type"]),
            "key": GraphQLField(_S, resolve=lambda r, i: r["key"]),
            "target": GraphQLField(entity, resolve=target),
        },
    )


def _key_property(
    ctx: RequestContext, own: ModuleInfo | None, module: str, local: str
) -> str | None:
    """The key property of a type, from this module or, for another, what the viewer may describe."""
    if own is not None:
        t = own.entity_type(local)
        return t.key if t else None
    name = f"{module}.{local}"
    if name not in ctx.keys:
        try:
            m = ctx.ontology.describe(module)[0]
            t = m.entity_type(local)
            ctx.keys[name] = t.key if t else None
        except (Refused, Invalid):
            ctx.keys[name] = None
    return ctx.keys[name]


def _entity_type(
    mod: ModuleInfo, t: EntityTypeInfo, entity: GraphQLInterfaceType, ref: GraphQLObjectType
) -> GraphQLObjectType:
    def fields() -> dict[str, GraphQLField]:
        out: dict[str, GraphQLField] = {
            "key": GraphQLField(_S, resolve=lambda n, i: n["__key__"]),
            "type": GraphQLField(_S, resolve=lambda n, i: t.name),
            "version": GraphQLField(BigInt, resolve=lambda n, i: n.get("_version")),
            "freshness": GraphQLField(_NN(Freshness_), resolve=lambda n, i: n["__freshness__"]),
            **_attribution_fields(),
        }
        for p in t.properties:
            out[p.name] = GraphQLField(_gql_type(p), resolve=lambda n, i, name=p.name: n.get(name))
        for name, other in relationships_of(mod, t):
            out[name] = GraphQLField(
                _list(ref),
                resolve=lambda n, i, name=name, other=other: [
                    {"type": other, "key": k} for k in n.get(name, [])
                ],
            )
        return out

    return GraphQLObjectType(t.local_name, fields, interfaces=[entity])


def _page_type(t: EntityTypeInfo, obj: GraphQLObjectType) -> GraphQLObjectType:
    return GraphQLObjectType(
        t.local_name + "Page",
        {
            "items": GraphQLField(_list(obj), resolve=lambda p, i: p["items"]),
            "truncated": GraphQLField(_NN(GraphQLBoolean), resolve=lambda p, i: p["truncated"]),
            "freshness": GraphQLField(_NN(Freshness_), resolve=lambda p, i: p["freshness"]),
        },
    )


def _node(t: EntityTypeInfo, row: Mapping[str, Any], fresh: Freshness) -> dict[str, Any]:
    return {
        **row,
        "__type__": t.local_name,
        "__key__": row[t.key],
        "__freshness__": fresh,
    }


def _rows(info: Any, module: str, sql: str, params: dict[str, Any], **kw: Any) -> Rows:
    return info.context.ontology.query(module, sql, params, **kw)


def _entities(
    info: Any,
    mod: ModuleInfo,
    t: EntityTypeInfo,
    where: str,
    params: dict[str, Any],
    count: int,
    wanted: frozenset[str] | None,
    **kw: Any,
) -> Rows:
    """The rows of an entity read, each relationship's keys under its name. A backend that cannot
    run the narrow projection (`Unsupported`: the memory adapter does not take a decimal without
    its precision and scale as a column) is asked for the whole entity."""
    narrow = entity_sql(mod, t, where, count, wanted)
    try:
        rows = _rows(info, mod.name, narrow, params, **kw)
    except Unsupported:
        whole = entity_sql(mod, t, where, count)
        if whole == narrow:
            raise
        rows = _rows(info, mod.name, whole, params, **kw)
    return entity_rows(mod, t, rows)


def _by_key(mod: ModuleInfo, t: EntityTypeInfo, obj: GraphQLObjectType) -> GraphQLField:
    @_guard
    def resolve(
        _: Any, info: Any, key: str, consistency: str = "latest", atLeast: str | None = None
    ) -> Any:
        info.context.reserve(1)
        rows = _entities(
            info,
            mod,
            t,
            f" WHERE x.{quoted(t.key)} = :key",
            {"key": key},
            1,
            selected_fields(info),
            limit=1,
            consistency=consistency,
            at_least=atLeast,
        )
        info.context.settle(1, len(rows.rows))
        info.context.request.check_revision(rows)
        if not rows.rows:
            return None
        return _node(t, rows.rows[0], rows.freshness)

    return GraphQLField(
        obj,
        args={
            "key": GraphQLArgument(_S),
            "consistency": GraphQLArgument(Consistency, default_value="latest"),
            "atLeast": GraphQLArgument(GraphQLString),
        },
        resolve=resolve,
    )


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _list_field(mod: ModuleInfo, t: EntityTypeInfo, page: GraphQLObjectType) -> GraphQLField:
    properties = {p.name for p in t.properties}
    relationships = {n for n, _ in relationships_of(mod, t)}

    @_guard
    def resolve(
        _: Any,
        info: Any,
        filter: Any = None,  # noqa: A002
        limit: int | None = 50,
        consistency: str = "latest",
        afterKey: str | None = None,  # noqa: N803
    ) -> Any:
        limit = 50 if limit is None else limit
        if not 1 <= limit <= MAX_LIMIT:
            raise coded("LIMIT_EXCEEDED", f"limit is 1 to {MAX_LIMIT}")
        if filter is not None and not isinstance(filter, Mapping):
            raise coded("BAD_QUERY", "filter is an object")
        clauses: list[str] = []
        params: dict[str, Any] = {}
        for i, (k, v) in enumerate((filter or {}).items()):
            if not _IDENT.fullmatch(k) or k not in properties | relationships:
                raise coded(
                    "BAD_QUERY", f"{k!r} is not a property or relationship of {t.local_name}"
                )
            # a relationship filter is Weft's HAS_RELATED; a property, an equality
            clauses.append(
                f"HAS_RELATED(x.{quoted(k)}, KEY(:p{i}))"
                if k in relationships
                else f"x.{quoted(k)} = :p{i}"
            )
            params[f"p{i}"] = v
        if afterKey is not None:  # the next page: the keyset on the key, the value a parameter
            if not isinstance(afterKey, str):
                raise coded("BAD_QUERY", "afterKey is a key")
            clauses.append(f"x.{quoted(t.key)} > :after")
            params["after"] = afterKey
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        info.context.reserve(limit)  # before the query, not after it
        rows = _entities(
            info,
            mod,
            t,
            where,
            params,
            limit + 1,
            selected_fields(info, under="items"),
            limit=limit,
            consistency=consistency,
        )
        info.context.settle(limit, len(rows.rows))
        info.context.request.check_revision(rows)
        return {
            "items": [_node(t, r, rows.freshness) for r in rows.rows],
            "truncated": rows.truncated,
            "freshness": rows.freshness,
        }

    return GraphQLField(
        page,  # nullable: a failing list is its own field's error, not the request's
        args={
            "filter": GraphQLArgument(JSON),
            "limit": GraphQLArgument(GraphQLInt, default_value=50),
            "consistency": GraphQLArgument(Consistency, default_value="latest"),
            # the next page: entities whose key follows this one (the last key of the page before)
            "afterKey": GraphQLArgument(GraphQLString),
        },
        resolve=resolve,
    )
