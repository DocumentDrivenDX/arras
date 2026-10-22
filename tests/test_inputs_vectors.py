# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""Typed inputs: the server reads text exactly as the UI does, and every kind of input reaches the
backend converted, through the real operator surface (CONTRACT-007, CONTRACT-009).

`tests/vectors/inputs.json` is shared with `ui/src/test/inputs.vectors.test.ts`: the same text is
accepted or refused on both sides. The server converts text for integers, decimals, timestamps and
binary; a boolean arrives as a JSON boolean, so its text vectors are the UI's alone."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from arras.inputs import convert_inputs, parse_timestamp, to_python
from test_operate import Client
from typed_module import VALID, lab_sandbox

VECTORS: list[dict[str, Any]] = json.loads(
    (Path(__file__).parent / "vectors" / "inputs.json").read_text()
)["vectors"]
TEXT_TYPES = ("timestamp", "integer", "decimal", "binary")
FROM_TEXT = [v for v in VECTORS if v["type"] in TEXT_TYPES]
INPUT_OF = {"integer": "count", "decimal": "amount", "timestamp": "at", "binary": "blob"}
RECORD = "/actions/lab/Record"


def _id(v: dict[str, Any]) -> str:
    return f"{v['type']}:{v['value']!r}:{'ok' if v['ok'] else 'bad'}"


@pytest.fixture(scope="module")
def lab() -> Client:
    return Client(lab_sandbox())


def test_the_vectors_cover_every_type_the_server_reads_from_text_both_ways() -> None:
    for t in TEXT_TYPES:
        assert {v["ok"] for v in VECTORS if v["type"] == t} == {True, False}, t


@pytest.mark.parametrize("v", FROM_TEXT, ids=_id)
def test_the_converter_accepts_exactly_the_shared_vectors(v: dict[str, Any], lab: Client) -> None:
    [mod] = lab.box.arras.session(lab.box.people["alice"]).describe("lab")
    out: list = []
    to_python(v["type"], "scalar", v["value"], "x", out, mod)
    assert (not out) == v["ok"]
    [action] = mod.actions
    values, faults = convert_inputs(action, mod, {INPUT_OF[v["type"]]: v["value"]})
    assert (not faults) == v["ok"]
    if faults:
        assert [(f.path, f.code) for f in faults] == [(f"inputs.{INPUT_OF[v['type']]}", "type")]
    else:
        assert not isinstance(values[INPUT_OF[v["type"]]], str) or v["type"] == "binary"


@pytest.mark.parametrize("v", FROM_TEXT, ids=_id)
def test_the_operator_surface_accepts_exactly_the_shared_vectors(
    v: dict[str, Any], lab: Client
) -> None:
    name = INPUT_OF[v["type"]]
    code = f"v{FROM_TEXT.index(v)}"
    inputs = {"code": code, "prior": "s0", name: v["value"]}
    status, val, _ = lab.post(f"{RECORD}/validate", {"inputs": inputs})
    assert status == 200 and val["ok"] == v["ok"], val
    if not v["ok"]:
        assert [x["path"] for x in val["violations"]] == [f"inputs.{name}"]
    status, r, _ = lab.post(f"{RECORD}/invoke", {"inputs": inputs})
    assert status == (200 if v["ok"] else 400), r
    if not v["ok"]:
        assert [x["path"] for x in r["error"]["violations"]] == [f"inputs.{name}"]


@pytest.mark.parametrize("v", [v for v in VECTORS if v["type"] == "timestamp"], ids=_id)
def test_audit_times_follow_the_same_rule(v: dict[str, Any], lab: Client) -> None:
    assert (parse_timestamp(v["value"]) is not None) == v["ok"]
    for key in ("since", "until"):
        status, _, _ = lab.post("/audit/changes", {"module": "catalog", key: v["value"]})
        assert status == (200 if v["ok"] else 400), (key, v)


def test_a_timestamp_keeps_its_instant_and_offset() -> None:
    t = parse_timestamp("2026-10-09t14:02:11.1234567-05:30")
    assert t is not None and t.isoformat() == "2026-10-09T14:02:11.123456-05:30"
    assert parse_timestamp("2026-10-09T14:02:11+24:00") is None  # an offset is in range too
    assert parse_timestamp("2026-10-09T14:02:11+05:60") is None


def test_a_boolean_is_a_json_boolean_on_the_server(lab: Client) -> None:
    for flag, ok in ((True, True), (False, True), ("true", False), (1, False)):
        _, val, _ = lab.post(
            f"{RECORD}/validate", {"inputs": {"code": "b", "prior": "s0", "flag": flag}}
        )
        assert val["ok"] == ok, flag
        if not ok:
            assert [x["path"] for x in val["violations"]] == ["inputs.flag"]


# -- every kind of input, end to end --------------------------------------------------------------

BAD = {
    "count": "1.5",
    "amount": "NaN",
    "at": "2026-02-30T00:00:00Z",
    "blob": "aGk",
    "dims": {"width": "wide", "depth": "1e"},
}
BAD_PATHS = {"inputs.count", "inputs.amount", "inputs.at", "inputs.blob", "inputs.dims.width"}
BAD_PATHS |= {"inputs.dims.depth"}


