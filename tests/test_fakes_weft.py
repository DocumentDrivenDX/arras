# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The memory adapter's stand-in for Weft: its declared subset, read and resolved. It is not Weft;
`test_weft_parser` checks the statements Arras itself writes against Weft's own parser, and
`test_weft_relational` holds the subset's relational reads against it."""

from decimal import Decimal
from pathlib import Path

import pytest

from arras import Invalid, Unsupported
from arras.fakes_plan import Cond, Ref, Rel, resolve_plan
from arras.fakes_sql import Bound
from arras.fakes_weft import (
    COUNT,
    ENTITY,
    GENERAL,
    RELATED,
    SUBSET,
    WEFT,
    Ident,
    check_profiles,
    parse,
    profiles_needed,
    resolve,
)
from arras.results import WeftSupport
from arras.types import Statement
from arras.umf import parse_module

NAMED = WeftSupport(WEFT.version, (ENTITY, RELATED, COUNT))  # the named profiles, no `general`


def test_whole_entity_by_key() -> None:
    q = parse("SELECT s.* FROM catalog.Solution s WHERE s.code = 'sol-pipeline-01'")
    assert [i.kind for i in q.items] == ["star"]
    assert (
        q.source.module and q.source.module.text == "catalog" and q.source.type.text == "Solution"
    )
    assert q.predicates[0].left[0].name == Ident("code") and q.predicates[0].right == (
        "sol-pipeline-01",
    )


def test_columns_and_keywords_case_insensitive() -> None:
    q = parse("select u.code, u.name from catalog.UseCase as u where u.workArea = 'a''b';")
    assert [i.col.name.text for i in q.items if i.col] == ["code", "name"]
    assert q.predicates[0].right[0] == "a'b"


def test_literals_and_params() -> None:
    q = parse(
        "SELECT u.* FROM m.T u WHERE u.a = 3 AND u.b = 1.50 AND u.c = TRUE AND u.d = :x",
        {"x": "v"},
    )
    # a parameter's value is kept apart from a literal: Weft types the two differently
    assert [p.right[0] for p in q.predicates] == [3, Decimal("1.50"), True, Bound("x", "v")]
    assert q.markers == ("x",)  # the one parameter, bound in place


def test_count_group_by() -> None:
    q = parse("SELECT u.workArea, COUNT(*) FROM catalog.UseCase u GROUP BY u.workArea")
    assert [g.name.text for g in q.group_by] == ["workArea"]
    assert [i.kind for i in q.items] == ["col", "count"]


def test_quoted_identifier_matches_exactly() -> None:
    q = parse('SELECT u.* FROM m.T u WHERE u."Name" = 1')
    name = q.predicates[0].left[0].name
    assert name.matches("Name") and not name.matches("name")
    assert Ident("name").matches("NAME")


@pytest.mark.parametrize(
    ("sql", "construct"),
    [
        ("SELECT * FROM m.T u", "bare *"),
        ("SELECT u.* FROM m.T u WHERE u.a = 1 OR u.a = 2", "OR"),
        ("SELECT u.* FROM m.T u ORDER BY u.a DESC", "DESC"),
        ("SELECT u.* FROM m.T u LIMIT :n", "a bound other than a whole number"),
        ("SELECT u.* FROM m.T u LIMIT 5 OFFSET 5", "OFFSET"),
        ("SELECT u.* FROM m.T u LEFT JOIN m.S s ON s.a = u.a", "outer join"),
        ("SELECT u.* FROM m.T u, m.S s", "a comma join"),
        ("SELECT u.* FROM m.T u JOIN m.S s ON s.a = 1", "an ON condition other than a.x = b.y"),
        ("SELECT u.* FROM m.T u WHERE u.a < 1", "<"),
        ("SELECT u.* FROM m.T u WHERE u.a = ?", "positional marker"),
        ("SELECT u.* FROM m.T u WHERE u.a IN (1)", "IN"),
        ("SELECT DISTINCT u.a FROM m.T u", "DISTINCT"),
        ("SELECT u.* FROM m.T u WHERE (u.a) = (1)", "a tuple comparison other than >"),
        ("SELECT u.* FROM m.T u WHERE (SELECT u.a FROM m.T u) > (1)", "subquery"),
        ("SELECT upper(u.a) FROM m.T u", "function upper"),
    ],
)
def test_unsupported(sql: str, construct: str) -> None:
    with pytest.raises(Unsupported) as e:
        parse(sql)
    assert e.value.construct == construct and e.value.supported == SUBSET


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "SELECT",
        "SELECT u.a FROM",
        "SELECT u.a FROM m.T u WHERE u.a = ",
        "SELECT u.a FROM m.T u garbage",
        "SELECT u.a FROM m.T u WHERE u.a = 'unterminated",
        "SELECT u.* FROM m.T u JOIN m.S s",
        "SELECT u.* FROM m.T u WHERE (u.a, u.b) > (1)",
    ],
)
def test_invalid(sql: str) -> None:
    with pytest.raises(Invalid):
        parse(sql)


