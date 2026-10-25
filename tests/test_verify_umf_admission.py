# SPDX-License-Identifier: MIT OR Apache-2.0
"""Offline negative controls for the installed UMF proof tool."""

from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


def _load_tool(name: str, filename: str) -> Any:
    path = Path(__file__).parents[1] / "tools" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe = _load_tool("umf_admission_probe", "_umf_admission_probe.py")
verifier = _load_tool("verify_umf_admission", "verify_umf_admission.py")

CORPUS = Path(__file__).parent / "fixtures/umf-core-reference/current-conformance.json"


def _passing_extra(ids: tuple[str, ...]) -> dict[str, Any]:
    controls = {
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
    return {
        "status": "passed",
        "mode": "extra",
        "controls": controls,
        "corpus": {
            "status": "passed",
            "case_count": 139,
            "unique_id_count": 139,
            "reference_matches": 139,
            "empty_registry_matches": 139,
            "skipped": 0,
            "ordered_case_ids": list(ids),
            "fixture_sha256": verifier.CORPUS_SHA256,
        },
        "payload": {"arras_exact_files": 32, "umf_exact_files": 18},
    }


def test_official_corpus_identity_is_ordered_and_nonempty() -> None:
    raw = CORPUS.read_bytes()
    corpus, ids = probe._validate_corpus(raw)

    assert hashlib.sha256(raw).hexdigest() == verifier.CORPUS_SHA256
    assert len(corpus["cases"]) == 139
    assert len(ids) == len(set(ids)) == 139
    assert ids[0] == corpus["cases"][0]["id"]
    assert ids[-1] == corpus["cases"][-1]["id"]


def test_corpus_rejects_duplicate_ids_and_noninteger_expectations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    corpus["cases"][1]["id"] = corpus["cases"][0]["id"]
    duplicate = json.dumps(corpus, separators=(",", ":")).encode()
    monkeypatch.setattr(probe, "CORPUS_SHA256", hashlib.sha256(duplicate).hexdigest())
    with pytest.raises(probe.VerificationError, match="duplicate-case-id"):
        probe._validate_corpus(duplicate)

    corpus["cases"][1]["id"] = "distinct-case"
    corpus["cases"][1]["valid"] = 1
    malformed = json.dumps(corpus, separators=(",", ":")).encode()
    monkeypatch.setattr(probe, "CORPUS_SHA256", hashlib.sha256(malformed).hexdigest())
    with pytest.raises(probe.VerificationError, match="invalid-case-expectation"):
        probe._validate_corpus(malformed)


def test_corpus_rejects_changed_bytes_before_using_references() -> None:
    raw = CORPUS.read_bytes() + b" "
    with pytest.raises(probe.VerificationError, match="fixture-digest-mismatch"):
        probe._validate_corpus(raw)


def test_installed_probe_requires_exact_case_ids_and_all_controls() -> None:
    _corpus, ids = probe._validate_corpus(CORPUS.read_bytes())
    candidate = _passing_extra(ids)

    verifier._validate_probe(candidate, "extra", ids)

    candidate["corpus"]["ordered_case_ids"][3] = "unknown/new-case"
    with pytest.raises(verifier.VerificationError, match="corpus-coverage-incomplete"):
        verifier._validate_probe(candidate, "extra", ids)

    candidate = _passing_extra(ids)
    candidate["corpus"]["skipped"] = 1
    with pytest.raises(verifier.VerificationError, match="corpus-coverage-incomplete"):
        verifier._validate_probe(candidate, "extra", ids)

    candidate = _passing_extra(ids)
    candidate["controls"].pop("metadata_profile_transition_refused")
    with pytest.raises(verifier.VerificationError, match="control-inventory-incomplete"):
        verifier._validate_probe(candidate, "extra", ids)

    candidate = _passing_extra(ids)
    candidate["payload"]["arras_exact_files"] = 0
    with pytest.raises(verifier.VerificationError, match="payload-parity-incomplete"):
        verifier._validate_probe(candidate, "extra", ids)


def test_wheel_record_rejects_tampered_payload_and_bad_paths() -> None:
    payload = b"official bytes"
    encoded = base64.urlsafe_b64encode(hashlib.sha256(payload).digest())
    digest = encoded.rstrip(b"=").decode("ascii")
    record = f"arras/module.py,sha256={digest},{len(payload)}\narras.dist-info/RECORD,,\n".encode()
    members = {"arras/module.py": payload, "arras.dist-info/RECORD": record}
    assert verifier._verify_record(members, record) == 2

    with pytest.raises(verifier.VerificationError, match="record-content-mismatch"):
        verifier._verify_record({**members, "arras/module.py": b"changed"}, record)
    with pytest.raises(verifier.VerificationError, match="unsafe-member-path"):
        verifier._verify_record({"../outside.py": payload}, b"../outside.py,,\n")


def test_umf_wheel_identity_requires_the_official_release_artifact(tmp_path: Path) -> None:
    wrong = tmp_path / "umf_core-0.10.0-py3-none-any.whl"
    wrong.write_bytes(b"not the released wheel")
    with pytest.raises(verifier.VerificationError, match="unexpected-official-artifact"):
        verifier._wheel_details(wrong, expected="umf")


def _write_arras_wheel(path: Path, requirements: tuple[str, ...]) -> None:
    dist_info = "arras-0.6.2.dist-info"
    metadata = (
        "Metadata-Version: 2.4\nName: arras\nVersion: 0.6.2\n"
        + "".join(f"Requires-Dist: {item}\n" for item in requirements)
        + "\n"
    ).encode()
    members = {
        f"{dist_info}/METADATA": metadata,
        f"{dist_info}/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    record_rows: list[list[str]] = []
    for name, payload in members.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest())
        record_rows.append(
            [name, f"sha256={digest.rstrip(b'=').decode('ascii')}", str(len(payload))]
        )
    record_rows.append([f"{dist_info}/RECORD", "", ""])
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(record_rows)
    members[f"{dist_info}/RECORD"] = buffer.getvalue().encode()
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)


