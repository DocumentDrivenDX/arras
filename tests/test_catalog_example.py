# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The catalog example's reads, against the example's own module and seed."""

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from arras.devhost import build
from arras.errors import Invalid, PreconditionFailed, Refused
from arras.sandbox import Sandbox

EXAMPLE = Path(__file__).parent.parent / "examples" / "catalog"


def _load_read() -> Any:
    spec = importlib.util.spec_from_file_location("catalog_example_read", EXAMPLE / "read.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


read = _load_read()


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"catalog_example_{name}", EXAMPLE / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def box() -> Sandbox:
    return build(EXAMPLE / "catalog.umf.json", EXAMPLE / "seed.json")


@pytest.fixture
def carol(box: Sandbox) -> Any:
    return box.arras.session(box.people["carol"])  # she may read and nothing else


def test_cards_are_one_per_solution_with_use_case_and_provider(carol: Any) -> None:
    cards = {c["id"]: c for c in read.cards(carol)}
    assert set(cards) == {
        "alert-triage-playbook",
        "datamap-app",
        "datamap-review",
        "doc-search",
        "log-query",
        "lumen-runbook-prompt",
        "lumen-triage-prompt",
        "public-research",
    }
    app = cards["datamap-app"]
    assert app["deliveryMode"] == "app" and app["workflow"] is None and app["prompt"] is None
    assert app["launchUrl"] == "https://datamap.example.test/"
    assert app["useCase"]["id"] == "document-datasets"
    alerts = cards["alert-triage-playbook"]
    assert alerts["title"] == "Alert triage against runbook" and alerts["deliveryMode"] == "chat"
    assert alerts["workflow"] == "alert-triage-playbook" and alerts["prompt"] is None
    assert alerts["useCase"]["id"] == "triage-incident-alerts" and alerts["useCase"]["problem"]
    assert alerts["provider"] is None
    lumen = cards["lumen-triage-prompt"]
    assert lumen["deliveryMode"] == "handoff" and lumen["workflow"] is None
    assert lumen["prompt"].startswith("Review the attached alert export")
    assert lumen["provider"]["id"] == "lumen" and lumen["provider"]["vendor"] == "Lumen Labs"
    assert lumen["useCase"]["id"] == "triage-incident-alerts"


def test_a_card_for_an_audience_shows_only_to_that_audience(carol: Any) -> None:
    assert "trace-search" not in {c["id"] for c in read.cards(carol)}
    assert "trace-search" not in {c["id"] for c in read.cards(carol, audiences=["Data analysts"])}
    builders = {c["id"]: c for c in read.cards(carol, audiences=["Platform engineers"])}
    assert len(builders) == 9 and builders["trace-search"]["audience"] == "Platform engineers"


def test_a_use_case_shows_every_way_of_doing_it(carol: Any) -> None:
    alerts = read.use_case(carol, "triage-incident-alerts")
    assert alerts["name"] == "Triage incoming alerts at volume"
    assert alerts["workArea"] == "Incident response"
    assert [s["id"] for s in alerts["solutions"]] == [
        "alert-triage-playbook",
        "lumen-triage-prompt",
    ]
    assert {s["deliveryMode"] for s in alerts["solutions"]} == {"chat", "handoff"}
    assert {c["product"]["id"]: c["level"] for c in alerts["coverage"]} == {
        "beacon": "partial",
        "pylon": "full",
    }
    assert all(c["product"]["name"] for c in alerts["coverage"])


def test_a_use_case_with_nothing_recorded_and_one_that_does_not_exist(carol: Any) -> None:
    trace = read.use_case(carol, "model-trace-search")
    assert trace["solutions"] == [] and trace["coverage"] == []
    assert [
        s["id"]
        for s in read.use_case(carol, "model-trace-search", audiences=["Platform engineers"])[
            "solutions"
        ]
    ] == ["trace-search"]
    assert read.use_case(carol, "no-such-use-case") is None


def test_rows_pages_with_a_keyset_to_the_end(carol: Any) -> None:
    whole = read.rows(carol, "UseCase")
    paged = read.rows(carol, "UseCase", page=7)
    assert len(whole) == 30 and [r["code"] for r in paged] == [r["code"] for r in whole]


def test_the_persons_own_access_decides_what_is_read(box: Sandbox) -> None:
    dave = box.arras.session(box.people["dave"])  # he holds nothing on the catalog
    with pytest.raises(Invalid, match="no module 'catalog'"):  # to him it does not exist
        read.cards(dave)
    with pytest.raises(Refused):
        read.cards(box.arras.session(box.principal("(no token)")))


def test_products_carry_their_status_coverage_and_solutions(carol: Any) -> None:
    products = {p["id"]: p for p in read.products(carol)}
    assert len(products) == 12
    lumen = products["lumen"]
    assert lumen["name"] == "Lumen Search" and lumen["lifecycleStatus"] == "Approved · live"
    assert lumen["solutions"] == ["lumen-runbook-prompt", "lumen-triage-prompt"]
    assert len(lumen["coverage"]) == 5
    pylon = products["pylon"]
    assert pylon["solutions"] == []
    assert {"id": "triage-incident-alerts", "level": "full"}.items() <= next(
        c for c in pylon["coverage"] if c["id"] == "triage-incident-alerts"
    ).items()
    assert all(c["name"] for p in products.values() for c in p["coverage"])
    assert sum(len(p["coverage"]) for p in products.values()) == 33


def test_the_schema_file_is_what_the_builder_writes() -> None:
    builder = _load("build")
    assert (EXAMPLE / "catalog.umf.json").read_text(encoding="utf-8") == builder.text(), (
        "catalog.umf.json has drifted from build.py: run `uv run python examples/catalog/build.py`"
    )
    assert builder.main(["--check"]) == 0


def test_a_use_case_carries_its_findings_with_product_and_version(carol: Any) -> None:
    diligence = read.use_case(carol, "search-application-logs")
    [finding] = diligence["findings"]
    assert finding["id"] == "fnd-seed-logs-1" and finding["relation"] == "primary"
    assert finding["product"]["id"] == "lumen" and finding["version"]["label"] == "v1"
    assert finding["statement"].startswith("Lumen v1 finds the log lines")
    [adjacent] = read.use_case(carol, "summarize-incident-timelines")["findings"]
    assert adjacent["id"] == "fnd-seed-logs-1" and adjacent["relation"] == "adjacent"
    assert read.use_case(carol, "triage-incident-alerts")["findings"] == []


def test_a_product_carries_its_versions_and_findings(carol: Any) -> None:
    products = {p["id"]: p for p in read.products(carol)}
    assert [(v["label"], v["status"]) for v in products["lumen"]["versions"]] == [
        ("v1", "superseded"),
        ("v2", "current"),
    ]
    assert products["lumen"]["findings"] == ["fnd-seed-logs-1"]
    assert products["pylon"]["versions"] == [] and products["pylon"]["findings"] == []


@pytest.fixture
def editor() -> Any:
    """A fresh catalog and someone who may change it, so one test's edits do not reach another."""
    box = build(EXAMPLE / "catalog.umf.json", EXAMPLE / "seed.json")
    return box.arras.session(box.people["alice"])


def _one(o: Any, type_name: str, code: str) -> Any:
    keys = {"UseCase": ("addressedBy", "coveredBy"), **read.RELATED}.get(type_name, ())
    cols = "".join(f", RELATED_KEYS(x.{r}, 100) AS {r}" for r in keys)
    sql = f"SELECT x.*{cols} FROM catalog.{type_name} x WHERE x.code = :k ORDER BY x.code LIMIT 100"
    found = o.query("catalog", sql, {"k": code}).rows
    return found[0] if found else None


def test_correcting_changes_what_is_given_and_leaves_the_rest(editor: Any) -> None:
    before = _one(editor, "Solution", "lumen-triage-prompt")
    editor.invoke(
        "catalog.CorrectSolution",
        {"solution": "lumen-triage-prompt", "launchUrl": "https://lumen.example.test/"},
    )
    after = _one(editor, "Solution", "lumen-triage-prompt")
    assert after["launchUrl"] == "https://lumen.example.test/"
    assert after["prompt"] == before["prompt"] and after["summary"] == before["summary"]
    assert after["name"] == before["name"] and after["_version"] == before["_version"] + 1

    editor.invoke("catalog.CorrectProduct", {"product": "lumen", "lifecycleStatus": "Paused"})
    assert _one(editor, "Product", "lumen")["lifecycleStatus"] == "Paused"
    editor.invoke(
        "catalog.CorrectUseCase",
        {"useCase": "triage-incident-alerts", "problem": "A new way to say it"},
    )
    assert _one(editor, "UseCase", "triage-incident-alerts")["problem"] == "A new way to say it"


def test_required_fields_change_through_an_action_of_their_own(editor: Any) -> None:
    editor.invoke(
        "catalog.UpdateSolution",
        {"solution": "datamap-app", "name": "Datamap app", "deliveryMode": "handoff"},
    )
    changed = _one(editor, "Solution", "datamap-app")
    assert changed["name"] == "Datamap app" and changed["deliveryMode"] == "handoff"
    editor.invoke(
        "catalog.RenameUseCase", {"useCase": "triage-incident-alerts", "name": "Alert triage"}
    )
    editor.invoke("catalog.RenameProduct", {"product": "lumen", "name": "Lumen Search Pro"})
    assert _one(editor, "UseCase", "triage-incident-alerts")["name"] == "Alert triage"
    assert _one(editor, "Product", "lumen")["name"] == "Lumen Search Pro"
    editor.invoke(
        "catalog.ChangeCoverageLevel",
        {"coverageAssertion": "beacon.triage-incident-alerts", "level": "full"},
    )
    assert _one(editor, "CoverageAssertion", "beacon.triage-incident-alerts")["level"] == "full"


def test_retiring_removes_the_record_and_its_links(editor: Any) -> None:
    editor.invoke("catalog.RetireSolution", {"solution": "lumen-triage-prompt"})
    assert _one(editor, "Solution", "lumen-triage-prompt") is None
    assert _one(editor, "UseCase", "triage-incident-alerts")["addressedBy"] == [
        "alert-triage-playbook"
    ]
    assert _one(editor, "Product", "lumen")["provides"] == ["lumen-runbook-prompt"]
    assert [c["id"] for c in read.cards(editor)].count("lumen-triage-prompt") == 0

    editor.invoke("catalog.RetireCoverage", {"coverageAssertion": "pylon.triage-incident-alerts"})
    assert _one(editor, "UseCase", "triage-incident-alerts")["coveredBy"] == [
        "beacon.triage-incident-alerts"
    ]


def test_a_change_to_something_that_is_not_there_is_refused(editor: Any) -> None:
    for action, inputs in (
        ("CorrectSolution", {"solution": "no-such", "summary": "x"}),
        ("RenameProduct", {"product": "no-such", "name": "x"}),
        ("RetireSolution", {"solution": "no-such"}),
        ("RetireCoverage", {"coverageAssertion": "no-such"}),
    ):
        with pytest.raises(PreconditionFailed):
            editor.invoke(f"catalog.{action}", inputs)


def test_a_reader_may_not_change_anything(carol: Any) -> None:
    with pytest.raises(Refused):
        carol.invoke(
            "catalog.UpdateSolution",
            {"solution": "datamap-app", "name": "x", "deliveryMode": "chat"},
        )


def test_every_property_but_a_key_has_an_action_that_changes_it() -> None:
    """The graph can be changed through the actions alone: each non-key property is the target of an
    update, each record but a use case, a product and a version can be retired where nothing points
    at it, and every relationship can be removed that a record can be without."""
    import json

    doc = json.loads((EXAMPLE / "catalog.umf.json").read_text(encoding="utf-8"))
    module = doc["modules"][0]
    effects = [(e, a["id"]) for a in module["actions"] for e in a["effects"]]
    updated = {
        (e["refType"], p) for e, _ in effects if e["op"] == "update" for p in e["properties"]
    }
    fields = [e["id"].split(".") for e in module["elements"] if e["kind"] == "field"]
    assert [f for f in fields if f[1] != "code" and tuple(f) not in updated] == []
    unlinked = {e["type"] for e, _ in effects if e["op"] == "unlink"}
    assert unlinked == {"addresses", "providedBy", "aboutVersion", "appliesTo", "adjacentTo"}


def test_the_new_actions_change_the_graph(editor: Any) -> None:
    editor.invoke(
        "catalog.CorrectCoverageAssertion",
        {"coverageAssertion": "beacon.triage-incident-alerts", "notes": "Checked again"},
    )
    assert (
        _one(editor, "CoverageAssertion", "beacon.triage-incident-alerts")["notes"]
        == "Checked again"
    )
    version = "pv-lumen-v1"
    editor.invoke("catalog.RelabelProductVersion", {"productVersion": version, "label": "v1.1"})
    editor.invoke("catalog.CorrectProductVersion", {"productVersion": version, "status": "retired"})
    assert _one(editor, "ProductVersion", version)["label"] == "v1.1"
    assert _one(editor, "ProductVersion", version)["status"] == "retired"
    editor.invoke(
        "catalog.ClearSolutionProvider", {"solution": "lumen-triage-prompt", "product": "lumen"}
    )
    assert "lumen-triage-prompt" not in _one(editor, "Product", "lumen")["provides"]
    editor.invoke(
        "catalog.UnaddressUseCase",
        {"solution": "lumen-triage-prompt", "useCase": "triage-incident-alerts"},
    )
    assert (
        "lumen-triage-prompt"
        not in _one(editor, "UseCase", "triage-incident-alerts")["addressedBy"]
    )
    editor.invoke(
        "catalog.AddressUseCase",
        {"solution": "lumen-triage-prompt", "useCase": "triage-incident-alerts"},
    )
    assert "lumen-triage-prompt" in _one(editor, "UseCase", "triage-incident-alerts")["addressedBy"]
    editor.invoke("catalog.RetireFinding", {"finding": "fnd-seed-logs-1"})
    assert _one(editor, "Finding", "fnd-seed-logs-1") is None


def test_the_graph_file_is_a_known_good_fixture_that_loads_and_reads_like_the_seed(
    box: Sandbox,
) -> None:
    """`catalog.graph.json` is what the interface's Export writes. Loading it reproduces the graph
    the seed builds (until someone iterates on the graph and commits a new file, which is the
    point: the file, not the seed, is then the record), and exporting that graph again gives the
    same bytes, so a committed file only changes when the graph does."""
    from arras import graphfile

    path = EXAMPLE / "catalog.graph.json"
    served = build(EXAMPLE / "catalog.umf.json", None, records=path)
    reader = served.arras.session(served.people["carol"])
    export = graphfile.export(served.arras.session(served.people["alice"]), "catalog")
    assert graphfile.dumps(export) == path.read_text(encoding="utf-8")
    assert export.complete and len(export.records) == 170
    seeded = box.arras.session(box.people["carol"])
    assert read.cards(reader) == read.cards(seeded)
    assert read.products(reader) == read.products(seeded)
    assert read.use_case(reader, "triage-incident-alerts") == read.use_case(
        seeded, "triage-incident-alerts"
    )