def test_the_subset_parses_the_relational_shapes() -> None:
    q = parse(
        "SELECT c.region, SUM(p.total) AS spent, COUNT(*) FROM shop.Customer c"
        " INNER JOIN shop.Purchase p ON p.customer = c.code AND p.code = c.code"
        " JOIN Line ON Line.code = p.code"
        " WHERE (c.region, c.code) > ('a', :k) AND p.qty > 1"
        " GROUP BY c.region, c.code ORDER BY c.region ASC, c.code LIMIT 7",
        {"k": "c1"},
    )
    assert [s.alias.text for s in q.sources] == ["c", "p", "Line"]  # a source's alias defaults
    assert [len(j.on) for j in q.joins] == [2, 1] and q.joins[1].source.module is None
    assert [p.kind for p in q.predicates] == ["tuple", ">"] and q.predicates[0].right == (
        "a",
        Bound("k", "c1"),
    )
    assert [(i.kind, i.output.text if i.output else None) for i in q.items] == [
        ("col", None),
        ("sum", "spent"),
        ("count", None),
    ]
    assert [c.name.text for c in q.order_by] == ["region", "code"] and q.limit == 7
    assert parse("SELECT u.a FROM m.T").source.alias == Ident("T")


def test_param_misuse_reports_all() -> None:
    with pytest.raises(Invalid) as e:
        parse("SELECT u.* FROM m.T u WHERE u.a = :a AND u.b = :b", {"a": 1, "z": 2})
    assert {v.code for v in e.value.violations} == {"missing_param", "unused_param"}


def test_param_type_checked() -> None:
    with pytest.raises(Invalid) as e:
        parse("SELECT u.* FROM m.T u WHERE u.a = :a", {"a": [1]})
    assert e.value.violations[0].code == "param_type"


def test_alias_and_group_by_fold_case_and_quoting() -> None:
    rq("SELECT U.code FROM catalog.UseCase u WHERE U.name = 'x'")
    rq('SELECT "u".code FROM catalog.UseCase u')
    rq("SELECT u.Name, COUNT(*) FROM catalog.UseCase u GROUP BY u.name")
    with pytest.raises(Invalid) as e:
        rq('SELECT "U".code FROM catalog.UseCase u')
    assert e.value.violations[0].code == "unknown_alias"


def test_reserved_words_name_members_only_quoted() -> None:
    """As in Weft: `order`, `group`, `in`, `right` ... are reserved, so a member of that name is
    written quoted; words Weft does not reserve (`count`, `key`, `type`) are names as they stand."""
    q = parse(
        'SELECT u."right", u."order", u.count, u.key, u.type FROM m.T u WHERE u."in" = 1 AND u."group" = 2'
    )
    assert [i.col.name.text for i in q.items if i.col] == ["right", "order", "count", "key", "type"]
    assert [p.left[0].name.text for p in q.predicates] == ["in", "group"]
    for sql in (
        "SELECT u.order FROM m.T u",
        "SELECT u.a FROM m.T u WHERE u.group = 2",
        "SELECT u.a FROM m.Order u",
        "SELECT select.a FROM m.T select",
    ):
        with pytest.raises(Invalid) as e:
            parse(sql)
        assert e.value.violations[0].code == "syntax", sql


def test_violations_are_all_reported() -> None:
    with pytest.raises(Invalid) as e:
        parse("SELECT u.a FROM m.T u WHERE u.a = :p AND u.b = :q", {})
    assert [v.code for v in e.value.violations] == ["missing_param", "missing_param"]
    with pytest.raises(Invalid) as e:
        rq("SELECT x.code, u.nope FROM catalog.UseCase u WHERE u.name = 3")
    assert sorted(v.code for v in e.value.violations) == ["type", "unknown_alias", "unknown_field"]


