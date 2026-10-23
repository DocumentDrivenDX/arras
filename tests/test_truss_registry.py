# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The Truss adapter's registry (TR-05): `describe`, `catalog`, `document`, `status`, `register` and
`validate_register`.

The unit tests are always on: a scripted fake of Truss's assembly behind the connection layer's
`Toolkit` seam, with results named as Truss names them (the adapter recognizes them by class name).
The Truss-marked tests run the registry corpus cases and the plan's gate checks against a real Truss
on PostgreSQL 18.6 (`uv run --extra truss --group truss-test pytest -m truss`).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from types import SimpleNamespace
from typing import Any

import pytest

from arras.adapters.truss import Connections, TrussBackend
from arras.adapters.truss.connection import Toolkit
from arras.conformance import _edited, load_corpus
from arras.errors import Conflict, Invalid, Refused, Unavailable, Unsupported
from arras.types import Principal, Revision
from arras.umf import parse_module
from test_truss_connection import FakeConn, FakeHost
from test_truss_harness import _world, cluster  # noqa: F401
from truss_harness import TrussHarness

TEXT: str = load_corpus()["_module_text"]
DOC = TEXT.encode()
MODULE = parse_module(DOC)
SHA = hashlib.sha256(DOC).hexdigest()
ALICE = Principal("alice", "alice-token")


# -- results as Truss names them


@dataclass(frozen=True)
class CatalogRefused:
    code: str = "unauthorized"


@dataclass(frozen=True)
class CatalogUnavailable:
    code: str


@dataclass(frozen=True)
class ReaderCatalog:
    catalog_revision: int
    modules: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class AcceptedDocument:
    content: bytes
    source_catalog_revision: int


@dataclass(frozen=True)
class ReaderCatalogSnapshot:
    catalog: Any
    validator: str


@dataclass(frozen=True)
class ReaderCatalogUnchanged:
    validator: str


@dataclass(frozen=True)
class RegistrarStatus:
    can_register: bool


@dataclass(frozen=True)
class PersonRuntimeStatus:
    installation: str
    catalog: str


@dataclass(frozen=True)
class LifecycleRefused:
    reason: str = "unauthorized"


@dataclass(frozen=True)
class CatalogCASConflict:
    code: str = "revision_conflict"


@dataclass(frozen=True)
class CatalogRegistration:
    revision: int
    replayed: bool = False


@dataclass(frozen=True)
class CatalogUnchanged:
    revision: int


@dataclass(frozen=True)
class CatalogAcceptanceRefused:
    violations: tuple[Any, ...]


