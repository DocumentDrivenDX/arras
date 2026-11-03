# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""Regressions from the scoped A6 review."""

import gc
import json
import weakref
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from arras import graphfile
from arras.adapters.truss import TrussBackend
from arras.branding import Brand
from arras.core import Arras
from arras.devhost import DevHost
from arras.distribution import DistributionConfig
from arras.fakes import FakeAccess, MemoryReplica, MemoryStore
from arras.results import RegisteredDocument
from arras.sandbox import Sandbox
from arras.types import Revision
from arras.ui._brand_page import branded
from arras.umf import parse_module
from arras.viewcache import ViewCache

ALIASES = ("legacy.view",)
VECTORS = json.loads((Path(__file__).parent / "vectors/graphfile.json").read_text())


def test_export_only_page_does_not_emit_unused_graph_alias_metadata() -> None:
    page = branded(b"<html><head><title>Host</title></head><body></body></html>", Brand())
    assert b"arras-brand" in page
    assert b"arras-graph-format-aliases" not in page


def test_served_page_bytes_do_not_depend_on_graph_read_policy(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html><head><title>Host</title></head></html>")
    pages = []
    for aliases in ((), ("legacy.graph",)):
        config = DistributionConfig(graph_format_aliases=aliases)
        host = DevHost(
            Sandbox(distribution=config), port=8000, ui_dir=tmp_path, distribution=config
        )
        status, _, page = host.static("/")
        assert status == 200
        pages.append(page)
    assert pages[0] == pages[1]
    assert b"arras-graph-format-aliases" not in pages[0]


@pytest.mark.parametrize("vector", VECTORS["invalid_formats"], ids=lambda v: v["name"])
def test_format_is_a_string_even_with_aliases(vector) -> None:
    text = json.dumps({"format": vector["format"], "version": 1, "module": "m", "records": []})
    with pytest.raises(ValueError, match="not a graph file"):
        graphfile.loads(text, graph_format_aliases=("legacy.graph",))


@pytest.mark.parametrize("owner", ["arras", "cache", "store", "replica", "truss"])
def test_fixed_instance_policy_cannot_be_reassigned(owner: str) -> None:
    access = FakeAccess()
    store = MemoryStore(access, view_vocabulary_aliases=ALIASES)
    instances = {
        "arras": Arras({}, distribution=DistributionConfig(view_vocabulary_aliases=ALIASES)),
        "cache": ViewCache(ALIASES),
        "store": store,
        "replica": MemoryReplica(store, access, view_vocabulary_aliases=ALIASES),
        "truss": TrussBackend("truss", view_vocabulary_aliases=ALIASES),
    }
    selected = instances[owner]
    with pytest.raises(AttributeError):
        cast(Any, selected).view_vocabulary_aliases = ()
    assert selected.view_vocabulary_aliases == ALIASES


def test_arras_and_sandbox_cannot_replace_their_distribution() -> None:
    config = DistributionConfig(view_vocabulary_aliases=ALIASES)
    box = Sandbox(distribution=config)
    for owner in (box, box.arras):
        with pytest.raises(AttributeError):
            cast(Any, owner).distribution = DistributionConfig()
        assert owner.distribution is config


def test_cache_releases_superseded_views_but_keeps_the_current_revision() -> None:
    text = (Path(__file__).parent.parent / "examples/catalog/catalog.umf.json").read_text()
    base = parse_module(text)
    cache = ViewCache()
    previous = []
    for revision in range(64):
        module = replace(base, revision=Revision({"memory": revision}))
        document = RegisteredDocument(module.name, module.revision, text, "json")
        view = cache.resolve(module, lambda document=document: document)
        previous.append(weakref.ref(view))
    del view
    gc.collect()
    assert all(held() is None for held in previous[:-1])
    assert previous[-1]() is not None

    def must_hit():
        raise AssertionError("the current revision must remain cached")

    assert cache.resolve(module, must_hit) is previous[-1]()


def test_custom_backend_without_policy_attribute_still_serves_canonical_modules() -> None:
    box = Sandbox().seed()

    class LegacyBackend:
        def __getattr__(self, name):
            if name == "view_vocabulary_aliases":
                raise AttributeError(name)
            return getattr(box.store, name)

    host = Arras.start(
        {box.store.name: cast(Any, LegacyBackend())},
        distribution=DistributionConfig(view_vocabulary_aliases=ALIASES),
        default_placement=box.arras.default_placement,
    )
    assert [module.name for module in host.session(box.people["alice"]).modules()] == ["catalog"]


def test_explicit_custom_policy_participant_still_refuses_mismatch() -> None:
    class Participant:
        view_vocabulary_aliases = ()

    with pytest.raises(ValueError, match="view_vocabulary_aliases mismatch"):
        Arras.start(
            {"custom": cast(Any, Participant())},
            distribution=DistributionConfig(view_vocabulary_aliases=ALIASES),
        )