def test_negative_numbers() -> None:
    q = parse("SELECT u.* FROM m.T u WHERE u.a = -3 AND u.b = -1.5")
    assert [p.right[0] for p in q.predicates] == [-3, Decimal("-1.5")]


@pytest.mark.parametrize(
    ("sql", "construct"),
    [
        ("SELECT u.* FROM m.T u WHERE u.a = 1 + 2", "expression"),
        ("SELECT u.* FROM m.T u WHERE u.a = 'x' || 'y'", "expression"),
        ("SELECT u.* FROM m.T u WHERE u.a = upper('x')", "function"),
        ("SELECT u.* FROM m.T u WHERE lower(u.a) = 'x'", "function lower"),
        ("SELECT u.* FROM m.T u WHERE u.a = NULL", "NULL"),
        ("SELECT u.* FROM m.T u WHERE u.a = 1.5e3", "exponent literal"),
        ("SELECT u.* FROM m.T u -- hi", "comment"),
        ("SELECT u.* FROM m.T u; SELECT u.* FROM m.T u", "multiple statements"),
        ("SELECT u.a, COUNT(u.a) FROM m.T u GROUP BY u.a", "COUNT(column)"),
        ("SELECT u.* AS x FROM m.T u", "alias.* AS"),
        ("SELECT u.a FROM m.T u WHERE u.a = 1::int", "cast"),
        ("SELECT u.a FROM m.T u GROUP BY u.a HAVING u.a = 1", "HAVING"),
        ("SELECT u.a FROM m.T u UNION SELECT u.a FROM m.T u", "UNION"),
    ],
)
def test_more_unsupported(sql: str, construct: str) -> None:
    with pytest.raises(Unsupported) as e:
        parse(sql)
    assert e.value.construct == construct


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT u.a FROM m.T u WHERE u.a = '" + "x" * 1001 + "'",
        "SELECT u.a FROM m.T u WHERE u.a = " + "9" * 41,
        "SELECT u.a FROM m.T u WHERE " + " AND ".join(f"u.a = {i}" for i in range(21)),
        "SELECT " + ", ".join(f"u.c{i}" for i in range(51)) + " FROM m.T u",
        "SELECT u.a FROM m.T u WHERE u.a = 1 " + " " * 4000,
        "SELECT u.a FROM m.T u " + " ".join(f"JOIN m.T t{i} ON t{i}.a = u.a" for i in range(17)),
    ],
)
def test_bounds(sql: str) -> None:
    with pytest.raises(Invalid) as e:
        parse(sql)
    assert e.value.violations[0].code == "bound"


def test_param_bound_and_bool_decimal_params() -> None:
    q = parse("SELECT u.* FROM m.T u WHERE u.a = :a AND u.b = :b", {"a": True, "b": Decimal("1.5")})
    assert [p.right[0] for p in q.predicates] == [Bound("a", True), Bound("b", Decimal("1.5"))]
    with pytest.raises(Invalid) as e:
        parse("SELECT u.* FROM m.T u WHERE u.a = :a", {"a": "x" * 1001})
    assert e.value.violations[0].code == "bound"


def test_quoted_identifier_unescapes_and_violation_paths() -> None:
    q = parse('SELECT u.* FROM m.T u WHERE u."a""b" = 1')
    assert q.predicates[0].left[0].name == Ident('a"b', quoted=True)
    with pytest.raises(Invalid) as e:
        parse("SELECT u.* FROM m.T u WHERE u.a = :a", {"z": 1})
    assert {(v.path, v.code) for v in e.value.violations} == {
        ("params.a", "missing_param"),
        ("params.z", "unused_param"),
    }


# -- resolution against the module's types

EXAMPLE = Path(__file__).parents[1] / "docs/helix/02-design/contracts/examples/catalog.umf.json"
MODULE = parse_module(EXAMPLE.read_bytes())


def rq(sql: str, params=None):
    return resolve(Statement(sql, params or {}), MODULE)


def test_resolves_the_whole_entity_by_key() -> None:
    r = rq("SELECT s.* FROM catalog.Solution s WHERE s.CODE = 'sol-1'")
    assert (r.type, r.key, r.whole) == ("catalog.Solution", "code", True)
    assert r.conds == (Cond("=", (Ref(0, "code"),), ("sol-1",)),)


