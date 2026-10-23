# SPDX-License-Identifier: MIT OR Apache-2.0
"""Host profile selection, source dispatch and qualification preflight."""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from _pytest.monkeypatch import MonkeyPatch

from arras import Arras, Invalid, Principal, Refused
from arras.errors import Unsupported
from arras.fakes import FakeAccess, MemoryStore
from arras.model import MetadataProfile, ModuleInfo, Placement
from arras.registration import host_violations, placed
from arras.results import BackendInfo
from arras.schema_admin import Schema
from arras.types import Revision

CORE_PROFILE: MetadataProfile = "umf-core-metadata/1"
PROFILE_FIXTURE = Path(__file__).parent / "fixtures/umf-core-metadata/primary-string-record.json"


def require_umf() -> None:
    if importlib.util.find_spec("umf") is None:
        if os.environ.get("ARRAS_REQUIRE_UMF") == "1":
            pytest.fail("ARRAS_REQUIRE_UMF=1 but the official UMF engine is missing")
        pytest.skip("profile source dispatch requires the explicitly selected arras[umf] extra")


class BackendStub:
    def __init__(self, descriptor: object) -> None:
        self.descriptor = descriptor
        self.describes = 0
        self.validate_calls = 0

    def describe(self) -> object:
        self.describes += 1
        return self.descriptor

    def validate_register(self, *args: Any, **kwargs: Any) -> None:
        self.validate_calls += 1


class DescriptorStub:
    reads = True
    provides = True

    def __init__(self, metadata_profiles: object) -> None:
        self.metadata_profiles = metadata_profiles


class QualifiedMemory:
    """Test double descriptor opt-in; the production memory adapter is not qualified here."""

    def __init__(self, store: MemoryStore, profiles: tuple[str, ...]) -> None:
        self.store = store
        self.profiles = profiles

    def describe(self):
        return replace(self.store.describe(), metadata_profiles=self.profiles)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.store, name)


def module(profile: MetadataProfile, placement: Placement) -> ModuleInfo:
    return ModuleInfo("catalog", placement, Revision(), (), metadata_profile=profile)


def memory_host(*, qualified: bool, person_has_schema: bool = True):
    access = FakeAccess()
    admin = access.grant("root", "m", "read", "write", "schema", admin=True)
    person = access.grant("alice", "m", "read", *(("schema",) if person_has_schema else ()))
    store = MemoryStore(access, "store")
    profiles = ("legacy-arras/1", CORE_PROFILE) if qualified else ("legacy-arras/1",)
    backend = QualifiedMemory(store, profiles)
    host = Arras.start(
        cast(Any, {"store": backend}),
        admin=admin,
        default_placement=Placement("store"),
        metadata_profile=CORE_PROFILE,
    )
    return host, store, admin, person


@pytest.mark.parametrize("bad", [None, 0, [], {}, "umf-core-metadata", "other"])
def test_unknown_or_nonstring_profile_fails_before_backend_mapping_access(bad: object) -> None:
    class Untouched:
        def __iter__(self):
            raise AssertionError("invalid profile was checked after backend access")

    with pytest.raises(ValueError, match="unknown metadata profile"):
        Arras(cast(Any, Untouched()), metadata_profile=cast(Any, bad))
    with pytest.raises(ValueError, match="unknown metadata profile"):
        Arras.start(cast(Any, Untouched()), metadata_profile=cast(Any, bad))


