# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""CONTRACT-009, `POST /query`: a read-only query as the viewer, answered as a grid."""

import logging

import pytest

from test_operate import Client

SQL = "SELECT u.code, u.name FROM catalog.UseCase u ORDER BY u.code LIMIT 100"
SECRET = "s3cret-value-in-a-query"


@pytest.fixture
def c() -> Client:
    return Client()


def test_a_query_is_a_grid_with_its_freshness_and_revision(c: Client) -> None:
    status, r, _ = c.post("/query", {"module": "catalog", "sql": SQL})
    assert status == 200
    assert [x["name"] for x in r["columns"]] == ["code", "name"]
    assert {row["code"] for row in r["rows"]} == {"uc-pipeline", "uc-alerts"}
    assert r["truncated"] is False and "nextCursor" not in r
    assert r["freshness"]["backend"] == "memory" and r["freshness"]["consistency"] == "latest"
    assert r["revision"] == {"memory": r["revision"]["memory"]}


def test_bulk_is_answered_by_the_replica_and_says_so(c: Client) -> None:
    status, r, _ = c.post("/query", {"module": "catalog", "sql": SQL, "consistency": "bulk"})
    assert status == 200 and r["freshness"]["backend"] == "memory_replica"
    assert r["freshness"]["consistency"] == "bulk"


def test_a_longer_answer_pages_by_a_keyset_in_the_statement(c: Client) -> None:
    status, first, _ = c.post("/query", {"module": "catalog", "sql": SQL, "limit": 1})
    assert status == 200 and len(first["rows"]) == 1 and first["truncated"] is True
    following = "SELECT u.code, u.name FROM catalog.UseCase u WHERE u.code > :last ORDER BY u.code LIMIT 100"
    body = {"sql": following, "params": {"last": first["rows"][0]["code"]}, "limit": 1}
    status, second, _ = c.post("/query", {"module": "catalog", **body})
    assert status == 200 and second["rows"][0]["code"] > first["rows"][0]["code"]
    status, err, _ = c.post("/query", {"module": "catalog", "sql": SQL, "after": "c1.x"})
    assert status == 400  # a page is the statement's own: there is no cursor to pass


def test_named_parameters_are_bound_not_spliced(c: Client) -> None:
    sql = "SELECT u.code FROM catalog.UseCase u WHERE u.code = :k ORDER BY u.code LIMIT 100"
    status, r, _ = c.post(
        "/query", {"module": "catalog", "sql": sql, "params": {"k": "uc-pipeline"}}
    )
    assert status == 200 and [row["code"] for row in r["rows"]] == ["uc-pipeline"]
    status, r, _ = c.post(
        "/query", {"module": "catalog", "sql": sql, "params": {"k": "x' OR '1'='1"}}
    )
    assert status == 200 and r["rows"] == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"module": "catalog", "sql": 3},
        {"module": "catalog", "sql": "  "},
        {"module": "catalog", "sql": SQL, "limit": 0},
        {"module": "catalog", "sql": SQL, "limit": 101},
        {"module": "catalog", "sql": SQL, "limit": "5"},
        {"module": "catalog", "sql": SQL, "consistency": "eventually"},
        {"module": "catalog", "sql": SQL, "consistency": 1},
        {"module": "catalog", "sql": SQL, "params": [1]},
        {"module": "catalog", "sql": SQL, "after": 5},
        {"sql": SQL},  # the module the statement reads is named
        {"module": 5, "sql": SQL},
    ],
)
def test_a_malformed_request_is_400(c: Client, body: dict) -> None:
    assert c.post("/query", body)[0] == 400


def test_the_text_is_at_most_4000_characters_and_16_kib(c: Client) -> None:
    pad = " " * (4000 - len(SQL))
    assert c.post("/query", {"module": "catalog", "sql": SQL + pad})[0] == 200
    assert (
        c.post("/query", {"module": "catalog", "sql": SQL + pad + " "})[0] == 400
    )  # the dialect's bound
    wide = SQL + " " + "é" * 8000  # 16 KiB of bytes, well over the character bound
    assert (
        c.post("/query", {"module": "catalog", "sql": wide + "é"})[0] == 400
    )  # refused before it is parsed


def test_a_query_that_does_not_parse_says_why_and_never_echoes_the_text(c: Client) -> None:
    status, err, _ = c.post(
        "/query", {"module": "catalog", "sql": f"DELETE FROM catalog.UseCase WHERE x = '{SECRET}'"}
    )
    assert status == 400 and err["error"]["violations"]
    assert SECRET not in str(err)