def test_valid_typed_inputs_round_trip_and_are_stored() -> None:
    c = Client(lab_sandbox())
    status, r, _ = c.post(f"{RECORD}/invoke", {"inputs": VALID})
    assert status == 200 and (r["created"], r["linked"]) == (3, 1), r
    q = """{ sample(key: "s1") { count amount at blob flag dims follows { key } }
             a: tag(key: "t-a") { key } b: tag(key: "t-b") { key } }"""
    status, out = _console(c, q)
    assert status == 200 and "errors" not in out, out
    s = out["data"]["sample"]
    assert s == {
        "count": "9007199254740993",  # BigInt: past 53 bits, kept exact
        "amount": "12.50",  # Decimal: as typed, trailing zero kept
        "at": "2026-10-09T14:02:11.500000+02:00",  # the instant and the offset as authored
        "blob": "aGk=",
        "flag": True,
        "dims": {"width": 3, "depth": "0.25"},  # a structured value, its fields converted
        "follows": [{"key": "s0"}],
    }
    assert out["data"]["a"] == {"key": "t-a"} and out["data"]["b"] == {"key": "t-b"}


def _console(c: Client, query: str) -> tuple[int, Any]:
    """A read through the real console app over the same sandbox."""
    import asyncio

    from arras.console import create_app as console_app

    app = console_app(c.box.arras, principal_for_request=lambda r: c.box.people["alice"])
    data = json.dumps({"query": query}).encode()
    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": data, "more_body": False}

    async def send(m: dict) -> None:
        sent.append(m)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/graphql/lab",
        "headers": [(b"content-type", b"application/json")],
        "query_string": b"",
    }
    asyncio.run(app(scope, receive, send))
    return sent[0]["status"], json.loads(sent[1]["body"])


def test_malformed_typed_inputs_are_violations_at_their_paths_and_nothing_is_applied() -> None:
    c = Client(lab_sandbox())
    bad = {**VALID, **BAD}
    status, v, _ = c.post(f"{RECORD}/validate", {"inputs": bad})
    assert status == 200 and v["ok"] is False
    assert {x["path"] for x in v["violations"]} == BAD_PATHS
    status, e, _ = c.post(f"{RECORD}/invoke", {"inputs": bad})
    assert status == 400 and e["error"]["type"] == "Invalid"
    assert {x["path"] for x in e["error"]["violations"]} == BAD_PATHS
    items = [{**VALID, "code": "s2", "tags": []}, bad]
    status, e, _ = c.post(f"{RECORD}/batch", {"items": items})
    assert status == 400
    assert {x["path"] for x in e["error"]["violations"]} == {
        p.replace("inputs.", "items[1].inputs.") for p in BAD_PATHS
    }
    _, page, _ = c.post("/audit/changes", {"module": "lab"})
    assert page["items"] == []  # nothing applied, nothing recorded


def test_a_fault_only_the_converter_sees_still_refuses_the_call() -> None:
    """An integer past 53 bits sent as a JSON number would be accepted by the library, which
    takes any `int`; the converter refuses it, because a browser has already rounded it. The
    refusal must reach the caller from validate, invoke and batch alike."""
    c = Client(lab_sandbox())
    big = {**VALID, "count": 2**53 + 1}
    status, v, _ = c.post(f"{RECORD}/validate", {"inputs": big})
    assert status == 200 and v["ok"] is False
    assert [x["path"] for x in v["violations"]] == ["inputs.count"]
    status, e, _ = c.post(f"{RECORD}/invoke", {"inputs": big})
    assert status == 400 and [x["path"] for x in e["error"]["violations"]] == ["inputs.count"]
    status, e, _ = c.post(f"{RECORD}/batch", {"items": [big], "atomic": True})
    assert status == 400
    assert [x["path"] for x in e["error"]["violations"]] == ["items[0].inputs.count"]
    status, e, _ = c.post(f"{RECORD}/batch", {"items": [{**VALID, "dims": {"width": 2**60}}]})
    assert status == 400
    assert [x["path"] for x in e["error"]["violations"]] == ["items[0].inputs.dims.width"]
    assert c.post("/audit/changes", {"module": "lab"})[1]["items"] == []


@pytest.mark.parametrize(
    "type_,text",
    [
        ("integer", "1_000"),  # Python's int() takes these; a person's text does not
        ("integer", " 12"),
        ("integer", "12 "),
        ("integer", "\u0661\u0662"),  # Arabic-Indic digits
        ("integer", "\uff11"),  # a full-width digit
        ("decimal", "1_000.5"),
        ("decimal", " 1.5"),
        ("decimal", "sNaN"),
        ("decimal", "inf"),
        ("timestamp", "20261009T140211Z"),  # ISO 8601 basic form, not RFC 3339
        ("timestamp", "2026-10-09T14:02:11 Z"),
        ("timestamp", "2026-10-09T14:02:11+0200"),
        ("timestamp", "2026-W41-5T14:02:11Z"),
        ("binary", "aGk=\n"),
    ],
)
def test_text_that_python_would_take_but_a_person_would_not_type_is_refused(
    type_: str, text: str, lab: Client
) -> None:
    """Beyond the shared vectors: what Python's own parsers accept and the RFCs do not."""
    [mod] = lab.box.arras.session(lab.box.people["alice"]).describe("lab")
    out: list = []
    to_python(type_, "scalar", text, "x", out, mod)
    assert [v.path for v in out] == ["x"]
