# SPDX-License-Identifier: MIT OR Apache-2.0
"""Generate and check the read corpus of the static profile (CONTRACT-012, ADR-031).

    uv run python tools/gen_static_reads.py          # write src/arras/conformance/read_cases.json
    uv run python tools/gen_static_reads.py --check  # fail if the file has drifted from the reference

The corpus is data: for each fixture (a UMF module document and an `arras.graph` file) a list of GraphQL
requests (a path, a query, variables) with the answer the Python reference gives. The reference is the
real console surface (`arras.console.create_app`) over the in-memory adapter holding the fixture, so the
TypeScript backend is held to what the Python library actually answers, not to a copy of it. What a run
compares is fixed by `normalise`, which CONTRACT-012 states: the profile-specific parts (the backend's
name and position, freshness times, attribution, a module's declared guards and effects) are dropped.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "examples"))
sys.path.insert(0, str(ROOT / "src"))

from arras.console import create_app  # noqa: E402
from arras.core import Arras  # noqa: E402
from arras.model import Placement  # noqa: E402
from arras.testing import InMemory  # noqa: E402

OUT = ROOT / "src" / "arras" / "conformance" / "read_cases.json"
VERSION = 1

# The two meta reads the interface makes (ui/src/api/client.ts), held here verbatim.
META_QUERY = (
    "{ modules { name record replicas providers revision view { title description } entityTypes { name key "
    "properties { name type required cardinality } capabilities } relationships { name source target "
    "sourceMultiplicity targetMultiplicity lifecycle inverse } actions { name description inputSpecs { name "
    "type kind cardinality } } } status { backend available reason position lag } }"
)
VIEW_FIELDS = (
    "declared label pluralLabel icon tone title summary sections { label properties collapsed } search "
    "fields { property label format hideWhenEmpty tones } relationships { field label hideWhenEmpty order }"
)
VIEWS_QUERY = f"{{ modules {{ name revision entityTypes {{ name view {{ {VIEW_FIELDS} }} }} }} }}"

DROP_KEYS = {
    "freshness",
    "createdBy",
    "createdAt",
    "updatedBy",
    "updatedAt",
    "position",
    "revision",
    "mutable",
    "latency_class",
    "locations",
}


def normalise(value: Any) -> Any:
    """What a run compares: the same reduction on both sides (see the module docstring)."""
    if isinstance(value, dict):
        return {
            ("static" if k == "memory" else k): normalise(v)
            for k, v in value.items()
            if k not in DROP_KEYS
        }
    if isinstance(value, list):
        return [normalise(v) for v in value]
    return "static" if value == "memory" else value


def normalise_result(status: int, body: Any) -> dict[str, Any]:
    """A response as compared: its status, data, and each error's code and path (and its message,
    except for a `BAD_QUERY`, whose text is the GraphQL implementation's own)."""
    out: dict[str, Any] = {"status": status}
    if "data" in body:
        out["data"] = normalise(body["data"])
    errors = []
    for e in body.get("errors", []):
        code = e.get("extensions", {}).get("code")
        item: dict[str, Any] = {"code": code}
        if "path" in e:
            item["path"] = e["path"]
        if code != "BAD_QUERY":
            item["message"] = e["message"]
            extra = {
                k: v for k, v in e.get("extensions", {}).items() if k not in ("code", "violations")
            }
            if extra:
                item["extensions"] = normalise(extra)
        errors.append(item)
    if errors:
        out["errors"] = errors
    return out


# -- fixtures -------------------------------------------------------------------------------------


