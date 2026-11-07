# SPDX-License-Identifier: MIT OR Apache-2.0
"""A synthetic public graph for measuring the static read-only profile (ADR-031): about a thousand nodes of up
to 8 KB, one hub with a thousand edges, a few thousand links. Deterministic: the same files every run.

    uv run python tools/gen_synthetic_graph.py OUT_DIR [--docs 1000]

Writes `OUT_DIR/synthetic.umf.json` and `OUT_DIR/synthetic.graph.json`.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "examples"))
from ontology import document  # noqa: E402

WORDS = (
    "agent pipeline runbook dataset review model prompt latency policy retrieval vector index schema "
    "ontology graph document evaluation metric baseline rollout incident alert triage summary quality "
    "workflow platform service gateway queue cache storage compute budget privacy security audit "
    "template guideline example benchmark release version upgrade migration integration connector"
).split()


def spec() -> dict[str, Any]:
    return {
        "id": "synthetic-fixture",
        "module": "synthetic",
        "view": {"title": "Synthetic atlas", "description": "A thousand documents and one hub"},
        "types": {
            "Doc": [
                ("code", "string", True),
                ("name", "string", True),
                ("summary", "string", False),
                ("body", "string", False),
                ("kind", "string", False),
            ],
            "Topic": [
                ("slug", "string", True),
                ("title", "string", True),
                ("notes", "string", False),
            ],
        },
        "relationships": [
            ("about", "Doc", "Topic", "coveredBy", False),
            ("links", "Doc", "Doc", "linkedFrom", False),
        ],
        "records": {
            "Doc": {
                "label": "Document",
                "icon": "file-text",
                "tone": "blue",
                "title": "{name}",
                "summary": "{summary}",
                "sections": [{"label": "Body", "properties": ["body", "kind"]}],
                "search": ["name", "summary", "body"],
            },
            "Topic": {"label": "Topic", "icon": "tag", "tone": "teal", "title": "{title}"},
        },
        "fields": {"Doc.kind": {"format": "badge", "tones": {"guide": "green", "note": "slate"}}},
        "relationshipViews": {
            "about": {"label": "About", "inverseLabel": "Covered by", "order": 10},
            "links": {"label": "Links to", "inverseLabel": "Linked from", "order": 20},
        },
        "seed": [],
    }


def text(rnd: random.Random, size: int) -> str:
    out: list[str] = []
    n = 0
    while n < size:
        sentence = (
            " ".join(rnd.choice(WORDS) for _ in range(rnd.randint(8, 16))).capitalize() + ". "
        )
        out.append(sentence)
        n += len(sentence)
    return "".join(out)[:size].rstrip()


def build(docs: int) -> tuple[dict[str, Any], dict[str, Any]]:
    rnd = random.Random(20261106)
    records: list[dict[str, Any]] = []
    topics = ["hub"] + [f"topic-{i:02d}" for i in range(1, 24)]
    for slug in topics:
        records.append(
            {"type": "Topic", "key": slug, "properties": {"title": slug.replace("-", " ").title()}}
        )
    for i in range(docs):
        body = text(rnd, rnd.randint(6000, 8000))
        marker = f"needle{i % 50:02d}"
        records.append(
            {
                "type": "Doc",
                "key": f"doc-{i:04d}",
                "properties": {
                    "name": f"Document {i:04d} {rnd.choice(WORDS)}",
                    "summary": f"{text(rnd, 120)} {marker}",
                    "body": f"{body} {marker}",
                    "kind": "guide" if i % 3 else "note",
                },
            }
        )
    for i in range(docs):
        records.append({"relationship": "about", "source": f"doc-{i:04d}", "target": "hub"})
        records.append(
            {"relationship": "about", "source": f"doc-{i:04d}", "target": rnd.choice(topics[1:])}
        )
        for j in rnd.sample(range(docs), 3):
            if j != i:
                records.append(
                    {"relationship": "links", "source": f"doc-{i:04d}", "target": f"doc-{j:04d}"}
                )
    seen: set[tuple[Any, ...]] = set()
    unique = []
    for r in records:
        k = tuple(sorted(r.items())) if "relationship" in r else (r["type"], r["key"])
        if k not in seen:
            seen.add(k)
            unique.append(r)
    graph = {
        "format": "arras.graph",
        "version": 1,
        "module": "synthetic",
        "complete": True,
        "records": unique,
    }
    return document(spec()), graph


def main(argv: list[str]) -> int:
    out = Path(argv[0])
    docs = int(argv[argv.index("--docs") + 1]) if "--docs" in argv else 1000
    out.mkdir(parents=True, exist_ok=True)
    doc, graph = build(docs)
    (out / "synthetic.umf.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    (out / "synthetic.graph.json").write_text(
        json.dumps(graph, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    n = len(graph["records"])
    print(f"wrote {out}: {docs} documents, 24 topics, {n} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