@pytest.mark.parametrize(
    "requirement",
    [
        'umf-core==0.10.0; extra == "umf"',
        f"{verifier.UMF_REQUIREMENT}; extra == 'umf'",
    ],
)
def test_arras_wheel_accepts_only_exact_umf_extra_requirement(
    tmp_path: Path, requirement: str
) -> None:
    wheel = tmp_path / "arras-0.6.2-py3-none-any.whl"
    _write_arras_wheel(wheel, (requirement,))

    assert verifier._wheel_details(wheel, expected="arras")["version"] == "0.6.2"


@pytest.mark.parametrize(
    "requirements",
    [
        ("umf-core==0.10.1; extra == 'umf'",),
        ("umf-core>=0.10.0; extra == 'umf'",),
        (
            'umf-core==0.10.0; extra == "umf"',
            'umf-core==0.10.0; extra == "umf"',
        ),
        ("umf-core==0.10.0; extra == 'other'",),
    ],
)
def test_arras_wheel_rejects_wrong_or_duplicate_umf_requirements(
    tmp_path: Path, requirements: tuple[str, ...]
) -> None:
    wheel = tmp_path / "arras-0.6.2-py3-none-any.whl"
    _write_arras_wheel(wheel, requirements)

    with pytest.raises(verifier.VerificationError, match="optional-extra-not-pinned"):
        verifier._wheel_details(wheel, expected="arras")


def test_umf_extra_install_uses_the_same_explicit_qualified_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = tmp_path / "arras-0.6.2-py3-none-any.whl"
    wheel.write_bytes(b"staged wheel")
    calls: list[list[str]] = []

    def capture(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(verifier, "_run", capture)
    verifier._install_requirement(
        tmp_path / "python",
        wheel,
        extra=True,
        cwd=tmp_path,
        env={},
        report=tmp_path / "report.json",
    )
    verifier._install_requirement(
        tmp_path / "python",
        wheel,
        extra=False,
        cwd=tmp_path,
        env={},
        report=tmp_path / "report.json",
    )

    assert calls[0][-2:] == [f"arras[umf] @ {wheel.as_uri()}", verifier.UMF_REQUIREMENT]
    assert calls[1][-1] == f"arras @ {wheel.as_uri()}"
    assert verifier.UMF_REQUIREMENT not in calls[1]


def test_staged_artifact_identity_is_rechecked_after_install_probes(tmp_path: Path) -> None:
    staged = tmp_path / "staged.whl"
    staged.write_bytes(b"initial verified bytes")
    expected = hashlib.sha256(staged.read_bytes()).hexdigest()
    verifier._check_staged_identity(staged, expected, "arras-wheel")

    staged.write_bytes(b"changed after initial verification")
    with pytest.raises(verifier.VerificationError, match="staged-artifact-changed"):
        verifier._check_staged_identity(staged, expected, "arras-wheel")


def test_bootstrap_pth_must_match_its_installed_distribution_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import base64
    import hashlib

    site = tmp_path / "site-packages"
    site.mkdir()
    pth = site / "distutils-precedence.pth"
    payload = b"trusted bootstrap line\n"
    pth.write_bytes(payload)
    expected = base64.urlsafe_b64encode(hashlib.sha256(payload).digest())
    expected = expected.rstrip(b"=").decode("ascii")
    entry: Any = SimpleNamespace(hash=SimpleNamespace(mode="sha256", value=expected))

    class DistributionStub:
        files: list[Any] = [entry]

        def locate_file(self, _entry: Any) -> Path:
            return pth

    distribution = DistributionStub()

    def get_distribution(_name: str) -> DistributionStub:
        return distribution

    monkeypatch.setattr(probe.importlib.metadata, "distribution", get_distribution)

    probe._verify_bootstrap_pth(pth, site)
    entry.hash = SimpleNamespace(mode="sha256", value="0" * 43)
    with pytest.raises(probe.VerificationError, match="bootstrap-pth-record-mismatch"):
        probe._verify_bootstrap_pth(pth, site)


def test_installed_payload_matches_wheel_bytes_and_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import csv

    site = tmp_path / "site-packages"
    site.mkdir()
    dist_info = "arras-0.5.1.dist-info"
    files = {
        "arras/__init__.py": b"installed Arras payload",
        f"{dist_info}/METADATA": b"Name: arras\nVersion: 0.5.1\n",
        f"{dist_info}/WHEEL": b"Root-Is-Purelib: true\n",
    }
    record_rows: list[list[str]] = []
    for name, payload in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest())
        record_rows.append(
            [name, f"sha256={digest.rstrip(b'=').decode('ascii')}", str(len(payload))]
        )
    record_rows.append([f"{dist_info}/RECORD", "", ""])
    record_buffer = io.StringIO()
    csv.writer(record_buffer, lineterminator="\n").writerows(record_rows)
    record = record_buffer.getvalue()
    all_files = {**files, f"{dist_info}/RECORD": record.encode("utf-8")}
    wheel = tmp_path / "arras.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, payload in all_files.items():
            archive.writestr(name, payload)
    for name, payload in all_files.items():
        destination = site / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)

    class DistributionStub:
        def locate_file(self, name: str) -> Path:
            return site / name

        def read_text(self, name: str) -> str | None:
            return record if name == "RECORD" else None

    def get_distribution(_name: str) -> DistributionStub:
        return DistributionStub()

    monkeypatch.setattr(probe.importlib.metadata, "distribution", get_distribution)
    assert probe._compare_installed_payload(wheel, "arras") == len(files)

    (site / "arras/__init__.py").write_bytes(b"tampered")
    with pytest.raises(probe.VerificationError, match="installed-wheel-payload-mismatch"):
        probe._compare_installed_payload(wheel, "arras")


