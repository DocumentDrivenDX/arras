# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The `arras.view` cases of CONTRACT-010 as data: each is one registration or resolution."""

import pytest

from arras.conformance.views import load_view_cases, run_case

CASES = load_view_cases()


@pytest.mark.parametrize("case", CASES["cases"], ids=[c["id"] for c in CASES["cases"]])
def test_view_case(case: dict) -> None:
    result = run_case(case, CASES["_document"])
    assert result.ok, result.message


def test_the_view_corpus_is_well_formed() -> None:
    ids = [c["id"] for c in CASES["cases"]]
    assert len(ids) == len(set(ids))
    for c in CASES["cases"]:
        assert c["covers"] and c["description"] and "expect" in c
        assert all("at" in s for s in c["set"])


def test_every_view_code_is_refused_by_some_case() -> None:
    """@covers US-070-AC4: each fault code of CONTRACT-010 has a case."""
    codes = {v["code"] for c in CASES["cases"] for v in c["expect"].get("violations", [])}
    assert codes == {
        "view_unknown_term",
        "view_unknown_property",
        "view_unknown_relationship",
        "view_format_mismatch",
        "view_unknown_icon",
        "view_unknown_tone",
        "view_bad_template",
        "view_duplicate",
        "view_too_large",
        "view_unsupported_version",
    }


def test_a_case_that_expects_a_refusal_fails_when_the_document_registers() -> None:
    case = {
        "id": "x",
        "covers": [],
        "set": [],
        "expect": {"violations": [{"code": "view_unknown_term", "path": "p"}]},
    }
    assert not run_case(case, CASES["_document"]).ok
