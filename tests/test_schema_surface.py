# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""CONTRACT-011: the schema administration surface, one test per rule of its tables."""

import json

import pytest

from arras.operate import create_app, create_schema_app
from arras.sandbox import Sandbox, catalog_document
from test_operate import OTHER, PUBLIC, Client
from test_schema_library import with_property

DOC = catalog_document()
OPTIONAL = with_property(DOC, "notes", required=False)


class Surface(Client):
    """The real schema app over the sandbox's fakes: `alice` holds the `schema` grant, `bob` only
    `write`, `carol` only `read`."""

    def __init__(self, **kw) -> None:
        box = kw.pop("box", None) or Sandbox().seed()
        kw.setdefault("public_origin", PUBLIC)
        kw.setdefault("allowed_origins", (OTHER,))
        super().__init__(box)
        self.app = create_schema_app(box.arras, principal_for_request=self.who, **kw)

    def document(self):
        return self.box.arras.session(self.box.people["alice"]).document("catalog")


@pytest.fixture
def s() -> Surface:
    return Surface()


def test_the_version_is_published_without_a_principal(s: Surface) -> None:
    status, body, _ = s.call("GET", "/version", user=None, origin=None)
    assert (status, body) == (200, {"contracts": {"schema": 1}})


def test_validate_answers_a_plan_and_applies_nothing(s: Surface) -> None:
    before = s.document()
    status, plan, _ = s.post("/validate", {"document": OPTIONAL})
    assert status == 200 and plan["ok"] and plan["changed"] and plan["module"] == "catalog"
    assert plan["changes"] == [
        {
            "kind": "added",
            "element": "property",
            "name": "catalog.UseCase.notes",
            "detail": "optional string",
        }
    ]
    assert plan["revision"] == dict(before.revision.by_backend)
    after = s.document()
    assert (after.text, after.revision) == (before.text, before.revision)


def test_an_incompatible_plan_is_a_200_that_names_the_rule_and_register_is_400(s: Surface) -> None:
    required = with_property(DOC, "notes", required=True)
    status, plan, _ = s.post("/validate", {"document": required})
    assert status == 200 and not plan["ok"]
    assert {v["code"] for v in plan["violations"]} == {"incompatible_change"}
    status, err, _ = s.post("/register", {"document": required})
    assert status == 400 and err["error"]["type"] == "Invalid"
    assert [v["code"] for v in err["error"]["violations"]] == ["incompatible_change"] * len(
        plan["violations"]
    )
    assert "notes" not in s.document().text


def test_register_applies_and_the_plan_then_says_nothing_would_change(s: Surface) -> None:
    status, plan, _ = s.post("/validate", {"document": OPTIONAL})
    status, result, _ = s.post(
        "/register", {"document": OPTIONAL, "expected_revision": plan["revision"]}
    )
    assert status == 200 and result["changed"] and result["revision"] != plan["revision"]
    assert "notes" in s.document().text
    _, again, _ = s.post("/validate", {"document": OPTIONAL})
    assert not again["changed"] and again["revision"] == result["revision"]


def test_a_stale_revision_is_409_and_applies_nothing(s: Surface) -> None:
    status, err, _ = s.post(
        "/register", {"document": OPTIONAL, "expected_revision": {"memory": 999}}
    )
    assert status == 409 and err["error"]["type"] == "Conflict"
    assert "notes" not in s.document().text


@pytest.mark.parametrize("user", ["bob", "carol"])
def test_without_the_schema_grant_the_backend_refuses_before_describing_the_host(
    s: Surface, user: str
) -> None:
    for verb in ("validate", "register"):
        status, err, _ = s.post(f"/{verb}", {"document": OPTIONAL}, user=user)
        assert (status, err["error"]["message"]) == (403, "no access")
    other = DOC.replace('"catalog"', '"unplaced"')
    assert s.post("/validate", {"document": other}, user="bob")[0] == 403
    assert "notes" not in s.document().text


def test_the_administrative_principal_is_refused(s: Surface) -> None:
    assert s.post("/validate", {"document": DOC}, user="root")[0] == 403


def test_no_principal_is_401(s: Surface) -> None:
    assert s.post("/validate", {"document": DOC}, user=None)[0] == 401


def test_the_host_can_narrow_and_the_library_is_not_called() -> None:
    asked: list[tuple[str, str]] = []

    def no(principal, module) -> bool:
        asked.append((principal.user, module))
        return False

    s = Surface(authorize_schema=no)
    before = s.document()
    for verb in ("validate", "register"):
        assert s.post(f"/{verb}", {"document": OPTIONAL})[0] == 403
    assert asked == [("alice", "catalog")] * 2
    assert s.document().revision == before.revision
    # a document that does not parse is 400 before the hook runs
    assert s.post("/validate", {"document": "{"})[0] == 400
    assert len(asked) == 2