def test_columns_resolve_to_declared_names() -> None:
    r = rq("SELECT u.CODE, u.name FROM CATALOG.usecase u")
    assert [o.name for o in r.outputs] == ["code", "name"] and r.type == "catalog.UseCase"


def test_relationship_filters_by_name_and_inverse() -> None:
    r = rq(
        "SELECT s.* FROM catalog.Solution s WHERE HAS_RELATED(s.addresses, KEY(:k))", {"k": "uc-1"}
    )
    assert r.conds == (
        Cond("related", right=("uc-1",), rel=Rel(0, "addresses", "addresses", True)),
    )
    r = rq("SELECT u.* FROM catalog.UseCase u WHERE has_related(u.addressedBy, key('sol-1'))")
    assert r.conds[0].rel == Rel(0, "addressedBy", "addresses", False)
    # a relationship is only a column of the types at its ends
    with pytest.raises(Invalid) as e:
        rq("SELECT u.* FROM catalog.UseCase u WHERE HAS_RELATED(u.addresses, KEY('x'))")
    assert e.value.violations[0].code == "unknown_field"


def test_a_relationship_compared_with_equals_is_unsupported() -> None:
    """Weft reads a relationship predicate as HAS_RELATED; `alias.rel = 'key'` is not served."""
    for sql in (
        "SELECT s.* FROM catalog.Solution s WHERE s.addresses = 'uc-1'",
        "SELECT u.code FROM catalog.UseCase u WHERE u.addressedBy = :k",
    ):
        with pytest.raises(Unsupported) as e:
            rq(sql, {"k": "s"} if ":k" in sql else None)
        assert e.value.construct.startswith("relationship")
        assert "HAS_RELATED" in e.value.supported[0] and e.value.supported[1:] == SUBSET


def test_has_related_is_read_with_its_key() -> None:
    q = parse(
        "SELECT s.code FROM m.T s WHERE HAS_RELATED(s.r, KEY('a')) AND s.code = :c", {"c": "x"}
    )
    assert [(p.left[0].name.text, p.right[0], p.related) for p in q.predicates] == [
        ("r", "a", True),
        ("code", Bound("c", "x"), False),
    ]
    for sql in (
        "SELECT s.code FROM m.T s WHERE HAS_RELATED(s.r, 'a')",
        "SELECT s.code FROM m.T s WHERE HAS_RELATED(s.r, KEY('a')",
        "SELECT s.code FROM m.T s WHERE HAS_RELATED(s.r KEY('a'))",
    ):
        with pytest.raises(Invalid) as e:
            parse(sql)
        assert e.value.violations[0].code == "syntax", sql
    with pytest.raises(Invalid) as e:
        rq("SELECT s.code FROM catalog.Solution s WHERE HAS_RELATED(x.addresses, KEY('a'))")
    assert e.value.violations[0].code == "unknown_alias"
    with pytest.raises(Unsupported):  # any other function is outside the subset
        parse("SELECT s.code FROM m.T s WHERE RELATED_KEYS(s.r, 2) = 'a'")
    with pytest.raises(Invalid) as e:  # a key here has one part
        rq("SELECT s.code FROM catalog.Solution s WHERE HAS_RELATED(s.addresses, KEY('a', 'b'))")
    assert e.value.violations[0].code == "key"


def test_count() -> None:
    r = rq("SELECT s.name, COUNT(*) FROM catalog.Solution s GROUP BY s.name")
    assert r.group == (Ref(0, "name"),) and r.aggregated


def test_unknowns_and_literal_typing_report_everything() -> None:
    # a type of the named module that this backend does not hold, or another module's, is not
    # served here (the store answers `unknown_type` for a module it does not hold)
    with pytest.raises(Unsupported) as u:
        rq("SELECT u.nope FROM catalog.Nope u")
    assert "does not hold" in u.value.construct
    with pytest.raises(Unsupported) as u:
        rq("SELECT u.nope FROM nomod.T u")
    assert "outside module catalog" in u.value.construct
    with pytest.raises(Invalid) as e:
        rq("SELECT u.nope FROM catalog.UseCase u WHERE u.name = 3 AND u.zip = 'x'")
    assert sorted(v.code for v in e.value.violations) == ["type", "unknown_field", "unknown_field"]
    with pytest.raises(Invalid) as e:
        rq("SELECT s.* FROM catalog.Solution s WHERE HAS_RELATED(s.addresses, KEY('bad key!'))")
    assert e.value.violations[0].code == "key"


