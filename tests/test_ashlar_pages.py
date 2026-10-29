# SPDX-License-Identifier: MIT OR Apache-2.0
"""Transport composition controls; no real compiler, SQL or policy qualification."""

import json
from typing import Any

import pytest

from arras.adapters.ashlar import pages
from arras.errors import Unavailable, Unsupported
from arras.types import Statement


class Parameters:
    def __init__(self, values: dict[str, Any]):
        self.values = values

    @classmethod
    def model_validate(cls, values: dict[str, Any]):
        return cls(values)

    def model_dump(self, *, mode: str):
        return dict(self.values)


class Entry:
    def __init__(self, program: str):
        self.program = program

    def artifact(self) -> dict[str, Any]:
        return json.loads(self.program)


class Compiler:
    def compile_engine_page_json(self, raw: str) -> str:
        return raw


def prepare(statement: Statement, **changes: Any) -> pages.PreparedPage:
    arguments: dict[str, Any] = {
        "source_bundle": {"original": "source"},
        "weft_inputs": {"original": "publication"},
        "compiler": Compiler(),
        "parameters_type": Parameters,
        "result_type": object,
        "page_size": 2,
    }
    arguments.update(changes)
    return pages.prepare_managed_page("replica", statement, **arguments)


def test_statement_and_owner_binding_are_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    sql = "SELECT p.name\nFROM original.Person p WHERE p.name = :name ORDER BY p.name"
    seen: list[object] = []
    source = {"original": {"source": "bytes"}}
    inputs = {"manifest": "publication-1"}

    def build(bundle: Any, binding: Any, statement: str, parameters: Any):
        assert bundle == source and binding == inputs and statement == sql
        assert parameters == {"name": {"family": "string", "value": "'SECRET%_\\"}}
        bundle.clear()  # Even a builder's mutation cannot alter retained caller input.
        return {"sql": statement, "parameters": parameters, "target": "original target"}

    def original(raw: str, *, parameters: Any, result: Any):
        seen.extend([parameters, result])
        return Entry(raw)

    monkeypatch.setattr(pages, "_owners", lambda: (build, original))
    out = prepare(Statement(sql, {"name": "'SECRET%_\\"}), source_bundle=source, weft_inputs=inputs)
    assert source == {"original": {"source": "bytes"}} and inputs == {"manifest": "publication-1"}
    envelope = json.loads(out.request_json)
    assert envelope["request"]["sql"] == sql
    assert envelope["compiler"] == "ashlar-spark4-pages" and envelope["pageSize"] == 2
    assert seen == [Parameters, object]
    assert out.parameters.model_dump(mode="python") == {"name": "'SECRET%_\\"}


@pytest.mark.parametrize("value", [1, True, None, 1.5, ["text"]])
def test_no_coercion_of_unsupported_parameters(value: Any) -> None:
    with pytest.raises(Unsupported):
        prepare(Statement("unchanged", {"value": value}))


@pytest.mark.parametrize("size", [0, True, 1000])
def test_page_bound_precedes_sdk(size: Any) -> None:
    with pytest.raises(Unsupported):
        prepare(Statement("unchanged"), page_size=size)


@pytest.mark.parametrize("failure", ["binding", "compile", "model", "correspondence", "bounds"])
def test_unknown_failure_is_safe_unavailable(monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    def build(*args: Any):
        if failure == "binding":
            raise ValueError("SECRET input")
        return {"sql": args[2]}

    def original(raw: str, **kwargs: Any):
        if failure == "model":
            raise ValueError("SECRET source")
        return Entry("{}" if failure == "correspondence" else raw)

    class BadCompiler(Compiler):
        def compile_engine_page_json(self, raw: str) -> str:
            if failure == "compile":
                raise RuntimeError("SECRET SQL")
            return "x" * 1_048_577 if failure == "bounds" else raw

    monkeypatch.setattr(pages, "_owners", lambda: (build, original))
    with pytest.raises(Unavailable) as found:
        prepare(Statement("SECRET statement"), compiler=BadCompiler())
    assert "SECRET" not in str(found.value)


def test_no_parameter_normalization(monkeypatch: pytest.MonkeyPatch) -> None:
    class Changed(Parameters):
        def model_dump(self, *, mode: str):
            return {"name": "changed"}

    def forbidden(*args: Any, **kwargs: Any):
        pytest.fail("normalizing model must not reach compiler")

    monkeypatch.setattr(pages, "_owners", lambda: (forbidden, forbidden))
    with pytest.raises(Unavailable):
        prepare(Statement("unchanged", {"name": "original"}), parameters_type=Changed)
