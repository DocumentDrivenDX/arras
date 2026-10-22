# SPDX-License-Identifier: MIT OR Apache-2.0
"""The generic EX-04 policy wrapper is opt-in, per-call, and fail-closed."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Lock
from typing import cast

import pytest

from arras import Arras
from arras.actions import Create, Plan, Ref
from arras.backend import Backend
from arras.errors import Conflict, PolicyRefused, Refused, Unsupported
from arras.model import ModuleInfo, Placement
from arras.policy import (
    PolicyAnnotationCapabilities,
    PolicyBackend,
    PolicyDecision,
    PolicyOperation,
    PolicyRequest,
    WritePolicy,
)
from arras.results import (
    Answer,
    BackendInfo,
    BackendStatus,
    BatchReceipt,
    ChangesPage,
    ImportResult,
    ItemResult,
    LoadsPage,
    Receipt,
    RecordsPage,
    RegisteredDocument,
    RegistrationCheck,
    RegistryResult,
    Validation,
)
from arras.searchplan import TextMatch
from arras.testing import InMemory, example_module
from arras.types import Principal, Revision, Statement

USER = Principal("person", "secret-token")
MODULE = ModuleInfo("catalog", Placement("memory"), Revision(), ())


class RecordingBackend:
    name = "memory"
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]]
    fail_with: Exception | None

    def __init__(self) -> None:
        self.calls = []
        self.fail_with = None
        self.info = BackendInfo("memory", ("reader", "provider"))
        self.state = BackendStatus(True)

    def _call(self, name: str, *args: object, **kwargs: object) -> None:
        self.calls.append((name, args, kwargs))
        if self.fail_with is not None:
            raise self.fail_with

    def describe(self) -> BackendInfo:
        return self.info

    def catalog(self, principal: Principal) -> Mapping[str, ModuleInfo]:
        self._call("catalog", principal)
        return {"catalog": MODULE}

    def status(self) -> BackendStatus:
        self._call("status")
        return self.state

    def query(
        self,
        principal: Principal,
        module: str,
        statement: Statement,
        *,
        limit: int,
        text: TextMatch | None = None,
    ) -> Answer:
        self._call("query", principal, module, statement, limit=limit, text=text)
        raise NotImplementedError

    def reached(self, principal: Principal, token: str) -> bool:
        self._call("reached", principal, token)
        return True

    def attach(self, principal: Principal, module: ModuleInfo) -> RegistryResult:
        self._call("attach", principal, module)
        return RegistryResult(module.name, module.revision, True)

    def apply(
        self,
        principal: Principal,
        plan: Plan,
        *,
        idempotency_key: str | None,
        dry_run: bool = False,
    ) -> Receipt | Validation:
        self._call("apply", principal, plan, idempotency_key=idempotency_key, dry_run=dry_run)
        return Receipt(plan.action, (), 1, 0, 0, 0, 0, "token")

    def apply_batch(
        self,
        principal: Principal,
        plans: Sequence[Plan],
        *,
        atomic: bool,
        idempotency_key: str | None,
        stop_on_error: bool = False,
    ) -> BatchReceipt:
        self._call(
            "apply_batch",
            principal,
            plans,
            atomic=atomic,
            idempotency_key=idempotency_key,
            stop_on_error=stop_on_error,
        )
        return BatchReceipt("batch", atomic, (), len(plans), 0, "token")

    def import_records(
        self,
        principal: Principal,
        module: str,
        records: Sequence[Mapping[str, object]],
        *,
        load_id: str,
        initiated_by: str,
    ) -> ImportResult:
        self._call(
            "import_records",
            principal,
            module,
            records,
            load_id=load_id,
            initiated_by=initiated_by,
        )
        return ImportResult(len(records), 0, ())

    def export_records(
        self, principal: Principal, module: str, *, limit: int, after: str | None
    ) -> RecordsPage:
        self._call("export_records", principal, module, limit=limit, after=after)
        raise NotImplementedError

    def changes(self, principal: Principal, **kwargs: object) -> ChangesPage:
        self._call("changes", principal, **kwargs)
        raise NotImplementedError

    def loads(
        self, principal: Principal, module: str, *, limit: int, after: str | None
    ) -> LoadsPage:
        self._call("loads", principal, module, limit=limit, after=after)
        raise NotImplementedError

    def register(
        self,
        principal: Principal,
        document: bytes,
        module: ModuleInfo,
        *,
        unknown_endpoint: str,
        expected_revision: Revision | None = None,
    ) -> RegistryResult:
        self._call(
            "register",
            principal,
            document,
            module,
            unknown_endpoint=unknown_endpoint,
            expected_revision=expected_revision,
        )
        return RegistryResult(module.name, module.revision, True)

    def validate_register(
        self,
        principal: Principal,
        document: bytes,
        module: ModuleInfo,
        *,
        unknown_endpoint: str,
    ) -> RegistrationCheck:
        self._call(
            "validate_register",
            principal,
            document,
            module,
            unknown_endpoint=unknown_endpoint,
        )
        return RegistrationCheck(module.revision, False, current=module)

    def document(self, principal: Principal, module: str) -> RegisteredDocument:
        self._call("document", principal, module)
        raise NotImplementedError


def plan_with_nested_values() -> Plan:
    nested: dict[str, object] = {"labels": ["first"], "amount": Decimal("1.25")}
    effect = Create(Ref("catalog.UseCase", "one"), {"metadata": nested})
    return Plan("catalog.create_use_case", (), (effect,), "digest")


def _allowed(request: PolicyRequest) -> PolicyDecision:
    return PolicyDecision(True)


def _mutating_calls(backend: RecordingBackend, policy: WritePolicy) -> None:
    wrapped = PolicyBackend(cast(Backend, backend), policy)
    wrapped.apply(USER, Plan("catalog.create", (), ()), idempotency_key="apply-key")
    wrapped.apply_batch(
        USER,
        [Plan("catalog.create", (), ()), Plan("catalog.update", (), ())],
        atomic=False,
        idempotency_key=None,
        stop_on_error=True,
    )
    wrapped.import_records(USER, "catalog", [{"id": "one"}], load_id="load", initiated_by="person")
    wrapped.register(
        USER,
        b'{"exact":"bytes"}',
        MODULE,
        unknown_endpoint="reject",
        expected_revision=Revision({"memory": 3}),
    )
    wrapped.validate_register(USER, b'{"exact":"bytes"}', MODULE, unknown_endpoint="reject")
    wrapped.attach(USER, MODULE)


def test_each_protocol_mutation_is_authorized_once_with_typed_scope() -> None:
    backend = RecordingBackend()
    observed: list[PolicyRequest] = []

    def policy(request: PolicyRequest) -> PolicyDecision:
        observed.append(request)
        return PolicyDecision(True, code="host_allowed")

    _mutating_calls(backend, policy)
    assert [request.operation for request in observed] == [
        "apply",
        "apply_batch",
        "import_records",
        "register",
        "validate_register",
        "attach",
    ]
    assert len(backend.calls) == 6
    assert all(call[1][0] is USER for call in backend.calls)
    assert observed[0].principal is USER
    assert observed[0].modules == ("catalog",)
    assert observed[0].options == {"idempotency_key": "apply-key"}
    assert observed[1].modules == ("catalog",)
    assert len(observed[1].plans) == 2
    assert observed[1].options == {
        "atomic": False,
        "idempotency_key": None,
        "stop_on_error": True,
    }
    assert observed[2].records == ({"id": "one"},)
    assert observed[2].options == {"load_id": "load", "initiated_by": "person"}
    assert observed[3].document == b'{"exact":"bytes"}'
    assert observed[3].options["expected_revision"] == Revision({"memory": 3})
    assert observed[4].dry_run is True
    assert observed[5].module == MODULE


@pytest.mark.parametrize(
    "operation",
    ["apply", "apply_batch", "import_records", "register", "validate_register", "attach"],
)
@pytest.mark.parametrize("mode", ["deny", "exception", "invalid_return"])
def test_refusal_and_bad_callback_fail_before_every_mutating_delegation(
    operation: PolicyOperation, mode: str
) -> None:
    backend = RecordingBackend()

    def policy(request: PolicyRequest) -> object:
        assert request.operation == operation
        if mode == "deny":
            return PolicyDecision(False, code="not_allowed")
        if mode == "exception":
            raise RuntimeError("sensitive callback payload")
        return object()

    wrapped = PolicyBackend(cast(Backend, backend), cast(WritePolicy, policy))
    with pytest.raises(Refused, match="memory refused"):
        _call_one(wrapped, operation)
    assert backend.calls == []


def test_policy_refusal_code_is_typed_safe_and_additive_to_serializers() -> None:
    backend = RecordingBackend()
    wrapped = PolicyBackend(
        cast(Backend, backend), lambda request: PolicyDecision(False, code="host_denied")
    )
    with pytest.raises(PolicyRefused) as raised:
        wrapped.apply(USER, Plan("catalog.a", (), ()), idempotency_key=None)
    assert raised.value.reason == "no_access"
    assert raised.value.policy_code == "host_denied"
    from arras.gqlschema import error_code
    from arras.operate.wire import error_json
    from arras.serialize import error_body

    body = error_body(raised.value)
    assert body["type"] == "Refused" and body["policy_code"] == "host_denied"
    assert error_json(raised.value)["error"]["policy_code"] == "host_denied"
    assert error_code(raised.value) == (
        "REFUSED",
        {"backend": "memory", "reason": "no_access", "policy_code": "host_denied"},
    )
    native = Refused("memory", "apply")
    native.policy_code = "arbitrary sensitive text"  # type: ignore[attr-defined]
    assert "policy_code" not in error_body(native)


def test_policy_refusal_hides_callback_exception_text() -> None:
    backend = RecordingBackend()

    def explode(request: PolicyRequest) -> PolicyDecision:
        raise RuntimeError("sensitive policy details")

    with pytest.raises(PolicyRefused) as raised:
        PolicyBackend(cast(Backend, backend), explode).apply(
            USER, Plan("catalog.a", (), ()), idempotency_key=None
        )
    assert raised.value.policy_code == "policy_error"
    assert "sensitive" not in str(raised.value)


def _call_one(wrapped: PolicyBackend, operation: PolicyOperation) -> object:
    if operation == "apply":
        return wrapped.apply(USER, Plan("catalog.a", (), ()), idempotency_key=None)
    if operation == "apply_batch":
        return wrapped.apply_batch(
            USER, [Plan("catalog.a", (), ())], atomic=False, idempotency_key=None
        )
    if operation == "import_records":
        return wrapped.import_records(USER, "catalog", [], load_id="l", initiated_by="person")
    if operation == "register":
        return wrapped.register(USER, b"document", MODULE, unknown_endpoint="reject")
    if operation == "validate_register":
        return wrapped.validate_register(USER, b"document", MODULE, unknown_endpoint="reject")
    return wrapped.attach(USER, MODULE)


def test_nonempty_annotations_refuse_before_apply_even_on_dry_run() -> None:
    backend = RecordingBackend()
    wrapped = PolicyBackend(
        cast(Backend, backend),
        lambda request: PolicyDecision(True, annotations={"ticket": "approved"}),
    )
    with pytest.raises(Unsupported, match="policy annotations"):
        wrapped.apply(USER, Plan("catalog.a", (), ()), idempotency_key=None, dry_run=True)
    assert backend.calls == []


def test_callback_and_provider_share_one_deep_immutable_approved_snapshot() -> None:
    backend = RecordingBackend()
    original = plan_with_nested_values()
    approved: list[Plan] = []

    def policy(request: PolicyRequest) -> PolicyDecision:
        assert request.principal is USER
        assert "secret-token" not in repr(request)
        approved.append(request.plans[0])
        properties = cast(Create, request.plans[0].effects[0]).properties
        with pytest.raises(TypeError):
            properties["other"] = "changed"  # type: ignore[index]
        with pytest.raises(TypeError):
            cast(Mapping[str, object], properties["metadata"])["new"] = "changed"  # type: ignore[index]
        with pytest.raises(TypeError):
            cast(list[object], cast(Mapping[str, object], properties["metadata"])["labels"])[0] = (
                "changed"
            )
        return PolicyDecision(True)

    wrapped = PolicyBackend(cast(Backend, backend), policy)
    result = wrapped.apply(USER, original, idempotency_key=None)
    assert isinstance(result, Receipt)
    delegated = cast(Plan, backend.calls[0][1][1])
    assert delegated is not approved[0]
    frozen_properties = cast(Create, approved[0].effects[0]).properties
    delegated_properties = cast(Create, delegated.effects[0]).properties
    approved_metadata = cast(Mapping[str, object], frozen_properties["metadata"])
    delegated_metadata = cast(Mapping[str, object], delegated_properties["metadata"])
    assert tuple(cast(Sequence[object], approved_metadata["labels"])) == ("first",)
    assert delegated_metadata["labels"] == ["first"]
    source = cast(Create, original.effects[0]).properties["metadata"]
    assert cast(Mapping[str, object], source)["labels"] == ["first"]
    approved_properties = cast(Create, delegated.effects[0]).properties
    metadata = cast(Mapping[str, object], approved_properties["metadata"])
    assert metadata["labels"] == ["first"]
    assert isinstance(metadata["labels"], list)
    assert metadata["amount"] == Decimal("1.25")
    assert "secret-token" not in repr(approved[0])


def test_batch_is_one_policy_decision_before_any_delegation() -> None:
    backend = RecordingBackend()
    seen: list[PolicyRequest] = []
    wrapped = PolicyBackend(
        cast(Backend, backend),
        lambda request: seen.append(request) or PolicyDecision(False),
    )
    with pytest.raises(Refused):
        wrapped.apply_batch(
            USER,
            [Plan("catalog.a", (), ()), Plan("other.b", (), ())],
            atomic=False,
            idempotency_key=None,
        )
    assert len(seen) == 1
    assert seen[0].modules == ("catalog", "other")
    assert len(seen[0].plans) == 2
    assert backend.calls == []


def test_each_retry_rechecks_policy_and_native_refusal_is_preserved() -> None:
    backend = RecordingBackend()
    attempts = 0

    def policy(request: PolicyRequest) -> PolicyDecision:
        assert request.operation == "apply"
        nonlocal attempts
        attempts += 1
        return PolicyDecision(attempts == 1)

    wrapped = PolicyBackend(cast(Backend, backend), policy)
    plan = Plan("catalog.a", (), ())
    wrapped.apply(USER, plan, idempotency_key="replayed")
    with pytest.raises(Refused):
        wrapped.apply(USER, plan, idempotency_key="replayed")
    assert attempts == 2
    assert len(backend.calls) == 1

    native = Refused("memory", "apply", "token_expired")
    backend.fail_with = native
    with pytest.raises(Refused) as error:
        PolicyBackend(cast(Backend, backend), _allowed).apply(USER, plan, idempotency_key=None)
    assert error.value is native


def test_reads_forward_and_optional_lifecycle_capability_is_not_fabricated() -> None:
    backend = RecordingBackend()
    wrapped = PolicyBackend(cast(Backend, backend), _allowed)
    assert wrapped.describe() is backend.info
    assert wrapped.status() is backend.state
    assert wrapped.reached(USER, "opaque") is True
    assert wrapped.catalog(USER) == {"catalog": MODULE}
    assert [call[0] for call in backend.calls] == ["status", "reached", "catalog"]
    assert not hasattr(wrapped, "migrate")

    class WithMigration(RecordingBackend):
        def migrate(self, *, timeout: float | None = None) -> str:
            self._call("migrate", timeout=timeout)
            return "installed"

    migrated = PolicyBackend(cast(Backend, WithMigration()), _allowed)
    assert migrated.migrate(timeout=1.0) == "installed"


def test_wrapped_replica_keeps_reader_capabilities_and_native_write_refusal() -> None:
    world = InMemory()
    replica = cast(Backend, world.backends["memory_replica"])
    wrapped = PolicyBackend(replica, _allowed)
    assert wrapped.describe() == replica.describe()
    assert wrapped.status() == replica.status()
    assert not hasattr(wrapped, "migrate")
    with pytest.raises(Unsupported):
        wrapped.apply(USER, Plan("catalog.a", (), ()), idempotency_key=None)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"allowed": 1},
        {"allowed": True, "code": "bad code"},
        {"allowed": True, "annotations": {"bad-key": "value"}},
        {"allowed": True, "annotations": {"key": "x" * 1025}},
        {"allowed": True, "annotations": {f"k{i}": "v" for i in range(33)}},
        {"allowed": True, "annotations": {f"k{i}": "x" * 1000 for i in range(17)}},
    ],
)
def test_decisions_validate_types_and_bounds(kwargs: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        PolicyDecision(**kwargs)  # type: ignore[arg-type]


def test_policy_value_repr_redacts_request_payload_and_annotation_values() -> None:
    decision = PolicyDecision(True, annotations={"note": "personal payload"})
    assert "personal payload" not in repr(decision)
    request = PolicyRequest(
        USER,
        "import_records",
        ("catalog",),
        records=({"sensitive": "request payload"},),
        options={"idempotency_key": "secret-key"},
    )
    rendered = repr(request)
    assert "secret-token" not in rendered
    assert "request payload" not in rendered
    assert "secret-key" not in rendered


def test_policy_values_cannot_be_deleted_to_unfreeze_them() -> None:
    request = PolicyRequest(USER, "apply", ("catalog",))
    decision = PolicyDecision(True)
    with pytest.raises(AttributeError):
        del request.operation
    with pytest.raises(AttributeError):
        del decision.allowed
    with pytest.raises(AttributeError):
        request.operation = "attach"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        decision.allowed = False  # type: ignore[misc]


def _many_valued_document() -> str:
    document = json.loads(example_module())
    module = document["modules"][0]
    record = next(item for item in module["elements"] if item.get("id") == "UseCase")
    record["members"].append({"module": "catalog", "element": "UseCase.tags"})
    record["extensions"]["umf.ddd"]["fields"]["tags"] = {
        "type": {"kind": "scalar", "name": "string"},
        "cardinality": "many",
    }
    module["elements"].append(
        {
            "id": "UseCase.tags",
            "kind": "field",
            "nullability": "absent-allowed",
            "cardinality": "many",
            "extensions": {},
            "scalarType": "string",
        }
    )
    return json.dumps(document)


def _policy_world(*, wrapped: bool) -> InMemory:
    world = InMemory()
    world.register(_many_valued_document())
    if wrapped:
        backend = cast(Backend, world.backends["memory"])
        world.arras = Arras.start(
            {
                "memory": PolicyBackend(backend, _allowed),
                "memory_replica": world.backends["memory_replica"],
            },
            admin=world.admin,
            default_placement=Placement("memory", ("memory_replica",)),
        )
    return world


def test_wrapped_import_and_action_keep_native_many_value_shape() -> None:
    plain = _policy_world(wrapped=False)
    wrapped = _policy_world(wrapped=True)
    imported = {
        "type": "UseCase",
        "key": "imported",
        "properties": {"code": "imported", "name": "Imported", "tags": ["a", "b"]},
    }
    plain_import = plain.arras.session(plain.admin).import_records(
        "catalog", [imported], load_id="plain-import"
    )
    wrapped_import = wrapped.arras.session(wrapped.admin).import_records(
        "catalog", [imported], load_id="wrapped-import"
    )
    assert wrapped_import.created == plain_import.created == 1

    member = wrapped.person("member", "catalog", "read", "write")
    ordinary_member = plain.person("member", "catalog", "read", "write")
    plan = Plan(
        "catalog.ManualListWrite",
        (),
        (
            Create(
                Ref("catalog.UseCase", "action"),
                {"name": "Action", "tags": ["x", "y"]},
            ),
        ),
    )
    plain_receipt = plain.backends["memory"].apply(ordinary_member, plan, idempotency_key=None)
    wrapped_receipt = PolicyBackend(cast(Backend, wrapped.backends["memory"]), _allowed).apply(
        member, plan, idempotency_key=None
    )
    assert isinstance(plain_receipt, Receipt) and isinstance(wrapped_receipt, Receipt)
    assert wrapped_receipt.action == plain_receipt.action == "catalog.ManualListWrite"
    assert len(wrapped_receipt.refs) == len(plain_receipt.refs) == 1


class TransactionalAnnotationBackend(RecordingBackend):
    """Neutral synthetic provider; its ledger is test evidence, not native support."""

    policy_annotation_capabilities = PolicyAnnotationCapabilities(
        operations=frozenset(
            {
                "apply",
                "apply_batch",
                "import_records",
                "register",
                "validate_register",
                "attach",
            }
        )
    )

    def __init__(self) -> None:
        super().__init__()
        self.annotation_ledger: list[tuple[str, str, Principal, Mapping[str, str]]] = []
        self.annotation_calls: list[str] = []
        self.idempotency: dict[str, tuple[Mapping[str, str], Receipt]] = {}
        self.annotation_lock = Lock()
        self.fail_before_commit = False
        self.business_state: dict[str, object] = {}
        self.next_group = 0
        self.batch_fail_at: int | None = None

    def apply_with_policy_annotations(
        self, request: PolicyRequest, *, annotations: Mapping[str, str]
    ) -> Receipt | Validation | BatchReceipt | ImportResult | RegistryResult | RegistrationCheck:
        with self.annotation_lock:
            self.annotation_calls.append(request.operation)
            key = request.options.get("idempotency_key")
            if request.operation == "apply" and isinstance(key, str) and key in self.idempotency:
                prior_annotations, prior_result = self.idempotency[key]
                if dict(prior_annotations) != dict(annotations):
                    raise Conflict("idempotency_key_reused")
                return Receipt(
                    prior_result.action,
                    prior_result.refs,
                    prior_result.created,
                    prior_result.updated,
                    prior_result.deleted,
                    prior_result.linked,
                    prior_result.unlinked,
                    prior_result.token,
                    replayed=True,
                    group=prior_result.group,
                )
            result, staged_state, staged_annotations, staged_group = _stage_operation(
                request,
                annotations,
                dict(self.business_state),
                self.next_group,
                batch_fail_at=self.batch_fail_at,
            )
            if (
                request.operation == "apply_batch"
                and request.options["atomic"]
                and self.batch_fail_at is not None
            ):
                self.batch_fail_at = None
            else:
                self.batch_fail_at = None
            if self.fail_before_commit:
                self.fail_before_commit = False
                raise RuntimeError("injected transactional failure")
            # Business state and annotation rows become visible together.
            self.business_state = staged_state
            self.annotation_ledger.extend(staged_annotations)
            self.next_group = staged_group
            if request.operation == "apply" and isinstance(result, Receipt):
                if isinstance(key, str):
                    self.idempotency[key] = (dict(annotations), result)
            return result


AnnotationEntry = tuple[str, str, Principal, Mapping[str, str]]
AnnotationResult = (
    Receipt | Validation | BatchReceipt | ImportResult | RegistryResult | RegistrationCheck
)


def _stage_operation(
    request: PolicyRequest,
    annotations: Mapping[str, str],
    state: dict[str, object],
    next_group: int,
    *,
    batch_fail_at: int | None,
) -> tuple[AnnotationResult, dict[str, object], list[AnnotationEntry], int]:
    if request.operation == "apply_batch":
        return _stage_batch(request, annotations, state, next_group, batch_fail_at)
    if request.operation == "validate_register":
        module = _request_module(request)
        return RegistrationCheck(module.revision, False, current=module), state, [], next_group
    if request.operation == "apply" and request.dry_run:
        return Validation(True, (), (), (), None, None), state, [], next_group
    label = _operation_label(request)
    group = f"g{next_group}"
    state[group] = label
    entry = (group, request.operation, request.principal, dict(annotations))
    result = _result_for_operation(request, group)
    return result, state, [entry], next_group + 1


def _stage_batch(
    request: PolicyRequest,
    annotations: Mapping[str, str],
    state: dict[str, object],
    next_group: int,
    batch_fail_at: int | None,
) -> tuple[AnnotationResult, dict[str, object], list[AnnotationEntry], int]:
    atomic = bool(request.options["atomic"])
    staged_state = dict(state)
    rows: list[AnnotationEntry] = []
    items: list[ItemResult] = []
    if atomic:
        group = f"g{next_group}"
        if batch_fail_at is not None:
            # Effects were staged locally but the single atomic business/audit group is discarded.
            staged_payload = tuple((plan.action, tuple(plan.effects)) for plan in request.plans)
            staged_state[group] = staged_payload
            raise RuntimeError("injected transactional failure")
        staged_payload = tuple((plan.action, tuple(plan.effects)) for plan in request.plans)
        staged_state[group] = staged_payload
        rows.append((group, request.operation, request.principal, dict(annotations)))
        items.extend(
            ItemResult(
                index,
                receipt=Receipt(plan.action, (), 1, 0, 0, 0, 0, "token", group=group),
            )
            for index, plan in enumerate(request.plans)
        )
        return (
            BatchReceipt("batch", True, tuple(items), len(items), 0, "token"),
            staged_state,
            rows,
            next_group + 1,
        )
    succeeded = 0
    failed = 0
    for index, plan in enumerate(request.plans):
        if batch_fail_at == index:
            failed += 1
            items.append(ItemResult(index, refusal=Conflict("injected")))
            continue
        group = f"g{next_group}"
        next_group += 1
        staged_state[group] = (plan.action, tuple(plan.effects))
        rows.append((group, request.operation, request.principal, dict(annotations)))
        items.append(
            ItemResult(index, receipt=Receipt(plan.action, (), 1, 0, 0, 0, 0, "token", group=group))
        )
        succeeded += 1
    result = BatchReceipt("batch", atomic, tuple(items), succeeded, failed, "token")
    return result, staged_state, rows, next_group


def _operation_label(request: PolicyRequest) -> object:
    if request.operation == "apply":
        return request.plans[0].action, tuple(request.plans[0].effects)
    if request.operation == "import_records":
        return "import", tuple(request.records)
    module = _request_module(request)
    if request.operation == "register":
        return "register", request.document, module.revision
    return request.operation, module


def _result_for_operation(request: PolicyRequest, group: str) -> AnnotationResult:
    if request.operation == "apply":
        if request.dry_run:
            return Validation(True, (), (), (), None, None)
        return Receipt(request.plans[0].action, (), 1, 0, 0, 0, 0, "token", group=group)
    if request.operation == "import_records":
        return ImportResult(len(request.records), 0, ())
    module = _request_module(request)
    return RegistryResult(module.name, module.revision, True)


def _request_module(request: PolicyRequest) -> ModuleInfo:
    assert request.module is not None
    return request.module


def _annotated_policy(request: PolicyRequest) -> PolicyDecision:
    return PolicyDecision(True, annotations={"source": request.operation})


@pytest.mark.parametrize(
    "operation",
    ["apply", "apply_batch", "import_records", "register", "validate_register", "attach"],
)
def test_synthetic_atomic_annotation_capability_covers_all_six_writes(
    operation: PolicyOperation,
) -> None:
    backend = TransactionalAnnotationBackend()
    wrapped = PolicyBackend(cast(Backend, backend), _annotated_policy)
    result = _call_one(wrapped, operation)
    assert isinstance(
        result,
        (Receipt, BatchReceipt, ImportResult, RegistryResult, RegistrationCheck),
    )
    assert backend.annotation_calls == [operation]
    if operation == "validate_register":
        assert backend.annotation_ledger == []
    else:
        assert [entry[1] for entry in backend.annotation_ledger] == [operation]
        group, _, principal, saved_annotations = backend.annotation_ledger[0]
        assert group in backend.business_state
        assert principal is USER
        assert saved_annotations == {"source": operation}
    assert backend.calls == []


def test_annotation_capability_dry_run_denial_rollback_and_no_ordinary_fallback() -> None:
    backend = TransactionalAnnotationBackend()
    wrapped = PolicyBackend(cast(Backend, backend), _annotated_policy)
    dry = wrapped.apply(USER, Plan("catalog.a", (), ()), idempotency_key=None, dry_run=True)
    assert isinstance(dry, Validation)
    assert backend.annotation_ledger == []
    assert backend.business_state == {}

    denied = PolicyBackend(
        cast(Backend, backend), lambda request: PolicyDecision(False, annotations={"x": "y"})
    )
    with pytest.raises(Refused):
        denied.apply(USER, Plan("catalog.a", (), ()), idempotency_key="denied")
    assert backend.annotation_ledger == []

    backend.fail_before_commit = True
    with pytest.raises(RuntimeError, match="injected transactional failure"):
        wrapped.apply(USER, Plan("catalog.a", (), ()), idempotency_key="rollback")
    assert backend.annotation_ledger == []
    assert backend.business_state == {}
    assert backend.calls == []

    batch = [Plan("catalog.a", (), ()), Plan("catalog.b", (), ())]
    backend.batch_fail_at = 1
    with pytest.raises(RuntimeError, match="injected transactional failure"):
        wrapped.apply_batch(USER, batch, atomic=True, idempotency_key=None)
    assert backend.business_state == {} and backend.annotation_ledger == []
    backend.batch_fail_at = 1
    partial = wrapped.apply_batch(USER, batch, atomic=False, idempotency_key=None)
    assert partial.succeeded == 1 and partial.failed == 1
    assert len(backend.business_state) == len(backend.annotation_ledger) == 1
    assert backend.annotation_ledger[0][0] in backend.business_state

    ordinary = RecordingBackend()
    unsupported = PolicyBackend(
        cast(Backend, ordinary),
        lambda request: PolicyDecision(True, annotations={"x": "y"}),
    )
    with pytest.raises(Unsupported):
        unsupported.apply(USER, Plan("catalog.a", (), ()), idempotency_key=None)
    assert ordinary.calls == []


@pytest.mark.parametrize(
    "capabilities",
    [object(), PolicyAnnotationCapabilities(operations=frozenset({"attach"}))],
)
def test_malformed_or_unadvertised_annotation_capability_is_unsupported(
    capabilities: object,
) -> None:
    class MalformedProvider(RecordingBackend):
        policy_annotation_capabilities = capabilities

        def apply_with_policy_annotations(
            self, request: PolicyRequest, *, annotations: Mapping[str, str]
        ) -> Receipt:
            raise AssertionError("unqualified method must never be called")

    provider = MalformedProvider()
    with pytest.raises(Unsupported):
        PolicyBackend(cast(Backend, provider), _annotated_policy).apply(
            USER, Plan("catalog.a", (), ()), idempotency_key=None
        )
    assert provider.calls == []


def test_nested_policy_wrapper_does_not_forward_annotation_bypass() -> None:
    provider = TransactionalAnnotationBackend()
    inner = PolicyBackend(cast(Backend, provider), _allowed)
    outer = PolicyBackend(cast(Backend, inner), _annotated_policy)
    with pytest.raises(Unsupported):
        outer.apply(USER, Plan("catalog.a", (), ()), idempotency_key=None)
    assert provider.annotation_calls == [] and provider.calls == []


def test_annotated_idempotency_replay_conflict_and_concurrent_attribution() -> None:
    backend = TransactionalAnnotationBackend()
    wrapped = PolicyBackend(cast(Backend, backend), _annotated_policy)
    plan = Plan("catalog.a", (), ())
    original = wrapped.apply(USER, plan, idempotency_key="same")
    replay = wrapped.apply(USER, plan, idempotency_key="same")
    assert isinstance(original, Receipt) and isinstance(replay, Receipt)
    assert not original.replayed and replay.replayed
    assert len(backend.annotation_ledger) == 1

    changed = PolicyBackend(
        cast(Backend, backend),
        lambda request: PolicyDecision(True, annotations={"source": "other"}),
    )
    with pytest.raises(Conflict):
        changed.apply(USER, plan, idempotency_key="same")
    assert len(backend.annotation_ledger) == 1

    revoked = PolicyBackend(
        cast(Backend, backend), lambda request: PolicyDecision(False, code="revoked")
    )
    with pytest.raises(PolicyRefused) as denied_replay:
        revoked.apply(USER, plan, idempotency_key="same")
    assert denied_replay.value.policy_code == "revoked"
    assert len(backend.annotation_ledger) == 1

    principals = [Principal("person", f"token-{index}") for index in range(12)]

    def write(index: int) -> Receipt | Validation:
        who = principals[index]
        return PolicyBackend(
            cast(Backend, backend),
            lambda request: PolicyDecision(True, annotations={"source": f"group_{index}"}),
        ).apply(who, plan, idempotency_key=f"group-{index}")

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(write, range(len(principals))))
    assert all(isinstance(result, Receipt) for result in results)
    concurrent = backend.annotation_ledger[1:]
    assert {(principal, annotations["source"]) for _, _, principal, annotations in concurrent} == {
        (principal, f"group_{index}") for index, principal in enumerate(principals)
    }
    assert len({group for group, _, _, _ in concurrent}) == len(principals)


def test_successful_validation_does_not_authorize_later_apply() -> None:
    backend = TransactionalAnnotationBackend()
    observed: list[str] = []

    def policy(request: PolicyRequest) -> PolicyDecision:
        observed.append(request.operation)
        return PolicyDecision(
            request.operation == "validate_register", annotations={"check": "yes"}
        )

    wrapped = PolicyBackend(cast(Backend, backend), policy)
    validated = wrapped.validate_register(USER, b"raw-document", MODULE, unknown_endpoint="reject")
    assert isinstance(validated, RegistrationCheck)
    assert backend.business_state == {} and backend.annotation_ledger == []
    with pytest.raises(PolicyRefused):
        wrapped.apply(USER, Plan("catalog.a", (), ()), idempotency_key="after-validation")
    assert observed == ["validate_register", "apply"]
    assert backend.business_state == {} and backend.annotation_ledger == []


def test_synthetic_transaction_persists_exact_controlled_payloads_with_annotations() -> None:
    backend = TransactionalAnnotationBackend()
    wrapped = PolicyBackend(cast(Backend, backend), _annotated_policy)
    plan = Plan(
        "catalog.create",
        (),
        (Create(Ref("catalog.UseCase", "controlled"), {"name": "Controlled", "tags": ["a", "b"]}),),
    )
    wrapped.apply(USER, plan, idempotency_key="payload")
    group, operation, principal, annotations = backend.annotation_ledger[0]
    assert operation == "apply" and principal is USER
    assert annotations == {"source": "apply"}
    stored_plan = cast(tuple[str, tuple[object, ...]], backend.business_state[group])
    assert stored_plan[0] == "catalog.create"
    effect = cast(Create, stored_plan[1][0])
    assert effect.ref == Ref("catalog.UseCase", "controlled")
    assert effect.properties["name"] == "Controlled"
    assert tuple(cast(Sequence[object], effect.properties["tags"])) == ("a", "b")

    records = [{"type": "UseCase", "key": "imported", "properties": {"name": "Imported"}}]
    wrapped.import_records(USER, "catalog", records, load_id="load-exact", initiated_by="person")
    import_group, import_operation, import_principal, import_annotations = (
        backend.annotation_ledger[-1]
    )
    assert import_operation == "import_records" and import_principal is USER
    assert backend.business_state[import_group] == (
        "import",
        ({"type": "UseCase", "key": "imported", "properties": {"name": "Imported"}},),
    )
    assert import_annotations == {"source": "import_records"}

    wrapped.register(USER, b"raw-document-bytes", MODULE, unknown_endpoint="reject")
    register_group, register_operation, register_principal, register_annotations = (
        backend.annotation_ledger[-1]
    )
    assert register_operation == "register" and register_principal is USER
    assert backend.business_state[register_group] == (
        "register",
        b"raw-document-bytes",
        MODULE.revision,
    )
    assert register_annotations == {"source": "register"}

    wrapped.attach(USER, MODULE)
    attach_group, attach_operation, attach_principal, attach_annotations = (
        backend.annotation_ledger[-1]
    )
    assert attach_operation == "attach" and attach_principal is USER
    assert backend.business_state[attach_group] == ("attach", MODULE)
    assert attach_annotations == {"source": "attach"}


def test_annotation_transaction_failure_leaves_full_prior_snapshot_unchanged() -> None:
    backend = TransactionalAnnotationBackend()
    wrapped = PolicyBackend(cast(Backend, backend), _annotated_policy)
    wrapped.apply(USER, Plan("catalog.before", (), ()), idempotency_key="before")
    prior_state = dict(backend.business_state)
    prior_ledger = list(backend.annotation_ledger)
    backend.fail_before_commit = True
    effect_plan = Plan(
        "catalog.create",
        (),
        (Create(Ref("catalog.UseCase", "staged"), {"name": "Staged"}),),
    )
    with pytest.raises(RuntimeError, match="injected transactional failure"):
        wrapped.apply(USER, effect_plan, idempotency_key="staged")
    assert backend.business_state == prior_state
    assert backend.annotation_ledger == prior_ledger


def test_atomic_batch_has_one_business_and_annotation_group() -> None:
    backend = TransactionalAnnotationBackend()
    wrapped = PolicyBackend(cast(Backend, backend), _annotated_policy)
    plans = [
        Plan(
            "catalog.create",
            (),
            (Create(Ref("catalog.UseCase", f"batch-{index}"), {"name": f"Batch {index}"}),),
        )
        for index in range(2)
    ]
    result = wrapped.apply_batch(USER, plans, atomic=True, idempotency_key="atomic")
    assert result.succeeded == 2 and result.failed == 0
    receipt_groups = {item.receipt.group for item in result.items if item.receipt is not None}
    assert len(receipt_groups) == 1
    group = next(iter(receipt_groups))
    assert list(backend.business_state) == [group]
    assert len(backend.annotation_ledger) == 1
    assert backend.annotation_ledger[0][0] == group
    saved_actions = backend.business_state[group]
    assert saved_actions == tuple((plan.action, tuple(plan.effects)) for plan in plans)