def test_optional_columns_are_projected_but_not_compared() -> None:
    """As in Weft: an absent-allowed scalar is a nullable column, and no filter or group."""
    r = rq("SELECT s.coverageLevel FROM catalog.Solution s")
    assert [(o.name, o.kind) for o in r.outputs] == [("coverageLevel", "col")]
    for sql in (
        "SELECT s.name FROM catalog.Solution s WHERE s.coverageLevel = 'x'",
        "SELECT s.coverageLevel, COUNT(*) FROM catalog.Solution s GROUP BY s.coverageLevel",
    ):
        with pytest.raises(Unsupported) as e:
            rq(sql)
        assert e.value.supported[0]


def test_the_declared_profiles_cover_the_statement() -> None:
    narrow = WeftSupport(WEFT.version, (ENTITY,))
    check_profiles(
        rq("SELECT s.code FROM catalog.Solution s WHERE s.name = 'u' ORDER BY s.code LIMIT 5"),
        narrow,
    )
    for sql, needed in (
        (
            "SELECT s.name, COUNT(*) FROM catalog.Solution s GROUP BY s.name ORDER BY s.name LIMIT 9",
            COUNT,
        ),
        (
            "SELECT u.* FROM catalog.UseCase u WHERE HAS_RELATED(u.addressedBy, KEY('x'))"
            " ORDER BY u.code LIMIT 9",
            RELATED,
        ),
    ):
        with pytest.raises(Unsupported) as e:
            check_profiles(rq(sql), narrow)
        assert e.value.construct == f"profile {needed}" and e.value.supported[1:] == SUBSET
        check_profiles(rq(sql), WEFT)  # the fake's own declaration serves the whole subset
    with pytest.raises(Unsupported) as e:  # a backend that hosts no Weft serves no statement
        check_profiles(rq("SELECT s.code FROM catalog.Solution s ORDER BY s.code LIMIT 5"), None)
    assert "no Weft" in e.value.supported[0]


def test_the_fake_says_what_it_is() -> None:
    assert "memory" in WEFT.version and set(WEFT.profiles) == {ENTITY, RELATED, COUNT, GENERAL}
    assert any("HAS_RELATED" in shape for shape in SUBSET)
    assert any("JOIN" in shape for shape in SUBSET) and any("SUM" in shape for shape in SUBSET)
    assert resolve(Statement("SELECT u.code FROM catalog.UseCase u"), MODULE).type
    with pytest.raises(Unsupported) as e:  # one module per statement: the one the caller named
        resolve(Statement("SELECT t.code FROM other.Thing t"), MODULE)
    assert "outside module catalog" in e.value.construct


def test_repeated_predicates() -> None:
    # two relationship predicates mean "related to both"; a repeated filter is kept, and matches
    # what it would alone, while two different values on one field match nothing (no error)
    r = rq(
        "SELECT s.* FROM catalog.Solution s"
        " WHERE HAS_RELATED(s.addresses, KEY('a')) AND HAS_RELATED(s.addresses, KEY('b'))"
    )
    assert [c.right[0] for c in r.conds] == ["a", "b"]
    r = rq("SELECT s.* FROM catalog.Solution s WHERE s.name = 'x' AND s.name = 'x'")
    assert r.conds[0] == r.conds[1]
    r = rq("SELECT s.* FROM catalog.Solution s WHERE s.name = 'x' AND s.name = 'y'")
    assert len(r.conds) == 2


def test_relationship_direction_and_columns() -> None:
    c = rq("SELECT s.* FROM catalog.Solution s WHERE HAS_RELATED(s.addresses, KEY('u'))").conds[0]
    assert c.rel and (c.rel.canonical, c.rel.out) == ("addresses", True)
    c = rq("SELECT u.* FROM catalog.UseCase u WHERE HAS_RELATED(u.addressedBy, KEY('s'))").conds[0]
    assert c.rel and (c.rel.canonical, c.rel.out) == ("addresses", False)
    whole = rq("SELECT s.* FROM catalog.Solution s")
    assert [o for o in whole.outputs if o.kind == "related"] == []  # alias.* has no keys
    inverse = rq("SELECT u.*, RELATED_KEYS(u.addressedBy, 5) FROM catalog.UseCase u")
    related = [o for o in inverse.outputs if o.kind == "related"]
    assert [(o.name, o.n, o.rel.name if o.rel else None) for o in related] == [
        ("addressedBy", 5, "addressedBy")
    ]