def _reads_spec() -> dict[str, Any]:
    from ontology import document  # the examples' generator

    spec: dict[str, Any] = {
        "id": "reads-fixture",
        "module": "reads",
        "view": {"title": "Reads", "description": "Every scalar, a hub, text that needs the fold"},
        "types": {
            "Note": [
                ("code", "string", True),
                ("name", "string", True),
                ("body", "string", False),
                ("status", "string", False),
                ("count", "integer", False),
                ("big", "integer", False),
                ("price", "decimal", False),
                ("active", "boolean", False),
                ("seen", "timestamp", False),
                ("blob", "binary", False),
            ],
            "Topic": [
                ("slug", "string", True),
                ("title", "string", True),
                ("notes", "string", False),
            ],
            "Bare": [("id", "string", True), ("value", "string", False)],
        },
        "relationships": [
            ("mentions", "Note", "Topic", "mentionedBy", False),
            ("follows", "Topic", "Topic", "followedBy", False),
        ],
        "records": {
            "Note": {
                "label": "Note",
                "pluralLabel": "Notes",
                "icon": "file-text",
                "tone": "blue",
                "title": "{name}[ ({status})]",
                "summary": "{body}",
                "sections": [
                    {"label": "Numbers", "properties": ["count", "big", "price", "active"]},
                    {"label": "When", "properties": ["seen"], "collapsed": True},
                ],
                "search": ["name", "body"],
            },
            "Topic": {"label": "Topic", "icon": "tag", "tone": "teal", "title": "{title}"},
            "Bare": {},
        },
        "fields": {
            "Note.status": {"format": "badge", "tones": {"open": "green", "closed": "slate"}},
            "Note.seen": {"format": "datetime"},
        },
        "relationshipViews": {
            "mentions": {"label": "Mentions", "inverseLabel": "Mentioned by", "order": 10},
            "follows": {"label": "Follows", "inverseLabel": "Followed by"},
        },
        "seed": [],
    }
    doc = document(spec)
    # a many-valued string property, which the example generator does not write
    mod = doc["modules"][0]
    note = next(e for e in mod["elements"] if e["id"] == "Note" and e["kind"] == "record")
    note["members"].append({"module": "reads", "element": "Note.tags"})
    note["extensions"]["umf.ddd"]["fields"]["tags"] = {
        "type": {"kind": "scalar", "name": "string"},
        "cardinality": "many",
    }
    mod["elements"].append(
        {
            "id": "Note.tags",
            "kind": "field",
            "name": "tags",
            "nullability": "absent-allowed",
            "cardinality": "many",
            "scalarType": "string",
            "extensions": {},
        }
    )
    return {"doc": doc}


def _reads_records() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    topics = ["hub", "alpha", "strasse", "omega", "wide"]
    for slug in topics:
        out.append(
            {
                "type": "Topic",
                "key": slug,
                "properties": {
                    "title": {"strasse": "Straße", "omega": "Ωmega"}.get(slug, slug.title()),
                    "notes": "Notes about " + slug,
                },
            }
        )
    named = [
        ("n-001", "Alpha release plan", "Plan the alpha release of the tool", "open"),
        ("n-002", "STRASSE and Straße", "Both spellings of the street, İstanbul too", "closed"),
        ("n-003", "Ωmega notes", "Greek capital sigma: ΟΔΟΣ and ΣΑΣ", "open"),
        ("n-004", "Emoji 😀 note", "A surrogate pair 😀 sits before the match: alpha", None),
        ("n-005", "Long text", "word " * 60 + "needle " + "word " * 60, "open"),
        ("n-006", "Alpha beta gamma", None, "closed"),
        ("n-007", "Priced at seven", "An integer where a decimal is held", "open"),
    ]
    for i, (code, name, body, status) in enumerate(named):
        props: dict[str, Any] = {"name": name}
        if body is not None:
            props["body"] = body
        if status is not None:
            props["status"] = status
        if i == 0:
            props.update(
                {
                    "count": -7,
                    "big": 9007199254740993,
                    "price": "12.5",
                    "active": True,
                    "seen": "2026-03-04T05:06:07.5+02:00",
                    "blob": "aGVsbG8=",
                    "tags": ["a", "b"],
                }
            )
        if i == 6:
            props.update({"price": 7, "count": 9223372036854775807, "tags": ["only"]})
        if i == 1:
            props.update({"big": -9223372036854775808, "price": "0.05", "active": False})
            props["seen"] = "2026-01-01T00:00:00Z"
        out.append({"type": "Note", "key": code, "properties": props})
    for i in range(150):  # the hub: more edges than the 100 keys an entity carries
        out.append(
            {
                "type": "Note",
                "key": f"h-{i:03d}",
                "properties": {"name": f"Hub note {i:03d}", "body": "alpha " + ("x" * (i % 7))},
            }
        )
    out.append({"type": "Bare", "key": "b1", "properties": {}})
    out.append({"type": "Bare", "key": "b2", "properties": {"value": "only a value"}})
    for i in range(150):
        out.append({"relationship": "mentions", "source": f"h-{i:03d}", "target": "hub"})
    out.append({"relationship": "mentions", "source": "n-001", "target": "alpha"})
    out.append({"relationship": "mentions", "source": "n-001", "target": "wide"})
    out.append({"relationship": "mentions", "source": "n-002", "target": "strasse"})
    out.append({"relationship": "follows", "source": "alpha", "target": "hub"})
    out.append({"relationship": "follows", "source": "wide", "target": "alpha"})
    return out


