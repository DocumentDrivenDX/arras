# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The read corpus of the static profile (CONTRACT-012, ADR-031) holds for the Python reference.

`src/arras/conformance/read_cases.json` is generated from the console surface over the in-memory adapter
(`tools/gen_static_reads.py`) and the TypeScript backend is held to it (`ui/src/test/static-read-corpus.test.ts`).
This checks the file is what the reference gives now, so a change to a read that does not regenerate the corpus
fails here, and the two implementations cannot drift apart without one of the two suites saying so.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import gen_static_reads as gen  # noqa: E402  # isort: skip  # pyright: ignore[reportMissingImports]


@pytest.fixture(scope="module")
def corpus() -> dict:
    return json.loads(gen.OUT.read_text(encoding="utf-8"))


def test_the_corpus_is_what_the_reference_answers_now() -> None:
    assert gen.OUT.read_text(encoding="utf-8") == gen.dumps(gen.generate())


def test_the_corpus_covers_every_kind_of_answer(corpus: dict) -> None:
    codes = {e["code"] for c in corpus["cases"] for e in c["expect"].get("errors", [])}
    assert {
        "BAD_QUERY",
        "LIMIT_EXCEEDED",
        "COST_EXCEEDED",
        "DEPTH_EXCEEDED",
        "NOT_FOUND",
    } <= codes
    statuses = {c["expect"]["status"] for c in corpus["cases"]}
    assert statuses == {200, 400, 404}
    ids = {c["id"] for c in corpus["cases"]}
    for name in ("reads", "catalog", "pizza"):
        assert {f"{name}.meta", f"{name}.views", f"{name}.search.0"} <= ids
    assert len(corpus["cases"]) >= 200


def test_the_example_graph_files_are_the_exports_of_their_modules() -> None:
    # the pizza graph is made by the Export control's own code path; the corpus reads it as a fixture
    from arras import graphfile

    for name in ("catalog", "pizza"):
        text = (ROOT / "examples" / name / f"{name}.graph.json").read_text(encoding="utf-8")
        assert graphfile.dumps(graphfile.loads(text)) == text


def test_the_domain_vectors_are_what_the_memory_adapter_holds() -> None:
    """`tests/vectors/domain.json` is the reference for how a numeric field holds a value; the static
    profile's TypeScript is held to it (`ui/src/test/static-backend.test.ts`)."""
    from decimal import Decimal

    from arras.fakes_domain import Domain, stored

    doc = json.loads((ROOT / "tests" / "vectors" / "domain.json").read_text(encoding="utf-8"))
    domains = {
        name: Domain(
            d["family"],
            d.get("precision"),
            d.get("scale"),
            d.get("bits", 64),
            d.get("signed", True),
        )
        for name, d in doc["domains"].items()
    }
    assert len(doc["vectors"]) >= 30
    for v in doc["vectors"]:
        raw = v["value"]
        value = Decimal(raw) if v["domain"].startswith("decimal") else int(raw)
        if isinstance(raw, int):  # a JSON integer in a decimal field
            value = raw
        try:
            got: dict[str, str] = {"held": str(stored(domains[v["domain"]], value))}
        except ValueError as e:
            got = {"refused": str(e)}
        want = {k: x for k, x in v.items() if k in ("held", "refused")}
        assert got == want, v