def test_filter_advice_is_not_about_alias_star() -> None:
    with pytest.raises(Unsupported) as e:
        rq("SELECT s.name FROM catalog.Solution s WHERE s.coverageLevel = 'x'")
    assert "alias.*" not in e.value.supported[0] and "filter" in e.value.supported[0]


def test_quoted_names_and_param_keys() -> None:
    assert rq('SELECT s.* FROM "catalog".Solution s').type == "catalog.Solution"
    for sql in ('SELECT s.* FROM "Catalog".Solution s', 'SELECT s.* FROM catalog."solution" s'):
        with pytest.raises(Unsupported):  # a quoted name matches exactly, or names nothing held
            rq(sql)
    with pytest.raises(Invalid) as e:
        rq('SELECT s.* FROM catalog.Solution s WHERE s."NAME" = 1')
    assert e.value.violations[0].code == "unknown_field"
    with pytest.raises(Invalid) as e:
        rq("SELECT s.* FROM catalog.Solution s WHERE HAS_RELATED(s.addresses, KEY(:k))", {"k": 5})
    assert e.value.violations[0].code == "key"


def test_profiles_needed_by_inverse_and_count() -> None:
    inverse = rq(
        "SELECT u.code FROM catalog.UseCase u WHERE HAS_RELATED(u.addressedBy, KEY('s'))"
        " ORDER BY u.code LIMIT 5"
    )
    assert profiles_needed(inverse) == (RELATED,)  # related-entity-page, not entity-page
    check_profiles(inverse, WeftSupport(WEFT.version, (RELATED,)))
    counted = rq(
        "SELECT u.name, COUNT(*) FROM catalog.UseCase u"
        " WHERE HAS_RELATED(u.addressedBy, KEY('s')) GROUP BY u.name ORDER BY u.name LIMIT 5"
    )
    assert profiles_needed(counted) == (GENERAL,)  # count-summary excludes related filters
    check_profiles(counted, WEFT)  # the general profile serves it
    with pytest.raises(Unsupported) as e:
        check_profiles(counted, NAMED)
    assert e.value.construct == "HAS_RELATED with COUNT(*)" and e.value.supported[1:] == SUBSET


def test_statements_take_the_shape_their_profile_requires() -> None:
    """Weft's application-read profiles: a page orders by the key and names a LIMIT; a grouped
    count orders by its grouping and names a LIMIT, filters by equality and has no keyset. The
    memory adapter bounds the general profile with a LIMIT of its own."""
    for sql, construct in (
        ("SELECT u.code FROM catalog.UseCase u", "a page without ORDER BY alias.code and LIMIT"),
        ("SELECT u.code FROM catalog.UseCase u ORDER BY u.code", "a page without"),
        ("SELECT u.code FROM catalog.UseCase u ORDER BY u.name", "a page without"),
        ("SELECT u.code FROM catalog.UseCase u WHERE u.name > 'a'", "a page without"),
        (
            "SELECT u.name, COUNT(*) FROM catalog.UseCase u GROUP BY u.name",
            "a grouped count without",
        ),
    ):
        for declared in (WEFT, NAMED):
            with pytest.raises(Unsupported) as e:
                check_profiles(rq(sql), declared)
            assert e.value.construct.startswith(construct) and e.value.supported[1:] == SUBSET, sql
    for sql, construct in (  # bounded, so the general profile serves them; the named ones do not
        ("SELECT u.code FROM catalog.UseCase u LIMIT 5", "a page without"),
        (
            "SELECT u.name, COUNT(*) FROM catalog.UseCase u WHERE u.code > 'a' GROUP BY u.name"
            " ORDER BY u.name LIMIT 5",
            "a keyset predicate with COUNT(*)",
        ),
        (
            "SELECT u.code FROM catalog.UseCase u WHERE u.name > 'a' ORDER BY u.code LIMIT 5",
            "profile general",
        ),
    ):
        check_profiles(rq(sql), WEFT)
        with pytest.raises(Unsupported) as e:
            check_profiles(rq(sql), NAMED)
        assert e.value.construct.startswith(construct), sql
    check_profiles(rq("SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 1000"), NAMED)
    with pytest.raises(Invalid) as inv:  # a LIMIT through 1,000
        parse("SELECT u.code FROM m.T u ORDER BY u.code LIMIT 1001")
    assert inv.value.violations[0].code == "bound"