def fixtures() -> dict[str, dict[str, Any]]:
    doc = _reads_spec()["doc"]
    catalog = ROOT / "examples" / "catalog"
    return {
        "reads": {
            "module": json.dumps(doc, indent=2, ensure_ascii=False),
            "records": _reads_records(),
        },
        "catalog": {
            "module": (catalog / "catalog.umf.json").read_text(encoding="utf-8"),
            "records": json.loads((catalog / "catalog.graph.json").read_text(encoding="utf-8"))[
                "records"
            ],
        },
        "pizza": {
            "module": (ROOT / "examples" / "pizza" / "pizza.umf.json").read_text(encoding="utf-8"),
            "records": json.loads(
                (ROOT / "examples" / "pizza" / "pizza.graph.json").read_text(encoding="utf-8")
            )["records"],
        },
    }


# -- the reference --------------------------------------------------------------------------------


class Reference:
    """The console surface over the in-memory adapter holding one fixture, as one reader."""

    def __init__(self, module_text: str, records: list[dict[str, Any]]) -> None:
        self.mem = InMemory()
        self.name = json.loads(module_text)["modules"][0]["id"]
        self.mem.register(module_text)
        result = self.mem.import_records(self.name, records)
        if result.rejected:
            raise SystemExit(f"fixture rejected: {result.rejected[:3]}")
        self.h = Arras.start(
            {"memory": self.mem.backends["memory"]},
            expected=("memory",),
            admin=self.mem.admin,
            default_placement=Placement("memory"),
        )
        reader = self.mem.person("reader", self.name, "read")
        self.app = create_app(self.h, principal_for_request=lambda _r: reader)

    def post(self, path: str, query: str, variables: dict[str, Any] | None) -> tuple[int, Any]:
        body = {"query": query, **({"variables": variables} if variables is not None else {})}
        data = json.dumps(body).encode()
        scope = {
            "type": "http",
            "method": "POST",
            "path": path,
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
        }
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": data, "more_body": False}

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        asyncio.run(self.app(scope, receive, send))
        return sent[0]["status"], json.loads(sent[1]["body"])


# -- the requests ---------------------------------------------------------------------------------

Case = dict[str, Any]


def _selection(t: dict[str, Any], rels: list[str]) -> str:
    props = [p["name"] for p in t["properties"] if p["name"] != t["key"]]
    refs = " ".join(f"{r} {{ module type key }}" for r in rels)
    return f"key type version {' '.join(props)} {refs}".strip()


def _case(
    cid: str,
    fixture: str,
    module: str,
    query: str,
    variables: dict[str, Any] | None = None,
    path: str | None = None,
) -> Case:
    c: Case = {"id": cid, "fixture": fixture, "path": path or f"/graphql/{module}", "query": query}
    if variables is not None:
        c["variables"] = variables
    return c


def _page_query(t: dict[str, Any], rels: list[str]) -> str:
    f = t["name"].split(".")[1]
    f = f[0].lower() + f[1:] + "List"
    sel = _selection(t, rels)
    return (
        "query($filter: JSON, $limit: Int, $afterKey: String) "
        f"{{ {f}(filter: $filter, limit: $limit, afterKey: $afterKey) {{ items {{ {sel} }} truncated }} }}"
    )


def _rels_of(meta: dict[str, Any], type_name: str) -> list[str]:
    out: list[str] = []
    for r in meta["relationships"]:
        if type_name in r["source"]:
            out.append(r["name"])
        if r["inverse"] and type_name in r["target"]:
            out.append(r["inverse"])
    return out


def _search_query(meta: dict[str, Any]) -> str:
    return (
        "query($text: String!, $types: [String!], $limit: Int) { _search(text: $text, types: $types, "
        "limit: $limit) { text hits { type key score label excerpt { text mark } matched entity { key type } } "
        "counts { type count atLeast } notSearched { type reason backend } truncated } }"
    )