class PreparationRejected(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def ok(value: Any) -> Any:
    return SimpleNamespace(status="ok", value=value)


def error(code: str, *, catalog_code: str | None = None, sql_state: str | None = None) -> Any:
    failure = SimpleNamespace(code=code, catalog_code=catalog_code, sql_state=sql_state)
    return SimpleNamespace(status="error", error=failure)


def entry(sha: str = SHA, document_id: str = "sandbox", module: str = "catalog") -> dict[str, Any]:
    return {"moduleId": module, "documentId": document_id, "documentSha256": sha}


class FakeAssembly:
    """Truss's assembly with scripted answers; `log` records what was asked, in order."""

    def __init__(self) -> None:
        self.log: list[str] = []
        self.keys: list[str] = []
        self.status = ok(SimpleNamespace(installed=True, revision=3))
        self.catalog = ok(ReaderCatalog(3, (entry(),)))
        self.documents: dict[str, Any] = {"sandbox": ok(AcceptedDocument(DOC, 2))}
        self.accepts: list[Any] = [ok(CatalogRegistration(4))]
        self.prepare_error: Exception | None = None
        self.documents_after_accept: dict[str, Any] | None = None  # a registration that raced
        self.expectations: list[tuple[Any, ...]] = []
        self.validators: list[str | None] = []
        self.registrar: Any = None  # the registrar answer, when it is not derived from `status`

    def status_in_transaction(self, tx: Any) -> Any:
        self.log.append("status")
        return self.status

    def reader_catalog_in_transaction(self, tx: Any, **kw: Any) -> Any:
        self.log.append("catalog")
        return self.catalog

    def reader_catalog_if_changed_in_transaction(
        self, tx: Any, *, validator: str | None = None, **kw: Any
    ) -> Any:
        """Truss's conditional read: the person's catalog as a snapshot with the validator it is
        known by, or `Unchanged` when the validator presented is that one."""
        self.log.append("catalog")
        self.validators.append(validator)
        if self.catalog.status != "ok" or not isinstance(self.catalog.value, ReaderCatalog):
            return self.catalog
        mine = f"v{self.catalog.value.catalog_revision}:{self.catalog.value.modules!r}"
        if validator == mine:
            return ok(ReaderCatalogUnchanged(mine))
        return ok(ReaderCatalogSnapshot(self.catalog.value, mine))

    def registrar_status_in_transaction(self, tx: Any) -> Any:
        self.log.append("registrar")
        if self.registrar is not None:
            return self.registrar
        if self.status.status != "ok":
            return self.status
        if not self.status.value.installed:
            return ok(CatalogUnavailable("installation"))
        return ok(RegistrarStatus(True))

    def person_runtime_status_in_transaction(self, tx: Any) -> Any:
        self.log.append("person")
        if self.status.status != "ok":
            return ok(LifecycleRefused())
        empty = self.status.value.revision == 0
        return ok(PersonRuntimeStatus("compatible", "empty" if empty else "accepted"))

    def accepted_document_in_transaction(self, tx: Any, *, document_id: str) -> Any:
        self.log.append(f"document:{document_id}")
        return self.documents.get(document_id, ok(CatalogRefused()))

    def prepare_catalog(self, docs: Any, **kw: Any) -> Any:
        self.log.append("prepare")
        if self.prepare_error:
            raise self.prepare_error
        return ("prepared", docs[0].document_id, docs[0].document_revision)

    def accept_in_transaction(
        self,
        tx: Any,
        prepared: Any,
        *,
        request_key: str,
        origin_bytes: bytes,
        expected_documents: tuple[Any, ...] = (),
    ) -> Any:
        self.log.append("accept")
        self.keys.append(request_key)
        self.expectations.append(
            tuple((e.document_id, e.source_catalog_revision) for e in expected_documents)
        )
        assert json.loads(origin_bytes) == {"x-action": "register"}
        if self.documents_after_accept is not None:
            self.documents = self.documents_after_accept
        out = self.accepts.pop(0) if len(self.accepts) > 1 else self.accepts[0]
        return out


@dataclass
class Rig:
    assembly: FakeAssembly = field(default_factory=FakeAssembly)
    conns: list[FakeConn] = field(default_factory=list)
    commit_failures: list[bool] = field(default_factory=list)  # per write, in order

    @contextmanager
    def source(self, principal: Principal) -> Iterator[FakeConn]:
        conn = FakeConn()
        self.conns.append(conn)
        yield conn

    def toolkit(self) -> Toolkit:
        def adopt_host(conn: FakeConn, statement: int, operation: int) -> FakeHost:
            if self.commit_failures and not conn.log[0].endswith("READ ONLY"):
                if self.commit_failures.pop(0):
                    conn.commit_raises = RuntimeError("lost")
            return FakeHost(conn.log)

        return Toolkit(adopt_host, lambda host, read_only: ("tx", self.assembly))

    def backend(self, *, installing: Callable[[], Any] | None = None) -> TrussBackend:
        return TrussBackend(
            "truss",
            Connections("truss", self.source, toolkit=self.toolkit(), installing=installing),
        )


@pytest.fixture(autouse=True)
def fake_truss(monkeypatch: pytest.MonkeyPatch) -> None:
    """`prepare_catalog` takes Truss's own document type, which the base install does not have."""
    if importlib.util.find_spec("truss") is None:
        module = SimpleNamespace(
            CatalogDocument=lambda document_id, document_revision, content: SimpleNamespace(
                document_id=document_id, document_revision=document_revision, content=content
            ),
            CatalogDocumentExpectation=lambda document_id, source_catalog_revision: SimpleNamespace(
                document_id=document_id, source_catalog_revision=source_catalog_revision
            ),
        )
        monkeypatch.setitem(sys.modules, "truss", module)


# -- catalog


def test_the_catalog_has_each_readable_module_at_its_sources_revision() -> None:
    rig = Rig()
    [(name, info)] = rig.backend().catalog(ALICE).items()
    assert name == "catalog"
    assert info.revision == Revision({"truss": 2})  # the document's own revision, not the head (3)
    assert info.placement.record == ""
    assert {t.name for t in info.entity_types} == {t.name for t in MODULE.entity_types}


def test_a_person_with_no_grant_holds_no_modules_rather_than_being_refused() -> None:
    rig = Rig()
    rig.assembly.catalog = ok(CatalogRefused())
    assert rig.backend().catalog(ALICE) == {}


@pytest.mark.parametrize(
    "code, reason",
    [
        ("profile", "unsupported_version"),
        ("installation", "not_configured"),
        ("observation", "busy"),
        ("resource", "unreachable"),
    ],
)
def test_an_unavailable_catalog_is_unavailable_for_its_reason(code: str, reason: str) -> None:
    rig = Rig()
    rig.assembly.catalog = ok(CatalogUnavailable(code))
    with pytest.raises(Unavailable) as raised:
        rig.backend().catalog(ALICE)
    assert raised.value.reason == reason


def test_the_cache_saves_the_second_read_and_the_catalog_head_invalidates_it() -> None:
    rig = Rig()
    backend = rig.backend()
    backend.catalog(ALICE)
    backend.catalog(ALICE)
    assert rig.assembly.log.count("document:sandbox") == 1  # the second call hit the cache
    assert rig.assembly.log.count("catalog") == 2  # access is asked of Truss every time
    rig.assembly.catalog = ok(ReaderCatalog(4, (entry(),)))
    rig.assembly.documents["sandbox"] = ok(AcceptedDocument(DOC, 4))  # reverted bytes, new revision
    assert backend.catalog(ALICE)["catalog"].revision == Revision({"truss": 4})


def test_the_cache_never_answers_an_access_question() -> None:
    rig = Rig()
    backend = rig.backend()
    backend.catalog(ALICE)
    rig.assembly.catalog = ok(CatalogRefused())  # another person, the same cache
    assert backend.catalog(Principal("dave", "t")) == {}


def test_a_document_that_cannot_be_read_whole_or_parsed_is_skipped() -> None:
    rig = Rig()
    rig.assembly.catalog = ok(
        ReaderCatalog(3, (entry(document_id="x"), entry(document_id="y"), entry()))
    )
    rig.assembly.documents["x"] = ok(CatalogRefused())
    rig.assembly.documents["y"] = ok(AcceptedDocument(b"{}", 2))
    assert set(rig.backend().catalog(ALICE)) == {"catalog"}


# -- document


def test_the_document_is_the_registered_bytes_at_the_modules_revision() -> None:
    rig = Rig()
    got = rig.backend().document(ALICE, "catalog")
    assert (got.text, got.format, got.revision) == (TEXT, "json", Revision({"truss": 2}))
    assert got.revision == rig.backend().catalog(ALICE)["catalog"].revision


@pytest.mark.parametrize("module", ["catalog", "other"])
def test_an_unreadable_or_unknown_document_is_refused_without_saying_which(module: str) -> None:
    rig = Rig()
    rig.assembly.catalog = ok(CatalogRefused() if module == "catalog" else ReaderCatalog(3, ()))
    with pytest.raises(Refused) as raised:
        rig.backend().document(ALICE, module)
    assert raised.value.reason == "no_access"


def test_a_document_read_with_no_token_never_connects() -> None:
    rig = Rig()
    with pytest.raises(Refused) as raised:
        rig.backend().document(Principal("anon", ""), "catalog")
    assert (raised.value.reason, rig.conns) == ("token_expired", [])


# -- an install with nothing registered (catalog head 0): Truss's reader catalog refuses it as a
# profile mismatch (`0A000`), which is not a release mismatch


def empty_install() -> Rig:
    rig = Rig()
    rig.assembly.status = ok(SimpleNamespace(installed=True, revision=0))
    rig.assembly.catalog = ok(CatalogUnavailable("profile"))
    return rig


def test_a_catalog_with_nothing_registered_is_empty_not_unavailable() -> None:
    rig = empty_install()
    assert rig.backend().catalog(ALICE) == {}


def test_a_document_of_a_catalog_with_nothing_registered_is_refused_as_an_unknown_module() -> None:
    rig = empty_install()
    with pytest.raises(Refused) as raised:
        rig.backend().document(ALICE, "catalog")
    assert raised.value.reason == "no_access"


def test_a_reader_who_cannot_state_the_head_still_sees_a_profile_refusal() -> None:
    rig = empty_install()
    rig.assembly.status = error("execution_obligation", sql_state="42501")
    with pytest.raises(Unavailable) as raised:
        rig.backend().catalog(ALICE)
    assert raised.value.reason == "unsupported_version"


def test_a_genuine_release_mismatch_stays_unsupported_version() -> None:
    rig = Rig()
    rig.assembly.catalog = ok(CatalogUnavailable("profile"))  # the head is 3
    with pytest.raises(Unavailable) as raised:
        rig.backend().catalog(ALICE)
    assert raised.value.reason == "unsupported_version"


def test_the_first_registration_reads_no_document_and_is_keyed_at_head_0() -> None:
    rig = empty_install()
    rig.assembly.accepts = [ok(CatalogRegistration(1))]
    got = register(rig, expected_revision=None)
    assert (got.changed, got.revision) == (True, Revision({"truss": 1}))
    assert not any(entry.startswith("document:") for entry in rig.assembly.log)  # the head is 0
    assert "person" in rig.assembly.log  # which the person's runtime status states: empty
    assert rig.assembly.keys == [f"register:0:{SHA}"]


def test_a_dry_run_on_an_install_with_nothing_registered_accepts_in_a_rolled_back_write() -> None:
    rig = empty_install()
    rig.assembly.accepts = [ok(CatalogRegistration(1))]
    check = validate(rig)
    assert (check.changed, check.revision) == (True, None)
    assert not any(e.startswith("document:") for e in rig.assembly.log)
    assert rig.conns[-1].log[-1] == "rollback"


def test_a_stated_revision_with_nothing_registered_is_a_conflict() -> None:
    rig = empty_install()
    with pytest.raises(Conflict) as raised:
        register(rig, expected_revision=Revision({"truss": 1}))
    assert raised.value.reason == "revision"
    assert "prepare" not in rig.assembly.log


# -- register


def register(rig: Rig, document: bytes = DOC, **kw: Any) -> Any:
    return rig.backend().register(
        ALICE, document, parse_module(document), unknown_endpoint="reject", **kw
    )


def test_a_person_who_is_no_registrar_is_refused_before_anything_is_prepared() -> None:
    rig = Rig()
    rig.assembly.status = error(
        "execution_obligation", sql_state="42501", catalog_code="unauthorized"
    )
    for document in (DOC, _edited(TEXT, "add-record-type").encode()):  # unchanged or changed
        with pytest.raises(Refused) as raised:
            register(rig, document)
        assert raised.value.reason == "no_access"
    assert "prepare" not in rig.assembly.log and "accept" not in rig.assembly.log


@pytest.mark.parametrize("operation", ["register", "validate_register"])
@pytest.mark.parametrize("profile", ["umf-core-metadata/1", "unrecognized-profile"])
def test_a_nonlegacy_profile_is_refused_after_registrar_auth_before_any_registry_work(
    operation: str, profile: str
) -> None:
    rig = Rig()
    backend = rig.backend()
    profiled = replace(MODULE, metadata_profile=profile)
    method = getattr(backend, operation)

    with pytest.raises(Unsupported) as raised:
        method(
            ALICE,
            b"not a document",
            profiled,
            unknown_endpoint="not a known option",
        )

    assert raised.value.construct == "metadata profile"
    assert rig.assembly.log == ["registrar"]
    assert backend.cache.seen() == []
    assert all(conn.log[-1] == "rollback" for conn in rig.conns)


@pytest.mark.parametrize("operation", ["register", "validate_register"])
@pytest.mark.parametrize("profile", ["umf-core-metadata/1", "unrecognized-profile"])
def test_truss_refuses_a_nonregistrar_before_inspecting_unsupported_profile(
    operation: str, profile: str
) -> None:
    rig = Rig()
    rig.assembly.registrar = ok(RegistrarStatus(False))
    backend = rig.backend()
    method = getattr(backend, operation)

    with pytest.raises(Refused) as raised:
        method(
            ALICE,
            b"not a document",
            replace(MODULE, metadata_profile=profile),
            unknown_endpoint="not a known option",
        )

    assert raised.value.reason == "no_access"
    assert rig.assembly.log == ["registrar"]
    assert backend.cache.seen() == []
    assert all(conn.log[-1] == "rollback" for conn in rig.conns)


def test_a_rewritten_equal_document_registers_nothing_and_calls_no_accept() -> None:
    rig = Rig()
    got = register(rig, _edited(TEXT, "rewrite").encode())
    assert (got.changed, got.revision) == (False, Revision({"truss": 2}))
    assert "prepare" not in rig.assembly.log and "accept" not in rig.assembly.log
    assert all(c.log[-1] == "rollback" for c in rig.conns)  # a read, never a write


def test_a_new_document_is_prepared_then_accepted_in_one_committed_write() -> None:
    rig = Rig()
    backend = rig.backend()
    got = backend.register(
        ALICE, _edited(TEXT, "add-record-type").encode(), MODULE, unknown_endpoint="reject"
    )
    assert (got.changed, got.revision, got.report) == (True, Revision({"truss": 4}), ("accepted",))
    assert rig.assembly.log.index("prepare") < rig.assembly.log.index("accept")
    assert rig.conns[-1].log[0].endswith("READ WRITE") and rig.conns[-1].log[-1] == "commit"
    assert backend.describe().capabilities  # the registered module is known to `describe`


@pytest.mark.parametrize("reason", ["resource", "unsupported_profile"])
def test_a_preparation_rejected_for_another_reason_is_unsupported_for_this_document(
    reason: str,
) -> None:
    rig = Rig()
    rig.assembly.prepare_error = PreparationRejected(reason)
    with pytest.raises(Unsupported) as raised:
        register(rig, _edited(TEXT, "add-record-type").encode())
    assert "this document" in str(raised.value)
    assert "accept" not in rig.assembly.log
    assert all(c.log[-1] == "rollback" for c in rig.conns)


def test_the_request_key_names_the_head_so_a_reverted_document_is_a_new_request() -> None:
    rig = Rig()
    new = _edited(TEXT, "add-record-type").encode()
    register(rig, new)
    rig.assembly.catalog = ok(
        ReaderCatalog(5, (entry(),))
    )  # another change landed, then ours reverts
    register(rig, new)
    sha = hashlib.sha256(new).hexdigest()
    assert rig.assembly.keys == [f"register:3:{sha}", f"register:5:{sha}"]


def test_a_stale_expected_revision_is_a_conflict_before_anything_is_prepared() -> None:
    rig = Rig()
    new = _edited(TEXT, "add-record-type").encode()
    with pytest.raises(Conflict) as raised:
        register(rig, new, expected_revision=Revision({"truss": 1}))
    assert raised.value.reason == "revision"
    assert "prepare" not in rig.assembly.log


def test_the_expected_revision_is_checked_even_for_an_unchanged_document() -> None:
    rig = Rig()
    with pytest.raises(Conflict):
        register(rig, expected_revision=Revision({"truss": 1}))
    assert register(rig, expected_revision=Revision({"truss": 2})).changed is False


def test_a_registration_that_lands_between_the_read_and_the_accept_is_a_conflict() -> None:
    rig = Rig()
    rig.assembly.accepts = [ok(CatalogCASConflict())]  # Truss's typed answer: another one landed
    new = _edited(TEXT, "add-record-type").encode()
    with pytest.raises(Conflict) as raised:
        register(rig, new, expected_revision=Revision({"truss": 2}))
    assert raised.value.reason == "revision"
    assert rig.assembly.expectations == [(("sandbox", 2),)]  # the document's own source revision
    assert rig.conns[-1].log[-1] == "rollback"  # nothing committed


def test_an_unrelated_registration_does_not_disturb_the_expectation() -> None:
    """The head moved (another document was registered) but this document's source revision did
    not: the expectation is the document's, so the registration is accepted."""
    rig = Rig()
    rig.assembly.catalog = ok(ReaderCatalog(9, (entry(),)))
    got = register(
        rig, _edited(TEXT, "add-record-type").encode(), expected_revision=Revision({"truss": 2})
    )
    assert got.changed is True
    assert rig.assembly.expectations == [(("sandbox", 2),)]


def test_a_registration_naming_no_revision_sends_no_expectation() -> None:
    rig = Rig()
    register(rig, _edited(TEXT, "add-record-type").encode())
    assert rig.assembly.expectations == [()]


def test_an_unknown_commit_repeats_the_same_request_once_and_reports_the_original() -> None:
    rig = Rig(commit_failures=[True])
    rig.assembly.accepts = [ok(CatalogRegistration(4)), ok(CatalogRegistration(4, replayed=True))]
    got = register(
        rig, _edited(TEXT, "add-record-type").encode(), expected_revision=Revision({"truss": 2})
    )
    assert (got.changed, got.revision) == (True, Revision({"truss": 4}))
    assert len(rig.assembly.keys) == 2 and rig.assembly.keys[0] == rig.assembly.keys[1]
    assert (
        rig.assembly.log.count("prepare") == 1
    )  # the replay skips the pre-checks and the preparation


def test_the_repeat_after_an_unknown_commit_still_detects_a_registration_that_landed_first() -> (
    None
):
    rig = Rig(commit_failures=[True])
    # the first commit's outcome is unknown; the repeat is a fresh apply, not a replay, and Truss
    # refuses it by the document's expectation because another registration landed in between
    rig.assembly.accepts = [ok(CatalogRegistration(4)), ok(CatalogCASConflict())]
    backend = rig.backend()
    with pytest.raises(Conflict) as raised:
        backend.register(
            ALICE,
            _edited(TEXT, "add-record-type").encode(),
            MODULE,
            unknown_endpoint="reject",
            expected_revision=Revision({"truss": 2}),
        )
    assert raised.value.reason == "revision"
    assert rig.conns[-1].log[-1] == "rollback"
    assert all(m.revision != Revision({"truss": 5}) for m in backend.cache.seen())


def _raced_unchanged_rig() -> Rig:
    """The module is held at 2; another registration of these bytes lands (at 3) before the accept."""
    rig = Rig()
    rig.assembly.documents_after_accept = {"sandbox": ok(AcceptedDocument(DOC, 3))}
    rig.assembly.accepts = [ok(CatalogUnchanged(3))]
    return rig


def test_an_unchanged_answer_returns_the_accepted_revision_not_the_held_one() -> None:
    rig = _raced_unchanged_rig()
    backend = rig.backend()
    got = backend.register(
        ALICE, _edited(TEXT, "add-record-type").encode(), MODULE, unknown_endpoint="reject"
    )
    assert (got.changed, got.revision) == (False, Revision({"truss": 3}))
    assert [m.revision for m in backend.cache.seen()] == [Revision({"truss": 3})]
    assert rig.assembly.log[-2:] == ["accept", "document:sandbox"]


def test_an_unchanged_answer_after_a_differing_read_is_a_conflict_when_a_revision_is_stated() -> (
    None
):
    rig = _raced_unchanged_rig()
    backend = rig.backend()
    with pytest.raises(Conflict) as raised:
        backend.register(
            ALICE,
            _edited(TEXT, "add-record-type").encode(),
            MODULE,
            unknown_endpoint="reject",
            expected_revision=Revision({"truss": 2}),
        )
    assert raised.value.reason == "revision"
    assert rig.conns[-1].log[-1] == "rollback"
    assert all(m.name != MODULE.name for m in backend.cache.seen())


def test_an_unchanged_answer_for_a_module_not_held_reads_its_source_revision_in_the_call() -> None:
    rig = Rig()
    rig.assembly.catalog = ok(ReaderCatalog(3, ()))  # the person holds no document of it
    rig.assembly.documents = {"sandbox": ok(AcceptedDocument(DOC, 2))}
    rig.assembly.accepts = [ok(CatalogUnchanged(3))]
    backend = rig.backend()
    got = backend.register(
        ALICE, _edited(TEXT, "add-record-type").encode(), MODULE, unknown_endpoint="reject"
    )
    assert got.revision == Revision({"truss": 2}) and got.changed is False
    assert rig.assembly.log[-2:] == ["accept", "document:sandbox"]
    assert rig.conns[-1].log[-1] == "commit"


def test_an_unchanged_answer_whose_document_cannot_be_read_is_an_unknown_revision() -> None:
    rig = Rig()
    rig.assembly.catalog = ok(ReaderCatalog(3, ()))
    rig.assembly.documents = {}
    rig.assembly.accepts = [ok(CatalogUnchanged(3))]
    backend = rig.backend()
    got = backend.register(
        ALICE, _edited(TEXT, "add-record-type").encode(), MODULE, unknown_endpoint="reject"
    )
    assert got.revision == Revision({"truss": None})
    assert all(m.name != MODULE.name for m in backend.cache.seen())


def test_an_unknown_commit_twice_is_unavailable() -> None:
    rig = Rig(commit_failures=[True, True])
    with pytest.raises(Unavailable) as raised:
        register(rig, _edited(TEXT, "add-record-type").encode())
    assert raised.value.detail == "outcome unknown"


@pytest.mark.parametrize(
    "failure, expected",
    [
        (error("execution_obligation", catalog_code="unauthorized", sql_state="42501"), Refused),
        (error("execution_obligation", catalog_code="unsupported_profile"), Unsupported),
        (error("invalid_transaction"), Unsupported),  # Truss's one message for any ValueError
        (error("execution_obligation", catalog_code="invalid_input"), Invalid),
        (error("execution_obligation", catalog_code="request_conflict"), Conflict),
        (error("execution_obligation", catalog_code="observation"), Unavailable),
        (error("execution_obligation", catalog_code="installation"), Unavailable),
        (error("something-else"), Unavailable),
    ],
)
def test_truss_failures_while_accepting_map_by_their_code(failure: Any, expected: type) -> None:
    rig = Rig()
    rig.assembly.accepts = [failure]
    with pytest.raises(expected):
        register(rig, _edited(TEXT, "add-record-type").encode())


def test_busy_is_unavailable_for_the_reason_busy() -> None:
    rig = Rig()
    rig.assembly.accepts = [error("execution_obligation", catalog_code="observation")]
    with pytest.raises(Unavailable) as raised:
        register(rig, _edited(TEXT, "add-record-type").encode())
    assert raised.value.reason == "busy"


def test_an_incompatible_change_is_invalid_with_one_violation_per_field() -> None:
    rig = Rig()
    v = SimpleNamespace(
        record_id="UseCase",
        field_id="UseCase.notes",
        rule="property.required",
        affected_object_count=2,
    )
    rig.assembly.accepts = [ok(CatalogAcceptanceRefused((v,)))]
    with pytest.raises(Invalid) as raised:
        register(rig, _edited(TEXT, "add-required-property").encode())
    [violation] = raised.value.violations
    assert (violation.path, violation.code) == (
        "types.UseCase.UseCase.notes",
        "incompatible_change",
    )
    assert "2 objects" in violation.message


@pytest.mark.parametrize(
    "reason, expected",
    [
        ("invalid_document", Invalid),
        ("invalid_input", Invalid),
        ("runtime_unavailable", Unavailable),
        ("producer_unavailable", Unavailable),
        ("resource", Unsupported),
    ],
)
def test_a_document_truss_cannot_prepare_is_mapped_by_its_reason(
    reason: str, expected: type
) -> None:
    rig = Rig()
    rig.assembly.prepare_error = PreparationRejected(reason)
    with pytest.raises(expected):
        register(rig, _edited(TEXT, "add-record-type").encode())
    assert "accept" not in rig.assembly.log


def test_a_value_error_that_is_not_a_preparation_refusal_is_unavailable_without_its_text() -> None:
    rig = Rig()
    rig.assembly.prepare_error = ValueError("bug")
    with pytest.raises(Unavailable) as raised:
        register(rig, _edited(TEXT, "add-record-type").encode())
    assert raised.value.detail == "truss error" and "bug" not in str(raised.value)


def test_unknown_endpoint_is_checked_after_the_grant() -> None:
    rig = Rig()
    backend = rig.backend()
    new = _edited(TEXT, "add-record-type").encode()
    with pytest.raises(Invalid):
        backend.register(ALICE, new, MODULE, unknown_endpoint="sideways")
    with pytest.raises(Unsupported):
        backend.register(ALICE, new, MODULE, unknown_endpoint="provisional")
    rig.assembly.status = error("execution_obligation", sql_state="42501")
    with pytest.raises(Refused):
        backend.register(ALICE, new, MODULE, unknown_endpoint="sideways")


def test_a_document_without_an_id_cannot_be_registered_on_truss() -> None:
    rig = Rig()
    bare = json.dumps({k: v for k, v in json.loads(TEXT).items() if k != "id"}).encode()
    with pytest.raises(Invalid) as raised:
        register(rig, bare)
    assert raised.value.violations[0].path == "id"


def test_a_module_held_under_another_document_id_is_not_registered_again() -> None:
    rig = Rig()
    rig.assembly.catalog = ok(ReaderCatalog(3, (entry(document_id="elsewhere"),)))
    with pytest.raises(Invalid) as raised:
        register(rig, _edited(TEXT, "add-record-type").encode())
    assert raised.value.violations[0].code == "document_id"


def test_a_registrar_who_cannot_read_the_module_cannot_state_an_expected_revision() -> None:
    rig = Rig()
    rig.assembly.catalog = ok(CatalogRefused())
    new = _edited(TEXT, "add-record-type").encode()
    with pytest.raises(Refused):
        register(rig, new, expected_revision=Revision({"truss": 2}))
    assert register(rig).changed is True  # unchecked: Truss compares the bytes it holds


# -- validate_register


def validate(rig: Rig, document: bytes = DOC) -> Any:
    return rig.backend().validate_register(
        ALICE, document, parse_module(document), unknown_endpoint="reject"
    )


def test_a_dry_run_accepts_in_a_transaction_it_rolls_back() -> None:
    rig = Rig()
    got = validate(rig, _edited(TEXT, "add-record-type").encode())
    assert (got.changed, got.violations, got.revision) == (True, (), Revision({"truss": 2}))
    assert got.current == rig.backend().catalog(ALICE)["catalog"]
    write = next(c for c in rig.conns if c.log[0].endswith("READ WRITE"))
    assert "commit" not in write.log and write.log[-1] == "rollback"


def test_a_dry_run_of_an_equal_document_calls_no_accept() -> None:
    rig = Rig()
    got = validate(rig, _edited(TEXT, "rewrite").encode())
    assert (got.changed, got.violations) == (False, ())
    assert "accept" not in rig.assembly.log


def test_a_dry_run_reports_incompatibility_as_an_answer() -> None:
    rig = Rig()
    v = SimpleNamespace(
        record_id="UseCase",
        field_id="UseCase.notes",
        rule="property.required",
        affected_object_count=1,
    )
    rig.assembly.accepts = [ok(CatalogAcceptanceRefused((v,)))]
    got = validate(rig, _edited(TEXT, "add-required-property").encode())
    assert [x.code for x in got.violations] == ["incompatible_change"]
    assert got.revision == Revision({"truss": 2})


def test_a_dry_run_by_a_non_registrar_is_refused() -> None:
    rig = Rig()
    rig.assembly.status = error("execution_obligation", sql_state="42501")
    with pytest.raises(Refused):
        validate(rig)


def test_a_change_truss_does_not_take_is_unsupported_for_register_and_dry_run() -> None:
    rig = Rig()
    rig.assembly.accepts = [error("execution_obligation", catalog_code="unsupported_profile")]
    new = _edited(TEXT, "add-optional-property").encode()
    with pytest.raises(Unsupported):
        validate(rig, new)
    with pytest.raises(Unsupported):
        register(rig, new)


# -- status and describe


def installer(rig: Rig) -> Callable[[], Any]:
    return lambda: rig.source(Principal("installer", ""))


def test_status_is_not_configured_without_an_installing_connection() -> None:
    status = Rig().backend().status()
    assert (status.available, status.reason) == (False, "not_configured")


def test_status_reads_the_install_state_on_the_installing_connection() -> None:
    rig = Rig()
    backend = rig.backend(installing=installer(rig))
    assert backend.status().available is True
    assert rig.conns[0].log[0].endswith("READ ONLY") and rig.conns[0].log[-1] == "rollback"
    rig.assembly.status = ok(SimpleNamespace(installed=False))
    assert backend.status().reason == "not_configured"
    rig.assembly.status = error("invalid_transaction", catalog_code="unsupported_profile")
    assert backend.status().reason == "unsupported_version"
    rig.assembly.status = error("execution_obligation", sql_state="42501")
    assert backend.status().reason == "access_denied"
    rig.assembly.status = error("other")
    assert (backend.status().available, backend.status().reason) == (False, "unreachable")


def test_status_reports_a_lost_installing_connection_and_never_raises() -> None:
    @contextmanager
    def lost() -> Iterator[Any]:
        raise Unavailable("truss", "unreachable", "cannot connect")
        yield  # pragma: no cover

    status = Rig().backend(installing=lost).status()
    assert (status.available, status.reason) == (False, "unreachable")


def test_status_without_the_truss_extra_reports_not_configured_and_never_raises() -> None:
    rig = Rig()

    @contextmanager
    def missing() -> Iterator[Any]:
        raise ModuleNotFoundError("No module named 'truss'")
        yield  # pragma: no cover

    got = TrussBackend("truss", Connections("truss", rig.source, installing=missing)).status()
    assert (got.available, got.reason) == (False, "not_configured")
    assert got.detail == "the truss extra is not installed"


def test_describe_states_the_types_the_adapter_has_served() -> None:
    rig = Rig()
    backend = rig.backend()
    assert backend.describe().capabilities == {}
    backend.catalog(ALICE)
    info = backend.describe()
    assert info.roles == ("reader", "provider")
    assert set(info.capabilities) == {t.name for t in MODULE.entity_types}
    caps = info.capabilities["catalog.UseCase"]
    assert (caps.read, caps.mutable, caps.search) == (True, True, "none")
    assert caps.columns == ("code", "name") and caps.count  # what `query` serves (TR-06)


# -- against a real Truss


def _call(h: Any, user: str, work: Callable[[Any, Any], Any], read_only: bool = True) -> Any:
    from truss_harness import transaction

    with h.world.connection_source(h.principal(user)) as conn:
        with transaction(conn, read_only=read_only) as (a, t):
            return work(a, t)


def _head(h: Any) -> int:
    return _call(h, "alice", lambda a, t: a.reader_catalog_in_transaction(t).value.catalog_revision)


@pytest.mark.truss
def test_a_rewritten_equal_document_makes_no_revision(cluster: Any) -> None:  # noqa: F811
    h = _world(cluster)
    before = _head(h)
    rewritten = _edited(TEXT, "rewrite").encode()
    got = h.backend().register(h.principal("alice"), rewritten, MODULE, unknown_endpoint="reject")
    assert got.changed is False
    assert _head(h) == before


@pytest.mark.truss
def test_validate_register_leaves_no_catalog_row(cluster: Any) -> None:  # noqa: F811
    h = _world(cluster)
    before = _head(h)
    new = _edited(TEXT, "add-record-type").encode()
    check = h.backend().validate_register(
        h.principal("alice"), new, parse_module(new), unknown_endpoint="reject"
    )
    assert (check.changed, check.violations) == (True, ())
    assert _head(h) == before
    held = h.backend().document(h.principal("carol"), "catalog")
    assert held.text == TEXT


@pytest.mark.truss
def test_a_non_registrar_is_refused_and_a_reader_sees_exactly_their_modules(cluster: Any) -> None:  # noqa: F811
    h = _world(cluster)
    backend = h.backend()
    new = _edited(TEXT, "add-record-type").encode()
    for user in ("carol", "bob", "dave"):
        with pytest.raises(Refused):
            backend.validate_register(
                h.principal(user), new, parse_module(new), unknown_endpoint="reject"
            )
    assert set(backend.catalog(h.principal("carol"))) == {"catalog"}
    assert backend.catalog(h.principal("dave")) == {}  # a non-member holds none: not an error


@pytest.mark.truss
def test_each_registry_call_runs_as_the_person(cluster: Any) -> None:  # noqa: F811
    h = _world(cluster)
    seen: list[str] = []
    source = h.world.connection_source

    @contextmanager
    def watching(principal: Principal) -> Iterator[Any]:
        with source(principal) as conn:
            seen.append(conn.execute("SELECT session_user").fetchone()[0])
            conn.rollback()  # the call needs an idle connection
            yield conn

    backend = TrussBackend("truss", Connections("truss", watching))
    backend.catalog(h.principal("carol"))
    backend.document(h.principal("carol"), "catalog")
    with pytest.raises(Refused):
        backend.validate_register(h.principal("bob"), DOC, MODULE, unknown_endpoint="reject")
    assert seen == ["carol", "carol", "bob"]


@pytest.mark.truss
def test_reverting_an_action_edit_registers_again_under_a_new_key(cluster: Any) -> None:  # noqa: F811
    h = _world(cluster)
    backend, alice = h.backend(), h.principal("alice")
    doc = json.loads(TEXT)
    edited = json.loads(TEXT)
    edited["modules"][0]["actions"][0]["description"] = "an edited description"
    a, b = DOC, json.dumps(edited).encode()
    assert backend.register(alice, b, parse_module(b), unknown_endpoint="reject").changed is True
    back = backend.register(alice, a, parse_module(a), unknown_endpoint="reject")
    assert back.changed is True  # a replayed key would have applied nothing
    assert backend.document(alice, "catalog").text == TEXT
    assert doc  # the module text is the one the harness installed


@pytest.mark.truss
def test_a_stale_expected_revision_conflicts_and_the_current_one_applies(cluster: Any) -> None:  # noqa: F811
    h = _world(cluster)
    backend, alice = h.backend(), h.principal("alice")
    new = _edited(TEXT, "add-record-type").encode()
    held = backend.document(alice, "catalog").revision
    stale = Revision({"truss": int(held.by_backend["truss"]) + 1000})  # type: ignore[arg-type]
    with pytest.raises(Conflict):
        backend.register(
            alice, new, parse_module(new), unknown_endpoint="reject", expected_revision=stale
        )
    got = backend.register(
        alice, new, parse_module(new), unknown_endpoint="reject", expected_revision=held
    )
    assert got.changed is True and got.revision != held


@pytest.mark.truss
def test_status_on_the_installing_connection_follows_the_install_state(cluster: Any) -> None:  # noqa: F811
    h = _world(cluster)
    backend = h.backend()
    assert backend.status().available is True
    h.outage("unsupported_version")
    assert backend.status().reason == "unsupported_version"
    h.outage("unreachable")
    assert backend.status().reason == "unreachable"
    h.outage("access_denied")
    assert backend.status().reason == "access_denied"
    h.outage(None)
    assert backend.status().available is True


@pytest.mark.truss
def test_the_first_registration_on_an_install_with_nothing_registered(cluster: Any) -> None:  # noqa: F811
    from truss import ModuleAccessGrant

    from truss_harness import document_id, transaction

    h: Any = TrussHarness(cluster)
    h.install(MODULE, DOC, registered=False)
    for step in load_corpus()["fixtures"]["empty"][1:]:
        if step["op"] == "grant":
            h.grant(step["user"], step["modules"], step.get("admin", False))
    backend, alice = h.backend(), h.principal("alice")
    assert backend.catalog(alice) == {}  # head 0: nothing, not unavailable
    with pytest.raises(Refused):
        backend.document(alice, "catalog")
    check = backend.validate_register(alice, DOC, MODULE, unknown_endpoint="reject")
    assert (check.changed, check.violations) == (True, ())
    got = backend.register(alice, DOC, MODULE, unknown_endpoint="reject")
    assert (got.changed, got.revision) == (True, Revision({"truss": 1}))
    grant = ModuleAccessGrant(document_id(DOC), MODULE.name, "catalog_reader", "catalog_writer")
    with h.world.installing_connection() as conn:
        with transaction(conn) as (assembly, handle):
            assembly.configure_module_access_in_transaction(handle, (grant,))
    assert set(backend.catalog(alice)) == {"catalog"}
    assert backend.document(alice, "catalog").revision == Revision({"truss": 1})


def test_the_race_is_prevented_not_detected_and_its_case_carries_no_limit() -> None:
    """Truss 0.0.44 checks a document-scoped expectation inside the acceptance, so the case that
    registers against a revision the store no longer holds passes whole and pins no limit."""
    case = next(
        c
        for c in load_corpus()["cases"]
        if c["id"] == "registry.register-checks-the-revision-it-was-planned-against"
    )
    assert "limits" not in case
    from truss_harness import TrussHarness as Harness

    assert case["id"] not in Harness.LIMITS


@pytest.mark.parametrize(
    ("code", "expected", "reason"),
    [
        ("request_conflict", Conflict, "idempotency_key_reused"),
        ("unsupported_profile", Unsupported, None),
        ("invalid_input", Invalid, None),
        ("observation", Unavailable, "busy"),
        ("resource", Unavailable, "resource"),
        ("installation", Unavailable, "not_configured"),
        ("another", Unavailable, "unreachable"),
    ],
)
def test_a_registration_failure_is_mapped_by_its_catalog_code(
    code: str, expected: type, reason: str | None
) -> None:
    from arras.adapters.truss.registry import mapped

    failure = SimpleNamespace(code="execution_obligation", sql_state=None, catalog_code=code)
    got = mapped("truss", "register", failure)
    assert isinstance(got, expected)
    assert reason is None or reason in (getattr(got, "reason", None), getattr(got, "detail", None))


def test_two_modules_defining_the_same_local_type_name_keep_their_own_capabilities() -> None:
    """Type names are module-qualified, so `describe` keys the capabilities of every module the
    cache has served without one overwriting another's columns or relationships."""
    from arras.adapters.truss.cache import CatalogCache
    from arras.adapters.truss.describe import describe

    other = parse_module(TEXT.replace('"catalog', '"other').replace("catalog.", "other."))
    local = MODULE.entity_types[0].local_name
    assert other.entity_types[0].local_name == local and other.name != MODULE.name
    cache = CatalogCache()
    cache.remember(MODULE)
    cache.remember(other)
    caps = describe("truss", cache.seen()).capabilities
    assert f"{MODULE.name}.{local}" in caps and f"other.{local}" in caps
    assert local not in caps
    assert set(caps) == {t.name for m in (MODULE, other) for t in m.entity_types}
