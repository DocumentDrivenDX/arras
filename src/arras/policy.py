# SPDX-License-Identifier: MIT OR Apache-2.0
"""Opt-in host write policy at the backend boundary (CONTRACT-005, EX-04)."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Literal, Protocol, cast, overload

from arras.actions import Plan
from arras.backend import Backend, Provider
from arras.errors import PolicyRefused, Unsupported
from arras.model import ModuleInfo
from arras.results import (
    Answer,
    BackendInfo,
    BackendStatus,
    BatchReceipt,
    ImportResult,
    Receipt,
    RegistrationCheck,
    RegistryResult,
    Validation,
)
from arras.searchplan import TextMatch
from arras.types import Principal, Revision, Statement

PolicyOperation = Literal[
    "apply",
    "apply_batch",
    "import_records",
    "register",
    "validate_register",
    "attach",
]
_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_MAX_ANNOTATIONS = 32
_MAX_ANNOTATION_VALUE_BYTES = 1024
_MAX_ANNOTATION_BYTES = 16 * 1024


class _FrozenList(Sequence[object]):
    """Tuple-backed immutable marker retaining the source list's container kind."""

    __slots__ = ("_items",)
    _items: tuple[object, ...]

    def __init__(self, values: Sequence[object]) -> None:
        object.__setattr__(self, "_items", tuple(values))

    @overload
    def __getitem__(self, index: int) -> object: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[object, ...]: ...

    def __getitem__(self, index: int | slice) -> object | tuple[object, ...]:
        return self._items[index]

    def __len__(self) -> int:
        return len(self._items)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("frozen list snapshot is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("frozen list snapshot is immutable")


class WritePolicy(Protocol):
    """A trusted host callback that may narrow a person's write authority."""

    def __call__(self, request: PolicyRequest) -> PolicyDecision: ...


@dataclass(frozen=True, slots=True)
class PolicyAnnotationCapabilities:
    """Explicit versioned operations a backend can persist with policy annotations."""

    version: int = 1
    operations: frozenset[PolicyOperation] = frozenset()

    def __post_init__(self) -> None:
        known: frozenset[str] = frozenset(
            {"apply", "apply_batch", "import_records", "register", "validate_register", "attach"}
        )
        if type(self.version) is not int or self.version != 1:
            raise ValueError("annotation capability version must be integer 1")
        try:
            copied = frozenset(self.operations)
        except TypeError:
            raise ValueError("annotation operations must be a set of known operations") from None
        if any(type(operation) is not str or operation not in known for operation in copied):
            raise ValueError("annotation operations must be known operations")
        object.__setattr__(self, "operations", copied)


class PolicyAnnotationProvider(Protocol):
    """Optional atomic annotation write entrypoint; never inferred from ordinary writes."""

    @property
    def policy_annotation_capabilities(self) -> PolicyAnnotationCapabilities: ...

    def apply_with_policy_annotations(
        self,
        request: PolicyRequest,
        *,
        annotations: Mapping[str, str],
    ) -> (
        Receipt | Validation | BatchReceipt | ImportResult | RegistryResult | RegistrationCheck
    ): ...


class PolicyRequest:
    """Immutable, value-preserving snapshot of one provider mutation request."""

    principal: Principal
    operation: PolicyOperation
    modules: tuple[str, ...]
    dry_run: bool
    plans: tuple[Plan, ...]
    records: tuple[Mapping[str, object], ...]
    document: bytes | None
    module: ModuleInfo | None
    options: Mapping[str, object]

    __slots__ = (
        "principal",
        "operation",
        "modules",
        "dry_run",
        "plans",
        "records",
        "document",
        "module",
        "options",
        "_frozen",
    )

    def __init__(
        self,
        principal: Principal,
        operation: PolicyOperation,
        modules: tuple[str, ...],
        *,
        dry_run: bool = False,
        plans: tuple[Plan, ...] = (),
        records: tuple[Mapping[str, object], ...] = (),
        document: bytes | None = None,
        module: ModuleInfo | None = None,
        options: Mapping[str, object] | None = None,
    ) -> None:
        object.__setattr__(self, "principal", principal)
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "modules", tuple(modules))
        object.__setattr__(self, "dry_run", dry_run)
        object.__setattr__(self, "plans", tuple(_snapshot(plan) for plan in plans))
        object.__setattr__(self, "records", tuple(_snapshot(record) for record in records))
        object.__setattr__(self, "document", document)
        object.__setattr__(self, "module", _snapshot(module) if module is not None else None)
        object.__setattr__(self, "options", _snapshot(options or {}))
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_frozen", False):
            raise AttributeError("PolicyRequest is immutable")
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if getattr(self, "_frozen", False):
            raise AttributeError("PolicyRequest is immutable")
        object.__delattr__(self, name)

    def __repr__(self) -> str:
        return (
            f"PolicyRequest(operation={self.operation!r}, modules={self.modules!r}, "
            f"dry_run={self.dry_run!r}, payload=<redacted>)"
        )