def requests(name: str, ref: Reference) -> list[Case]:
    module = ref.name
    status, body = ref.post("/graphql", META_QUERY, None)
    meta = body["data"]["modules"][0]
    cases: list[Case] = [
        _case(f"{name}.meta", name, module, META_QUERY, None, "/graphql"),
        _case(f"{name}.views", name, module, VIEWS_QUERY, None, "/graphql"),
        _case(
            f"{name}.status",
            name,
            module,
            "{ status { backend available reason lag } }",
            None,
            "/graphql",
        ),
    ]
    for t in meta["entityTypes"]:
        local = t["name"].split(".")[1]
        rels = _rels_of(meta, t["name"])
        q = _page_query(t, rels)
        cases.append(_case(f"{name}.{local}.list", name, module, q, {"limit": 3}))
        _, first = ref.post(f"/graphql/{module}", q, {"limit": 3})
        items = next(iter(first["data"].values()))["items"]
        if items:
            cases.append(
                _case(
                    f"{name}.{local}.after",
                    name,
                    module,
                    q,
                    {"limit": 4, "afterKey": items[-1]["key"]},
                )
            )
            cases.append(
                _case(
                    f"{name}.{local}.filter-key",
                    name,
                    module,
                    q,
                    {"filter": {t["key"]: items[0]["key"]}},
                )
            )
            by = local[0].lower() + local[1:]
            sel = _selection(t, rels)
            cases.append(
                _case(
                    f"{name}.{local}.by-key",
                    name,
                    module,
                    f"query($key: String!) {{ {by}(key: $key) {{ {sel} }} }}",
                    {"key": items[0]["key"]},
                )
            )
            cases.append(
                _case(
                    f"{name}.{local}.by-key-missing",
                    name,
                    module,
                    f"query($key: String!) {{ {by}(key: $key) {{ key }} }}",
                    {"key": "no-such-key"},
                )
            )
        cases.append(
            _case(f"{name}.{local}.bad-filter", name, module, q, {"filter": {"nope": "x"}})
        )
        cases.append(_case(f"{name}.{local}.filter-not-object", name, module, q, {"filter": "x"}))
        cases.append(_case(f"{name}.{local}.limit-0", name, module, q, {"limit": 0}))
        cases.append(_case(f"{name}.{local}.limit-101", name, module, q, {"limit": 101}))
        cases += _relationship_cases(name, module, meta, t, local, ref)
    if name == "reads":
        note = next(t for t in meta["entityTypes"] if t["name"] == "reads.Note")
        sel = _selection(note, _rels_of(meta, "reads.Note"))
        q = f"query($key: String!) {{ note(key: $key) {{ {sel} }} }}"
        for k in ("n-001", "n-002", "n-003", "n-004", "n-005", "n-006", "n-007"):
            cases.append(_case(f"reads.Note.named-{k}", name, module, q, {"key": k}))
    cases += _search_cases(name, module, meta)
    cases += _fault_cases(name, module, meta)
    return cases


def _relationship_cases(
    name: str, module: str, meta: dict[str, Any], t: dict[str, Any], local: str, ref: Reference
) -> list[Case]:
    cases: list[Case] = []
    rels = _rels_of(meta, t["name"])
    if not rels:
        return cases
    by = local[0].lower() + local[1:]
    q = _page_query(t, rels)
    _, page = ref.post(f"/graphql/{module}", q, {"limit": 100})
    rows = next(iter(page["data"].values()))["items"]
    for rel in rels:
        # the entity with the most keys on this relationship, then each of its targets opened
        best = max(rows, key=lambda r: len(r.get(rel) or []), default=None)
        if best is None or not best.get(rel):
            continue
        follow = f"query($key: String!) {{ {by}(key: $key) {{ {rel} {{ module type key target {{ key type }} }} }} }}"
        cases.append(
            _case(f"{name}.{local}.follow-{rel}", name, module, follow, {"key": best["key"]})
        )
        other = best[rel][0]
        o_local = other["type"].split(".")[1]
        o_type = next(x for x in meta["entityTypes"] if x["name"] == other["type"])
        cases.append(
            _case(
                f"{name}.{local}.has-related-{rel}",
                name,
                module,
                _page_query(o_type, _rels_of(meta, o_type["name"])),
                {"filter": {_inverse_of(meta, t["name"], rel): best["key"]}, "limit": 5},
            )
        ) if _inverse_of(meta, t["name"], rel) else None
        _ = o_local
    return cases


def _inverse_of(meta: dict[str, Any], type_name: str, field: str) -> str | None:
    for r in meta["relationships"]:
        if r["name"] == field and type_name in r["source"]:
            return r["inverse"]
        if r["inverse"] == field and type_name in r["target"]:
            return r["name"]
    return None


