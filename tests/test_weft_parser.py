# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""Every statement Arras writes, and every statement its corpus and examples use, is Weft SQL.

The memory adapter reads a subset of Weft's syntax of its own (`arras.fakes_weft`), and that
reader can drift from Weft's. So the statements themselves are put through Weft's own parser
(`weft.compile_json`, from Weft's Python extension) when it is importable: a statement Weft cannot
read (`WFT-SYNTAX`), refuses as a construct (`WFT-UNSUPPORTED`), or holds to be outside the read
profile it is written to, a name it cannot resolve, a type, a grouping or a parameter it rejects,
fails. Only a clean compile, or a refusal from the target and binding stages after all that, passes;
any other code (the module model, a limit, the request) fails, naming it, since the statement was
not shown to be checked. When no
Weft is importable the check is skipped and says so. (`truss.weft` is a boundary around a
`compile_json` the host supplies, not a parser, so it does not stand in for one.)

The statements are collected, not listed: the corpus's own, and those the GraphQL layer, the MCP
tool description, the dev UI and the catalog example send while they run.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import re
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from arras.conformance import load_corpus
from arras.devhost import build
from arras.errors import Invalid, Unsupported
from arras.fakes import MemoryReplica, MemoryStore
from arras.fakes_weft import GENERAL, profiles_needed, resolve
from arras.mcp.server import McpServer
from arras.names import quoted, quoted_type
from arras.sandbox import Sandbox
from arras.types import Statement
from arras.umf import parse_module

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "catalog"
Found = tuple[str, dict[str, Any], str]  # sql, params, the UMF document of the module it reads


def _weft() -> Callable[[str], str] | None:
    try:
        return importlib.import_module("weft").compile_json
    except (ImportError, AttributeError):
        return None


INSTALL = (
    "install the `weft-sql` 0.4.51 wheel from Weft's GitHub release into this environment "
    "(README, Development; the Weft delegation build plan)"
)


def compile_or_skip(what: str) -> Callable[[str], str]:
    """Weft's `compile_json`, or a visible skip saying `what` was not checked against it. With
    `ARRAS_REQUIRE_WEFT=1` (CI sets it) the missing parser is a failure instead."""
    compile_json = _weft()
    if compile_json is not None:
        return compile_json
    reason = f"Weft's parser is not importable (`import weft` failed; {INSTALL}): {what}"
    if os.environ.get("ARRAS_REQUIRE_WEFT") == "1":
        pytest.fail(f"ARRAS_REQUIRE_WEFT=1 and {reason}")
    pytest.skip(reason)


def _corpus() -> list[Found]:
    corpus = load_corpus()
    out: list[Found] = []
    for c in corpus["cases"]:
        for s in c["steps"]:
            if s["op"] == "query" and "error" not in s["expect"]:  # a refusal case is not Weft's
                out.append((s["sql"], s.get("params") or {}, corpus["_module_text"]))
    return out


def _recording(monkeypatch: pytest.MonkeyPatch, seen: list[Found]) -> None:
    """Record every statement a memory backend is asked to run, with its module's document."""
    for cls in (MemoryStore, MemoryReplica):
        real: Any = cls.query

        def spy(self, principal, module: str, statement: Statement, *, _real=real, **kw):
            store = self if isinstance(self, MemoryStore) else self.source
            doc = store.documents[module].decode()
            seen.append((statement.sql, dict(statement.params), doc))
            return _real(self, principal, module, statement, **kw)

        monkeypatch.setattr(cls, "query", spy)


def _load_read() -> Any:
    spec = importlib.util.spec_from_file_location("catalog_example_read_w", EXAMPLE / "read.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _callers(monkeypatch: pytest.MonkeyPatch) -> list[Found]:
    from arras.console import create_app
    from test_console import Client

    seen: list[Found] = []
    _recording(monkeypatch, seen)
    # the catalog example
    box = build(EXAMPLE / "catalog.umf.json", EXAMPLE / "seed.json")
    read = _load_read()
    carol = box.arras.session(box.people["carol"])
    read.cards(carol)
    read.use_case(carol, "triage-incident-alerts")
    read.products(carol)
    # the GraphQL layer: by key, a list filtered by a property and a relationship, a target
    c = Client()
    c.app = create_app(c.h, principal_for_request=c.who)
    c.gql('{ useCase(key: "uc-pipeline") { key addressedBy { target { key } } } }')
    c.gql('{ useCaseList(filter: {addressedBy: "sol-1", name: "Pipeline"}) { items { key } } }')
    c.gql("{ solutionList(consistency: BULK) { items { key } } }")
    c.gql('{ useCaseList(limit: 1, afterKey: "uc-1") { items { key } truncated } }')
    # the MCP tool description's example, and what the console's query panel puts in its editor
    sandbox = Sandbox().seed()
    o = sandbox.arras.session(sandbox.principal("carol"))
    mods = o.describe()
    doc = sandbox.store.documents["catalog"].decode()
    example = re.search(
        r'Example: module "catalog", (SELECT .*?) with params', McpServer._example(mods)
    )
    assert example is not None
    seen.append((example.group(1), {"k": "uc-pipeline"}, doc))
    panel = (ROOT / "ui/src/areas/QueryPanels.tsx").read_text()
    template = (
        "SELECT ${projection} FROM ${weftType(type.name)} x"
        " ORDER BY x.${weftName(type.key)} LIMIT ${size + 1}"
    )
    assert template in panel
    for m in mods:  # the statements the panel offers for each type, at the default page of 100
        for t in m.entity_types:
            cols = [
                p.name for p in t.properties if p.required and p.scalar and p.cardinality == "one"
            ]
            for projection in ("x.*", ", ".join(f"x.{quoted(c)}" for c in cols)):
                source, key = quoted_type(t.name), quoted(t.key)
                sql = f"SELECT {projection} FROM {source} x ORDER BY x.{key} LIMIT 101"
                seen.append((sql, {}, doc))
    return seen


def test_the_statements_are_collected(monkeypatch: pytest.MonkeyPatch) -> None:
    """The collection itself: every caller is reached, and relationship predicates are Weft's."""
    found = _corpus() + _callers(monkeypatch)
    sqls = [sql for sql, _, _ in found]
    assert len(found) > 40
    assert any('HAS_RELATED(x."addressedBy"' in s for s in sqls)  # GraphQL
    assert any("HAS_RELATED(s.addresses" in s for s in sqls)  # the example and the corpus
    assert any("COUNT(*)" in s for s in sqls)
    # every page and grouped count takes its profile's shape (ORDER BY and LIMIT), and every other
    # statement names a LIMIT or is a global aggregate: one row
    assert [s for s in sqls if "LIMIT" not in s and not s.startswith("SELECT COUNT(*)")] == []
    assert [s for s in sqls if "LIMIT" in s and "ORDER BY" not in s] == []
    assert any(" JOIN " in s for s in sqls)  # the corpus's relational reads
    assert any('RELATED_KEYS(x."addressedBy", 100)' in s for s in sqls)  # GraphQL
    assert any('RELATED_KEYS(x."addresses", 100)' in s for s in sqls)  # the example
    assert any(
        re.search(r'\."?code"? > :\w+ ORDER BY \w\."?code"? LIMIT', s) for s in sqls
    )  # keyset
    assert any('x."code" > :after' in s for s in sqls)  # a GraphQL list's next page (afterKey)
    # no relationship is compared with `=` any more, anywhere a statement is written
    rel = re.compile(r'\."?(addresses|addressedBy|ofUseCase|appliesTo|adjacentTo|uses)"?\s*=')
    assert [s for s in sqls if rel.search(s)] == []


def _family(v: Any) -> str:
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, Decimal):
        return "decimal"
    return "string"


def _profile(sql: str, params: dict[str, Any], document: str) -> str | None:
    """The Weft read profile the statement is written to, as the memory adapter classifies it; `None`
    for the general dialect, and for a statement the memory adapter refuses (Weft then judges it
    against the whole dialect, the least it can refuse)."""
    try:
        plan = resolve(Statement(sql, params), parse_module(document))
    except (Invalid, Unsupported):
        return None
    needed = profiles_needed(plan)[0]
    return None if needed == GENERAL else needed


def _named(document: str) -> str:
    """The document as Weft reads a model: every record and field carries a `name` (Weft's
    CONTRACT-001, Naming), and an integer field its width. Arras's registered documents name
    elements by `id` only, so the check derives the names the way a backend's model would carry
    them, and does not alter the document Arras holds. Weft 0.4.51 reads a UMF 0.10 record or field
    that carries an extension (Arras's `umf.ddd` entity semantics, `arras.view`) as outside the
    raw scalar profile (`WFT-TYPE`), so the model it is shown has no extensions: a read names
    records, fields and their scalar types only."""
    d = json.loads(document)
    for module in d["modules"]:
        for e in module.get("elements", []):
            if e["kind"] == "record":
                e["name"] = e["id"]
                e["extensions"] = {}
            elif e["kind"] == "field":
                e["extensions"] = {}
                e["name"] = e["id"].split(".", 1)[-1]
                if e.get("scalarType") == "integer":
                    e.setdefault("facets", {"integerWidth": {"bits": 64, "signed": True}})
    return json.dumps(d)


_AUTO = "auto"  # the profile the memory adapter classifies the statement to


def _request(sql: str, params: dict[str, Any], document: str, profile: str | None = _AUTO) -> str:
    """A compile request under `profile` (`None` for the general dialect)."""
    if profile == _AUTO:
        profile = _profile(sql, params, document)
    document = _named(document)
    d = json.loads(document)
    binding = json.dumps({"fixtureOnly": True, "purpose": "arras parse check"})
    sha = lambda text: hashlib.sha256(text.encode()).hexdigest()  # noqa: E731
    read_profile = (
        {"readProfile": {"version": "weft-application-read/0.2.0", "subset": profile}}
        if profile
        else {}
    )
    return json.dumps(
        {
            "interfaceVersion": "weft-compile/0.2.0",
            "dialect": "weft-sql/0.2.0",
            "sql": sql,
            **read_profile,
            "parameters": {
                k: {
                    "family": _family(v),
                    "value": str(v).lower() if isinstance(v, bool) else str(v),
                }
                for k, v in params.items()
            },
            "modules": [
                {
                    "documentJson": document,
                    "pin": {
                        "documentId": d["id"],
                        "revision": "arras-parse-check",
                        "umfVersion": d["umf"],
                        "sha256": sha(document),
                    },
                    "selectedModuleIds": [m["id"] for m in d["modules"]],
                }
            ],
            "target": {
                "backendId": "truss.postgresql",
                "backendVersion": "parse-check",
                "targetProfile": "parse-check",
                "bindingJson": binding,
                "bindingSha256": sha(binding),
            },
        }
    )


# What Weft's response says. Only a clean compile (no code) or a refusal from the target and binding
# stages, which come after the statement was parsed, named, typed and held to its read profile,
# counts as read. A fault of the statement itself (its syntax, a construct, its profile's shape, a
# name, a type, its grouping or a parameter) fails it; any other code (the request, the module
# model or a limit refused before or around the parse, such as WFT-MODEL, WFT-MODEL-VERSION or
# WFT-LIMIT) means the check did not see the statement checked, and fails naming the code.
PARSE_FAULTS = {
    "WFT-SYNTAX",
    "WFT-UNSUPPORTED",
    "WFT-PROFILE",
    "WFT-NAME-MISSING",
    "WFT-NAME-AMBIGUOUS",
    "WFT-TYPE",
    "WFT-GROUPING",
    "WFT-PARAMETER",
    "WFT-OUTPUT-NAME",
    "WFT-NUMERIC-DOMAIN",
}
AFTER_PARSE = {"WFT-BACKEND-MISSING", "WFT-BACKEND-VERSION", "WFT-BINDING", "WFT-CAPABILITY"}


def _codes(raw: str) -> set[str]:
    return set(re.findall(r'"(WFT-[A-Z0-9-]+)"', raw))


def classify(codes: set[str]) -> str:
    """`read` (the parser read it), `unread` (a parse fault), or `unseen` (no parse was shown)."""
    if codes & PARSE_FAULTS:
        return "unread"
    return "read" if codes <= AFTER_PARSE else "unseen"


def test_only_a_parse_stage_result_counts_as_read() -> None:
    assert classify(set()) == "read" and classify({"WFT-BACKEND-MISSING"}) == "read"
    for code in sorted(PARSE_FAULTS):  # the statement's own faults, the profile's shape included
        assert classify({code}) == "unread", code
        assert classify({code, "WFT-BACKEND-MISSING"}) == "unread", code
    for code in ("WFT-MODEL", "WFT-MODEL-VERSION", "WFT-LIMIT", "WFT-INPUT", "WFT-PIN"):
        assert classify({code}) == "unseen"
    assert classify({"WFT-BACKEND-MISSING", "WFT-LIMIT"}) == "unseen"


Intended = tuple[str, dict[str, Any], str, str | None]


def _intended(monkeypatch: pytest.MonkeyPatch) -> list[Intended]:
    """Each statement with the read profile it is written to, which Weft holds it to: a corpus
    step names its own (`requires.profiles`; `general` sends none); a caller's is the named profile
    its shape takes (a page or a count), never the general dialect."""
    corpus = load_corpus()
    out: list[Intended] = []
    for c in corpus["cases"]:
        for s in c["steps"]:
            if s["op"] == "query" and "error" not in s["expect"]:
                params = s.get("params") or {}
                needs = (s.get("requires") or {}).get("profiles", [])
                named = [p for p in needs if p != GENERAL]
                want = (
                    named[0]
                    if named
                    else None
                    if needs
                    else _profile(s["sql"], params, corpus["_module_text"])
                )
                out.append((s["sql"], params, corpus["_module_text"], want))
    out += [(sql, p, doc, _profile(sql, p, doc)) for sql, p, doc in _callers(monkeypatch)]
    return out


def test_every_caller_writes_to_a_named_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """GraphQL, the MCP example, the console and the catalog example write pages and counts: each
    takes a named profile's shape, so Weft holds it to that profile, never to the general dialect."""
    general = [sql for sql, p, doc in _callers(monkeypatch) if _profile(sql, p, doc) is None]
    assert general == []


def test_every_statement_is_read_by_weft_s_own_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    compile_json = compile_or_skip("the statements were not checked against it")
    unread: list[str] = []
    unseen: list[str] = []
    for sql, params, document, profile in _intended(monkeypatch):
        codes = _codes(compile_json(_request(sql, params, document, profile)))
        verdict = classify(codes)
        if verdict == "unread":
            unread.append(f"{sql} -> {sorted(codes & PARSE_FAULTS)}")
        elif verdict == "unseen":
            unseen.append(f"{sql} -> {sorted(codes - AFTER_PARSE)}")
    assert unseen == [], (
        "Weft answered before or around the parse: the check's request needs updating"
    )
    assert unread == []


def test_a_missing_parser_skips_visibly_or_fails_when_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    me = sys.modules[__name__]
    monkeypatch.setattr(me, "_weft", lambda: None)
    monkeypatch.delenv("ARRAS_REQUIRE_WEFT", raising=False)
    with pytest.raises(pytest.skip.Exception, match="not importable"):
        me.compile_or_skip("nothing checked")
    monkeypatch.setenv("ARRAS_REQUIRE_WEFT", "1")  # CI: a missing parser fails the run
    with pytest.raises(pytest.fail.Exception, match="ARRAS_REQUIRE_WEFT=1"):
        me.compile_or_skip("nothing checked")
