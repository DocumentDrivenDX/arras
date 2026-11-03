# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bounded host-selected aliases for legacy vocabulary and graph reads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from arras import Invalid, Refused, graphfile
from arras._doctor_types import DoctorRequest
from arras.adapters.truss import TrussBackend
from arras.core import Arras
from arras.devhost import build
from arras.devtruss import TrussBox
from arras.distribution import DistributionConfig
from arras.doctor import check
from arras.sandbox import Sandbox
from arras.umf import parse_module
from arras.view import declared_from_text

EXAMPLE = Path(__file__).parent.parent / "docs/helix/02-design/contracts/examples/catalog.umf.json"


def _view_document() -> dict[str, Any]:
    doc = json.loads(EXAMPLE.read_text())
    doc["vocabularies"].pop("arras.view", None)
    module = doc["modules"][0]
    module.get("extensions", {}).pop("arras.view", None)
    for carrier in (*module["elements"], *module["relationships"]):
        carrier.get("extensions", {}).pop("arras.view", None)
    return doc


def test_distribution_aliases_are_bounded_and_immutable() -> None:
    config = DistributionConfig(
        view_vocabulary_aliases=("legacy.view",),
        graph_format_aliases=("legacy.graph",),
    )
    assert config.view_vocabulary_aliases == ("legacy.view",)
    assert config.graph_format_aliases == ("legacy.graph",)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"view_vocabulary_aliases": ["legacy.view"]},
        {"view_vocabulary_aliases": ("arras.view",)},
        {"view_vocabulary_aliases": ("umf.view",)},
        {"view_vocabulary_aliases": ("Legacy.view",)},
        {"view_vocabulary_aliases": ("legacy.view", "legacy.view")},
        {"view_vocabulary_aliases": tuple(f"legacy.v{i}" for i in range(17))},
        {"view_vocabulary_aliases": ("legacy.view",), "graph_format_aliases": ("legacy.view",)},
    ],
)
def test_invalid_distribution_aliases_refuse_without_echoing_values(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValueError) as exc:
        DistributionConfig(**kwargs)  # type: ignore[arg-type]
    assert "view_vocabulary_aliases" in str(exc.value) or "graph_format_aliases" in str(exc.value)
    assert "legacy.view" not in str(exc.value)


def test_selected_view_alias_reads_same_terms_and_keeps_source_text() -> None:
    doc = _view_document()
    doc["vocabularies"]["legacy.view"] = {"version": "0.1.0"}
    doc["modules"][0]["extensions"]["legacy.view"] = {"title": "Legacy catalog"}
    raw = json.dumps(doc, ensure_ascii=False).encode()

    module = parse_module(raw, view_vocabulary_aliases=("legacy.view",))
    declared = declared_from_text(raw.decode(), module, view_vocabulary_aliases=("legacy.view",))

    assert declared.title == "Legacy catalog"
    assert raw == json.dumps(doc, ensure_ascii=False).encode()


def test_view_alias_is_not_enabled_by_default() -> None:
    doc = _view_document()
    doc["vocabularies"]["legacy.view"] = {"version": "0.1.0"}
    doc["modules"][0]["extensions"]["legacy.view"] = {"title": "Legacy catalog"}
    with pytest.raises(Invalid):
        parse_module(json.dumps(doc))


def test_view_alias_ambiguity_names_original_source_keys() -> None:
    doc = _view_document()
    doc["vocabularies"]["legacy.view"] = {"version": "0.1.0"}
    doc["vocabularies"]["arras.view"] = {"version": "0.1.0"}
    doc["modules"][0]["extensions"]["legacy.view"] = {"title": "Legacy catalog"}
    with pytest.raises(Invalid) as exc:
        parse_module(json.dumps(doc), view_vocabulary_aliases=("legacy.view",))
    (fault,) = exc.value.violations
    assert fault.code == "view_ambiguous_vocabulary"
    assert "legacy.view" in fault.path or "arras.view" in fault.path


def test_graph_alias_is_read_only_and_new_output_is_canonical() -> None:
    text = json.dumps(
        {"format": "legacy.graph", "version": 1, "module": "m", "records": [{"id": 1}]}
    )
    graph = graphfile.loads(text, graph_format_aliases=("legacy.graph",))
    assert graph.module == "m"
    assert json.loads(graphfile.dumps(graph))["format"] == "arras.graph"
    with pytest.raises(ValueError, match="not a graph file"):
        graphfile.loads(text)


