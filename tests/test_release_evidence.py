from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest

SCRIPT = Path(__file__).parents[1] / ".github/scripts/assemble_release_evidence.py"
SPEC = importlib.util.spec_from_file_location("release_evidence", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
assembler = importlib.util.module_from_spec(SPEC)
sys.path.insert(0, str(SCRIPT.parent))
try:
    SPEC.loader.exec_module(assembler)
finally:
    sys.path.pop(0)

VERSION = "9.8.7"
WHEEL_NAME = f"arras-{VERSION}-py3-none-any.whl"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value: object) -> bytes:
    raw = (json.dumps(value, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    return raw


SPECS = [
    "a11y.spec.ts",
    "brand.spec.ts",
    "browse-actions.spec.ts",
    "browse-history.spec.ts",
    "browse-new.spec.ts",
    "browse-retire.spec.ts",
    "browser.spec.ts",
    "cross-links.spec.ts",
    "flows.spec.ts",
    "host-isolation.spec.ts",
    "operator.spec.ts",
    "query.spec.ts",
    "routes.spec.ts",
    "schema-admin.spec.ts",
    "shortcuts.spec.ts",
    "umf-explorer.spec.ts",
    "visual.spec.ts",
]
COUNTS = {"chromium": 132, "schema-admin": 3, "browser": 70, "visual": 67}


def resources_doc() -> dict[str, Any]:
    return {
        "version": 1,
        "specs": SPECS,
        "expectedCounts": COUNTS,
        "files": {f"acceptance/e2e/{spec}": sha(b"spec source") for spec in SPECS},
    }


def make_npm(version: str = VERSION) -> tuple[bytes, bytes]:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        raw = json.dumps({"name": "@documentdrivendx/arras-ui", "version": version}).encode()
        item = tarfile.TarInfo("package/package.json")
        item.size = len(raw)
        archive.addfile(item, io.BytesIO(raw))
        resources = (json.dumps(resources_doc(), sort_keys=True) + "\n").encode()
        item = tarfile.TarInfo("package/support/acceptance/resources.json")
        item.size = len(resources)
        archive.addfile(item, io.BytesIO(resources))
        spec = b"spec source"
        for spec_name in SPECS:
            item = tarfile.TarInfo(f"package/support/acceptance/e2e/{spec_name}")
            item.size = len(spec)
            archive.addfile(item, io.BytesIO(spec))
    return output.getvalue(), resources


def make_wheel(path: Path, npm: bytes) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("arras-9.8.7.dist-info/METADATA", "Name: arras\nVersion: 9.8.7\n")
        archive.writestr("arras/ui/npm/arras-ui.tgz", npm)


def make_sdist(path: Path) -> None:
    with tarfile.open(path, "w:gz") as archive:
        raw = b"Metadata-Version: 2.1\nName: arras\nVersion: 9.8.7\n"
        item = tarfile.TarInfo("arras-9.8.7/PKG-INFO")
        item.size = len(raw)
        archive.addfile(item, io.BytesIO(raw))


def doctor_receipt(wheel_sha: str, npm_sha: str) -> dict[str, Any]:
    verifier_sha, probe_sha = assembler._inputs.doctor_probe_hashes(
        Path(__file__).parents[1] / "tools/verify_doctor.py"
    )
    phases = {
        name: {
            "spans": 2,
            "events": 2,
            "logs": 2,
            "service_name": service,
        }
        for name, service in assembler._inputs.DOCTOR_PHASE_SERVICES.items()
    }
    return {
        "schema": "arras.ui.doctor-installed-qualification.v1",
        "status": "passed",
        "verifier_source_sha256": verifier_sha,
        "generated_probe_sha256": probe_sha,
        "platform": {"os": "darwin", "architecture": "arm64", "release": "27.0.0"},
        "python": "3.13.16",
        "wheel": {"filename": WHEEL_NAME, "version": VERSION, "sha256": wheel_sha},
        "npm_sha256": npm_sha,
        "cases": [
            {"name": name, "status": status, "codes": []}
            for name, status in assembler._inputs.DOCTOR_CASE_STATUSES
        ],
        "tripwire_report": {
            "tripwires": "passed",
            "positive": {"ok": True, "complete": True},
            "invalid_config": {"ok": False, "complete": True},
            "unsupported": {"ok": False, "complete": False},
        },
        "launcher_probes": {
            name: "passed"
            for name in (
                "custom_mcp_help",
                "custom_mcp_unsupported_args",
                "alias_conflict_refused",
                "custom_devhost_help",
                "custom_devhost_unsupported_args",
                "custom_devhost_startup_forwarding",
            )
        },
        "telemetry_probes": {
            "status": "passed",
            "generated_probe_sha256": probe_sha,
            "global_provider_unchanged": True,
            "false_pass_controls": list(assembler._inputs.DOCTOR_FALSE_PASS_CONTROLS),
            "sdk_resource_names": ["extension-alpha", "extension-beta"],
            "launcher_effective_names": {
                "attribute_namespace": "extension_host",
                "log_prefix": "extension_host",
                "event_prefix": "extension_host",
            },
            "public_direct_library": "passed",
            "public_mcp_frame": "passed",
            "public_worker_backed_asgi": "passed",
            "concurrent_and_nested_contexts": "passed",
            "default_deny_and_failure_isolation": "passed",
            "phases": phases,
        },
    }


def cohort(wheel_sha: str, index_sha: str) -> dict[str, Any]:
    wheels = [
        ("truss-toolkit", "truss_toolkit-1.0-py3-none-any.whl"),
        ("weft-sql", "weft_sql-1.0-py3-none-any.whl"),
        ("pgserver-pg18", "pgserver_pg18-1.0-py3-none-any.whl"),
    ]
    native = [
        {
            "distribution": name,
            "version": "1.0",
            "filename": filename,
            "url": f"https://packages.example/{filename}",
            "sha256": "a" * 64,
        }
        for name, filename in wheels
    ]
    return {
        "schema_version": 1,
        "arras": {"version": VERSION, "sha256": wheel_sha},
        "runtime": {"python": "3.11", "sys_platform": "darwin", "machine": "arm64"},
        "find_links": {"sha256": index_sha},
        "native_wheels": native,
        "corpus": {"version": 13, "roles": ["reader", "provider"], "limits": {}},
    }


def native_receipt(
    cohort_value: dict[str, Any], cohort_sha: str, index_sha: str, wheel_sha: str
) -> dict[str, Any]:
    native = cohort_value["native_wheels"]
    cases = ["read.one", "write.two"]
    return {
        "schema_version": 1,
        "status": "passed",
        "inputs": {
            "arras_wheel": {"path": "/private/wheel.whl", "sha256": wheel_sha},
            "cohort": {"path": "/private/cohort.json", "sha256": cohort_sha},
            "find_links": {"path": "/private/index.html", "sha256": index_sha},
        },
        "runtime": cohort_value["runtime"],
        "native_wheels": [{**item, "verified_sha256": item["sha256"]} for item in native],
        "corpus": {
            "version": 13,
            "roles": ["reader", "provider"],
            "applicable_case_ids": cases,
            "skipped_case_ids": ["schema.unavailable"],
            "limits": {},
            "counts": {
                "passed": 2,
                "failed": 0,
                "harness_error": 0,
                "limit": 0,
                "host_specific": 0,
            },
            "results": [
                {"case": case, "status": "passed", "message": "temporary path"} for case in cases
            ],
        },
        "cli": {"exit_code": 0, "stdout": "secret raw log", "stderr": ""},
        "native_binary_scope": {
            "observed": "native files declared by installed Python distributions",
            "system_dynamic_link_audit": "not performed",
        },
    }


def ui_receipt(wheel_sha: str, npm_sha: str, sidecars: dict[str, bytes]) -> dict[str, Any]:
    projects = [
        {
            "name": name,
            "expected": COUNTS[name],
            "discovered": COUNTS[name],
            "passed": COUNTS[name],
            "failed": 0,
            "skipped": 0,
        }
        for name in ("chromium", "schema-admin", "browser")
    ]
    expected_total = sum(cast(int, row["expected"]) for row in projects)
    return {
        "schema": "arras.ui.downstream-qualification.v1",
        "runtime": {"platform": "linux"},
        "cohort": {
            "wheel": {"file": WHEEL_NAME, "version": VERSION, "sha256": wheel_sha},
            "npm": {
                "file": f"documentdrivendx-arras-ui-{VERSION}.tgz",
                "version": VERSION,
                "sha256": npm_sha,
            },
            "theme": {
                "name": "@arras-fixtures/neutral-theme",
                "version": "1.0.0",
                "sha256": "4" * 64,
            },
            "runner": {"sha256": "5" * 64},
        },
        "acceptance_suite": {
            "schema": "arras.ui.portable-acceptance.v1",
            "status": "passed",
            "themeId": "neutral-theme",
            "projects": projects,
            "canonical": {
                "specCount": 17,
                "expectedTestCount": expected_total,
                "sourceExpectedCounts": COUNTS,
                "inventoryPath": "acceptance-inventory-neutral-theme.json",
                "inventorySha256": sha(sidecars["acceptance-inventory-neutral-theme.json"]),
                "resourcesPath": "acceptance-resources-neutral-theme.json",
                "resourcesSha256": sha(sidecars["acceptance-resources-neutral-theme.json"]),
            },
            "playwright": {
                "reportPath": "playwright-summary-neutral-theme.json",
                "sha256": sha(sidecars["playwright-summary-neutral-theme.json"]),
            },
            "visual": {"status": "skipped-non-Darwin"},
            "negativeControls": {
                "missingResource": "refused",
                "tamperedResource": "refused",
                "invalidOptions": "refused",
                "controlledFailure": "exit-1",
            },
        },
    }


def consumer_receipt(wheel_sha: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "arras_wheel": {"path": "/private/wheel.whl", "sha256": wheel_sha},
        "extension_host_wheel": {
            "filename": "example_extension_host-0.1.0-py3-none-any.whl",
            "sha256": "6" * 64,
            "build_backend": "hatchling via declared pyproject.toml and uv build",
        },
        "environment": {
            "dependency_mode": "fresh-public-index-resolution",
            "isolated_imports": True,
        },
        "consumer_runs": {
            "graph": {
                "selected_resource": "graph.json",
                "module": "notes",
                "imported": 2,
                "imported_by": "admin",
                "created_by_action": 1,
            },
            "seed": {
                "selected_resource": "seed.json",
                "module": "notes",
                "imported": 1,
                "imported_by": "admin",
                "created_by_action": 1,
            },
        },
        "installed_consumer_test": {
            "mode": "isolated pytest against installed distributions",
            "counts": {"tests": 3, "errors": 0, "failures": 0, "skipped": 0},
        },
        "memory_corpus": {
            "backend": "memory-store",
            "corpus_version": 13,
            "roles": ["reader", "provider"],
            "counts": {
                "passed": 2,
                "failed": 0,
                "harness_error": 0,
                "host_specific": 0,
                "limit": 0,
            },
            "newer_corpus": False,
            "results": [
                {"case": "read.one", "status": "passed"},
                {"case": "write.two", "status": "passed"},
            ],
            "skipped": ["schema.unavailable"],
        },
    }


def make_inputs(root: Path) -> dict[str, Any]:
    bundle, wheel_sha, npm_sha, npm_resources = make_build_bundle(root)
    links = root / "find-links.html"
    cohort_value = cohort(wheel_sha, "0" * 64)
    links_raw = (
        "<html><body>"
        + "".join(
            f'<a href="{item["url"]}#sha256={item["sha256"]}">{item["filename"]}</a>'
            for item in cohort_value["native_wheels"]
        )
        + "</body></html>"
    ).encode()
    links.write_bytes(links_raw)
    cohort_value["find_links"]["sha256"] = sha(links_raw)
    cohort_path = root / "cohort.json"
    cohort_raw = write_json(cohort_path, cohort_value)
    binding_path = root / "binding.json"
    binding = {
        "schema_version": 1,
        "status": "bound",
        "wheel": {
            "path": f"/private/{WHEEL_NAME}",
            "name": "arras",
            "version": VERSION,
            "sha256": wheel_sha,
        },
        "find_links": {"sha256": sha(links_raw)},
        "bound_manifest": {"sha256": sha(cohort_raw)},
    }
    write_json(binding_path, binding)
    native_path = root / "native.json"
    write_json(
        native_path, native_receipt(cohort_value, sha(cohort_raw), sha(links_raw), wheel_sha)
    )
    ui_path = root / "qualification-linux.json"
    inventory = {
        "schema": "arras.ui.canonical-acceptance-inventory.v1",
        "specs": SPECS,
        "expectedCounts": COUNTS,
    }
    inventory_raw = (json.dumps(inventory, sort_keys=True) + "\n").encode()
    resources_path = root / "acceptance-resources-neutral-theme.json"
    resources_path.write_bytes(npm_resources)
    inventory_path = root / "acceptance-inventory-neutral-theme.json"
    inventory_path.write_bytes(inventory_raw)
    projects = [
        {
            "name": name,
            "expected": COUNTS[name],
            "discovered": COUNTS[name],
            "passed": COUNTS[name],
            "failed": 0,
            "skipped": 0,
        }
        for name in ("chromium", "schema-admin", "browser")
    ]
    summary = {
        "schema": "arras.ui.canonical-playwright-summary.v1",
        "status": "passed",
        "platform": "linux",
        "projects": projects,
        "expectedTestCount": sum(cast(int, row["expected"]) for row in projects),
        "unexpectedSkips": 0,
    }
    summary_raw = (json.dumps(summary, sort_keys=True) + "\n").encode()
    summary_path = root / "playwright-summary-neutral-theme.json"
    summary_path.write_bytes(summary_raw)
    sidecars = {
        "acceptance-inventory-neutral-theme.json": inventory_raw,
        "acceptance-resources-neutral-theme.json": npm_resources,
        "playwright-summary-neutral-theme.json": summary_raw,
    }
    ui_value = ui_receipt(wheel_sha, npm_sha, sidecars)
    outer_cohort = ui_value["cohort"]
    ui_value["acceptance_suite"]["cohort"] = {
        "wheelSha256": outer_cohort["wheel"]["sha256"],
        "npmSha256": outer_cohort["npm"]["sha256"],
        "themeSha256": outer_cohort["theme"]["sha256"],
        "runnerSha256": outer_cohort["runner"]["sha256"],
    }
    write_json(ui_path, ui_value)
    consumer_path = root / "consumer.json"
    write_json(consumer_path, consumer_receipt(wheel_sha))
    return {
        "build_bundle": bundle,
        "native_receipt_path": native_path,
        "binding_path": binding_path,
        "cohort_path": cohort_path,
        "index_path": links,
        "ui_path": ui_path,
        "consumer_path": consumer_path,
        "expected_version": VERSION,
        "expected_wheel": WHEEL_NAME,
        "expected_wheel_sha256": wheel_sha,
        "output_dir": root / "release",
        "wheel_sha": wheel_sha,
        "npm_sha": npm_sha,
    }


def make_build_bundle(root: Path) -> tuple[Path, str, str, bytes]:
    bundle = root / "build"
    bundle.mkdir(parents=True)
    npm, npm_resources = make_npm()
    wheel = bundle / WHEEL_NAME
    make_wheel(wheel, npm)
    sdist = bundle / f"arras-{VERSION}.tar.gz"
    make_sdist(sdist)
    npm_path = bundle / f"documentdrivendx-arras-ui-{VERSION}.tgz"
    npm_path.write_bytes(npm)
    wheel_sha, sdist_sha, npm_sha = (sha(path.read_bytes()) for path in (wheel, sdist, npm_path))
    write_json(
        bundle / "distribution-verification.json",
        {
            "source_wheel": {"file": WHEEL_NAME, "sha256": wheel_sha},
            "sdist": {"file": sdist.name, "sha256": sdist_sha},
            "sdist_rebuilt_wheel": {"file": WHEEL_NAME, "sha256": "9" * 64},
            "npm": {"file": npm_path.name, "sha256": npm_sha, "exact_between_wheels": True},
            "qualification": ["artifact-inspected", "installed-consumer-tested"],
        },
    )
    write_json(bundle / "doctor-installed.json", doctor_receipt(wheel_sha, npm_sha))
    selected_names = [
        WHEEL_NAME,
        sdist.name,
        npm_path.name,
        "distribution-verification.json",
        "doctor-installed.json",
    ]
    (bundle / "SHA256SUMS").write_text(
        "".join(f"{sha((bundle / name).read_bytes())}  {name}\n" for name in selected_names),
        encoding="ascii",
    )
    return bundle, wheel_sha, npm_sha, npm_resources


def test_assemble_links_exact_assets_and_regenerates_complete_sums(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    aggregate = assembler.assemble(
        **{
            key: value
            for key, value in inputs.items()
            if key.endswith("path")
            or key
            in {
                "build_bundle",
                "expected_version",
                "expected_wheel",
                "expected_wheel_sha256",
                "output_dir",
            }
        }
    )
    output = inputs["output_dir"]
    expected = {
        WHEEL_NAME,
        f"arras-{VERSION}.tar.gz",
        f"documentdrivendx-arras-ui-{VERSION}.tgz",
        "distribution-verification.json",
        "doctor-installed.json",
        "native-qualification.json",
        "native-cohort-binding.json",
        "native-cohort.json",
        "native-find-links.html",
        "ui-qualification.json",
        "consumer-qualification.json",
        "release-evidence.json",
        "acceptance-inventory-neutral-theme.json",
        "acceptance-resources-neutral-theme.json",
        "playwright-summary-neutral-theme.json",
        "SHA256SUMS",
    }
    assert {path.name for path in output.iterdir()} == expected
    assert aggregate["gates"]["public_download"]["status"] == "not_run_at_assembly"
    assert aggregate["release_artifacts"]["sdist"]["filename"] == f"arras-{VERSION}.tar.gz"
    assert aggregate["qualification_scope"]["doctor_runtime"] == {
        "os": "darwin",
        "architecture": "arm64",
        "release": "27.0.0",
        "python": "3.13.16",
    }
    for name in (
        WHEEL_NAME,
        f"arras-{VERSION}.tar.gz",
        f"documentdrivendx-arras-ui-{VERSION}.tgz",
        "distribution-verification.json",
        "doctor-installed.json",
    ):
        assert (output / name).read_bytes() == (inputs["build_bundle"] / name).read_bytes()
    assert b"secret raw log" not in (output / "native-qualification.json").read_bytes()
    lines = (output / "SHA256SUMS").read_text().splitlines()
    assert {line.split("  ", 1)[1] for line in lines} == expected - {"SHA256SUMS"}
    assert all(
        line.split("  ", 1)[0] == sha((output / line.split("  ", 1)[1]).read_bytes())
        for line in lines
    )
    raw_files = {
        "native-cohort.json": inputs["cohort_path"],
        "native-find-links.html": inputs["index_path"],
        **{
            name: inputs["ui_path"].parent / name
            for name in (
                "acceptance-inventory-neutral-theme.json",
                "acceptance-resources-neutral-theme.json",
                "playwright-summary-neutral-theme.json",
            )
        },
    }
    for name, path in raw_files.items():
        assert (output / name).read_bytes() == path.read_bytes()
    component_hashes = json.loads((output / "release-evidence.json").read_bytes())[
        "published_components"
    ]
    assert set(component_hashes) == expected - {
        WHEEL_NAME,
        f"arras-{VERSION}.tar.gz",
        f"documentdrivendx-arras-ui-{VERSION}.tgz",
        "distribution-verification.json",
        "doctor-installed.json",
        "release-evidence.json",
        "SHA256SUMS",
    }
    assert all(
        component_hashes[name] == sha((output / name).read_bytes()) for name in component_hashes
    )
    with pytest.raises(assembler.AssemblyError, match="output directory must be new"):
        assembler.assemble(
            **{
                key: value
                for key, value in inputs.items()
                if key.endswith("path")
                or key
                in {
                    "build_bundle",
                    "expected_version",
                    "expected_wheel",
                    "expected_wheel_sha256",
                    "output_dir",
                }
            }
        )


def test_native_receipt_rejects_wrong_identity_failure_and_duplicate_ids(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    cohort_value = json.loads(inputs["cohort_path"].read_text())
    cohort_hash = sha(inputs["cohort_path"].read_bytes())
    index_hash = sha(inputs["index_path"].read_bytes())
    receipt = json.loads(inputs["native_receipt_path"].read_text())
    valid = assembler._validate_native(
        receipt, cohort_value, cohort_hash, index_hash, inputs["wheel_sha"], VERSION
    )
    assert valid["status"] == "passed"
    controls: list[dict[str, Any]] = []
    malformed = json.loads(json.dumps(receipt))
    malformed["inputs"]["cohort"]["sha256"] = "f" * 64
    controls.append(malformed)
    malformed = json.loads(json.dumps(receipt))
    malformed["status"] = "failed"
    controls.append(malformed)
    malformed = json.loads(json.dumps(receipt))
    malformed["corpus"]["results"][1]["case"] = malformed["corpus"]["results"][0]["case"]
    controls.append(malformed)
    for item in controls:
        with pytest.raises(assembler.AssemblyError):
            assembler._validate_native(
                item, cohort_value, cohort_hash, index_hash, inputs["wheel_sha"], VERSION
            )


def test_native_and_memory_corpus_must_share_applicability(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    native = assembler._validate_native(
        json.loads(inputs["native_receipt_path"].read_text()),
        json.loads(inputs["cohort_path"].read_text()),
        sha(inputs["cohort_path"].read_bytes()),
        sha(inputs["index_path"].read_bytes()),
        inputs["wheel_sha"],
        VERSION,
    )
    consumer = assembler._validate_consumer(
        json.loads(inputs["consumer_path"].read_text()),
        WHEEL_NAME,
        inputs["wheel_sha"],
        VERSION,
    )
    assembler._validate_corpus_parity(native["corpus"], consumer["memory_corpus"])
    consumer["memory_corpus"]["applicable_case_ids"].pop()
    with pytest.raises(assembler.AssemblyError, match="same source cohort"):
        assembler._validate_corpus_parity(native["corpus"], consumer["memory_corpus"])


def test_ui_requires_full_suite_and_exact_cohort(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    ui = json.loads(inputs["ui_path"].read_text())
    sidecars = {
        name: (inputs["ui_path"].parent / name).read_bytes()
        for name in (
            "acceptance-inventory-neutral-theme.json",
            "acceptance-resources-neutral-theme.json",
            "playwright-summary-neutral-theme.json",
        )
    }
    passed, _ = assembler._validate_ui(
        ui,
        inputs["ui_path"],
        WHEEL_NAME,
        inputs["wheel_sha"],
        inputs["npm_sha"],
        VERSION,
        sidecars["acceptance-resources-neutral-theme.json"],
    )
    assert passed["status"] == "passed"
    outer_cohort = ui["cohort"]
    suite_cohort = ui["acceptance_suite"]["cohort"]
    malformed_cohorts = [
        outer_cohort,
        {**suite_cohort, "extra": "0" * 64},
        {key: value for key, value in suite_cohort.items() if key != "runnerSha256"},
        {**suite_cohort, "wheelSha256": 1},
        {**suite_cohort, "npmSha256": True},
        {**suite_cohort, "themeSha256": "not-a-digest"},
        {**suite_cohort, "wheelSha256": "0" * 64},
        {**suite_cohort, "npmSha256": "0" * 64},
        {**suite_cohort, "themeSha256": "0" * 64},
        {**suite_cohort, "runnerSha256": "0" * 64},
    ]
    for malformed_cohort in malformed_cohorts:
        altered_ui = json.loads(json.dumps(ui))
        altered_ui["acceptance_suite"]["cohort"] = malformed_cohort
        with pytest.raises(assembler.AssemblyError):
            assembler._validate_ui(
                altered_ui,
                inputs["ui_path"],
                WHEEL_NAME,
                inputs["wheel_sha"],
                inputs["npm_sha"],
                VERSION,
                sidecars["acceptance-resources-neutral-theme.json"],
            )
    summary_path = inputs["ui_path"].parent / "playwright-summary-neutral-theme.json"
    summary = json.loads(sidecars["playwright-summary-neutral-theme.json"])
    for target in ("summary", "project"):
        altered_summary = json.loads(json.dumps(summary))
        if target == "summary":
            altered_summary["raw_log"] = "private diagnostic"
        else:
            altered_summary["projects"][0]["raw_log"] = "private diagnostic"
        raw = (json.dumps(altered_summary, sort_keys=True) + "\n").encode()
        summary_path.write_bytes(raw)
        altered_ui = json.loads(inputs["ui_path"].read_text())
        altered_ui["acceptance_suite"]["playwright"]["sha256"] = sha(raw)
        with pytest.raises(assembler.AssemblyError, match="exactly"):
            assembler._validate_ui(
                altered_ui,
                inputs["ui_path"],
                WHEEL_NAME,
                inputs["wheel_sha"],
                inputs["npm_sha"],
                VERSION,
                sidecars["acceptance-resources-neutral-theme.json"],
            )
    summary_path.write_bytes(sidecars["playwright-summary-neutral-theme.json"])
    ui["acceptance_suite"]["projects"][0]["skipped"] = 1
    with pytest.raises(assembler.AssemblyError, match="failed or skipped"):
        assembler._validate_ui(
            ui,
            inputs["ui_path"],
            WHEEL_NAME,
            inputs["wheel_sha"],
            inputs["npm_sha"],
            VERSION,
            sidecars["acceptance-resources-neutral-theme.json"],
        )
    ui = json.loads(inputs["ui_path"].read_text())
    del ui["acceptance_suite"]
    with pytest.raises(assembler.AssemblyError, match="must be a JSON object"):
        assembler._validate_ui(
            ui,
            inputs["ui_path"],
            WHEEL_NAME,
            inputs["wheel_sha"],
            inputs["npm_sha"],
            VERSION,
            sidecars["acceptance-resources-neutral-theme.json"],
        )


def test_index_rejects_active_content_unselected_urls_and_credentials(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    cohort_value = json.loads(inputs["cohort_path"].read_text())
    original = inputs["index_path"].read_bytes()
    assembler._validate_index(original, cohort_value)
    for raw in (
        original + b"<script>alert(1)</script>",
        original.replace(
            b"</body>",
            b'<a href="https://elsewhere.invalid/file.whl#sha256=' + b"c" * 64 + b'"></a></body>',
        ),
    ):
        with pytest.raises(assembler.AssemblyError):
            assembler._validate_index(raw, cohort_value)


def test_assembler_refuses_duplicate_json_output_alias_and_old_doctor(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    duplicate = inputs["ui_path"]
    duplicate.write_text('{"schema":1,"schema":1}')
    with pytest.raises(assembler.AssemblyError, match="duplicate JSON key"):
        assembler.assemble(
            **{
                key: value
                for key, value in inputs.items()
                if key.endswith("path")
                or key
                in {
                    "build_bundle",
                    "expected_version",
                    "expected_wheel",
                    "expected_wheel_sha256",
                    "output_dir",
                }
            }
        )

    second = tmp_path / "second"
    second_inputs = make_inputs(second)
    (second_inputs["build_bundle"] / "doctor-installed.json").write_text(
        json.dumps(
            {
                "schema": "arras.ui.doctor-installed-qualification.v1",
                "wheel": {
                    "filename": WHEEL_NAME,
                    "version": VERSION,
                    "sha256": second_inputs["wheel_sha"],
                },
            }
        )
    )
    sums = second_inputs["build_bundle"] / "SHA256SUMS"
    lines: list[str] = []
    for name in (
        WHEEL_NAME,
        f"arras-{VERSION}.tar.gz",
        f"documentdrivendx-arras-ui-{VERSION}.tgz",
        "distribution-verification.json",
        "doctor-installed.json",
    ):
        lines.append(f"{sha((second_inputs['build_bundle'] / name).read_bytes())}  {name}\n")
    sums.write_text("".join(lines))
    with pytest.raises(assembler.AssemblyError, match="overall passed status"):
        assembler.assemble(
            **{
                key: value
                for key, value in second_inputs.items()
                if key.endswith("path")
                or key
                in {
                    "build_bundle",
                    "expected_version",
                    "expected_wheel",
                    "expected_wheel_sha256",
                    "output_dir",
                }
            }
        )


def test_json_bounds_and_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"a":1,"a":2}')
    with pytest.raises(assembler.AssemblyError, match="duplicate JSON key"):
        assembler._load_json(path)
    with pytest.raises(assembler.AssemblyError, match="non-JSON numeric"):
        assembler._inputs.parse_json_object(b'{"unused":NaN}', "synthetic evidence")
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(assembler.AssemblyError, match="symlink"):
        assembler._input_file(link, 100, "test")


def test_npm_resources_require_exact_specs_and_all_spec_files() -> None:
    with tarfile.open(fileobj=io.BytesIO(), mode="w:gz") as archive:
        resources = resources_doc()
        resources["specs"] = [*SPECS[:-1], "invented.spec.ts"]
        with pytest.raises(assembler.AssemblyError, match="canonical specs"):
            assembler._inputs._validate_resource_manifest(resources, {}, archive)

        resources = resources_doc()
        resources["files"].pop("acceptance/e2e/visual.spec.ts")
        with pytest.raises(assembler.AssemblyError, match="omit a canonical UI spec"):
            assembler._inputs._validate_resource_manifest(resources, {}, archive)


def test_bounded_reader_refuses_fifo_without_waiting(tmp_path: Path) -> None:
    import os

    if not hasattr(os, "mkfifo"):
        pytest.skip("named pipes are unavailable on this platform")
    pipe = tmp_path / "evidence.fifo"
    os.mkfifo(pipe)
    with pytest.raises(assembler.AssemblyError, match="regular file"):
        assembler._input_file(pipe, 1024, "test")


def test_doctor_receipt_must_match_trusted_probe_builder(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    path = inputs["build_bundle"] / "doctor-installed.json"
    value = json.loads(path.read_text())
    value["generated_probe_sha256"] = "f" * 64
    with pytest.raises(assembler.AssemblyError, match="trusted literal builder"):
        assembler._validate_doctor(
            value, VERSION, WHEEL_NAME, inputs["wheel_sha"], inputs["npm_sha"]
        )
    path.write_text(json.dumps(doctor_receipt(inputs["wheel_sha"], inputs["npm_sha"])))
    value = json.loads(path.read_text())
    del value["telemetry_probes"]["phases"]["worker_backed_asgi_operate"]
    with pytest.raises(assembler.AssemblyError, match="phase coverage"):
        assembler._validate_doctor(
            value, VERSION, WHEEL_NAME, inputs["wheel_sha"], inputs["npm_sha"]
        )
    value = doctor_receipt(inputs["wheel_sha"], inputs["npm_sha"])
    value["telemetry_probes"]["phases"]["mcp_frame"]["service_name"] = "extension-alpha"
    with pytest.raises(assembler.AssemblyError, match="misrouted"):
        assembler._validate_doctor(
            value, VERSION, WHEEL_NAME, inputs["wheel_sha"], inputs["npm_sha"]
        )
    value = doctor_receipt(inputs["wheel_sha"], inputs["npm_sha"])
    value["telemetry_probes"]["phases"]["direct"]["events"] = 0
    with pytest.raises(assembler.AssemblyError, match="phase .* malformed"):
        assembler._validate_doctor(
            value, VERSION, WHEEL_NAME, inputs["wheel_sha"], inputs["npm_sha"]
        )
    value = doctor_receipt(inputs["wheel_sha"], inputs["npm_sha"])
    value["tripwire_report"]["positive"]["ok"] = 1
    with pytest.raises(assembler.AssemblyError, match="booleans are malformed"):
        assembler._validate_doctor(
            value, VERSION, WHEEL_NAME, inputs["wheel_sha"], inputs["npm_sha"]
        )
    value = doctor_receipt(inputs["wheel_sha"], inputs["npm_sha"])
    value["telemetry_probes"]["false_pass_controls"].remove(
        "finish-time ambient-context misrouting"
    )
    with pytest.raises(assembler.AssemblyError, match="false-pass controls"):
        assembler._validate_doctor(
            value, VERSION, WHEEL_NAME, inputs["wheel_sha"], inputs["npm_sha"]
        )


def test_doctor_runtime_is_validated_and_reported_separately(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    value = doctor_receipt(inputs["wheel_sha"], inputs["npm_sha"])
    runtime = assembler._validate_doctor(
        value, VERSION, WHEEL_NAME, inputs["wheel_sha"], inputs["npm_sha"]
    )
    assert runtime == {
        "os": "darwin",
        "architecture": "arm64",
        "release": "27.0.0",
        "python": "3.13.16",
    }
    windows_runtime = assembler._inputs.doctor_runtime(
        {
            **value,
            "platform": {"os": "win32", "architecture": "AMD64", "release": "10"},
        }
    )
    assert windows_runtime["architecture"] == "AMD64"
    for platform in (
        {"os": "posix", "architecture": "arm64", "release": "27.0.0"},
        {"os": "darwin", "architecture": "mips", "release": "27.0.0"},
    ):
        with pytest.raises(assembler.AssemblyError, match="doctor runtime"):
            assembler._inputs.doctor_runtime({**value, "platform": platform})
    with pytest.raises(assembler.AssemblyError, match="doctor.python"):
        assembler._inputs.doctor_runtime({**value, "python": ""})
