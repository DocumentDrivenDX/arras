#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Validate the exact portable UI qualification component."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

if __package__:
    from . import _release_evidence_inputs as _inputs
else:
    import _release_evidence_inputs as _inputs

_fail = _inputs.fail
_object = _inputs.object_value
_keys = _inputs.exact_object
_string = _inputs.string
_digest = _inputs.digest
_parse_json_object = _inputs.parse_json_object
_read_ui_sidecars = _inputs._read_ui_sidecars
_validate_ui_suite_cohort = _inputs.validate_ui_suite_cohort


def validate_ui(
    value: dict[str, Any],
    receipt_path: Path,
    wheel_name: str,
    wheel_sha: str,
    npm_sha: str,
    version: str,
    npm_resources: bytes,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    if value.get("schema") != "arras.ui.downstream-qualification.v1":
        _fail("unsupported UI receipt schema")
    suite = _object(value.get("acceptance_suite"), "ui.acceptance_suite")
    if suite.get("schema") != "arras.ui.portable-acceptance.v1" or suite.get("status") != "passed":
        _fail("UI receipt lacks a successful complete portable acceptance suite")
    cohort = _object(value.get("cohort"), "ui.cohort")
    wheel = _object(cohort.get("wheel"), "ui.cohort.wheel")
    npm = _object(cohort.get("npm"), "ui.cohort.npm")
    if (
        wheel.get("file") != wheel_name
        or wheel.get("version") != version
        or wheel.get("sha256") != wheel_sha
        or npm.get("file") != f"documentdrivendx-arras-ui-{version}.tgz"
        or npm.get("version") != version
        or npm.get("sha256") != npm_sha
    ):
        _fail("portable UI suite is not bound to the selected wheel/npm artifacts")
    theme = _object(cohort.get("theme"), "ui.cohort.theme")
    if theme.get("name") != "@arras-fixtures/neutral-theme" or theme.get("version") != "1.0.0":
        _fail("UI receipt does not identify the reviewed neutral theme")
    theme_sha = _digest(theme.get("sha256"), "UI theme SHA")
    runner_sha = _digest(
        _object(cohort.get("runner"), "ui.cohort.runner").get("sha256"), "UI runner SHA"
    )
    _validate_ui_suite_cohort(suite.get("cohort"), wheel_sha, npm_sha, theme_sha, runner_sha)
    runtime = _object(value.get("runtime"), "UI runtime")
    sidecars = _read_ui_sidecars(receipt_path, suite)
    projects, inventory = _validate_ui_projects(suite, sidecars, runtime.get("platform"))
    resources = _validate_ui_resources(
        suite, sidecars, inventory, runtime.get("platform"), npm_resources
    )
    return {
        "schema": "arras.ui.portable-acceptance.v1",
        "status": "passed",
        "themeId": _string(suite.get("themeId"), "UI theme ID"),
        "projects": projects,
        **resources,
        "cohort": {
            "wheelSha256": wheel_sha,
            "npmSha256": npm_sha,
            "themeSha256": theme_sha,
            "runnerSha256": runner_sha,
        },
    }, sidecars


def _validate_ui_projects(
    suite: dict[str, Any], sidecars: dict[str, bytes], platform_name: object
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    resources, counts, expected_names = _prepare_ui_inventory(suite, sidecars, platform_name)
    value = suite.get("projects")
    if not isinstance(value, list) or not value:
        _fail("portable UI suite omits independently counted projects")
    rows = [_object(item, "UI project") for item in value]
    if [row.get("name") for row in rows] != expected_names:
        _fail("portable UI projects differ from the platform contract")
    project_names: set[str] = set()
    safe_projects: list[dict[str, Any]] = []
    for raw in value:
        row = _keys(
            raw,
            "UI project",
            {"name", "expected", "discovered", "passed", "failed", "skipped"},
        )
        name = _string(row.get("name"), "UI project name")
        if name in project_names:
            _fail("portable UI project names must be unique")
        project_names.add(name)
        for field in ("expected", "discovered", "passed"):
            if type(row.get(field)) is not int or row[field] <= 0:
                _fail(f"UI project {name} has no positive {field} count")
        if row["expected"] != row["discovered"] or row["passed"] != row["expected"]:
            _fail(f"UI project {name} was not independently discovered and fully passed")
        if row["expected"] != counts[name]:
            _fail(f"UI project {name} differs from canonical source discovery")
        if (
            type(row.get("failed")) is not int
            or type(row.get("skipped")) is not int
            or row["failed"] != 0
            or row["skipped"] != 0
        ):
            _fail(f"UI project {name} has failed or skipped cases")
        safe_projects.append(
            {
                key: row[key]
                for key in ("name", "expected", "discovered", "passed", "failed", "skipped")
            }
        )
    return safe_projects, resources


def _prepare_ui_inventory(
    suite: dict[str, Any], sidecars: dict[str, bytes], platform_name: object
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    inventory = _parse_json_object(
        sidecars["acceptance-inventory-neutral-theme.json"], "UI canonical inventory"
    )
    inventory = _keys(inventory, "UI canonical inventory", {"schema", "specs", "expectedCounts"})
    if inventory.get("schema") != "arras.ui.canonical-acceptance-inventory.v1":
        _fail("unsupported UI canonical inventory schema")
    resources = _parse_json_object(
        sidecars["acceptance-resources-neutral-theme.json"], "UI acceptance resources"
    )
    if type(resources.get("version")) is not int or resources.get("version") != 1:
        _fail("unsupported UI acceptance resources version")
    if inventory.get("specs") != resources.get("specs") or inventory.get(
        "expectedCounts"
    ) != resources.get("expectedCounts"):
        _fail("UI inventory differs from packaged acceptance resources")
    specs = resources.get("specs")
    if not isinstance(specs, list) or tuple(specs) != _inputs.CANONICAL_UI_SPECS:
        _fail("UI acceptance resources must enumerate 17 canonical specs")
    counts = _object(resources.get("expectedCounts"), "UI source expectedCounts")
    if set(counts) != {"chromium", "schema-admin", "browser", "visual"}:
        _fail("UI acceptance resources omit a canonical Playwright project")
    if platform_name not in {"linux", "darwin"}:
        _fail("UI portable qualification must run on Linux or Darwin")
    canonical = _object(suite.get("canonical"), "UI canonical inventory")
    if canonical.get("sourceExpectedCounts") != counts:
        _fail("UI source-discovered counts differ from canonical resources")
    expected_names = ["chromium", "schema-admin", "browser"]
    if platform_name == "darwin":
        expected_names.append("visual")
    return resources, counts, expected_names


def _validate_ui_resources(
    suite: dict[str, Any],
    sidecars: dict[str, bytes],
    resources: dict[str, Any],
    platform_name: object,
    npm_resources: bytes,
) -> dict[str, Any]:
    canonical = _object(suite.get("canonical"), "UI canonical inventory")
    specs = resources.get("specs")
    if type(canonical.get("specCount")) is not int or canonical["specCount"] != len(specs):
        _fail("UI canonical suite does not cover all 17 planned specifications")
    expected_total = sum(row["expected"] for row in cast(list[dict[str, Any]], suite["projects"]))
    if (
        type(canonical.get("expectedTestCount")) is not int
        or canonical["expectedTestCount"] != expected_total
    ):
        _fail("UI canonical suite expected test count differs from its project inventory")
    if canonical.get("sourceExpectedCounts") != resources.get("expectedCounts"):
        _fail("UI canonical suite source counts differ from npm acceptance resources")
    if sidecars["acceptance-resources-neutral-theme.json"] != npm_resources:
        _fail("UI acceptance resources bytes differ from selected npm archive")
    summary = _inputs.validate_ui_playwright_summary(
        _parse_json_object(
            sidecars["playwright-summary-neutral-theme.json"], "UI Playwright summary"
        )
    )
    if summary.get("platform") != platform_name or summary.get("projects") != suite.get("projects"):
        _fail("UI Playwright summary differs from suite outcomes")
    if (
        type(summary.get("expectedTestCount")) is not int
        or type(summary.get("unexpectedSkips")) is not int
        or summary.get("unexpectedSkips") != 0
        or summary.get("expectedTestCount") != canonical["expectedTestCount"]
    ):
        _fail("UI Playwright summary has unexpected skips or count drift")
    visual = _object(suite.get("visual"), "UI visual result")
    expected_visual = "compared" if platform_name == "darwin" else "skipped-non-Darwin"
    if visual.get("status") != expected_visual:
        _fail("UI visual comparison status is unsupported")
    if platform_name == "darwin":
        visual_project = next(row for row in suite["projects"] if row["name"] == "visual")
        if (
            set(visual) != {"status", "comparedScreenshots"}
            or type(visual.get("comparedScreenshots")) is not int
            or visual["comparedScreenshots"] <= 0
            or visual.get("comparedScreenshots") != visual_project["passed"]
        ):
            _fail("UI visual screenshot count differs from the passing visual project")
    elif set(visual) != {"status"}:
        _fail("Linux UI run must explicitly skip visual comparison without extra fields")
    negative = _object(suite.get("negativeControls"), "UI negative controls")
    if set(negative) != {
        "missingResource",
        "tamperedResource",
        "invalidOptions",
        "controlledFailure",
    } or any(
        negative.get(key) != expected
        for key, expected in {
            "missingResource": "refused",
            "tamperedResource": "refused",
            "invalidOptions": "refused",
            "controlledFailure": "exit-1",
        }.items()
    ):
        _fail("UI negative controls are incomplete or did not pass")
    return {
        "canonical": {
            "specCount": canonical["specCount"],
            "expectedTestCount": canonical["expectedTestCount"],
            "sourceExpectedCounts": canonical["sourceExpectedCounts"],
        },
        "playwright": {
            "schema": summary["schema"],
            "status": summary["status"],
            "expectedTestCount": summary["expectedTestCount"],
            "unexpectedSkips": summary["unexpectedSkips"],
        },
        "visual": {
            "status": visual["status"],
            **(
                {"comparedScreenshots": visual["comparedScreenshots"]}
                if platform_name == "darwin"
                else {}
            ),
        },
        "negativeControls": negative,
    }