def test_devhost_build_propagates_selected_aliases_to_module_and_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = _view_document()
    doc["vocabularies"]["legacy.view"] = {"version": "0.1.0"}
    doc["modules"][0]["extensions"]["legacy.view"] = {"title": "Legacy catalog"}
    module_path = tmp_path / "module.json"
    module_path.write_text(json.dumps(doc), encoding="utf-8")
    graph_path = tmp_path / "catalog.graph.json"
    graph_path.write_text(
        json.dumps({"format": "legacy.graph", "version": 1, "module": "catalog", "records": []}),
        encoding="utf-8",
    )
    loaded: dict[str, object] = {}

    def capture_load(sandbox: Sandbox, document: str, steps: object, graph: object) -> Sandbox:
        loaded["document"] = document
        loaded["graph"] = graph
        return sandbox

    monkeypatch.setattr(Sandbox, "load", capture_load)
    box = build(
        module_path,
        None,
        records=graph_path,
        distribution=DistributionConfig(
            view_vocabulary_aliases=("legacy.view",),
            graph_format_aliases=("legacy.graph",),
        ),
    )
    assert box.arras.distribution.view_vocabulary_aliases == ("legacy.view",)
    graph = loaded["graph"]
    assert isinstance(graph, graphfile.GraphFile)
    assert graph.module == "catalog"


def test_doctor_parses_module_documents_with_selected_aliases(tmp_path: Path) -> None:
    doc = _view_document()
    doc["vocabularies"]["legacy.view"] = {"version": "0.1.0"}
    doc["modules"][0]["extensions"]["legacy.view"] = {"title": "Legacy catalog"}
    path = tmp_path / "module.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    report = check(
        DoctorRequest(
            module_documents=(path,),
            module_profile="legacy-arras",
            distribution=DistributionConfig(view_vocabulary_aliases=("legacy.view",)),
        )
    )
    assert cast(Any, report.observed["module_documents"])[0]["module"] == "catalog"
    assert not any(row.code == "module_invalid" for row in report.diagnostics)


def test_registered_alias_document_round_trips_without_rewrite_and_cache_isolated() -> None:
    doc = _view_document()
    doc["vocabularies"]["legacy.view"] = {"version": "0.1.0"}
    doc["modules"][0]["extensions"]["legacy.view"] = {"title": "Legacy catalog"}
    raw = json.dumps(doc, ensure_ascii=False).encode()
    distribution = DistributionConfig(view_vocabulary_aliases=("legacy.view",))
    box = Sandbox(distribution=distribution).load(raw.decode())
    session = box.arras.session(box.people["alice"])
    module = next(m for m in session.modules() if m.name == "catalog")

    assert session.document("catalog").text.encode() == raw
    assert session.view_of(module).module.title == "Legacy catalog"
    with pytest.raises(ValueError, match="view_vocabulary_aliases mismatch"):
        Arras.start(box.backends, distribution=DistributionConfig())


@pytest.mark.truss
def test_native_truss_registration_and_view_round_trip_preserve_alias_source(
    tmp_path: Path,
) -> None:
    from test_truss_harness import _require  # pyright: ignore[reportPrivateUsage]

    _require()
    doc = _view_document()
    doc["vocabularies"]["legacy.view"] = {"version": "0.1.0"}
    doc["modules"][0]["extensions"]["legacy.view"] = {"title": "Legacy catalog"}
    raw = json.dumps(doc, ensure_ascii=False)
    box = TrussBox(
        directory=tmp_path / "native",
        distribution=DistributionConfig(view_vocabulary_aliases=("legacy.view",)),
    )
    try:
        box.load(raw)
        session = box.arras.session(box.people["alice"])
        module = next(item for item in session.modules() if item.name == "catalog")
        original = session.document("catalog")
        assert original.text.encode() == raw.encode()
        assert session.view_of(module).module.title == "Legacy catalog"

        # The native fixture is already registered. Fresh readers select policy without a write.
        backend = box.truss.backend
        assert backend is not None and backend.connections is not None
        canonical = TrussBackend(box.name, backend.connections)
        assert "catalog" not in canonical.catalog(box.people["alice"])
        with pytest.raises(Refused):
            canonical.document(box.people["alice"], "catalog")

        enabled = TrussBackend(
            box.name, backend.connections, view_vocabulary_aliases=("legacy.view",)
        )
        host = Arras.start(
            {box.name: enabled},
            distribution=box.arras.distribution,
            default_placement=box.arras.default_placement,
        )
        reader = host.session(box.people["alice"])
        reread = reader.document("catalog")
        assert reread.text.encode() == original.text.encode()
        assert reread.revision == original.revision
        assert reader.view_of(reader.modules()[0]).module.title == "Legacy catalog"
    finally:
        box.close()
