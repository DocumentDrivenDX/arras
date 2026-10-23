from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import io
import json
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT_DIR = ROOT / ".github/scripts"
Mutation = Callable[[dict[str, Any]], object]


def load_script(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


receipt_gate = load_script("umf_admission_receipt_gate", SCRIPT_DIR / "_umf_admission_receipt.py")
assembler = load_script("release_assembler_for_umf", SCRIPT_DIR / "assemble_release_evidence.py")
assets = load_script("release_assets_for_umf", SCRIPT_DIR / "verify_public_release_assets.py")


def passing_receipt() -> dict[str, Any]:
    corpus_path = ROOT / "tests/fixtures/umf-core-reference/current-conformance.json"
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    ids = [case["id"] for case in corpus["cases"]]
    tool_sha = hashlib.sha256((ROOT / "tools/verify_umf_admission.py").read_bytes()).hexdigest()
    probe_sha = hashlib.sha256((ROOT / "tools/_umf_admission_probe.py").read_bytes()).hexdigest()
    base_controls = {
        "legacy_registration_document_and_empty_read": True,
        "base_has_no_umf_distribution": True,
        "base_imported_no_umf": True,
        "admission_refuses_missing_engine": True,
        "projection_refuses_missing_engine": True,
        "selected_host_refuses_without_fallback": True,
    }
    extra_controls = {
        "public_admission_and_projection": True,
        "metadata_registration_readback_original_bytes": True,
        "metadata_description_immutable_and_empty_read": True,
        "metadata_direct_write_refused_without_effects": True,
        "valid_but_unsupported_profile_control": True,
        "valid_incomplete_unknown_source_control": True,
        "source_only_repr_privacy": True,
        "default_profile_does_not_auto_detect": True,
        "unqualified_provider_does_not_accept": True,
        "metadata_profile_transition_refused": True,
    }
    corpus_result = {
        "status": "passed",
        "fixture_sha256": receipt_gate._CORPUS_SHA,
        "case_count": 139,
        "unique_id_count": 139,
        "ordered_case_ids": ids,
        "reference_matches": 139,
        "empty_registry_matches": 139,
        "skipped": 0,
    }
    return {
        "schema": "arras.umf-admission-installed/1",
        "status": "passed",
        "qualification_scope": "installed-wheel-umf-admission/1",
        "qualification_phase": "release-build",
        "arras_wheel": {
            "filename": "arras-0.6.0-py3-none-any.whl",
            "version": "0.6.0",
            "sha256": "a" * 64,
            "record_entries": 412,
        },
        "umf_wheel": {
            "filename": "umf_core-0.10.0-py3-none-any.whl",
            "version": "0.10.0",
            "sha256": receipt_gate._UMF_SHA,
            "url": receipt_gate._UMF_URL,
            "source_mode": "pinned-public-url",
            "record_entries": 26,
        },
        "tool_sha256": tool_sha,
        "fixed_probe_sha256": probe_sha,
        "fixtures": {
            "official_corpus_sha256": receipt_gate._CORPUS_SHA,
            "official_corpus_case_count": 139,
            "ordered_case_ids": ids,
            "metadata_fixture_sha256": receipt_gate._METADATA_SHA,
        },
        "runtime": {
            "version": "3.11.9",
            "implementation": "CPython",
            "platform": "linux",
            "machine": "x86_64",
        },
        "environments": {
            "base": {
                "status": "passed",
                "mode": "base",
                "arras_version": "0.6.0",
                "controls": base_controls,
                "installed_distributions": {"arras": "0.6.0"},
                "payload": {"arras_exact_files": 412},
                "import_origins": {"arras": "arras/__init__.py"},
                "pth_reuse": False,
                "source_aliases": False,
            },
            "extra": {
                "status": "passed",
                "mode": "extra",
                "arras_version": "0.6.0",
                "umf_version": "0.10.0",
                "umf_sha256": receipt_gate._UMF_SHA,
                "direct_url_verified": True,
                "controls": extra_controls,
                "corpus": copy.deepcopy(corpus_result),
                "installed_distributions": {"arras": "0.6.0", "umf-core": "0.10.0"},
                "payload": {"arras_exact_files": 412, "umf_exact_files": 26},
                "import_origins": {"arras": "arras/__init__.py", "umf": "umf/__init__.py"},
                "pth_reuse": False,
                "source_aliases": False,
            },
        },
        "corpus": corpus_result,
        "controls": {"base": base_controls, "extra": extra_controls},
        "cleanup": {"completed": True, "fresh_environments": 2, "shared_site_packages": False},
        "limitations": [
            "This proves only the named installed wheel and runtime.",
            "This does not qualify native Truss, browser, UI, or production behavior.",
        ],
    }


def validate(value: object) -> dict[str, Any]:
    return receipt_gate.validate_receipt(
        value,
        version="0.6.0",
        wheel_name="arras-0.6.0-py3-none-any.whl",
        wheel_sha256="a" * 64,
        phase="release-build",
        repository=ROOT,
    )


def test_release_umf_receipt_projects_only_safe_exact_wheel_proof() -> None:
    projected = validate(passing_receipt())
    assert projected["status"] == "passed"
    assert projected["arras_wheel"] == {
        "filename": "arras-0.6.0-py3-none-any.whl",
        "version": "0.6.0",
        "sha256": "a" * 64,
    }
    assert projected["corpus"]["case_count"] == 139
    assert projected["controls"] == {"base": 6, "extra": 10, "cleanup": 2}
    assert 'ordered_case_ids":' not in json.dumps(projected)
    assert "limitations" not in projected
    assert "selector_sha256" not in projected


def test_new_historical_receipt_selector_binding_is_verified_and_projected() -> None:
    row = passing_receipt()
    row["selector_sha256"] = hashlib.sha256(
        (ROOT / "tools/_umf_sdk_cohorts.py").read_bytes()
    ).hexdigest()
    projected = validate(row)
    assert projected["selector_sha256"] == row["selector_sha256"]

    row["selector_sha256"] = "0" * 64
    with pytest.raises(receipt_gate.AdmissionReceiptError, match="selector digest"):
        validate(row)


def _native_receipt(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    cohorts = receipt_gate._cohort_module()
    native = cohorts.SDKCohort(
        "synthetic-umf-core-0.10.1-macos-arm64",
        "0.10.1",
        "0.10.0",
        "darwin",
        "arm64",
        "umf_core-0.10.1-cp311-abi3-macosx_11_0_arm64.whl",
        "https://github.com/example/umf/releases/download/test/umf_core-0.10.1-cp311-abi3-macosx_11_0_arm64.whl",
        "c" * 64,
    )
    monkeypatch.setattr(cohorts, "KNOWN_COHORTS", (*cohorts.KNOWN_COHORTS, native))
    row = passing_receipt()
    row["umf_wheel"].update(
        filename=native.filename,
        version=native.distribution_version,
        sha256=native.sha256,
        url=native.url,
    )
    row["selector_sha256"] = hashlib.sha256(
        (ROOT / "tools/_umf_sdk_cohorts.py").read_bytes()
    ).hexdigest()
    row["runtime"].update(platform="darwin", machine="arm64")
    extra = row["environments"]["extra"]
    extra["umf_version"] = native.distribution_version
    extra["umf_sha256"] = native.sha256
    extra["installed_distributions"]["umf-core"] = native.distribution_version
    return row


def test_native_cohort_receipt_requires_selector_binding_and_observed_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _native_receipt(monkeypatch)
    projected = validate(row)
    assert projected["umf_wheel"]["version"] == "0.10.1"
    assert projected["selector_sha256"] == row["selector_sha256"]
    assert "SDK distribution 0.10.1" in projected["qualification_scope"]
    receipt_gate.validate_public_projection(
        projected,
        version="0.6.0",
        wheel_name="arras-0.6.0-py3-none-any.whl",
        wheel_sha256="a" * 64,
    )

    missing = copy.deepcopy(row)
    missing.pop("selector_sha256")
    with pytest.raises(receipt_gate.AdmissionReceiptError, match="selector SHA"):
        validate(missing)

    wrong_runtime = copy.deepcopy(row)
    wrong_runtime["runtime"].update(platform="linux", machine="x86_64")
    with pytest.raises(receipt_gate.AdmissionReceiptError, match="runtime"):
        validate(wrong_runtime)


_RECEIPT_MUTATIONS: list[Mutation] = [
    lambda row: row.pop("arras_wheel"),
    lambda row: row["arras_wheel"].update(filename="arras-0.5.1-py3-none-any.whl"),
    lambda row: row["umf_wheel"].update(sha256="0" * 64),
    lambda row: row["fixtures"].update(official_corpus_sha256="0" * 64),
    lambda row: row["corpus"].update(case_count=138),
    lambda row: row["corpus"].update(skipped=1),
    lambda row: row["corpus"].update(case_count=139.0),
    lambda row: row["corpus"].update(skipped=False),
    lambda row: row["environments"]["extra"].update(corpus={"status": "failed"}),
    lambda row: row["environments"]["extra"]["corpus"].update(case_count=139.0),
    lambda row: row["environments"]["extra"].pop("import_origins"),
    lambda row: row["environments"]["extra"]["import_origins"].update(umf="/private/tmp/SENTINEL"),
    lambda row: row["environments"]["base"]["installed_distributions"].clear(),
    lambda row: row["environments"]["extra"]["installed_distributions"].update(arras="0.5.1"),
    lambda row: row["runtime"].update(platform="/private/tmp/SENTINEL"),
    lambda row: row["controls"]["base"].update(base_imported_no_umf=1),
    lambda row: row["cleanup"].update(completed=False),
    lambda row: row.update(tool_sha256="0" * 64),
]


@pytest.mark.parametrize(
    "mutate",
    _RECEIPT_MUTATIONS,
    ids=[
        "missing-wheel",
        "foreign-wheel",
        "foreign-sdk",
        "fixture-digest",
        "wrong-count",
        "skipped-case",
        "fractional-count",
        "boolean-skip-count",
        "contradictory-extra-corpus",
        "extra-corpus-fractional-count",
        "missing-import-origin",
        "unsafe-import-origin",
        "missing-arras-distribution",
        "wrong-arras-version",
        "unsafe-runtime-platform",
        "integer-control-flag",
        "cleanup",
        "tool-digest",
    ],
)
def test_release_umf_receipt_rejects_tampering(mutate: Any) -> None:
    changed = copy.deepcopy(passing_receipt())
    mutate(changed)
    with pytest.raises(receipt_gate.AdmissionReceiptError):
        validate(changed)


def test_release_umf_receipt_is_versioned_and_phase_bound() -> None:
    assert receipt_gate.required_for_version("0.5.1") is False
    assert receipt_gate.required_for_version("0.6.0") is True
    row = passing_receipt()
    row["qualification_phase"] = "public-download"
    with pytest.raises(receipt_gate.AdmissionReceiptError, match="phase"):
        validate(row)
    with pytest.raises(receipt_gate.AdmissionReceiptError, match="not part"):
        receipt_gate.validate_receipt(
            passing_receipt(),
            version="0.5.1",
            wheel_name="arras-0.5.1-py3-none-any.whl",
            wheel_sha256="a" * 64,
            phase="release-build",
            repository=ROOT,
        )


def test_assembler_cannot_omit_or_add_the_umf_receipt_for_wrong_release_version() -> None:
    assert assembler._read_umf_admission(
        "0.5.1",
        None,
        wheel_name="arras-0.5.1-py3-none-any.whl",
        wheel_sha="a" * 64,
        selected_inputs={},
    ) == (None, None)
    with pytest.raises(assembler.AssemblyError, match="presence"):
        assembler._read_umf_admission(
            "0.6.0",
            None,
            wheel_name="arras-0.6.0-py3-none-any.whl",
            wheel_sha="a" * 64,
            selected_inputs={},
        )


def test_public_umf_projection_rejects_wheel_sdk_and_count_tampering() -> None:
    projected = validate(passing_receipt())
    assert (
        receipt_gate.validate_public_projection(
            projected,
            version="0.6.0",
            wheel_name="arras-0.6.0-py3-none-any.whl",
            wheel_sha256="a" * 64,
        )
        == projected
    )
    projection_mutations: tuple[Mutation, ...] = (
        lambda value: value["arras_wheel"].update(sha256="0" * 64),
        lambda value: value["umf_wheel"].update(url="https://example.invalid/wheel.whl"),
        lambda value: value["corpus"].update(skipped=1),
        lambda value: value["corpus"].update(ordered_case_ids_sha256="0" * 64),
        lambda value: value["controls"].update(extra=True),
        lambda value: value["runtime"].update(platform="/private/tmp/SENTINEL"),
        lambda value: value["controls"].update(extra=9),
    )
    for mutate in projection_mutations:
        changed = copy.deepcopy(projected)
        mutate(changed)
        with pytest.raises(receipt_gate.AdmissionReceiptError):
            receipt_gate.validate_public_projection(
                changed,
                version="0.6.0",
                wheel_name="arras-0.6.0-py3-none-any.whl",
                wheel_sha256="a" * 64,
            )


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', '{"a":NaN}'])
def test_strict_json_rejects_duplicate_keys_and_non_finite_values(raw: str) -> None:
    with pytest.raises(receipt_gate.AdmissionReceiptError):
        receipt_gate.strict_json_loads(raw)


def test_public_inventory_keeps_v051_and_adds_required_v060_receipt() -> None:
    old = assets._expected_names("0.5.1", "arras-0.5.1-py3-none-any.whl")
    current = assets._expected_names("0.6.0", "arras-0.6.0-py3-none-any.whl")
    assert len(old) == 15 and "umf-admission-installed.json" not in old
    assert len(current) == 16 and "umf-admission-installed.json" in current


def _write_v2_bundle(directory: Path, proof: dict[str, Any] | None = None) -> tuple[str, str]:
    version = "0.6.0"
    wheel = f"arras-{version}-py3-none-any.whl"
    sdist = f"arras-{version}.tar.gz"
    npm = f"documentdrivendx-arras-ui-{version}.tgz"
    names = assets._expected_names(version, wheel)
    directory.mkdir()
    payloads = {name: f"fixture:{name}".encode() for name in names}
    wheel_buffer = io.BytesIO()
    with zipfile.ZipFile(wheel_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"arras/ui/npm/{npm}", b"npm bytes")
    payloads[wheel] = wheel_buffer.getvalue()
    payloads[sdist] = b"sdist bytes"
    payloads[npm] = b"npm bytes"
    wheel_sha = hashlib.sha256(payloads[wheel]).hexdigest()
    proof_value = validate(passing_receipt()) if proof is None else proof
    if proof is None:
        proof_value["arras_wheel"]["sha256"] = wheel_sha
    payloads["umf-admission-installed.json"] = (
        json.dumps(proof_value, sort_keys=True) + "\n"
    ).encode()
    for name, raw in payloads.items():
        (directory / name).write_bytes(raw)
    component_names = assets._PUBLISHED_COMPONENTS | {"umf-admission-installed.json"}
    components = {name: hashlib.sha256(payloads[name]).hexdigest() for name in component_names}
    aggregate = {
        "schema_version": 2,
        "status": "passed",
        "version": version,
        "release_artifacts": {
            "wheel": {"filename": wheel, "sha256": wheel_sha},
            "sdist": {"filename": sdist, "sha256": hashlib.sha256(payloads[sdist]).hexdigest()},
            "npm": {"filename": npm, "sha256": hashlib.sha256(payloads[npm]).hexdigest()},
        },
        "published_components": components,
        "umf_admission": {
            "filename": "umf-admission-installed.json",
            "sha256": components["umf-admission-installed.json"],
            "qualification_phase": "release-build",
            "status": "passed",
        },
    }
    aggregate_raw = (json.dumps(aggregate, sort_keys=True) + "\n").encode()
    (directory / "release-evidence.json").write_bytes(aggregate_raw)
    payloads["release-evidence.json"] = aggregate_raw
    sums = "".join(
        f"{hashlib.sha256(payloads[name]).hexdigest()}  {name}\n" for name in sorted(names)
    ).encode("ascii")
    (directory / "SHA256SUMS").write_bytes(sums)
    return wheel_sha, hashlib.sha256(sums).hexdigest()


def test_v2_bundle_binds_umf_receipt_and_exact_versioned_inventory(tmp_path: Path) -> None:
    bundle = tmp_path / "v060"
    wheel_sha, _ = _write_v2_bundle(bundle)
    sums_raw, entries = assets._validate_trusted(
        bundle, "0.6.0", "arras-0.6.0-py3-none-any.whl", wheel_sha
    )
    assert len(entries) == 16
    assert "umf-admission-installed.json" in entries
    assert (
        hashlib.sha256(sums_raw).hexdigest()
        == hashlib.sha256((bundle / "SHA256SUMS").read_bytes()).hexdigest()
    )


def test_v2_anonymous_public_plan_and_verify_require_umf_receipt(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted"
    public = tmp_path / "anonymous-download"
    public.mkdir()
    wheel_sha, sums_sha = _write_v2_bundle(trusted)
    (public / "SHA256SUMS").write_bytes((trusted / "SHA256SUMS").read_bytes())

    plan = assets.run(
        argparse.Namespace(
            phase="plan",
            trusted_dir=trusted,
            public_dir=public,
            expected_version="0.6.0",
            expected_wheel="arras-0.6.0-py3-none-any.whl",
            expected_wheel_sha256=wheel_sha,
            expected_sums_sha256=sums_sha,
            output=tmp_path / "plan.txt",
        )
    )
    assert plan == {"status": "planned", "asset_count": 16}
    for name in (trusted / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        filename = name.split("  ", maxsplit=1)[1]
        (public / filename).write_bytes((trusted / filename).read_bytes())

    result = assets.run(
        argparse.Namespace(
            phase="verify",
            trusted_dir=trusted,
            public_dir=public,
            expected_version="0.6.0",
            expected_wheel="arras-0.6.0-py3-none-any.whl",
            expected_wheel_sha256=wheel_sha,
            expected_sums_sha256=sums_sha,
            output=tmp_path / "verified.json",
        )
    )
    assert result["status"] == "passed"
    assert result["asset_count"] == 16
    assert result["npm_matches_wheel_payload"] is True
    assert (tmp_path / "verified.json").is_file()


@pytest.mark.parametrize(
    "mutation", ["foreign-wheel", "skipped-case", "wrong-sdk", "missing-proof"]
)
def test_v2_bundle_refuses_unbound_or_incomplete_umf_proof(tmp_path: Path, mutation: str) -> None:
    proof = validate(passing_receipt())
    if mutation == "foreign-wheel":
        proof["arras_wheel"]["sha256"] = "0" * 64
    elif mutation == "skipped-case":
        proof["corpus"]["skipped"] = 1
    elif mutation == "wrong-sdk":
        proof["umf_wheel"]["sha256"] = "0" * 64
    bundle = tmp_path / mutation
    wheel_sha, _ = _write_v2_bundle(bundle, proof=proof)
    if mutation == "missing-proof":
        (bundle / "umf-admission-installed.json").unlink()
        sums = "".join(
            f"{hashlib.sha256((bundle / name).read_bytes()).hexdigest()}  {name}\n"
            for name in sorted(
                assets._expected_names("0.6.0", "arras-0.6.0-py3-none-any.whl")
                - {"umf-admission-installed.json"}
            )
        ).encode("ascii")
        (bundle / "SHA256SUMS").write_bytes(sums)
    with pytest.raises(assets.AssetError):
        assets._validate_trusted(bundle, "0.6.0", "arras-0.6.0-py3-none-any.whl", wheel_sha)
