# SPDX-License-Identifier: MIT OR Apache-2.0
"""The memory adapter's reader of Weft SQL 0.2 text (W-011): a parse of the subset it serves.

This is not Weft. It reads the shapes of Weft SQL 0.2's grammar the memory adapter evaluates
(`SUBSET`) and refuses every other construct with `Unsupported` carrying that list, so a client
learns what the stand-in serves. Reserved words name a member only when quoted, as in Weft. The
differential test (`tests/test_weft_relational.py`) holds both batteries, what the fake accepts and
what Weft refuses, against Weft's own parser.

`parse` checks what the text and the parameters can show; names, types and groupings are checked
against a module's types by `arras.fakes_plan`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from arras.errors import Invalid, Unsupported, Violation

SUBSET = [
    "SELECT item, ... FROM [module.]Type [AS] alias {[INNER] JOIN [module.]Type alias ON a.x = b.y"
    " [AND ...]} [WHERE predicate AND ...] [GROUP BY a.x, ...] [ORDER BY a.x [ASC], ...] [LIMIT n]",
    "item: alias.* | a.x [AS name] | COUNT(*) [AS name] | SUM(a.x) [AS name]"
    " | RELATED_KEYS(a.relationship, n) [AS name]",
    "predicate: a.x = value | a.x > value | (a.x, b.y, ...) > (value, ...)"
    " | HAS_RELATED(a.relationship, KEY(literal | :name)); value: literal | :name | a.x",
    "at most 16 joins; 1 <= n <= 1000",
]

MAX_SQL_CHARS = 4000
MAX_LITERAL_CHARS = 1000
MAX_NUMBER_CHARS = 40
MAX_PREDICATES = 20
MAX_COLUMNS = 50
MAX_JOINS = 16
MAX_BOUND = 1000  # a LIMIT or a RELATED_KEYS count: 1 through 1000

Scalar = str | int | Decimal | bool

# Words Weft reserves: as a name (an alias, a type, a member, a parameter) they must be quoted,
# and a parameter cannot be one. `count` and `related_keys` begin a projection, so neither names an
# alias unquoted, while a member may be called either.
RESERVED = frozenset(
    {"select", "from", "as", "where", "and", "or", "group", "by", "order", "limit", "offset"}
    | {"inner", "join", "left", "right", "full", "outer", "cross", "on", "union", "having"}
    | {"distinct", "in", "is", "null", "true", "false", "sum"}
)
ALIAS_RESERVED = RESERVED | {"count", "related_keys"}
WHITESPACE = " \t\n\r\f"  # the whitespace Weft reads; any other is outside the text profile
_EXCLUDED = {
    "or": "OR",
    "offset": "OFFSET",
    "left": "outer join",
    "right": "outer join",
    "full": "outer join",
    "outer": "outer join",
    "cross": "cross join",
    "union": "UNION",
    "having": "HAVING",
    "distinct": "DISTINCT",
    "in": "IN",
    "is": "IS",
    "null": "NULL",
    "desc": "DESC",
    "not": "NOT",
    "like": "LIKE",
    "between": "BETWEEN",
    "case": "CASE",
    "cast": "CAST",
    "exists": "EXISTS",
    "with": "WITH",
}
_COMPARISONS = {"<>", "!=", "<=", ">=", "<"}
_TOKEN = re.compile(
    r"""[ \t\n\r\f]*(?:
      (?P<string>'(?:[^']|'')*')
    | (?P<qident>"(?:[^"]|"")+")
    | (?P<number>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)
    | (?P<param>:[ \t\n\r\f]*[A-Za-z_][A-Za-z0-9_]*)
    | (?P<word>[A-Za-z_][A-Za-z0-9_]*)
    | (?P<op>--|/\*|<>|!=|<=|>=|::|\|\||[<>+\-/%])
    | (?P<punct>[.,=*;()])
    | (?P<positional>\?|\$\d+)
    )""",
    re.VERBOSE,
)


@dataclass(frozen=True)
class Ident:
    """An identifier: unquoted ones match case-insensitively, double-quoted ones exactly."""

    text: str
    quoted: bool = False

    def matches(self, declared: str) -> bool:
        return self.text == declared if self.quoted else self.text.lower() == declared.lower()

    def same(self, other: Ident) -> bool:
        """Whether two written identifiers name the same thing."""
        if self.quoted and other.quoted:
            return self.text == other.text
        if self.quoted or other.quoted:
            quoted, bare = (self, other) if self.quoted else (other, self)
            return quoted.text == bare.text.lower()
        return self.text.lower() == other.text.lower()


@dataclass(frozen=True)
class Col:
    """`alias.name`."""

    alias: Ident
    name: Ident


@dataclass(frozen=True)
class Marker:
    """A `:name` parameter (its name case-folded), bound by `parse`."""

    name: str


@dataclass(frozen=True)
class Bound:
    """A parameter's value, kept apart from a literal: Weft types the two differently (an
    integer parameter is no decimal, an integer literal is)."""

    name: str
    value: Scalar


Value = Scalar | Marker | Bound | Col


@dataclass(frozen=True)
class Item:
    """A projection: `col`, `star` (`alias.*`), `count`, `sum` or `related` (`RELATED_KEYS`)."""

    kind: str
    col: Col | None = None  # the column, or the relationship as `alias.name`, or the star's alias
    n: int = 0  # a RELATED_KEYS count
    output: Ident | None = None  # AS


@dataclass(frozen=True)
class Source:
    module: Ident | None
    type: Ident
    alias: Ident


@dataclass(frozen=True)
class Join:
    source: Source
    on: tuple[tuple[Col, Col], ...]


@dataclass(frozen=True)
class Predicate:
    """`=` or `>` (`left` one column, `right` one value), `tuple` (`left` > `right`, same arity),
    or `related` (`HAS_RELATED(left[0], KEY(right[0]))`)."""

    kind: str
    left: tuple[Col, ...]
    right: tuple[Value, ...]

    @property
    def related(self) -> bool:
        return self.kind == "related"


@dataclass(frozen=True)
class Query:
    items: tuple[Item, ...]
    source: Source
    joins: tuple[Join, ...] = ()
    predicates: tuple[Predicate, ...] = ()
    group_by: tuple[Col, ...] = ()
    order_by: tuple[Col, ...] = ()
    limit: int | None = None
    markers: tuple[str, ...] = field(default=(), compare=False)

    @property
    def sources(self) -> tuple[Source, ...]:
        return (self.source, *(j.source for j in self.joins))


@dataclass(frozen=True)
class _Tok:
    kind: str  # word, qident, string, number, param, punct, op
    text: str
    pos: int


def _unsupported(construct: str) -> Unsupported:
    return Unsupported(construct, SUBSET)


def _invalid(path: str, code: str, message: str) -> Invalid:
    return Invalid([Violation(path, code, message)])


def _syntax(pos: int, message: str) -> Invalid:
    return _invalid(f"sql[{pos}]", "syntax", message)


def _bound(path: str, what: str, limit: int) -> Invalid:
    return _invalid(path, "bound", f"{what} exceeds the bound of {limit}")


def _reject(t: _Tok) -> None:
    """Raise `Unsupported` if the token is a construct outside the subset."""
    if t.kind == "word" and t.text.lower() in _EXCLUDED:
        raise _unsupported(_EXCLUDED[t.text.lower()])
    if t.kind == "op":
        if t.text in _COMPARISONS:
            raise _unsupported(t.text)
        if t.text in ("--", "/*"):
            raise _unsupported("comment")
        if t.text == "::":
            raise _unsupported("cast")
        if t.text != ">":
            raise _unsupported("expression")
    if t.kind == "number" and re.search(r"[eE]", t.text):
        raise _unsupported("exponent literal")


def _tokenize(sql: str) -> list[_Tok]:
    if len(sql) > MAX_SQL_CHARS:
        raise _bound("sql", "the statement", MAX_SQL_CHARS)
    toks: list[_Tok] = []
    i = 0
    while True:
        while i < len(sql) and sql[i] in WHITESPACE:
            i += 1
        if i >= len(sql):
            return toks
        m = _TOKEN.match(sql, i)
        if m is None or m.end() == i:
            raise _syntax(i, f"unexpected character {sql[i]!r}")
        group = m.lastgroup or ""
        text = m.group(group)
        if group == "positional":
            raise _unsupported("positional marker")
        if "\x00" in text:
            raise _syntax(m.start(group), "a NUL character is outside the text profile")
        if group == "string" and len(text) - 2 > MAX_LITERAL_CHARS:
            raise _bound(f"sql[{m.start(group)}]", "a string literal", MAX_LITERAL_CHARS)
        if group == "number" and len(text) > MAX_NUMBER_CHARS:
            raise _bound(f"sql[{m.start(group)}]", "a number literal", MAX_NUMBER_CHARS)
        toks.append(_Tok(group, text, m.start(group)))
        i = m.end()


class _Parser:
    def __init__(self, sql: str) -> None:
        self.toks = _tokenize(sql)
        self.i = 0
        self.end = len(sql)
        self.markers: list[str] = []

    # -- tokens
    def peek(self, ahead: int = 0) -> _Tok | None:
        j = self.i + ahead
        return self.toks[j] if j < len(self.toks) else None

    def next(self) -> _Tok:
        t = self.peek()
        if t is None:
            raise _syntax(self.end, "the statement ends too soon")
        self.i += 1
        return t

    def at_word(self, word: str, ahead: int = 0) -> bool:
        t = self.peek(ahead)
        return t is not None and t.kind == "word" and t.text.lower() == word

    def at_punct(self, ch: str, ahead: int = 0) -> bool:
        t = self.peek(ahead)
        return t is not None and t.kind == "punct" and t.text == ch

    def at_op(self, op: str) -> bool:
        t = self.peek()
        return t is not None and t.kind == "op" and t.text == op

    def word(self, w: str) -> None:
        t = self.next()
        if t.kind != "word" or t.text.lower() != w:
            _reject(t)
            raise _syntax(t.pos, f"expected {w.upper()}, found {t.text!r}")

    def punct(self, ch: str) -> None:
        t = self.next()
        if t.kind != "punct" or t.text != ch:
            _reject(t)
            raise _syntax(t.pos, f"expected {ch!r}, found {t.text!r}")

    def name(self, what: str, reserved: frozenset[str] = RESERVED) -> Ident:
        """A name: unquoted, it must not be a reserved word; quoted, it is anything. A word that
        begins an excluded construct elsewhere (`NOT`, `DESC`, `WITH` ...) is a name here."""
        t = self.next()
        if t.kind == "qident":
            return Ident(t.text[1:-1].replace('""', '"'), quoted=True)
        if t.kind == "word" and t.text.lower() in reserved:
            if t.text.lower() in _EXCLUDED:
                _reject(t)
            raise _syntax(t.pos, f"{t.text!r} is a reserved word: quote it to use it as {what}")
        if t.kind == "word":
            return Ident(t.text)
        _reject(t)
        raise _syntax(t.pos, f"expected {what}, found {t.text!r}")

    def alias(self) -> Ident:
        return self.name("an alias", ALIAS_RESERVED)

    def col(self) -> Col:
        t = self.peek()
        if t is not None and t.kind == "word" and not self.at_punct(".", 1):
            _reject(t)  # an excluded construct where a column belongs
        a = self.alias()
        self.punct(".")
        return Col(a, self.name("a member"))

    def bound(self) -> int:
        t = self.next()
        if t.kind != "number" or "." in t.text:
            _reject(t)
            raise _unsupported("a bound other than a whole number")
        if not 1 <= int(t.text) <= MAX_BOUND:
            raise _invalid(f"sql[{t.pos}]", "bound", f"a bound is from 1 to {MAX_BOUND}")
        return int(t.text)

    def literal(self) -> Scalar | Marker:
        t = self.next()
        if t.kind == "string":
            return t.text[1:-1].replace("''", "'")
        if t.kind == "number":
            _reject(t)
            return Decimal(t.text) if "." in t.text else int(t.text)
        if t.kind == "op" and t.text == "-":
            n = self.peek()
            if n is not None and n.kind == "number":
                self.next()
                _reject(n)
                return -(Decimal(n.text) if "." in n.text else int(n.text))
        if t.kind == "word" and t.text.lower() in ("true", "false"):
            return t.text.lower() == "true"
        if t.kind == "param":
            name = t.text[1:].lstrip(WHITESPACE).lower()
            if name in RESERVED:
                raise _syntax(t.pos, f"{name!r} is a reserved word and names no parameter")
            self.markers.append(name)
            return Marker(name)
        _reject(t)
        raise _syntax(t.pos, f"expected a literal, found {t.text!r}")

    def value(self) -> Value:
        """A literal, a parameter or a column."""
        t = self.peek()
        if t is not None and t.kind in ("word", "qident") and self.at_punct(".", 1):
            if t.kind == "word" and t.text.lower() in ("true", "false"):
                return self.literal()
            return self.col()
        if t is not None and t.kind == "word" and self.at_punct("(", 1):
            _reject(t)
            raise _unsupported("function")
        if self.at_punct("("):
            raise _unsupported("subquery")
        return self.literal()

    # -- clauses
    def parse(self) -> Query:
        self.word("select")
        items = self.items()
        self.word("from")
        source = self.source()
        joins = self.joins()
        predicates = self.where()
        group = self.columns_after("group")
        order = self.columns_after("order", ordering=True)
        limit = None
        if self.at_word("limit"):
            self.next()
            limit = self.bound()
        self.end_of_statement()
        return Query(items, source, joins, predicates, group, order, limit, tuple(self.markers))

    def items(self) -> tuple[Item, ...]:
        items: list[Item] = []
        while True:
            items.append(self.item())
            if len(items) > MAX_COLUMNS:
                raise _bound("sql", "the number of columns", MAX_COLUMNS)
            if not self.at_punct(","):
                return tuple(items)
            self.next()

    def item(self) -> Item:
        if self.at_punct("*"):
            raise _unsupported("bare *")
        if self.at_word("distinct"):
            raise _unsupported("DISTINCT")
        if self.at_word("count") and self.at_punct("(", 1):
            self.next()
            self.punct("(")
            if not self.at_punct("*"):
                raise _unsupported("COUNT(column)")
            self.next()
            self.punct(")")
            return Item("count", output=self.output())
        if self.at_word("sum") and self.at_punct("(", 1):
            self.next()
            self.punct("(")
            c = self.col()
            self.punct(")")
            return Item("sum", c, output=self.output())
        if self.at_word("related_keys") and self.at_punct("(", 1):
            self.next()
            self.punct("(")
            c = self.col()
            self.punct(",")
            n = self.bound()
            self.punct(")")
            return Item("related", c, n, self.output())
        t = self.peek()
        if t is not None and t.kind == "word" and self.at_punct("(", 1):
            _reject(t)
            raise _unsupported(f"function {t.text}")
        a = self.alias()
        self.punct(".")
        if self.at_punct("*"):
            self.next()
            if self.at_word("as"):
                raise _unsupported("alias.* AS")
            return Item("star", Col(a, Ident("*")))
        return Item("col", Col(a, self.name("a member")), output=self.output())

    def output(self) -> Ident | None:
        if not self.at_word("as"):
            return None
        self.next()
        return self.name("an output name")

    def source(self) -> Source:
        first = self.name("a type")
        module, typ = None, first
        if self.at_punct("."):
            self.next()
            module, typ = first, self.name("a type")
        alias = typ
        if self.at_word("as"):
            self.next()
            alias = self.alias()
        else:
            t = self.peek()
            if t is not None and (t.kind == "qident" or (t.kind == "word" and _free(t.text))):
                alias = self.alias()
        return Source(module, typ, alias)

    def joins(self) -> tuple[Join, ...]:
        joins: list[Join] = []
        while self.at_word("inner") or self.at_word("join"):
            if self.at_word("inner"):
                self.next()
            self.word("join")
            source = self.source()
            self.word("on")
            on = [self.equality()]
            while self.at_word("and"):
                self.next()
                on.append(self.equality())
            joins.append(Join(source, tuple(on)))
            if len(joins) > MAX_JOINS:
                raise _bound("sql", "the number of joins", MAX_JOINS)
        if self.at_punct(","):
            raise _unsupported("a comma join")
        return tuple(joins)

    def equality(self) -> tuple[Col, Col]:
        left = self.col()
        self.punct("=")
        if not (self.peek() is not None and self.at_punct(".", 1)):
            raise _unsupported("an ON condition other than a.x = b.y")
        return (left, self.col())

    def where(self) -> tuple[Predicate, ...]:
        preds: list[Predicate] = []
        if not self.at_word("where"):
            return ()
        self.next()
        while True:
            preds.append(self.predicate())
            if len(preds) > MAX_PREDICATES:
                raise _bound("sql", "the number of predicates", MAX_PREDICATES)
            if not self.at_word("and"):
                return tuple(preds)
            self.next()

    def predicate(self) -> Predicate:
        if self.at_word("has_related") and self.at_punct("(", 1):
            self.next()
            self.punct("(")
            c = self.col()
            self.punct(",")
            self.word("key")
            self.punct("(")
            keys = [self.literal()]
            while self.at_punct(","):
                self.next()
                keys.append(self.literal())
            self.punct(")")
            self.punct(")")
            return Predicate("related", (c,), tuple(keys))
        t = self.peek()
        if t is not None and t.kind == "word" and self.at_punct("(", 1):
            _reject(t)
            raise _unsupported(f"function {t.text}")
        if self.at_punct("("):
            self.next()
            if self.at_word("select"):
                raise _unsupported("subquery")
            left = [self.col()]
            while self.at_punct(","):
                self.next()
                left.append(self.col())
            self.punct(")")
            if not self.at_op(">"):
                t = self.next()
                _reject(t)
                raise _unsupported("a tuple comparison other than >")
            self.next()
            self.punct("(")
            right = [self.value()]
            while self.at_punct(","):
                self.next()
                right.append(self.value())
            self.punct(")")
            if len(left) != len(right):
                raise _invalid("sql", "tuple", "a tuple is compared with one of the same length")
            return Predicate("tuple", tuple(left), tuple(right))
        left = self.col()
        if self.at_op(">"):
            self.next()
            return Predicate(">", (left,), (self.value(),))
        self.punct("=")
        return Predicate("=", (left,), (self.value(),))

    def columns_after(self, word: str, *, ordering: bool = False) -> tuple[Col, ...]:
        if not self.at_word(word):
            return ()
        self.next()
        self.word("by")
        cols = [self.ordered() if ordering else self.col()]
        while self.at_punct(","):
            self.next()
            cols.append(self.ordered() if ordering else self.col())
        return tuple(cols)

    def ordered(self) -> Col:
        c = self.col()
        if self.at_word("asc"):
            self.next()
        elif self.at_word("desc"):
            raise _unsupported("DESC")
        return c

    def end_of_statement(self) -> None:
        if self.at_punct(";"):
            self.next()
            if self.peek() is not None:
                raise _unsupported("multiple statements")
        t = self.peek()
        if t is not None:
            _reject(t)
            raise _syntax(t.pos, f"unexpected {t.text!r}")


def _free(word: str) -> bool:
    """Whether a bare word after a source is its alias rather than the next clause."""
    return word.lower() not in ALIAS_RESERVED


def parse(sql: str, params: Mapping[str, Any] | None = None) -> Query:
    """Parse `sql` and bind `params`: `Unsupported` outside the subset, `Invalid` for misuse."""
    p = _Parser(sql)
    query = p.parse()
    violations: list[Violation] = []
    bound: dict[str, Any] = {}
    for name, value in (params or {}).items():  # names are case-folded, as markers are
        if name.lower() in bound:
            msg = "parameter names are distinct after case folding"
            violations.append(Violation(f"params.{name}", "param_name", msg))
        bound[name.lower()] = value
    used = set(p.markers)
    for name in dict.fromkeys(p.markers):
        if name not in bound:
            violations.append(Violation(f"params.{name}", "missing_param", f"no value for :{name}"))
    for name, value in bound.items():
        if name not in used:
            violations.append(Violation(f"params.{name}", "unused_param", f"no marker :{name}"))
        elif not isinstance(value, str | int | Decimal):  # bool is an int
            msg = "a parameter is a string, integer, decimal or boolean"
            violations.append(Violation(f"params.{name}", "param_type", msg))
        elif isinstance(value, str) and len(value) > MAX_LITERAL_CHARS:
            msg = f"exceeds the bound of {MAX_LITERAL_CHARS}"
            violations.append(Violation(f"params.{name}", "bound", msg))
        elif isinstance(value, str) and "\x00" in value:
            msg = "a NUL character is outside the text profile"
            violations.append(Violation(f"params.{name}", "param_type", msg))
    if violations:
        raise Invalid(violations)
    return _bind(query, bound)


def _bind(q: Query, bound: Mapping[str, Any]) -> Query:
    def v(x: Value) -> Value:
        return Bound(x.name, bound[x.name]) if isinstance(x, Marker) else x

    preds = tuple(Predicate(p.kind, p.left, tuple(v(r) for r in p.right)) for p in q.predicates)
    return Query(q.items, q.source, q.joins, preds, q.group_by, q.order_by, q.limit, q.markers)