class PolicyDecision:
    """Validated immutable policy result."""

    allowed: bool
    code: str
    annotations: Mapping[str, str]

    __slots__ = ("allowed", "code", "annotations", "_frozen")

    def __init__(
        self,
        allowed: bool,
        *,
        code: str = "policy",
        annotations: Mapping[str, str] | None = None,
    ) -> None:
        if type(allowed) is not bool:
            raise TypeError("allowed must be bool")
        if type(code) is not str or _CODE.fullmatch(code) is None:
            raise ValueError("code must be a stable identifier")
        raw_annotations: object = cast(object, annotations) if annotations is not None else {}
        if not isinstance(raw_annotations, Mapping):
            raise TypeError("annotations must be a mapping")
        copied: dict[str, str] = {}
        for raw_key, raw_value in cast(Mapping[object, object], raw_annotations).items():
            if not isinstance(raw_key, str) or not isinstance(raw_value, str):
                raise TypeError("annotation keys and values must be text")
            copied[raw_key] = raw_value
        if len(copied) > _MAX_ANNOTATIONS:
            raise ValueError("too many annotations")
        total = 0
        for key, value in copied.items():
            if _CODE.fullmatch(key) is None:
                raise ValueError("annotation keys must be stable identifiers")
            key_size, value_size = len(key.encode("utf-8")), len(value.encode("utf-8"))
            if value_size > _MAX_ANNOTATION_VALUE_BYTES:
                raise ValueError("annotation value is too large")
            total += key_size + value_size
        if total > _MAX_ANNOTATION_BYTES:
            raise ValueError("annotations are too large")
        object.__setattr__(self, "allowed", allowed)
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "annotations", MappingProxyType(copied))
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_frozen", False):
            raise AttributeError("PolicyDecision is immutable")
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if getattr(self, "_frozen", False):
            raise AttributeError("PolicyDecision is immutable")
        object.__delattr__(self, name)

    def __repr__(self) -> str:
        return (
            f"PolicyDecision(allowed={self.allowed!r}, code={self.code!r}, "
            f"annotation_count={len(self.annotations)})"
        )


def _snapshot(value: object) -> object:
    """Copy and recursively freeze supported protocol values without JSON coercion."""
    if isinstance(value, _FrozenList):
        return _FrozenList(tuple(_snapshot(item) for item in value))
    if isinstance(value, Mapping):
        source = cast(Mapping[object, object], value)
        copied: dict[object, object] = {}
        for key, item in source.items():
            copied[key] = _snapshot(item)
        return MappingProxyType(copied)
    if isinstance(value, list):
        return _FrozenList(tuple(_snapshot(item) for item in cast(Sequence[object], value)))
    if isinstance(value, tuple):
        return tuple(_snapshot(item) for item in cast(Sequence[object], value))
    if isinstance(value, set | frozenset):
        return frozenset(_snapshot(item) for item in cast(Sequence[object], value))
    if is_dataclass(value) and not isinstance(value, type):
        return replace(value, **{f.name: _snapshot(getattr(value, f.name)) for f in fields(value)})
    if isinstance(
        value,
        str | bytes | int | float | bool | type(None) | Decimal | date | datetime,
    ):
        return value
    raise TypeError("unsupported mutable value in policy request")


