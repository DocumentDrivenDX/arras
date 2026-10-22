# SPDX-License-Identifier: MIT OR Apache-2.0
"""The CONTRACT-010 template grammar against the vectors the UI also reads
(`tests/vectors/template.json`); the Python evaluator in `arras.view` is the reference."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from arras.view import TemplateError, evaluate, parse_template

DOC: dict[str, Any] = json.loads((Path(__file__).parent / "vectors" / "template.json").read_text())
ROW: dict[str, Any] = DOC["row"]
VECTORS: list[dict[str, Any]] = DOC["vectors"]


@pytest.mark.parametrize("v", VECTORS, ids=[v["note"] for v in VECTORS])
def test_template_vector(v: dict[str, Any]) -> None:
    if v.get("malformed"):
        with pytest.raises(TemplateError):
            parse_template(v["template"])
    else:
        assert evaluate(v["template"], ROW) == v["expected"]


def test_vectors_cover_both_outcomes() -> None:
    assert len(VECTORS) >= 40
    assert any(v.get("malformed") for v in VECTORS)
    assert any(not v.get("malformed") for v in VECTORS)