SCALARS = """{"umf":"0.10.0","id":"x","vocabularies":{"umf.ddd":{"version":"0.1.0"}},"extensions":{},"modules":[{"id":"m","extensions":{"umf.ddd":{"kind":"bounded-context","terms":[]}},"elements":[
 {"id":"T","kind":"record","members":[{"module":"m","element":"T.k"},{"module":"m","element":"T.n"},{"module":"m","element":"T.d"},{"module":"m","element":"T.b"}],
  "extensions":{"umf.ddd":{"kind":"entity","fields":{"k":{"type":{"kind":"scalar","name":"string"},"cardinality":"one"},"n":{"type":{"kind":"scalar","name":"integer"},"cardinality":"one"},"d":{"type":{"kind":"scalar","name":"decimal"},"cardinality":"one"},"b":{"type":{"kind":"scalar","name":"boolean"},"cardinality":"one"}},"identity":{"fields":["k"],"scope":"context"}}},
  "keys":[{"id":"i","name":"I","fields":[{"module":"m","element":"T.k"}],"primary":true}]},
 {"id":"T.k","kind":"field","nullability":"required","cardinality":"one","scalarType":"string","extensions":{}},
 {"id":"T.n","kind":"field","nullability":"required","cardinality":"one","scalarType":"integer","extensions":{}},
 {"id":"T.d","kind":"field","nullability":"required","cardinality":"one","scalarType":"decimal","extensions":{}},
 {"id":"T.b","kind":"field","nullability":"required","cardinality":"one","scalarType":"boolean","extensions":{}}]}]}"""


def test_literal_typing_for_numbers_and_booleans() -> None:
    mod = parse_module(SCALARS)

    def go(sql: str, params=None):
        return resolve_plan(parse(sql, params), mod)

    go("SELECT t.* FROM m.T t WHERE t.n = 3 AND t.d = 2 AND t.b = TRUE")
    go("SELECT t.* FROM m.T t WHERE t.d = 1.5 AND t.b = :b", {"b": False})
    for sql, params in (
        ("SELECT t.* FROM m.T t WHERE t.n = 1.0", None),
        ("SELECT t.* FROM m.T t WHERE t.n = TRUE", None),
        ("SELECT t.* FROM m.T t WHERE t.b = 1", None),
        ("SELECT t.* FROM m.T t WHERE t.b = :b", {"b": 1}),
        ("SELECT t.* FROM m.T t WHERE t.k = 5", None),
    ):
        with pytest.raises(Invalid) as e:
            go(sql, params)
        assert e.value.violations[0].code == "type", sql


def test_attribution_is_not_a_column() -> None:
    for sql in (
        "SELECT s._created_by FROM catalog.Solution s",
        "SELECT s.code, s._version FROM catalog.Solution s",
        "SELECT s._updated_at, COUNT(*) FROM catalog.Solution s GROUP BY s._updated_at",
    ):
        with pytest.raises(Unsupported) as e:
            rq(sql)
        assert "alias.*" in e.value.supported[0]


def test_attribution_names_are_matched_exactly() -> None:
    from arras import Invalid

    with pytest.raises(Unsupported):
        rq('SELECT s."_created_by" FROM catalog.Solution s')  # quoting does not change the answer
    with pytest.raises(Unsupported) as e:
        rq("SELECT s.code FROM catalog.Solution s WHERE s._created_by = 'x'")
    assert "alias.*" in e.value.supported[0] and "filter" in e.value.supported[0]
    with pytest.raises(Invalid) as inv:  # a typo is an unknown field, not attribution
        rq("SELECT s._typo FROM catalog.Solution s")
    assert inv.value.violations[0].code == "unknown_field"


