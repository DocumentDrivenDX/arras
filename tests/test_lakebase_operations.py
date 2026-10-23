# SPDX-License-Identifier: MIT OR Apache-2.0
"""Offline controls for the explicit Lakebase operation runner."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest


def _load_tool(name: str, filename: str) -> Any:
    path = Path(__file__).parents[1] / "tools" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


TOOLS = Path(__file__).parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
try:
    native = _load_tool("_lakebase_native", "_lakebase_native.py")
    operations = _load_tool("_lakebase_operations", "_lakebase_operations.py")
finally:
    sys.path.pop(0)


def _inputs(*, allowed_operations: tuple[str, ...] = (), scope: str = "baseline") -> object:
    baseline = (
        "LB-ADMISSION",
        "LB-INSTALL",
        "LB-PERSON",
        "LB-CUSTODY",
        "LB-SETTLEMENT",
        "LB-ACL",
    )
    cases = baseline + (
        ("MP-01", "MP-02", "MP-03", "MP-04", "MP-05", "MP-06") if scope == "full-managed" else ()
    )
    return SimpleNamespace(
        required_cases=cases,
        scope=scope,
        authorization={
            "allowed_operations": allowed_operations,
            "allowed_cases": cases,
        },
        target={
            "expected": {
                "truss_version": "0.0.49",
                "truss_wheel_sha256": "a" * 64,
                "native_manifest_sha256": "b" * 64,
                "migration_manifest_sha256": "c" * 64,
            },
            "resources": {
                "tolerated_grantees": ("platform_role",),
                "ordinary_role_names": ("registrar", "writer", "reader", "denied"),
                "module_access": {
                    "document_id": "arras-lakebase-qualification-v1",
                    "reader_role": "arras_probe_reader",
                    "writer_role": "arras_probe_writer",
                    "auditor_role": "arras_probe_auditor",
                    "source_sha256": operations.HARNESS_MODULE_SHA256,
                },
            },
        },
    )


def test_fixed_document_is_a_deterministic_legacy_arras_module() -> None:
    from arras.umf import parse_module

    module = parse_module(operations.HARNESS_MODULE_DOCUMENT)
    assert module.name == "lakebase_qualification"
    assert operations.HARNESS_MODULE_SHA256 == (
        "0d9c4bd6c390803483937200812e838d45734e0e0ab7925374d88aceb767f16f"
    )
    assert json.loads(operations.HARNESS_MODULE_DOCUMENT)["id"] == "arras-lakebase-qualification-v1"
    assert tuple(action.name for action in module.actions) == (
        "lakebase_qualification.CreateProbe",
    )


def test_fixed_document_reaches_public_truss_preparation_without_a_database() -> None:
    import truss

    prepared = truss.prepare_catalog(
        (
            truss.CatalogDocument(
                "arras-lakebase-qualification-v1",
                "1",
                operations.HARNESS_MODULE_DOCUMENT,
            ),
        )
    )
    assert len(prepared.documents) == 1
    interpretation = prepared.documents[0]
    assert interpretation.document.document_id == "arras-lakebase-qualification-v1"
    assert interpretation.document.content == operations.HARNESS_MODULE_DOCUMENT
    report = json.loads(interpretation.observation_bytes)
    assert report["documents"][0]["contentSha256"] == operations.HARNESS_MODULE_SHA256
    assert report["documents"][0]["validation"]["valid"] is True


def test_missing_operation_authority_blocks_each_case_without_calling_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        operations,
        "_artifact_facts",
        lambda: {
            "truss_version": None,
            "truss_wheel_sha256": None,
            "native_manifest_sha256": None,
            "migration_manifest_sha256": None,
            "evidence_codes": ["test_stub"],
        },
    )

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("the offline blocker must not call fixture capabilities")

    fixture = ModuleType("inert_fixture")
    fixture.cleanup_owned = forbidden  # type: ignore[attr-defined]
    fixture.observe_provider = forbidden  # type: ignore[attr-defined]
    result = operations.run_baseline(_inputs(), fixture, {})

    assert [row["case"] for row in result["cases"]] == [
        "LB-INSTALL",
        "LB-PERSON",
        "LB-CUSTODY",
        "LB-SETTLEMENT",
        "LB-ACL",
    ]
    assert [row["status"] for row in result["cases"]] == ["blocked"] * 5
    assert result["cases"][0]["code"] == "required_operation_not_authorized"
    assert result["cleanup"] == {
        "status": "blocked",
        "resources": [],
        "independent_absence": {
            "truss_schema_absent": None,
            "generated_roles_absent": None,
        },
    }
    assert result["module_document_sha256"] == operations.HARNESS_MODULE_SHA256


def test_full_managed_keeps_every_managed_case_explicitly_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        operations,
        "_artifact_facts",
        lambda: {
            "truss_version": "0.0.49",
            "truss_wheel_sha256": None,
            "native_manifest_sha256": None,
            "migration_manifest_sha256": None,
            "evidence_codes": ["wheel_archive_digest_unavailable"],
        },
    )
    fixture = ModuleType("inert_fixture")
    fixture.cleanup_owned = lambda: pytest.fail("must not run without install authorization")  # type: ignore[attr-defined]
    result = operations.run_baseline(
        _inputs(
            allowed_operations=(
                "read",
                "install",
                "configure",
                "apply",
                "feed",
                "refresh",
                "restart",
                "fault",
                "cleanup",
            ),
            scope="full-managed",
        ),
        fixture,
        {},
    )

    assert [row["case"] for row in result["cases"]] == [
        "LB-INSTALL",
        "LB-PERSON",
        "LB-CUSTODY",
        "LB-SETTLEMENT",
        "LB-ACL",
        "MP-01",
        "MP-02",
        "MP-03",
        "MP-04",
        "MP-05",
        "MP-06",
    ]
    assert all(row["status"] == "blocked" for row in result["cases"])
    assert result["observed"]["artifacts"]["truss_version"] == "0.0.49"
    assert result["observed"]["artifacts"]["truss_wheel_sha256"] is None


def test_contrary_native_artifact_evidence_blocks_before_opening_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        operations,
        "_artifact_facts",
        lambda: {
            "truss_version": "0.0.49",
            "truss_wheel_sha256": None,
            "native_manifest_sha256": "0" * 64,
            "migration_manifest_sha256": "c" * 64,
            "evidence_codes": ["wheel_archive_digest_unavailable"],
        },
    )
    fixture = ModuleType("inert_fixture")
    fixture.cleanup_owned = lambda: pytest.fail("must not clean up before a mutation")  # type: ignore[attr-defined]

    def forbidden() -> object:
        raise AssertionError("artifact mismatch must block before opening a database")

    result = operations.run_baseline(
        _inputs(allowed_operations=("read", "install", "cleanup")),
        fixture,
        {
            "installer_connection_source": forbidden,
            "person_connection_source": forbidden,
        },
    )
    assert result["cases"][0] == {
        "case": "LB-INSTALL",
        "status": "blocked",
        "code": "installed_artifact_evidence_incomplete",
    }
    assert result["cleanup"]["resources"] == []


@pytest.mark.parametrize(
    "value",
    [
        {"archive_info": {"hashes": {"sha256": "x" * 64}}},
        {"archive_info": {"hashes": {"sha256": "A" * 64}}},
        {"archive_info": {"hashes": {"sha256": "0" * 63}}},
        {"archive_info": {"hashes": {"sha256": "../" + "0" * 61}}},
    ],
)
def test_artifact_digest_is_not_fabricated_from_malformed_direct_url(
    monkeypatch: pytest.MonkeyPatch, value: object
) -> None:
    class Distribution:
        version = "0.0.49"

        def read_text(self, name: str) -> str | None:
            assert name == "direct_url.json"
            import json

            return json.dumps(value)

    def distribution(_name: str) -> Distribution:
        return Distribution()

    monkeypatch.setattr(native.importlib.metadata, "distribution", distribution)

    class Package:
        def joinpath(self, *parts: str) -> Package:
            self.path = "/".join(parts)
            return self

        def read_bytes(self) -> bytes:
            return self.path.encode("ascii")

    import importlib.resources

    def files(_package: Any) -> Package:
        return Package()

    monkeypatch.setattr(importlib.resources, "files", files)
    facts = native._artifact_facts()
    assert facts["truss_version"] == "0.0.49"
    assert facts["truss_wheel_sha256"] is None
    assert facts["native_manifest_sha256"] is not None
    assert facts["migration_manifest_sha256"] is not None


def test_public_dry_run_effect_is_planned_and_residue_is_checked_before_invoke() -> None:
    initial: tuple[object, ...] = ()

    class Reader:
        expected_code: str | None = None
        calls = 0

        def query(self, *_: object) -> SimpleNamespace:
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(rows=initial)
            return SimpleNamespace(
                rows=({"code": self.expected_code, "value": "arras-lakebase-qualification"},)
            )

    class Writer:
        def __init__(self, reader: Reader) -> None:
            self.reader = reader
            self.invoked = False

        def validate(self, *_: object) -> SimpleNamespace:
            return SimpleNamespace(ok=True, effects=[{"op": "create", "type": "Probe"}])

        def invoke(self, _: object, draft: dict[str, str], **__: object) -> SimpleNamespace:
            self.invoked = True
            self.reader.expected_code = draft["code"]
            return SimpleNamespace(created=1)

    reader = Reader()
    writer = Writer(reader)
    observed: dict[str, object] = {"operations": {"write": "not_run"}}
    operations._exercise_public_write(writer, reader, initial, observed)
    assert writer.invoked is True
    assert observed["operations"] == {"write": "passed"}


def test_public_write_requires_exact_tuple_readback_and_value() -> None:
    class Reader:
        calls = 0
        expected_code: str | None = None

        def query(self, *_: object) -> SimpleNamespace:
            self.calls += 1
            rows = () if self.calls == 1 else ({"code": self.expected_code, "value": "wrong"},)
            return SimpleNamespace(rows=rows)

    class Writer:
        def __init__(self, reader: Reader) -> None:
            self.reader = reader

        def validate(self, *_: object) -> SimpleNamespace:
            return SimpleNamespace(ok=True, effects=[{"op": "create", "type": "Probe"}])

        def invoke(self, _action: object, draft: dict[str, str], **__: object) -> SimpleNamespace:
            self.reader.expected_code = draft["code"]
            return SimpleNamespace(created=1)

    reader = Reader()
    with pytest.raises(operations._ObservedFailure, match="readback_mismatch"):
        operations._exercise_public_write(Writer(reader), reader, (), {"operations": {}})


def test_strict_probe_classifies_actual_public_typed_grant_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import truss

    refusal = truss.InstallRefused(
        code="third_party_grant",
        role_name="platform_role",
        object_class="relation",
        phase="post_installation",
    )

    class Connection:
        def __init__(self) -> None:
            self.rollback_called = False
            self.committed = False
            self.queries: list[str] = []

        def execute(self, query: str, *_: object) -> SimpleNamespace:
            self.queries.append(query)
            if query.startswith('SELECT value FROM "probe"'):
                return SimpleNamespace(fetchall=lambda: [("retain",)])
            return SimpleNamespace(
                fetchone=lambda: (
                    "session",
                    "session",
                    "",
                    '"$user", public',
                    "10s",
                    "read committed",
                    "off",
                )
            )

        def rollback(self) -> None:
            self.rollback_called = True

        def commit(self) -> None:
            self.committed = True

    connection = Connection()

    class Host:
        def adopt_transaction(self, **_: object) -> object:
            return truss.Ok(object())

        def detach(self) -> bool:
            return True

    class Assembly:
        def install_in_transaction(self, *_: object, **__: object) -> object:
            return truss.Ok(refusal)

    def adopt(_connection: Any, *, statement_timeout_ms: int, operation_timeout_ms: int) -> Host:
        assert statement_timeout_ms == 10_000
        assert operation_timeout_ms == 30_000
        return Host()

    def create_assembly(_configuration: Any, _host: Any) -> Any:
        return truss.Ok(Assembly())

    monkeypatch.setattr(truss, "adopt_psycopg_host", adopt)
    monkeypatch.setattr(truss, "create_reference_assembly", create_assembly)
    probe = native._strict_install_attempt(
        connection,
        ("platform_role",),
        "probe",
        [("retain",)],
        ("session", "session", "", '"$user", public', "10s", "read committed", "off"),
    )
    assert probe.outcome == "typed_refusal"
    assert probe.object_class == "relation"
    assert probe.phase == "post_installation"
    assert probe.role_selected is True
    assert probe.selected_role_sha256 == native._digest_name("platform_role")
    assert probe.caller_state_unchanged is True
    assert native._CALLER_IDENTITY_SQL in connection.queries
    assert connection.rollback_called is True
    assert connection.committed is False


def test_strict_success_requires_public_pending_installation_type_and_unknown_ok_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import truss

    pending = truss.PendingCatalogInstallation(
        installation_id="run-id",
        owner_role="truss_owner_run",
        registrar_role="truss_registrar_run",
        release_id="0.74-candidate",
    )
    classified = native._classify_strict_result(
        truss.Ok(pending),
        ("platform_role",),
        truss.InstallRefused,
        truss.PendingCatalogInstallation,
    )
    assert classified.outcome == "unexpected_success"
    assert classified.commit_unexpected_success is True

    class Connection:
        def __init__(self) -> None:
            self.committed = False
            self.rolled_back = False

        def execute(self, query: str, *_: object) -> SimpleNamespace:
            if query.startswith('SELECT value FROM "probe"'):
                return SimpleNamespace(fetchall=lambda: [("retain",)])
            return SimpleNamespace(
                fetchone=lambda: (
                    "session",
                    "session",
                    "",
                    '"$user", public',
                    "10s",
                    "read committed",
                    "off",
                )
            )

        def commit(self) -> None:
            self.committed = True

        def rollback(self) -> None:
            self.rolled_back = True

    class Host:
        def adopt_transaction(self, **_: object) -> object:
            return truss.Ok(object())

        def detach(self) -> bool:
            return True

    class Assembly:
        def install_in_transaction(self, *_: object, **__: object) -> object:
            return truss.Ok(SimpleNamespace(owner_role="untrusted", registrar_role="untrusted"))

    def adopt(_connection: Any, **_kwargs: Any) -> Host:
        return Host()

    def create_assembly(_configuration: Any, _host: Any) -> Any:
        return truss.Ok(Assembly())

    monkeypatch.setattr(truss, "adopt_psycopg_host", adopt)
    monkeypatch.setattr(truss, "create_reference_assembly", create_assembly)
    connection = Connection()
    probe = native._strict_install_attempt(
        connection,
        ("platform_role",),
        "probe",
        [("retain",)],
        ("session", "session", "", '"$user", public', "10s", "read committed", "off"),
    )
    assert probe.outcome == "other_refusal"
    assert probe.owner_role is None
    assert connection.committed is False
    assert connection.rolled_back is True


def test_strict_probe_detach_failure_stops_caller_queries_and_marks_state_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import truss

    class Connection:
        def __init__(self) -> None:
            self.queries: list[str] = []
            self.closed = False

        def execute(self, query: str, *_: object) -> None:
            self.queries.append(query)

        def close(self) -> None:
            self.closed = True

    connection = Connection()

    class Host:
        def adopt_transaction(self, **_: object) -> object:
            return truss.Ok(object())

        def detach(self) -> bool:
            return False

    class Assembly:
        def install_in_transaction(self, *_: object, **__: object) -> object:
            return truss.Ok(
                truss.InstallRefused(
                    code="third_party_grant",
                    role_name="platform_role",
                    object_class="relation",
                    phase="post_installation",
                )
            )

    def adopt(_connection: Any, *, statement_timeout_ms: int, operation_timeout_ms: int) -> Host:
        assert statement_timeout_ms == 10_000
        assert operation_timeout_ms == 30_000
        return Host()

    def create_assembly(_configuration: Any, _host: Any) -> Any:
        return truss.Ok(Assembly())

    monkeypatch.setattr(truss, "adopt_psycopg_host", adopt)
    monkeypatch.setattr(truss, "create_reference_assembly", create_assembly)
    probe = native._strict_install_attempt(
        connection,
        ("platform_role",),
        "probe",
        [("retain",)],
        ("session", "session", "", '"$user", public'),
    )
    assert probe.outcome == "typed_refusal"
    assert probe.caller_state_unchanged is None
    assert probe.native_state_unchanged is None
    assert connection.queries == []
    assert connection.closed is True


@pytest.mark.parametrize(
    ("autocommit", "expected_first"),
    [
        (False, "SET TRANSACTION ISOLATION LEVEL READ COMMITTED READ WRITE"),
        (True, "BEGIN ISOLATION LEVEL READ COMMITTED READ WRITE"),
    ],
)
def test_strict_probe_establishes_bounded_transaction_before_public_adoption(
    monkeypatch: pytest.MonkeyPatch,
    autocommit: bool,
    expected_first: str,
) -> None:
    calls: list[str] = []
    identity = ("session", "session", "", '"$user", public', "10s", "read committed", "off")

    class Connection:
        def __init__(self) -> None:
            self.autocommit = autocommit
            self.info = SimpleNamespace(transaction_status=0)

        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, query: str, *_: object) -> SimpleNamespace:
            calls.append(query)
            if query.startswith("SELECT session_user"):
                return SimpleNamespace(fetchone=lambda: identity)
            if query.startswith("SELECT value FROM"):
                return SimpleNamespace(fetchall=lambda: [("retain",)])

            def no_rows() -> list[tuple[object, ...]]:
                return []

            return SimpleNamespace(fetchone=lambda: None, fetchall=no_rows)

        def rollback(self) -> None:
            calls.append("ROLLBACK")

    def snapshot(_connection: Any) -> tuple[bool, str]:
        return False, "a" * 64

    def strict_attempt(
        connection: Any,
        _selected: tuple[str, ...],
        _temp: str,
        _prior_work: list[Any],
        caller_identity: Any,
    ) -> Any:
        assert calls[0] == expected_first
        assert calls[1] == "SET LOCAL statement_timeout = '10000ms'"
        assert caller_identity == identity
        connection.rollback()
        return native._StrictProbe(
            "typed_refusal",
            "relation",
            "post_installation",
            native._digest_name("platform_role"),
            True,
            True,
            None,
        )

    monkeypatch.setattr(native, "_native_install_snapshot", snapshot)
    monkeypatch.setattr(native, "_strict_install_attempt", strict_attempt)

    def source() -> Connection:
        return Connection()

    probe = native._strict_default_probe(
        {"installer_connection_source": source}, ("platform_role",)
    )
    assert probe.caller_state_unchanged is True
    assert probe.native_state_unchanged is True
    assert calls[:2] == [
        expected_first,
        "SET LOCAL statement_timeout = '10000ms'",
    ]
    assert calls[-1] == "ROLLBACK"


@pytest.mark.parametrize(
    ("caller_state_unchanged", "expected_owned"),
    [(None, False), (True, True)],
)
def test_unexpected_strict_success_requires_confirmed_detach_before_cleanup_ownership(
    monkeypatch: pytest.MonkeyPatch,
    caller_state_unchanged: bool | None,
    expected_owned: bool,
) -> None:
    strict = native._StrictProbe(
        "unexpected_success",
        None,
        None,
        None,
        None,
        caller_state_unchanged,
        False,
        "truss_owner_run",
        "truss_registrar_run",
    )

    def fake_strict_probe(*_args: Any) -> Any:
        return strict

    monkeypatch.setattr(operations, "_strict_default_probe", fake_strict_probe)
    observed = {"strict_probe": {}, "operations": {"installation_ran": None}}
    results = {"LB-INSTALL": operations._case_row("LB-INSTALL", "blocked", "pending")}
    state = operations._attempt_selected_install(
        object(),
        {},
        ("platform_role",),
        observed,
        results,
    )
    assert state is not None
    assert state.mutation_started is expected_owned
    assert bool(state.expected_names) is expected_owned
    assert results["LB-INSTALL"]["code"] == "strict_policy_unexpectedly_succeeded"


def test_public_dry_run_refuses_to_invoke_if_independent_read_shows_residue() -> None:
    class Reader:
        def query(self, *_: object) -> SimpleNamespace:
            return SimpleNamespace(rows=[{"code": "unexpected"}])

    class Writer:
        invoked = False

        def validate(self, *_: object) -> SimpleNamespace:
            return SimpleNamespace(ok=True, effects=[{"op": "create", "type": "Probe"}])

        def invoke(self, *_: object, **__: object) -> SimpleNamespace:
            self.invoked = True
            return SimpleNamespace(created=1)

    writer = Writer()
    with pytest.raises(operations._ObservedFailure, match="dry_run_changed_records"):
        operations._exercise_public_write(writer, Reader(), [], {"operations": {}})
    assert writer.invoked is False


def test_cleanup_facts_are_retained_and_unowned_runs_never_call_cleanup() -> None:
    raw = [
        {"resource_kind": "schema", "name_or_opaque_id": "truss", "removed": True},
        {"resource_kind": "role", "name_or_opaque_id": "truss_owner_run", "removed": True},
    ]

    class Connection:
        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, statement: str, *_: object) -> SimpleNamespace:
            if "to_regnamespace" in statement:
                return SimpleNamespace(fetchone=lambda: (True,))
            return SimpleNamespace(fetchone=lambda: (0,))

    fixture = ModuleType("cleanup_fixture")
    fixture.cleanup_owned = lambda: raw  # type: ignore[attr-defined]
    sources = {"installer_connection_source": Connection}
    expected = {("schema", "truss"), ("role", "truss_owner_run")}
    untouched = operations._cleanup_owned_run(
        fixture, sources, expected, mutation_started=False, cleanup_authorized=True
    )
    assert untouched["status"] == "blocked"
    attempted = operations._cleanup_owned_run(
        fixture, sources, expected, mutation_started=True, cleanup_authorized=True
    )
    assert attempted["status"] == "passed"
    assert attempted["resources"] == [
        {
            "resource_kind": "schema",
            "name_or_opaque_id": operations._digest_name("truss"),
            "removed": True,
        },
        {
            "resource_kind": "role",
            "name_or_opaque_id": operations._digest_name("truss_owner_run"),
            "removed": True,
        },
    ]


def test_partial_role_setup_failure_is_typed_as_uncertain_ownership() -> None:
    class Connection:
        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, _: str, params: object) -> SimpleNamespace:
            installation_roles = ["truss_owner_run", "truss_registrar_run"]
            rows = (
                [
                    ("truss_owner_run", False, False, False, False),
                    ("truss_registrar_run", False, False, False, False),
                ]
                if params == (installation_roles,)
                else []
            )
            return SimpleNamespace(fetchall=lambda: rows)

    fixture = ModuleType("partial_role_setup")

    def create_then_interrupt(_: object) -> object:
        raise RuntimeError("private detail must not be copied")

    fixture.prepare_owned_access_roles = create_then_interrupt  # type: ignore[attr-defined]
    fixture.grant_owned_memberships = lambda _: pytest.fail("grant follows incomplete provisioning")  # type: ignore[attr-defined]
    principals = {
        label: SimpleNamespace(user=label) for label in ("registrar", "writer", "reader", "denied")
    }
    access = SimpleNamespace(
        reader_role="arras_reader",
        writer_role="arras_writer",
        auditor_role=None,
    )
    migrated = SimpleNamespace(owner_role="truss_owner_run", registrar_role="truss_registrar_run")
    with pytest.raises(operations._OwnershipUncertain):
        operations._prepare_access_roles(
            fixture,
            {"installer_connection_source": Connection},
            principals,
            access,
            migrated,
            set(),
        )


def test_post_install_operation_failure_retains_verified_cleanup_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roles = ("truss_owner_run", "truss_registrar_run")
    expected_names = {("schema", "truss"), *(("role", role) for role in roles)}
    migrated = SimpleNamespace(owner_role=roles[0], registrar_role=roles[1])
    all_operations = (
        "read",
        "install",
        "configure",
        "apply",
        "cleanup",
        "provision_module_roles",
        "prepare_owned_access_roles",
        "grant_owned_memberships",
        "revoke_owned_memberships",
    )
    inputs = _inputs(allowed_operations=all_operations)
    fixture = ModuleType("cleanup_after_failure")
    fixture.__dict__["cleanup_owned"] = lambda: [
        {"resource_kind": "schema", "name_or_opaque_id": "truss", "removed": True},
        *({"resource_kind": "role", "name_or_opaque_id": role, "removed": True} for role in roles),
    ]

    class Connection:
        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, statement: str, *_: object) -> SimpleNamespace:
            if "to_regnamespace" in statement:
                return SimpleNamespace(fetchone=lambda: (True,))
            return SimpleNamespace(fetchone=lambda: (0,))

    def prepare_baseline(*_args: Any) -> tuple[Any, Any, dict[str, Any]]:
        return object(), object(), {}

    def fresh_preconditions(*_args: Any) -> bool:
        return True

    monkeypatch.setattr(operations, "_prepare_baseline", prepare_baseline)
    monkeypatch.setattr(operations, "_fresh_install_preconditions", fresh_preconditions)

    def successful_install(*args: Any) -> Any:
        results = args[4]
        results["LB-INSTALL"] = operations._case_row(
            "LB-INSTALL", "passed", "typed_strict_refusal_then_selected_install"
        )
        return operations._InstallState(migrated, expected_names, True)

    monkeypatch.setattr(
        operations,
        "_attempt_selected_install",
        successful_install,
    )

    def fail_after_install(*_: object, **__: object) -> None:
        raise RuntimeError("controlled post-install failure")

    monkeypatch.setattr(operations, "_prepare_access_roles", fail_after_install)
    result = operations.run_baseline(
        inputs,
        fixture,
        {
            "installer_connection_source": Connection,
            "person_connection_source": lambda: None,
        },
    )
    assert result["cases"][0]["status"] == "passed", result
    assert result["cases"][4] == {
        "case": "LB-ACL",
        "status": "blocked",
        "code": "authorized_public_operation_unavailable",
    }
    assert result["cleanup"]["status"] == "passed"
    assert {item["resource_kind"] for item in result["cleanup"]["resources"]} == {
        "schema",
        "role",
    }


def test_unexpected_strict_success_retains_final_cleanup_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roles = ("truss_owner_run", "truss_registrar_run")
    expected_names = {("schema", "truss"), *(("role", role) for role in roles)}
    fixture = ModuleType("unexpected_strict_success")
    fixture.__dict__["cleanup_owned"] = lambda: [
        {"resource_kind": "schema", "name_or_opaque_id": "truss", "removed": True},
        *({"resource_kind": "role", "name_or_opaque_id": role, "removed": True} for role in roles),
    ]  # type: ignore[attr-defined]

    class Connection:
        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, statement: str, *_: object) -> SimpleNamespace:
            if "to_regnamespace" in statement:
                return SimpleNamespace(fetchone=lambda: (True,))
            return SimpleNamespace(fetchone=lambda: (0,))

    def prepare_baseline(*_args: Any) -> tuple[Any, Any, dict[str, Any]]:
        return object(), object(), {}

    def fresh_preconditions(*_args: Any) -> bool:
        return True

    def unexpected_success(*args: Any) -> Any:
        args[4]["LB-INSTALL"] = operations._case_row(
            "LB-INSTALL", "blocked", "strict_policy_unexpectedly_succeeded"
        )
        return operations._InstallState(None, set(expected_names), True)

    monkeypatch.setattr(operations, "_prepare_baseline", prepare_baseline)
    monkeypatch.setattr(operations, "_fresh_install_preconditions", fresh_preconditions)
    monkeypatch.setattr(operations, "_attempt_selected_install", unexpected_success)
    result = operations.run_baseline(
        _inputs(allowed_operations=("read", "install", "cleanup")),
        fixture,
        {
            "installer_connection_source": Connection,
            "person_connection_source": lambda: None,
        },
    )
    assert result["cases"][0] == {
        "case": "LB-INSTALL",
        "status": "blocked",
        "code": "strict_policy_unexpectedly_succeeded",
    }
    assert result["cleanup"]["status"] == "passed"
    assert {row["resource_kind"] for row in result["cleanup"]["resources"]} == {
        "schema",
        "role",
    }


@pytest.mark.parametrize("interrupt_type", [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("interrupt_cleanup", [False, True])
def test_interruption_after_owned_install_returns_partial_failure_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    interrupt_type: type[BaseException],
    interrupt_cleanup: bool,
) -> None:
    roles = ("truss_owner_run", "truss_registrar_run")
    expected_names = {("schema", "truss"), *(("role", role) for role in roles)}
    migrated = SimpleNamespace(owner_role=roles[0], registrar_role=roles[1])
    operations_allowed = (
        "read",
        "install",
        "configure",
        "apply",
        "cleanup",
        "provision_module_roles",
        "prepare_owned_access_roles",
        "grant_owned_memberships",
        "revoke_owned_memberships",
    )
    fixture = ModuleType("interrupted_after_install")
    cleanup_calls: list[str] = []

    def cleanup_owned() -> list[dict[str, object]]:
        cleanup_calls.append("called")
        if interrupt_cleanup:
            raise interrupt_type
        return [
            {"resource_kind": "schema", "name_or_opaque_id": "truss", "removed": True},
            *(
                {"resource_kind": "role", "name_or_opaque_id": role, "removed": True}
                for role in roles
            ),
        ]

    fixture.cleanup_owned = cleanup_owned  # type: ignore[attr-defined]

    class Connection:
        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, statement: str, *_: object) -> SimpleNamespace:
            if "to_regnamespace" in statement:
                return SimpleNamespace(fetchone=lambda: (True,))
            return SimpleNamespace(fetchone=lambda: (0,))

    def prepare_baseline(*_args: Any) -> tuple[Any, Any, dict[str, Any]]:
        return object(), object(), {}

    def fresh_preconditions(*_args: Any) -> bool:
        return True

    monkeypatch.setattr(operations, "_prepare_baseline", prepare_baseline)
    monkeypatch.setattr(operations, "_fresh_install_preconditions", fresh_preconditions)

    def successful_install(*args: Any) -> Any:
        args[4]["LB-INSTALL"] = operations._case_row(
            "LB-INSTALL", "passed", "typed_strict_refusal_then_selected_install"
        )
        return operations._InstallState(migrated, set(expected_names), True)

    monkeypatch.setattr(operations, "_attempt_selected_install", successful_install)

    def interrupt_access(*_args: Any, **_kwargs: Any) -> Any:
        raise interrupt_type

    monkeypatch.setattr(operations, "_prepare_access_roles", interrupt_access)
    result = operations.run_baseline(
        _inputs(allowed_operations=operations_allowed),
        fixture,
        {
            "installer_connection_source": Connection,
            "person_connection_source": lambda: None,
        },
    )
    assert result["cases"][0]["status"] == "passed"
    assert result["cases"][4] == {
        "case": "LB-ACL",
        "status": "failed",
        "code": "operation_interrupted",
    }
    assert cleanup_calls == ["called"]
    assert result["cleanup"]["status"] == ("blocked" if interrupt_cleanup else "passed")
