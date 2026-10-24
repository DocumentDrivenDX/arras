# SPDX-License-Identifier: MIT OR Apache-2.0
"""Leaf model declarations for explicit metadata interpretation profiles."""

from __future__ import annotations

from dataclasses import fields, replace
from typing import get_args

import pytest

from arras import Invalid
from arras.compat import check
from arras.model import ActionProfile, MetadataProfile, ModuleInfo, Placement
from arras.results import BackendInfo
from arras.types import Revision


class EmptyStats:
    def count(self, type_name: str) -> int:
        return 0

    def missing(self, type_name: str, prop: str) -> list[str]:
        return []


def test_profile_types_and_defaulted_fields_preserve_positional_construction() -> None:
    assert get_args(MetadataProfile) == ("legacy-arras/1", "umf-core-metadata/1", "arras-umf-set/1")
    assert get_args(ActionProfile) == ("arras-umf-set/1",)
    module = ModuleInfo("catalog", Placement("store"), Revision(), (), (), (), (), {})
    backend = BackendInfo("store", ("reader",), {}, None, True)

    assert module.metadata_profile == "legacy-arras/1"
    assert backend.metadata_profiles == ("legacy-arras/1",)
    assert backend.action_profiles == ()
    assert [field.name for field in fields(ModuleInfo)][-1] == "metadata_profile"
    assert [field.name for field in fields(BackendInfo)][-2:] == [
        "metadata_profiles",
        "action_profiles",
    ]
    assert ModuleInfo.__annotations__["metadata_profile"] == "MetadataProfile"


def test_profile_is_semantic_and_existing_modules_cannot_switch_it() -> None:
    old = ModuleInfo("catalog", Placement("store"), Revision(), ())
    same = replace(old)
    selected = replace(old, metadata_profile="umf-core-metadata/1")

    check(None, selected, EmptyStats())
    check(old, same, EmptyStats())
    assert old != selected
    with pytest.raises(Invalid) as error:
        check(old, selected, EmptyStats())
    assert [(v.path, v.code) for v in error.value.violations] == [
        ("metadata_profile", "incompatible_change")
    ]