def _native(value: object) -> object:
    """Rebuild an isolated provider-shaped copy from the immutable approved snapshot."""
    if isinstance(value, _FrozenList):
        return [_native(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _native(item) for key, item in cast(Mapping[object, object], value).items()}
    if isinstance(value, tuple):
        return tuple(_native(item) for item in cast(tuple[object, ...], value))
    if isinstance(value, frozenset):
        return {_native(item) for item in cast(Iterable[object], value)}
    if is_dataclass(value) and not isinstance(value, type):
        return replace(value, **{f.name: _native(getattr(value, f.name)) for f in fields(value)})
    return value


def _modules(plans: Sequence[Plan]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for plan in plans:
        name = plan.action.split(".", 1)[0]
        if name not in seen:
            seen.add(name)
            out.append(name)
    return tuple(out)


class PolicyBackend:
    """Wrap a backend and evaluate current host policy before each write."""

    def __init__(self, backend: Backend, policy: WritePolicy) -> None:
        self._backend = backend
        self._policy = policy

    def __getattr__(self, name: str) -> Any:
        # Annotation dispatch must be explicit; never expose the wrapped provider's bypass path.
        if name in {"policy_annotation_capabilities", "apply_with_policy_annotations"}:
            raise AttributeError(name)
        # Expose optional adapter capabilities (for example migrate) only when present underneath.
        return getattr(self._backend, name)

    def _refuse(
        self, operation: PolicyOperation, policy_code: str = "policy_error"
    ) -> PolicyRefused:
        try:
            name = self._backend.describe().name
        except Exception:
            name = "arras"
        return PolicyRefused(name, operation, policy_code)

    def _authorize(self, request: PolicyRequest) -> PolicyDecision:
        try:
            callback = cast(Callable[[PolicyRequest], object], self._policy)
            decision: object = callback(request)
        except Exception:
            raise self._refuse(request.operation) from None
        if not isinstance(decision, PolicyDecision):
            raise self._refuse(request.operation)
        if not decision.allowed:
            raise self._refuse(request.operation, decision.code)
        return decision

    def _annotated(
        self, request: PolicyRequest, decision: PolicyDecision
    ) -> Receipt | Validation | BatchReceipt | ImportResult | RegistryResult | RegistrationCheck:
        unsupported = Unsupported(
            "policy annotations", ["a provider advertising the requested operation at version 1"]
        )
        try:
            provider = cast(PolicyAnnotationProvider, self._backend)
            capabilities = provider.policy_annotation_capabilities
            entrypoint = provider.apply_with_policy_annotations
        except Exception:
            raise unsupported from None
        if (
            type(capabilities) is not PolicyAnnotationCapabilities
            or capabilities.version != 1
            or request.operation not in capabilities.operations
            or not callable(entrypoint)
        ):
            raise unsupported
        # The callback saw the immutable request; pass that same approved value and
        # the decision's copied immutable annotations to the single explicit entrypoint.
        result = entrypoint(request, annotations=decision.annotations)
        expected: dict[str, type[object]] = {
            "apply": Receipt if not request.dry_run else Validation,
            "apply_batch": BatchReceipt,
            "import_records": ImportResult,
            "register": RegistryResult,
            "validate_register": RegistrationCheck,
            "attach": RegistryResult,
        }
        result_type = expected[request.operation]
        if not isinstance(result, result_type):
            raise TypeError("annotation provider returned an invalid operation result")
        return result

    def describe(self) -> BackendInfo:
        return self._backend.describe()

    def catalog(self, principal: Principal) -> Mapping[str, ModuleInfo]:
        return self._backend.catalog(principal)

    def status(self) -> BackendStatus:
        return self._backend.status()

    def query(
        self,
        principal: Principal,
        module: str,
        statement: Statement,
        *,
        limit: int,
        text: TextMatch | None = None,
    ) -> Answer:
        return self._backend.query(principal, module, statement, limit=limit, text=text)

    def reached(self, principal: Principal, token: str) -> bool:
        return self._backend.reached(principal, token)

    def attach(self, principal: Principal, module: ModuleInfo) -> RegistryResult:
        snapshot = cast(ModuleInfo, _snapshot(module))
        request = PolicyRequest(principal, "attach", (snapshot.name,), module=snapshot)
        decision = self._authorize(request)
        if decision.annotations:
            return cast(RegistryResult, self._annotated(request, decision))
        return self._backend.attach(principal, cast(ModuleInfo, _native(request.module)))

    def apply(
        self,
        principal: Principal,
        plan: Plan,
        *,
        idempotency_key: str | None,
        dry_run: bool = False,
    ) -> Receipt | Validation:
        snapshot = cast(Plan, _snapshot(plan))
        request = PolicyRequest(
            principal,
            "apply",
            _modules((snapshot,)),
            dry_run=dry_run,
            plans=(snapshot,),
            options={"idempotency_key": idempotency_key},
        )
        decision = self._authorize(request)
        if decision.annotations:
            return cast(Receipt | Validation, self._annotated(request, decision))
        return cast(Provider, self._backend).apply(
            principal,
            cast(Plan, _native(request.plans[0])),
            idempotency_key=idempotency_key,
            dry_run=dry_run,
        )

    def apply_batch(
        self,
        principal: Principal,
        plans: Sequence[Plan],
        *,
        atomic: bool,
        idempotency_key: str | None,
        stop_on_error: bool = False,
    ) -> BatchReceipt:
        snapshot = cast(tuple[Plan, ...], _snapshot(tuple(plans)))
        request = PolicyRequest(
            principal,
            "apply_batch",
            _modules(snapshot),
            plans=snapshot,
            options={
                "atomic": atomic,
                "idempotency_key": idempotency_key,
                "stop_on_error": stop_on_error,
            },
        )
        decision = self._authorize(request)
        if decision.annotations:
            return cast(BatchReceipt, self._annotated(request, decision))
        return cast(Provider, self._backend).apply_batch(
            principal,
            cast(Sequence[Plan], _native(request.plans)),
            atomic=atomic,
            idempotency_key=idempotency_key,
            stop_on_error=stop_on_error,
        )

    def import_records(
        self,
        principal: Principal,
        module: str,
        records: Sequence[Mapping[str, object]],
        *,
        load_id: str,
        initiated_by: str,
    ) -> ImportResult:
        request = PolicyRequest(
            principal,
            "import_records",
            (module,),
            records=tuple(records),
            options={"load_id": load_id, "initiated_by": initiated_by},
        )
        decision = self._authorize(request)
        if decision.annotations:
            return cast(ImportResult, self._annotated(request, decision))
        return cast(Provider, self._backend).import_records(
            principal,
            module,
            cast(Sequence[Mapping[str, object]], _native(request.records)),
            load_id=load_id,
            initiated_by=initiated_by,
        )

    def register(
        self,
        principal: Principal,
        document: bytes,
        module: ModuleInfo,
        *,
        unknown_endpoint: str,
        expected_revision: Revision | None = None,
    ) -> RegistryResult:
        snapshot = cast(ModuleInfo, _snapshot(module))
        request = PolicyRequest(
            principal,
            "register",
            (snapshot.name,),
            document=bytes(document),
            module=snapshot,
            options={"unknown_endpoint": unknown_endpoint, "expected_revision": expected_revision},
        )
        decision = self._authorize(request)
        if decision.annotations:
            return cast(RegistryResult, self._annotated(request, decision))
        return cast(Provider, self._backend).register(
            principal,
            cast(bytes, request.document),
            cast(ModuleInfo, _native(request.module)),
            unknown_endpoint=unknown_endpoint,
            expected_revision=cast(Revision | None, _native(request.options["expected_revision"])),
        )

    def validate_register(
        self,
        principal: Principal,
        document: bytes,
        module: ModuleInfo,
        *,
        unknown_endpoint: str,
    ) -> RegistrationCheck:
        snapshot = cast(ModuleInfo, _snapshot(module))
        request = PolicyRequest(
            principal,
            "validate_register",
            (snapshot.name,),
            dry_run=True,
            document=bytes(document),
            module=snapshot,
            options={"unknown_endpoint": unknown_endpoint},
        )
        decision = self._authorize(request)
        if decision.annotations:
            return cast(RegistrationCheck, self._annotated(request, decision))
        return cast(Provider, self._backend).validate_register(
            principal,
            cast(bytes, request.document),
            cast(ModuleInfo, _native(request.module)),
            unknown_endpoint=unknown_endpoint,
        )


__all__ = [
    "PolicyBackend",
    "PolicyRequest",
    "PolicyDecision",
    "PolicyOperation",
    "WritePolicy",
    "PolicyAnnotationCapabilities",
    "PolicyAnnotationProvider",
    "PolicyRefused",
]