def test_base_probe_validation_requires_arras_payload_parity() -> None:
    candidate: dict[str, Any] = {
        "status": "passed",
        "mode": "base",
        "controls": {
            "legacy_registration_document_and_empty_read": True,
            "base_has_no_umf_distribution": True,
            "base_imported_no_umf": True,
            "admission_refuses_missing_engine": True,
            "projection_refuses_missing_engine": True,
            "selected_host_refuses_without_fallback": True,
        },
        "payload": {"arras_exact_files": 1},
    }
    verifier._validate_probe(candidate, "base")
    candidate["payload"]["arras_exact_files"] = True
    with pytest.raises(verifier.VerificationError, match="payload-parity-incomplete"):
        verifier._validate_probe(candidate, "base")


def test_fixed_probe_runs_as_direct_script_under_isolated_mode() -> None:
    script = Path(__file__).parents[1] / "tools/_umf_admission_probe.py"
    result = subprocess.run(
        [sys.executable, "-I", str(script), "--_probe", "base"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 2
    assert "required: arguments" in result.stderr
    assert "No module named 'arras'" not in result.stderr


@pytest.mark.parametrize("alias_kind", ["same-path", "hardlink", "symlink"])
def test_main_refuses_output_alias_without_overwriting_wheel(
    tmp_path: Path, alias_kind: str
) -> None:
    wheel = tmp_path / "arras-0.5.1-py3-none-any.whl"
    wheel.write_bytes(b"preserve this input")
    output = tmp_path / "receipt.json"
    if alias_kind == "same-path":
        output = wheel
    elif alias_kind == "hardlink":
        os.link(wheel, output)
    else:
        output.symlink_to(wheel)
    before = wheel.read_bytes()

    assert verifier.main(["--wheel", str(wheel), "--output-json", str(output)]) == 1
    assert wheel.read_bytes() == before
    if alias_kind == "symlink":
        assert output.is_symlink()


def test_main_refuses_output_alias_with_selected_python(tmp_path: Path) -> None:
    wheel = tmp_path / "arras-0.5.1-py3-none-any.whl"
    wheel.write_bytes(b"input wheel")
    selected_python = tmp_path / "python"
    selected_python.write_bytes(b"selected interpreter")
    before = selected_python.read_bytes()

    assert (
        verifier.main(
            [
                "--wheel",
                str(wheel),
                "--python",
                str(selected_python),
                "--output-json",
                str(selected_python),
            ]
        )
        == 1
    )
    assert selected_python.read_bytes() == before


def test_atomic_receipt_write_does_not_follow_predicted_temp_symlink(tmp_path: Path) -> None:
    target = tmp_path / "receipt.json"
    protected = tmp_path / "protected-input"
    protected.write_bytes(b"preserve")
    predicted_temp = tmp_path / f".{target.name}.{os.getpid()}.tmp"
    predicted_temp.symlink_to(protected)

    verifier._atomic_json(target, {"status": "failed"})

    assert json.loads(target.read_text(encoding="utf-8")) == {"status": "failed"}
    assert protected.read_bytes() == b"preserve"
    assert predicted_temp.is_symlink()


def test_cleanup_failure_cannot_be_serialized_as_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    temp = tmp_path / "owned"
    temp.mkdir()

    def fail_cleanup(_path: str | os.PathLike[str]) -> None:
        raise OSError("cleanup failed")

    monkeypatch.setattr(verifier.shutil, "rmtree", fail_cleanup)
    with pytest.raises(verifier.VerificationError, match="owned-temp-cleanup-failed"):
        verifier._remove_owned_temp(temp)