def test_a_page_is_the_statements_order_limit_and_keyset() -> None:
    q = parse(
        "SELECT u.code FROM m.T u WHERE u.code > :last ORDER BY u.code ASC LIMIT 20", {"last": "a"}
    )
    assert (q.limit, [c.name.text for c in q.order_by]) == (20, ["code"])
    assert [(p.left[0].name.text, p.kind) for p in q.predicates] == [("code", ">")]
    r = rq("SELECT u.code FROM catalog.UseCase u WHERE u.code > 'uc-1' ORDER BY u.code LIMIT 2")
    assert r.limit == 2 and r.conds[0].kind == ">" and profiles_needed(r) == (ENTITY,)
    counted = rq("SELECT u.name, COUNT(*) FROM catalog.UseCase u GROUP BY u.name ORDER BY u.name")
    assert counted.group == (Ref(0, "name"),)
    tupled = rq(
        "SELECT u.code FROM catalog.UseCase u WHERE (u.code) > ('uc-1') ORDER BY u.code LIMIT 2"
    )
    assert profiles_needed(tupled) == (ENTITY,)  # a one-column tuple keyset on the key is a page
    for sql in (  # a page orders by the key, and its keyset compares the key
        "SELECT u.code FROM catalog.UseCase u ORDER BY u.name LIMIT 5",
        "SELECT u.code FROM catalog.UseCase u WHERE u.name > 'a' ORDER BY u.code LIMIT 5",
        "SELECT u.code FROM catalog.UseCase u WHERE (u.name, u.code) > ('a', 'b') ORDER BY u.code LIMIT 5",
    ):
        assert profiles_needed(rq(sql)) == (GENERAL,), sql
    with pytest.raises(Invalid) as e:
        parse("SELECT u.code FROM m.T u LIMIT 0")
    assert e.value.violations[0].code == "bound"


def test_related_keys_are_a_projection_of_the_subset() -> None:
    q = parse("SELECT s.*, RELATED_KEYS(s.addresses, 3) AS uses FROM m.T s")
    assert [
        (i.col.name.text, i.n, i.output.text)
        for i in q.items
        if i.kind == "related" and i.col and i.output
    ] == [("addresses", 3, "uses")]
    r = rq(
        "SELECT s.code, RELATED_KEYS(s.addresses, 100) FROM catalog.Solution s ORDER BY s.code LIMIT 5"
    )
    related = [(o.name, o.n) for o in r.outputs if o.kind == "related"]
    assert related == [("addresses", 100)] and profiles_needed(r) == (RELATED,)
    with pytest.raises(Invalid) as e:  # a relationship of the type, under a column name of its own
        rq("SELECT u.*, RELATED_KEYS(u.addresses, 5) FROM catalog.UseCase u")
    assert e.value.violations[0].code == "unknown_field"
    with pytest.raises(Invalid) as e:
        rq("SELECT s.*, RELATED_KEYS(s.addresses, 5) AS name FROM catalog.Solution s")
    assert e.value.violations[0].code == "duplicate_column"
    for sql in (
        "SELECT s.code, RELATED_KEYS(s.r, 0) FROM m.T s",
        "SELECT s.code, RELATED_KEYS(s.r, 1001) FROM m.T s",
    ):
        with pytest.raises(Invalid) as e:
            parse(sql)
        assert e.value.violations[0].code == "bound"
    with pytest.raises(Invalid) as e:
        rq("SELECT s.code, RELATED_KEYS(x.addresses, 2) FROM catalog.Solution s")
    assert e.value.violations[0].code == "unknown_alias"
    with pytest.raises(Unsupported):  # keys are read per entity, never per group
        rq(
            "SELECT s.name, RELATED_KEYS(s.addresses, 2), COUNT(*) FROM catalog.Solution s"
            " GROUP BY s.name"
        )


def test_aggregates_resolve_with_their_grouping() -> None:
    for sql, code in (
        (
            "SELECT s.name, COUNT(*), COUNT(*) FROM catalog.Solution s GROUP BY s.name",
            "duplicate_column",
        ),
        ("SELECT s.name, s.code, COUNT(*) FROM catalog.Solution s GROUP BY s.name", "group_by"),
        (
            "SELECT s.name, COUNT(*) FROM catalog.Solution s GROUP BY s.name ORDER BY s.code",
            "group_by",
        ),
        ("SELECT SUM(s.name) FROM catalog.Solution s", "type"),
    ):
        with pytest.raises(Invalid) as e:
            rq(sql)
        assert e.value.violations[0].code == code, sql
    r = rq("SELECT COUNT(*) AS n, s.name FROM catalog.Solution s GROUP BY s.name")
    assert [o.name for o in r.outputs] == ["n", "name"] and r.aggregated
    with pytest.raises(Unsupported):
        rq("SELECT s.*, COUNT(*) FROM catalog.Solution s GROUP BY s.code")
