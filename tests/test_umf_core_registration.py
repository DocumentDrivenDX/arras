# SPDX-License-Identifier: MIT OR Apache-2.0
"""Host profile selection and reader qualification preflight, isolated from projection dispatch."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any, cast

import pytest
from _pytest.monkeypatch import MonkeyPatch

from arras import Arras, Invalid, Principal, Refused
from arras.model import MetadataProfile, ModuleInfo, Placement
from arras.registration import host_violations
from arras.results import BackendInfo
from arras.schema_admin import Schema
from arras.types import Revision

CORE_PROFILE: MetadataProfile = "umf-core-metadata/1"


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


def module(profile: MetadataProfile, placement: Placement) -> ModuleInfo:
    return ModuleInfo("catalog", placement, Revision(), (), metadata_profile=profile)


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