def test_the_origin_rules_are_the_operator_surfaces(s: Surface) -> None:
    body = {"document": DOC}
    assert s.post("/validate", body, origin="https://evil.example")[0] == 403
    assert s.post("/validate", body, origin=None)[0] == 403
    assert s.post("/validate", body, origin=None, extra={"sec-fetch-site": "same-origin"})[0] == 200
    assert s.post("/validate", body, origin=OTHER)[0] == 200
    assert s.call("OPTIONS", "/validate", origin=OTHER)[0] == 204
    assert s.call("OPTIONS", "/validate", origin="https://evil.example")[0] == 403


def test_methods_and_paths(s: Surface) -> None:
    status, _, hdrs = s.call("GET", "/validate", origin=None)
    assert status == 405 and hdrs["allow"] == "POST"
    assert s.post("/delete", {})[0] == 404
    assert s.post("/actions/catalog/AddUseCase/invoke", {})[0] == 404
    assert s.call("PUT", "/register", {"document": DOC})[0] == 405


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"document": 3},
        {"document": DOC, "unknown_endpoint": "sure"},
        {"document": DOC, "expected_revision": "3"},
        {"document": DOC, "expected_revision": {"memory": 1.5}},
    ],
)
def test_a_malformed_request_is_400(s: Surface, body: dict) -> None:
    assert s.post("/register", body)[0] == 400


def test_a_document_that_does_not_parse_is_400_with_its_violations(s: Surface) -> None:
    status, err, _ = s.post("/validate", {"document": json.dumps({"umf": "0.10.0"})})
    assert status == 400 and err["error"]["violations"]


def test_the_document_and_body_limits() -> None:
    s = Surface()

    def padded(n: int) -> str:
        d = json.loads(DOC)
        d["modules"][0]["actions"][0]["description"] = "x" * n  # text the action carries
        return json.dumps(d)

    base = len(padded(0).encode())
    just_under = padded(1024 * 1024 - base)
    assert len(just_under.encode()) == 1024 * 1024
    assert s.post("/validate", {"document": just_under})[0] == 200
    assert s.post("/validate", {"document": padded(1024 * 1024 - base + 1)})[0] == 413
    assert s.post("/validate", {"document": "y" * (5 * 1024 * 1024)})[0] == 413


def test_a_backend_fault_is_answered_by_type_and_never_echoes_detail(s: Surface) -> None:
    s.box.store.outage = "unreachable"
    status, err, _ = s.post("/validate", {"document": DOC})
    assert status == 503
    assert err["error"]["message"] == "memory is unavailable (unreachable)"
    assert "detail" not in err["error"]


def test_a_record_store_with_no_dry_run_is_501(s: Surface, monkeypatch) -> None:
    monkeypatch.setattr(s.box.store, "validate_register", None)
    status, err, _ = s.post("/validate", {"document": DOC})
    assert (status, err["error"]["type"]) == (501, "Unsupported")


def test_the_operator_surface_has_no_schema_write(s: Surface) -> None:
    ops = Client(s.box)
    for verb in ("validate", "register"):
        assert ops.post(f"/{verb}", {"document": DOC})[0] == 404
    assert create_app is not create_schema_app


def test_a_non_operator_is_refused_before_anything_and_an_operator_is_not() -> None:
    from arras.operate import operators_in_groups

    s = Surface(authorize_operator=operators_in_groups("builders"))
    before = s.document()
    status, err, _ = s.post("/validate", {"document": OPTIONAL}, user="carol")  # no groups
    assert (status, err) == (403, {"error": "REFUSED", "reason": "not_operator"})
    assert s.post("/register", {"document": OPTIONAL}, user="dave")[0] == 403
    assert s.post("/validate", {"document": "{"}, user="carol")[0] == 403  # before the body is read
    assert s.post("/validate", {"document": OPTIONAL}, user="alice")[0] == 200  # builders
    assert s.call("GET", "/version", user=None, origin=None)[0] == 200  # no principal needed
    assert s.document().revision == before.revision


def test_a_hook_that_fails_refuses_rather_than_assuming_an_operator() -> None:
    def broken(_principal) -> bool:
        raise RuntimeError("the group service is down")

    s = Surface(authorize_operator=broken)
    assert s.post("/validate", {"document": DOC})[0] == 403