def test_profile_is_keyword_only_and_start_passes_it_through() -> None:
    for method in (Arras.__init__, Arras.start):
        parameter = inspect.signature(method).parameters["metadata_profile"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default == "legacy-arras/1"
    assert Arras.start({}, metadata_profile=CORE_PROFILE).metadata_profile == CORE_PROFILE
    assert Arras({}).metadata_profile == "legacy-arras/1"


def test_selected_profile_projects_source_and_keeps_original_bytes() -> None:
    require_umf()
    source = PROFILE_FIXTURE.read_bytes()
    host = Arras({}, default_placement=Placement("store"), metadata_profile=CORE_PROFILE)

    raw, projected = placed(host, source)

    assert raw == source
    assert hashlib.sha256(raw).digest() == hashlib.sha256(source).digest()
    assert projected.name == "m"
    assert projected.entity_types[0].name == "m.Order"
    assert projected.metadata_profile == CORE_PROFILE
    assert projected.placement == Placement("store")


def test_selected_profile_passes_text_through_strict_source_boundary() -> None:
    require_umf()
    host = Arras({}, default_placement=Placement("store"), metadata_profile=CORE_PROFILE)
    text = PROFILE_FIXTURE.read_text(encoding="utf-8")

    raw, projected = placed(host, text)

    assert raw == text.encode("utf-8")
    assert projected.name == "m"


def test_selected_profile_rejects_str_subclass_before_custom_encoding() -> None:
    require_umf()
    host = Arras({}, metadata_profile=CORE_PROFILE)

    class EncodableStr(str):
        def encode(self, *_args: Any, **_kwargs: Any) -> bytes:
            return PROFILE_FIXTURE.read_bytes()

    with pytest.raises(TypeError, match="document must be bytes or str"):
        placed(host, EncodableStr("ignored"))


def test_legacy_profile_does_not_auto_detect_the_core_document() -> None:
    host = Arras({}, default_placement=Placement("store"))

    with pytest.raises(Invalid):
        placed(host, PROFILE_FIXTURE.read_bytes())


def test_selected_profile_converts_projection_refusal_without_legacy_fallback() -> None:
    require_umf()
    host = Arras({}, metadata_profile=CORE_PROFILE)

    with pytest.raises(Invalid) as error:
        placed(host, b"not a UMF document")

    assert [(item.path, item.code) for item in error.value.violations] == [
        ("document", "incomplete_interpretation")
    ]


def test_profile_dispatch_does_not_fall_back_when_optional_engine_is_missing(
    monkeypatch: MonkeyPatch,
) -> None:
    host = Arras({}, metadata_profile=CORE_PROFILE)

    def legacy_parser_must_not_run(_source: bytes) -> ModuleInfo:
        raise AssertionError("selected profile fell back to the legacy parser")

    monkeypatch.setattr("arras.registration.parse_module", legacy_parser_must_not_run)

    def missing_engine(_name: str) -> object:
        raise ModuleNotFoundError("No module named 'umf'", name="umf")

    monkeypatch.setattr("arras._umf_engine.import_module", missing_engine)
    with pytest.raises(Unsupported, match="official UMF admission"):
        placed(host, PROFILE_FIXTURE.read_bytes())


def test_registry_authorization_precedes_profile_source_admission(monkeypatch: MonkeyPatch) -> None:
    host, _store, _admin, person = memory_host(qualified=True)

    def admission_must_not_run(_source: bytes) -> object:
        raise AssertionError("source admission ran before administrator authorization")

    monkeypatch.setattr("arras.umf_admission.project_document", admission_must_not_run)
    with pytest.raises(Refused):
        host.session(person).registry().register(b"not parsed")


def test_registry_registers_projected_source_only_with_explicit_descriptor_optin() -> None:
    require_umf()
    host, store, admin, _person = memory_host(qualified=True)
    source = PROFILE_FIXTURE.read_bytes()

    result = host.session(admin).registry().register(source)

    assert result.module == "m" and result.changed
    assert store.documents["m"] == source
    assert store.modules["m"].metadata_profile == CORE_PROFILE


def test_person_schema_validate_uses_projected_source_after_qualification() -> None:
    require_umf()
    host, _store, _admin, person = memory_host(qualified=True)

    plan = host.session(person).schema().validate(PROFILE_FIXTURE.read_bytes())

    assert plan.module == "m" and plan.ok


def test_registry_refuses_unqualified_profile_before_provider_acceptance() -> None:
    require_umf()
    host, store, admin, _person = memory_host(qualified=False)
    calls = 0
    real_register = store.register

    def spy_register(*args: Any, **kwargs: Any):
        nonlocal calls
        calls += 1
        return real_register(*args, **kwargs)

    store.register = spy_register  # type: ignore[method-assign]
    with pytest.raises(Invalid) as error:
        host.session(admin).registry().register(PROFILE_FIXTURE.read_bytes())

    assert [(item.path, item.code) for item in error.value.violations] == [
        ("placement", "invalid_placement")
    ]
    assert calls == 0 and store.modules == {}


def test_schema_keeps_provider_refusal_first_after_profile_qualification() -> None:
    require_umf()
    host, _store, _admin, person = memory_host(qualified=True, person_has_schema=False)

    with pytest.raises(Refused):
        host.session(person).schema().validate(PROFILE_FIXTURE.read_bytes())


@pytest.mark.parametrize(
    "advertised",
    [
        None,
        "umf-core-metadata/1",
        ["umf-core-metadata/1"],
        {"umf-core-metadata/1": True},
        ("umf-core-metadata/1", 1),
    ],
)
def test_qualification_rejects_missing_or_malformed_descriptor_optin(advertised: object) -> None:
    backend = BackendStub(DescriptorStub(advertised))
    host = SimpleNamespace(backends={"store": backend})

    violations = host_violations(cast(Any, host), module(CORE_PROFILE, Placement("store")), ())

    assert [(v.path, v.code) for v in violations] == [("placement", "invalid_placement")]
    assert "does not qualify" in violations[0].message


def test_qualification_requires_exact_profile_string_but_allows_other_declared_profiles() -> None:
    for profiles in (("legacy-arras/1", CORE_PROFILE), (CORE_PROFILE,)):
        host = SimpleNamespace(
            backends={
                "store": BackendStub(
                    BackendInfo("store", ("reader", "provider"), metadata_profiles=profiles)
                )
            }
        )
        assert host_violations(cast(Any, host), module(CORE_PROFILE, Placement("store")), ()) == []

    legacy = BackendStub(BackendInfo("store", ("reader", "provider")))
    legacy_host = SimpleNamespace(backends={"store": legacy})
    assert (
        host_violations(cast(Any, legacy_host), module("legacy-arras/1", Placement("store")), ())
        == []
    )
    assert legacy.describes == 1  # the existing reader-role check only; no profile probe is added


def test_schema_checks_record_and_replica_profiles_before_provider_dry_run(
    monkeypatch: MonkeyPatch,
) -> None:
    store = BackendStub(BackendInfo("store", ("provider",), metadata_profiles=(CORE_PROFILE,)))
    replica = BackendStub(BackendInfo("replica", ("reader",)))

    def placement_of(_name: str) -> Placement:
        return Placement("store", ("replica",))

    host = SimpleNamespace(
        backends={"store": store, "replica": replica},
        placement_of=placement_of,
    )
    principal = Principal("person", "token")

    def allow_user(_op: str) -> None:
        return None

    ontology = SimpleNamespace(h=host, principal=principal, require_user=allow_user)

    def fake_placed(_host: object, _document: bytes) -> tuple[bytes, ModuleInfo]:
        return b"fixture", module(CORE_PROFILE, Placement("store", ("replica",)))

    monkeypatch.setattr(
        "arras.schema_admin.placed",
        fake_placed,
    )

    with pytest.raises(Invalid) as error:
        Schema(cast(Any, ontology)).validate(b"fixture")

    assert [(v.path, v.code) for v in error.value.violations] == [
        ("placement", "invalid_placement")
    ]
    assert store.validate_calls == 0


def test_schema_missing_replica_refuses_before_provider_dry_run(monkeypatch: MonkeyPatch) -> None:
    store = BackendStub(BackendInfo("store", ("provider",), metadata_profiles=(CORE_PROFILE,)))
    host = SimpleNamespace(backends={"store": store})

    def allow_user(_op: str) -> None:
        return None

    ontology = SimpleNamespace(
        h=host,
        principal=Principal("person", "token"),
        require_user=allow_user,
    )

    def fake_placed(_host: object, _document: bytes) -> tuple[bytes, ModuleInfo]:
        return b"fixture", module(CORE_PROFILE, Placement("store", ("missing",)))

    monkeypatch.setattr("arras.schema_admin.placed", fake_placed)

    with pytest.raises(Invalid) as error:
        Schema(cast(Any, ontology)).validate(b"fixture")

    assert [(v.path, v.code) for v in error.value.violations] == [
        ("placement", "invalid_placement")
    ]
    assert "not configured" in error.value.violations[0].message
    assert store.validate_calls == 0


def test_schema_person_authorization_still_precedes_document_parsing(
    monkeypatch: MonkeyPatch,
) -> None:
    def denied(op: str) -> None:
        raise Refused("arras", op)

    ontology = SimpleNamespace(
        h=object(), principal=Principal("person", "token"), require_user=denied
    )

    def parsing_must_not_run(*_args: object, **_kwargs: object) -> Any:
        pytest.fail("document parsing preceded person authorization")

    monkeypatch.setattr(
        "arras.schema_admin.placed",
        parsing_must_not_run,
    )
    with pytest.raises(Refused):
        Schema(cast(Any, ontology)).validate(b"not parsed")
