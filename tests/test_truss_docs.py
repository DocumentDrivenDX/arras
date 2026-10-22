# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""Release readiness of the Truss adapter: the documents describe what was built.

The governed documents state the present design only: no migration tool of Arras's own, no
vendored DDL, no embedded Postgres 16, no journal-row receipts. The release gates the publish on
the Truss-marked suite and keeps the Truss extra in its sync, so the adapter stays strictly typed
and the base wheel stays free of Truss.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs/helix"

# The plan, the traceability matrix and the spikes record what was found or decided on the way;
# every other governed document and the README describe the design as it stands.
EXEMPT = ("02-design/spikes/", "04-build/", "03-test/traceability.md")
STALE = re.compile(
    r"alembic|vendored|embedded postgres|postgres(ql)? 16|history schema|apply_group"
    r"|import_batch(?!ed_in_transaction|es\b)"
    r"|(?<!no )migration history|administrative principal[^.|]*\bmigrations?\b",
    re.IGNORECASE,
)


def _governed() -> list[Path]:
    found = [p for p in DOCS.rglob("*.md") if not any(x in p.as_posix() for x in EXEMPT)]
    return [*found, ROOT / "README.md"]


def test_no_governed_document_describes_a_design_that_is_gone() -> None:
    hits = [
        f"{p.relative_to(ROOT)}:{n}: {line.strip()[:80]}"
        for p in _governed()
        for n, line in enumerate(p.read_text().splitlines(), 1)
        if STALE.search(line)
    ]
    assert hits == []


def test_the_requirements_note_is_generic_and_states_the_pinned_release() -> None:
    note = (DOCS / "02-design/truss-requirements.md").read_text()
    assert "arras" not in note.lower()
    assert "0.1.0.dev38" not in note
    assert "truss-toolkit==0.0.45" in note
    for ask in ("R19", "R20", "R21", "R22"):
        assert re.search(rf"^\| {ask} \|", note, re.MULTILINE), ask


def test_the_readme_states_the_host_prerequisites() -> None:
    readme = (ROOT / "README.md").read_text()
    for needle in ("ConnectionSource", "PostgreSQL 18.6", "Unsupported"):
        assert needle in readme, needle
    assert "Not built, because they wait on Truss" not in readme
    assert "No Bun, Node or other process on the machine" in readme
    assert "deploy-time job" in readme


def test_no_bun_is_named_or_passed_anywhere() -> None:
    """Truss 0.0.45 prepares a module in process: no adapter call is given a Bun path."""
    adapter = ROOT / "src/arras/adapters/truss"
    users = sorted(p.name for p in adapter.glob("*.py") if "bun" in p.read_text().lower())
    assert users == []
    contract = (DOCS / "02-design/contracts/CONTRACT-005-embedding-and-lifecycle.md").read_text()
    assert "no Bun, no Node and an empty `PATH`" in contract
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "setup-bun" not in ci and "bun-version" not in ci


def test_the_release_gates_the_publish_on_the_truss_suite() -> None:
    release = (ROOT / ".github/workflows/release.yml").read_text()
    assert "uv sync --locked --extra truss" in release
    assert "assert importlib.util.find_spec('truss') is None" in release
    assert "pytest -m truss" in release
    assert "setup-bun" not in release
    publish = release.split("\n  publish-pypi:\n", 1)[1].split("\n  publish-npm:", 1)[0]
    assert re.search(r"needs:\s*\[(?=.*build)(?=.*truss)", publish) is not None
    build = release.split("\n  build:\n", 1)[1].split("\n  truss:", 1)[0]
    assert re.search(r"needs:\s*\[(?=.*truss)", build) is not None


def test_the_requirements_note_names_the_corpus_limits_the_harness_pins() -> None:
    from truss_harness import TrussHarness

    text = (DOCS / "02-design/truss-requirements.md").read_text()
    sentence = next(
        s for s in re.split(r"(?<=\))[,.] ", text) if "corpus cases end at documented limits" in s
    )
    words = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
    stated = re.search(r"(\w+) corpus cases end at documented limits", sentence)
    assert stated is not None
    count = stated.group(1).lower()
    assert (words.index(count) + 1 if count in words else int(count)) == len(TrussHarness.LIMITS)
    limits_part = text[text.index(stated.group(0)) :].split("\n", 1)[0]
    named = set(re.findall(r"`([a-z]+\.[a-z0-9.-]+)`", limits_part.split("), and ")[0]))
    assert named == set(TrussHarness.LIMITS)