def test_a_value_of_the_wrong_type_is_not_echoed_in_the_answer_or_the_logs(
    c: Client, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    sql = "SELECT s.code FROM catalog.Solution s WHERE s.code = :v ORDER BY s.code LIMIT 100"
    assert (
        c.post("/query", {"module": "catalog", "sql": sql, "params": {"v": SECRET}})[0] == 200
    )  # a string fits
    typed = "SELECT u.code FROM catalog.UseCase u WHERE u.code = 12345 ORDER BY u.code LIMIT 100"
    status, err, _ = c.post("/query", {"module": "catalog", "sql": typed})
    assert status == 400 and err["error"]["violations"][0]["code"] == "type"
    assert "12345" not in str(err)
    assert not any(SECRET in r.getMessage() for r in caplog.records)


def test_a_lone_surrogate_is_a_400_not_a_fault(c: Client) -> None:
    status, err, _ = c.post("/query", {"module": "catalog", "sql": SQL + " \ud800"})
    assert status == 400 and err["error"]["type"] in ("Invalid", "BadRequest")


def test_an_unreadable_module_is_answered_as_an_unknown_one(c: Client) -> None:
    status, err, _ = c.post("/query", {"module": "catalog", "sql": SQL}, user="dave")
    unknown = c.post(
        "/query",
        {"module": "nothing", "sql": "SELECT u.code FROM nothing.Here u ORDER BY u.code LIMIT 5"},
    )
    assert status == 404 and unknown[0] == 404
    assert err["error"]["message"] == unknown[1]["error"]["message"]


def test_the_backends_grants_decide_per_person(c: Client) -> None:
    assert c.post("/query", {"module": "catalog", "sql": SQL}, user="carol")[0] == 200  # read only
    assert c.post("/query", {"module": "catalog", "sql": SQL}, user="dave")[0] == 404  # no access
    assert c.post("/query", {"module": "catalog", "sql": SQL}, user=None)[0] == 401
    c.box.access.expire(c.box.people["alice"].token)
    status, err, _ = c.post("/query", {"module": "catalog", "sql": SQL})
    assert (status, err["error"]["message"]) == (401, "sign in again")


def test_an_outage_is_a_503_never_an_empty_grid(c: Client) -> None:
    c.box.store.outage = "unreachable"
    status, err, _ = c.post("/query", {"module": "catalog", "sql": SQL})
    assert status == 503 and "rows" not in err


def test_a_replica_that_has_not_reached_a_token_is_409(c: Client) -> None:
    body = {"module": "catalog", "sql": SQL, "consistency": "bulk", "at_least": "fake:999999"}
    assert c.post("/query", body)[0] == 409


def test_a_cross_origin_post_is_refused_and_a_get_is_not_a_route(c: Client) -> None:
    assert (
        c.post("/query", {"module": "catalog", "sql": SQL}, origin="https://evil.example")[0] == 403
    )
    status, _, headers = c.call("GET", "/query")
    assert status == 405 and headers["allow"] == "POST"


def test_the_text_is_in_no_log_or_telemetry_attribute(
    c: Client, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    good = (
        f"SELECT u.code FROM catalog.UseCase u WHERE u.name = '{SECRET}' ORDER BY u.code LIMIT 100"
    )
    bad = (
        f"SELECT u.code FROM catalog.UseCase u WHERE u.name > '{SECRET}' ORDER BY u.code LIMIT 100"
    )
    c.post("/query", {"module": "catalog", "sql": good})
    c.post("/query", {"module": "catalog", "sql": bad})
    c.post("/query", {"module": "catalog", "sql": good}, user="dave")
    emitted = [r.getMessage() + str(r.__dict__.get("arras_attrs", "")) for r in caplog.records]
    assert emitted and not any(SECRET in e for e in emitted)


def test_a_non_operator_cannot_query_and_an_operator_can() -> None:
    from arras.operate import operators_in_groups

    c = Client(authorize_operator=operators_in_groups("builders"))
    status, err, _ = c.post("/query", {"module": "catalog", "sql": SQL}, user="carol")
    assert (status, err) == (403, {"error": "REFUSED", "reason": "not_operator"})
    assert c.post("/query", {"module": "catalog", "sql": SQL}, user="alice")[0] == 200