def _search_cases(name: str, module: str, meta: dict[str, Any]) -> list[Case]:
    q = _search_query(meta)
    words = {
        "reads": [
            "alpha",
            "STRASSE",
            "straße",
            "ωmega",
            "οδοσ",
            "σας",
            "needle",
            "😀",
            "alpha beta",
            "alpha  hub",
            "zzzz",
            "al",
            "a",
            "hub note",
            "x" * 201,
            "a b c d e f g",
            "İstanbul",
        ],
        "catalog": ["pipeline", "runbook", "ai", "review", "zzzz", "data"],
        "pizza": ["mozz", "pepperoni", "hot", "zz", "italy"],
    }[name]
    out = [_case(f"{name}.search.{i}", name, module, q, {"text": w}) for i, w in enumerate(words)]
    t0 = meta["entityTypes"][0]["name"].split(".")[1]
    out += [
        _case(f"{name}.search.types", name, module, q, {"text": words[0], "types": [t0]}),
        _case(f"{name}.search.bad-type", name, module, q, {"text": words[0], "types": ["Nope"]}),
        _case(f"{name}.search.limit-1", name, module, q, {"text": words[0], "limit": 1}),
        _case(f"{name}.search.limit-0", name, module, q, {"text": words[0], "limit": 0}),
        _case(f"{name}.search.limit-51", name, module, q, {"text": words[0], "limit": 51}),
    ]
    return out


def _fault_cases(name: str, module: str, meta: dict[str, Any]) -> list[Case]:
    t = meta["entityTypes"][0]
    local = t["name"].split(".")[1]
    f = local[0].lower() + local[1:] + "List"
    nest = "key " * 51
    lists = " ".join(f"a{i}: {f}(limit: 100) {{ items {{ key }} }}" for i in range(11))
    return [
        _case(f"{name}.fault.syntax", name, module, "{ not valid"),
        _case(
            f"{name}.fault.unknown-module", name, "nope", "{ __typename }", None, "/graphql/nope"
        ),
        _case(f"{name}.fault.unknown-field", name, module, "{ nope }"),
        _case(
            f"{name}.fault.too-deep",
            name,
            module,
            f"{{ {f} {{ items {{ key {_deep(meta, t)} }} }} }}",
        ),
        _case(f"{name}.fault.too-many-fields", name, module, f"{{ {f} {{ items {{ {nest} }} }} }}"),
        _case(f"{name}.fault.entity-budget", name, module, f"{{ {lists} }}"),
        _case(f"{name}.fault.typename", name, module, "{ __typename }"),
    ]


def _deep(meta: dict[str, Any], t: dict[str, Any]) -> str:
    rels = _rels_of(meta, t["name"])
    if not rels:
        return "type"
    r = rels[0]
    return f"{r} {{ target {{ key {r} {{ target {{ key }} }} }} }}"


# -- generate / check -----------------------------------------------------------------------------


def generate() -> dict[str, Any]:
    fx = fixtures()
    cases: list[Case] = []
    for name, f in fx.items():
        ref = Reference(f["module"], f["records"])
        for c in requests(name, ref):
            status, body = ref.post(c["path"], c["query"], c.get("variables"))
            c["expect"] = normalise_result(status, body)
            cases.append(c)
    shipped = {
        "reads": {
            "module": fx["reads"]["module"],
            "graph": _graph(fx["reads"]["module"], fx["reads"]["records"]),
        },
        "catalog": {
            "module": "examples/catalog/catalog.umf.json",
            "graph": "examples/catalog/catalog.graph.json",
        },
        "pizza": {
            "module": "examples/pizza/pizza.umf.json",
            "graph": "examples/pizza/pizza.graph.json",
        },
    }
    return {"version": VERSION, "fixtures": shipped, "cases": cases}


def _graph(module_text: str, records: list[dict[str, Any]]) -> str:
    return (
        json.dumps(
            {
                "format": "arras.graph",
                "version": 1,
                "module": json.loads(module_text)["modules"][0]["id"],
                "complete": True,
                "records": records,
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )


def dumps(corpus: dict[str, Any]) -> str:
    return json.dumps(corpus, indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    text = dumps(generate())
    if "--check" in argv:
        if OUT.read_text(encoding="utf-8") != text:
            print(
                "read_cases.json drifted from the reference: run tools/gen_static_reads.py",
                file=sys.stderr,
            )
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    _declare(OUT)
    print(f"wrote {OUT} ({len(text)} bytes)")
    return 0


def _declare(path: Path) -> None:
    """Record the file's new digest in the public-content policy, which pins every shipped fixture."""
    import hashlib
    import re

    policy = ROOT / "tools" / "public-content-policy.json"
    rel = path.relative_to(ROOT).as_posix()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    text = policy.read_text(encoding="utf-8")
    pattern = re.compile(r'("path":"' + re.escape(rel) + r'".*?"sha256":")[0-9a-f]{64}')
    policy.write_text(pattern.sub(lambda m: m.group(1) + digest, text, count=1), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
