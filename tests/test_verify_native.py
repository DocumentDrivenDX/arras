from __future__ import annotations

# pyright: basic
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
import subprocess
import sys
import sysconfig
import types
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, cast

import pytest

TOOL = Path(__file__).parents[1] / "tools" / "verify_native.py"
_SPEC = importlib.util.spec_from_file_location("verify_native", TOOL)
assert _SPEC is not None and _SPEC.loader is not None
verify_native = importlib.util.module_from_spec(_SPEC)
sys.path.insert(0, str(TOOL.parent))
try:
    _SPEC.loader.exec_module(verify_native)
finally:
    sys.path.pop(0)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_conformance_timeout_is_strictly_bounded_before_input_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for invalid in (0, -1, 7201, True, 35.0, "2100"):
        with pytest.raises(verify_native.VerificationError, match="conformance timeout"):
            verify_native.validate_conformance_timeout(invalid)

    def inputs_must_not_be_read(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("input preparation ran before timeout validation")

    monkeypatch.setattr(verify_native, "_prepare_inputs", inputs_must_not_be_read)
    with pytest.raises(verify_native.VerificationError, match="conformance timeout"):
        verify_native.verify(
            Path("arras.whl"),
            Path("cohort.json"),
            Path("find-links.html"),
            Path("receipt.json"),
            conformance_timeout_seconds=7201,
        )
    assert verify_native.validate_conformance_timeout(1) == 1
    assert verify_native.validate_conformance_timeout(7200) == 7200
    assert verify_native._conformance_timeout_argument("2100") == 2100
    for invalid in ("1.5", "1e2", "7201"):
        with pytest.raises(verify_native.argparse.ArgumentTypeError):
            verify_native._conformance_timeout_argument(invalid)


def test_runner_keeps_default_for_setup_and_forwards_override_only_when_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    def capture(
        _args: list[str], *, cwd: Path, env: dict[str, str], timeout: int
    ) -> subprocess.CompletedProcess[str]:
        calls.append(timeout)
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(verify_native, "run_owned", capture)
    verify_native._run(["setup"], cwd=tmp_path, env={})
    verify_native._run(["conformance"], cwd=tmp_path, env={}, timeout=123)
    assert calls == [verify_native.DEFAULT_CONFORMANCE_TIMEOUT_SECONDS, 123]


def test_conformance_timeout_failure_retains_selected_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def timeout(*_args: Any, **_kwargs: Any) -> Any:
        raise verify_native.ProcessTimeout("partial stdout", "partial stderr", [])

    monkeypatch.setattr(verify_native, "run_owned", timeout)
    with pytest.raises(verify_native.VerificationError) as captured:
        verify_native._run(["conformance"], cwd=tmp_path, env={}, timeout=123)
    assert captured.value.details["process"]["timed_out"] is True
    assert captured.value.details["process"]["timeout_seconds"] == 123


def test_conformance_receipt_records_selected_timeout_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = good_report()
    monkeypatch.setattr(
        verify_native,
        "_run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, json.dumps(report), ""),
    )
    context = {
        "venv_python": tmp_path / "python",
        "env": {},
        "probe": {
            "applicable_case_ids": ["case-one"],
            "skipped_case_ids": ["skip-me"],
            "corpus_version": 4,
            "roles": ["reader", "provider"],
            "limits": {},
            "distributions": {},
        },
        "runtime": {"python": "3.11", "sys_platform": "darwin", "machine": "arm64"},
        "downloaded": [],
        "parity": {"actual_versions": {}, "native_inventory": {}, "payloads": {}},
        "install_inventory": [],
    }
    receipt = verify_native._run_and_record(
        tmp_path,
        context,
        {"corpus": {"roles": ["reader", "provider"], "version": 4, "limits": {}}},
        conformance_timeout_seconds=123,
    )
    assert receipt["conformance_timeout_seconds"] == 123
    assert receipt["cli"] == {
        "command": "python -I -m arras.conformance --backend truss",
        "exit_code": 0,
        "timeout_seconds": 123,
    }


def cohort() -> dict[str, Any]:
    native = [
        ("truss-toolkit", "truss_toolkit-1.0-py3-none-any.whl"),
        ("weft-sql", "weft_sql-1.0-py3-none-any.whl"),
        ("pgserver-pg18", "pgserver_pg18-1.0-py3-none-any.whl"),
    ]
    wheels = [
        {
            "distribution": name,
            "version": "1.0",
            "filename": filename,
            "url": f"https://packages.example/{filename}",
            "sha256": "a" * 64,
        }
        for name, filename in native
    ]
    return {
        "schema_version": 1,
        "arras": {"version": "0.5.0", "sha256": "b" * 64},
        "runtime": {"python": "3.11", "sys_platform": "darwin", "machine": "arm64"},
        "find_links": {"sha256": "c" * 64},
        "native_wheels": wheels,
        "corpus": {"version": 1, "roles": ["reader", "provider"], "limits": {}},
    }


def good_report() -> dict[str, Any]:
    return {
        "backend": "truss",
        "roles": ["reader", "provider"],
        "corpus_version": 4,
        "newer_corpus": False,
        "skipped": ["skip-me"],
        "results": [{"case": "case-one", "status": "passed"}],
        "counts": {"passed": 1, "failed": 0, "harness_error": 0, "limit": 0, "host_specific": 0},
    }


def test_cohort_requires_exact_supported_native_runtime_and_corpus() -> None:
    value = cohort()
    assert verify_native.validate_cohort(value) == value

    invalids = []
    malformed = cohort()
    malformed["corpus"]["roles"] = ["reader"]
    invalids.append(malformed)
    malformed = cohort()
    malformed["runtime"]["python"] = "3.12"
    invalids.append(malformed)
    malformed = cohort()
    malformed["native_wheels"] = malformed["native_wheels"][:-1]
    invalids.append(malformed)
    malformed = cohort()
    malformed["corpus"]["version"] = True
    invalids.append(malformed)
    malformed = cohort()
    malformed["schema_version"] = 1.0
    invalids.append(malformed)

    for value in invalids:
        with pytest.raises(verify_native.VerificationError):
            verify_native.validate_cohort(value)


def test_cohort_rejects_unsafe_artifact_urls_and_ambiguous_wheels() -> None:
    for url in (
        "http://packages.example/a.whl",
        "https://user@packages.example/a.whl",
        "https://packages.example/a.whl?token=x",
        "https://packages.example/a.whl#fragment",
    ):
        value = cohort()
        value["native_wheels"][0]["url"] = url
        with pytest.raises(verify_native.VerificationError):
            verify_native.validate_cohort(value)

    value = cohort()
    value["native_wheels"][1]["filename"] = value["native_wheels"][0]["filename"]
    with pytest.raises(verify_native.VerificationError, match="duplicate native wheel filename"):
        verify_native.validate_cohort(value)


def test_cohort_json_rejects_duplicate_keys(tmp_path: Path) -> None:
    manifest = tmp_path / "cohort.json"
    manifest.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(verify_native.VerificationError, match="duplicate JSON object key"):
        verify_native._load_json_unique(manifest)


def test_find_links_requires_both_exact_url_and_digest(tmp_path: Path) -> None:
    value = cohort()
    links = tmp_path / "index.html"
    links.write_text(
        "<html>"
        + "".join(
            f'<a href="{item["url"]}#sha256={item["sha256"]}">{item["filename"]}</a>'
            for item in value["native_wheels"]
        )
        + "</html>"
    )
    value["find_links"]["sha256"] = digest(links.read_bytes())
    verify_native.verify_find_links(links, value["find_links"]["sha256"], value["native_wheels"])

    value["native_wheels"][0]["sha256"] = "d" * 64
    with pytest.raises(verify_native.VerificationError, match="does not contain"):
        verify_native.verify_find_links(
            links, value["find_links"]["sha256"], value["native_wheels"]
        )


def test_report_requires_exact_case_set_counts_and_declared_limits() -> None:
    probe = {"applicable_case_ids": ["case-one"], "skipped_case_ids": ["skip-me"]}
    specification = {"version": 4, "roles": ["reader", "provider"], "limits": {}}
    assert verify_native._verify_report(good_report(), probe, specification, 0)["passed"] == 1

    mutations = [
        lambda report: report["counts"].update(passed=True),
        lambda report: report["results"].append({"case": "case-one", "status": "passed"}),
        lambda report: report["results"][0].update(status="host_specific"),
        lambda report: report.update(skipped=[]),
        lambda report: report.update(newer_corpus=True),
    ]
    for mutate in mutations:
        report = good_report()
        mutate(report)
        with pytest.raises(verify_native.VerificationError):
            verify_native._verify_report(report, probe, specification, 0)

    overlapping_probe = {"applicable_case_ids": ["case-one"], "skipped_case_ids": ["case-one"]}
    with pytest.raises(verify_native.VerificationError, match="overlap"):
        verify_native._verify_report(good_report(), overlapping_probe, specification, 0)

    limited = good_report()
    limited["results"][0]["status"] = "limit"
    limited["counts"].update(passed=0, limit=1)
    with pytest.raises(verify_native.VerificationError, match="unlisted documented limit"):
        verify_native._verify_report(limited, probe, specification, 0)


def test_inventory_rejects_unselected_native_bearing_dependency() -> None:
    foreign_pe = verify_native.classify_native(b"MZ\x00\x00", ".exe", "linux")
    assert foreign_pe == ("PE", False)
    foreign_bootstrap = {
        "pip": [{"format": foreign_pe[0], "runtime_native": foreign_pe[1], "path": "pip.exe"}]
    }
    assert verify_native._verify_native_inventory(foreign_bootstrap, cohort()) == foreign_bootstrap
    extensionless_elf = verify_native.classify_native(b"\x7fELF\x02\x01", "", "linux")
    assert extensionless_elf == ("ELF", True)
    extensionless_runtime_binary = {
        "surprise-native": [
            {
                "format": extensionless_elf[0],
                "runtime_native": extensionless_elf[1],
                "path": "bin/pg_ctl",
            }
        ]
    }
    with pytest.raises(verify_native.VerificationError, match="absent from the selected cohort"):
        verify_native._verify_native_inventory(extensionless_runtime_binary, cohort())
    assert verify_native._verify_native_inventory({"arras": []}, cohort()) == {"arras": []}


def test_installed_probe_classifies_real_extensionless_elf_and_foreign_pe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elf = tmp_path / "pg_ctl"
    pe = tmp_path / "pip.exe"
    elf.write_bytes(b"\x7fELF\x02\x01synthetic")
    pe.write_bytes(b"MZ\x00\x00synthetic")

    class Distribution:
        def __init__(self, name: str, files: list[Path]) -> None:
            self.metadata = {"Name": name}
            self.version = "1.0"
            self.files = files

        def locate_file(self, relative: Path) -> Path:
            return relative

    monkeypatch.setattr(
        importlib.metadata,
        "distributions",
        lambda: [Distribution("arras", [elf]), Distribution("pip", [pe])],
    )
    arras_module = types.ModuleType("arras")
    arras_module.__file__ = str(tmp_path / "site" / "arras.py")
    conformance_module = types.ModuleType("arras.conformance")
    conformance_stub = cast(Any, conformance_module)
    conformance_stub.load_corpus = lambda: {
        "version": 4,
        "cases": [{"id": "read.key", "tags": ["reader"]}],
    }
    conformance_stub.tags = lambda roles: set(roles)
    truss_module = types.ModuleType("arras.conformance.truss")
    cast(Any, truss_module).TrussHarness = type(
        "TrussHarness", (), {"roles": ("reader", "provider"), "LIMITS": {}}
    )
    arras_module.__path__ = []
    conformance_module.__path__ = []
    monkeypatch.setitem(sys.modules, "arras", arras_module)
    monkeypatch.setitem(sys.modules, "arras.conformance", conformance_module)
    monkeypatch.setitem(sys.modules, "arras.conformance.truss", truss_module)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        sysconfig,
        "get_paths",
        lambda: {
            key: str(tmp_path / key) for key in ("purelib", "platlib", "scripts", "data", "include")
        },
    )

    def execute_probe(args: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        output = io.StringIO()
        with redirect_stdout(output):
            exec(args[-1], {})
        return subprocess.CompletedProcess(args, 0, output.getvalue(), "")

    monkeypatch.setattr(verify_native, "_run", execute_probe)
    probe = verify_native._installed_probe(Path("/venv/bin/python"), tmp_path, {})
    assert probe["native_files"]["arras"][0]["format"] == "ELF"
    assert probe["native_files"]["arras"][0]["runtime_native"] is True
    assert probe["native_files"]["pip"][0]["format"] == "PE"
    assert probe["native_files"]["pip"][0]["runtime_native"] is False


def test_environment_removes_user_pip_python_and_uv_configuration(tmp_path: Path) -> None:
    base = {
        "PIP_INDEX_URL": "https://private.example/simple",
        "PIP_EXTRA_INDEX_URL": "https://private.example/extra",
        "PYTHONPATH": "/checkout",
        "PYTHONHOME": "/custom/python",
        "UV_INDEX_URL": "https://private.example/uv",
        "UV_CONFIG_FILE": "/custom/uv.toml",
        "DYLD_LIBRARY_PATH": "/custom/libs",
        "PGHOST": "production.example",
        "CONDA_PREFIX": "/custom/conda",
        "KEEP_ME": "yes",
    }
    clean = verify_native._sanitize_environment(base, tmp_path / "cache")
    assert clean["PIP_INDEX_URL"] == verify_native.PUBLIC_INDEX
    assert clean["PIP_CONFIG_FILE"] == os.devnull
    assert clean["PYTHONPATH"] == ""
    assert clean["KEEP_ME"] == "yes"
    assert "PIP_EXTRA_INDEX_URL" not in clean
    assert "PYTHONHOME" not in clean
    assert "UV_INDEX_URL" not in clean
    assert "DYLD_LIBRARY_PATH" not in clean
    assert "PGHOST" not in clean
    assert "CONDA_PREFIX" not in clean


def test_install_command_uses_explicit_local_artifacts_and_public_index(tmp_path: Path) -> None:
    value = cohort()
    paths = {item["filename"]: tmp_path / item["filename"] for item in value["native_wheels"]}
    args = verify_native.install_command(
        tmp_path / "venv-python",
        tmp_path / "arras.whl",
        value,
        paths,
        tmp_path / "report.json",
        public_index=verify_native.PUBLIC_INDEX,
        canonical_name=verify_native._canonical_name,
    )
    assert "--only-binary=:all:" in args
    assert "--no-cache-dir" in args
    assert args[args.index("--index-url") + 1] == "https://pypi.org/simple"
    assert any("truss-toolkit[native,query,local] @ file:" in arg for arg in args)
    assert all("packages.example" not in arg for arg in args)


def test_payload_parity_covers_metadata_and_data_script(tmp_path: Path) -> None:
    purelib, platlib, scripts = (tmp_path / name for name in ("purelib", "platlib", "scripts"))
    for path in (purelib, platlib, scripts):
        path.mkdir()
    roots = {
        "purelib": purelib,
        "platlib": platlib,
        "scripts": scripts,
        "data": tmp_path,
        "include": tmp_path,
        "base": tmp_path,
        "executable": tmp_path / "venv" / "bin" / "python",
    }
    members = {
        "sample.py": b"value = 1\n",
        "sample-1.0.dist-info/METADATA": b"Name: sample\nVersion: 1.0\n\n",
        "sample-1.0.data/scripts/sample-tool": b"#!python\nprint('ok')\n",
        "sample-1.0.dist-info/RECORD": b"",
    }
    wheel = tmp_path / "sample-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    (purelib / "sample.py").write_bytes(members["sample.py"])
    (purelib / "sample-1.0.dist-info").mkdir()
    (purelib / "sample-1.0.dist-info/METADATA").write_bytes(
        members["sample-1.0.dist-info/METADATA"]
    )
    (scripts / "sample-tool").write_bytes(
        b"#!" + str(roots["executable"]).encode() + b"\nprint('ok')\n"
    )

    observed = verify_native._verify_payload_parity(wheel, roots)
    assert set(observed) == {
        "sample.py",
        "sample-1.0.dist-info/METADATA",
        "sample-1.0.data/scripts/sample-tool",
    }

    (scripts / "sample-tool").write_text("tampered")
    with pytest.raises(verify_native.VerificationError, match="differs from the verified wheel"):
        verify_native._verify_payload_parity(wheel, roots)


def test_main_does_not_overwrite_input_on_output_alias(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_file = tmp_path / "input.bin"
    input_file.write_bytes(b"preserve this evidence")
    before = digest(input_file.read_bytes())
    result = verify_native.main(
        [
            "--wheel",
            str(input_file),
            "--cohort",
            str(input_file),
            "--find-links",
            str(input_file),
            "--output-json",
            str(input_file),
        ]
    )
    assert result == 1
    assert digest(input_file.read_bytes()) == before
    assert "must not overwrite" in capsys.readouterr().err


def test_main_rejects_hardlink_and_selected_interpreter_output_alias(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    wheel = tmp_path / "wheel.whl"
    cohort_path = tmp_path / "cohort.json"
    links = tmp_path / "links.html"
    wheel.write_bytes(b"wheel fixture")
    cohort_path.write_text("{}")
    links.write_text("<html></html>")
    alias = tmp_path / "receipt.json"
    os.link(cohort_path, alias)
    before = digest(cohort_path.read_bytes())
    assert (
        verify_native.main(
            [
                "--wheel",
                str(wheel),
                "--cohort",
                str(cohort_path),
                "--find-links",
                str(links),
                "--output-json",
                str(alias),
            ]
        )
        == 1
    )
    assert digest(cohort_path.read_bytes()) == before
    capsys.readouterr()

    selected_python = tmp_path / "python"
    selected_python.write_text("interpreter")
    before_python = digest(selected_python.read_bytes())
    assert (
        verify_native.main(
            [
                "--wheel",
                str(wheel),
                "--cohort",
                str(cohort_path),
                "--find-links",
                str(links),
                "--python",
                str(selected_python),
                "--output-json",
                str(selected_python),
            ]
        )
        == 1
    )
    assert digest(selected_python.read_bytes()) == before_python


def test_failed_cli_validation_retains_raw_report_and_streams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = good_report()
    report["results"][0]["status"] = "failed"
    report["counts"].update(passed=0, failed=1)
    stdout = json.dumps(report)
    monkeypatch.setattr(
        verify_native,
        "_run",
        lambda *_args, **_kwargs: verify_native.subprocess.CompletedProcess(
            [], 1, stdout, "fixture stderr"
        ),
    )
    context = {
        "venv_python": tmp_path / "python",
        "env": {},
        "probe": {"applicable_case_ids": ["case-one"], "skipped_case_ids": ["skip-me"]},
    }
    with pytest.raises(verify_native.VerificationError) as captured:
        verify_native._run_and_record(
            tmp_path,
            context,
            {"corpus": {"roles": ["reader", "provider"], "version": 4, "limits": {}}},
        )
    assert captured.value.details["cli"]["stdout"] == stdout
    assert captured.value.details["cli"]["stderr"] == "fixture stderr"
    assert captured.value.details["cli"]["exit_code"] == 1
    assert captured.value.details["cli"]["timeout_seconds"] == (
        verify_native.DEFAULT_CONFORMANCE_TIMEOUT_SECONDS
    )
    assert captured.value.details["cli"]["report"] == report


def test_failed_receipt_keeps_input_hashes_and_cli_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = tmp_path / "arras.whl"
    manifest = tmp_path / "cohort.json"
    links = tmp_path / "find-links.html"
    output = tmp_path / "receipt.json"
    wheel.write_bytes(b"wheel")
    manifest.write_text("manifest")
    links.write_text("index")
    input_receipt = {
        "arras_wheel": {"path": str(wheel), "sha256": digest(wheel.read_bytes())},
        "cohort": {"path": str(manifest), "sha256": digest(manifest.read_bytes())},
        "find_links": {"path": str(links), "sha256": digest(links.read_bytes())},
    }
    pending = {"schema_version": 1, "status": "pending", "inputs": input_receipt}
    monkeypatch.setattr(
        verify_native,
        "_prepare_inputs",
        lambda *_args: ({}, wheel, links, Path(sys.executable), output, pending),
    )
    monkeypatch.setattr(verify_native, "temp_parent", lambda: tmp_path)
    installed_context = {
        "runtime": {"python": "3.11", "sys_platform": "darwin", "machine": "arm64"},
        "downloaded": [{"distribution": "truss-toolkit", "verified_sha256": "a" * 64}],
        "venv_python": Path(sys.executable),
        "wheel_paths": {},
        "install_inventory": [{"distribution": "truss-toolkit", "version": "1.0"}],
        "probe": {"corpus_version": 4, "roles": ["reader", "provider"]},
        "parity": {
            "payloads": {"arras": {"a.py": "b"}},
            "roots": {"purelib": tmp_path / "venv" / "site-packages"},
        },
    }
    monkeypatch.setattr(verify_native, "_provision_and_probe", lambda *_args: installed_context)
    monkeypatch.setattr(
        verify_native, "_validate_installed", lambda *_args: installed_context["parity"]
    )
    cli_evidence = {
        "exit_code": 1,
        "stdout": "case report",
        "stderr": "details",
        "timeout_seconds": 123,
    }

    def failed_run(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["conformance_timeout_seconds"] == 123
        raise verify_native.VerificationError("failed conformance", details={"cli": cli_evidence})

    monkeypatch.setattr(verify_native, "_run_and_record", failed_run)
    assert (
        verify_native.main(
            [
                "--wheel",
                str(wheel),
                "--cohort",
                str(manifest),
                "--find-links",
                str(links),
                "--output-json",
                str(output),
                "--conformance-timeout-seconds",
                "123",
            ]
        )
        == 1
    )
    saved = json.loads(output.read_text())
    assert saved["inputs"] == input_receipt
    assert saved["conformance_timeout_seconds"] == 123
    assert saved["cli"] == cli_evidence
    assert saved["runtime"] == installed_context["runtime"]
    assert saved["native_wheels"] == installed_context["downloaded"]
    assert saved["pip_artifacts"] == installed_context["install_inventory"]
    assert saved["installed_probe"] == installed_context["probe"]
    assert saved["installed_checks"] == {
        **installed_context["parity"],
        "roots": {"purelib": str(tmp_path / "venv" / "site-packages")},
    }
    assert saved["status"] == "failed"


def test_failed_receipt_keeps_input_hashes_for_untyped_provision_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = tmp_path / "arras.whl"
    manifest = tmp_path / "cohort.json"
    links = tmp_path / "find-links.html"
    output = tmp_path / "receipt.json"
    wheel.write_bytes(b"wheel")
    manifest.write_text("manifest")
    links.write_text("index")
    inputs = {
        "arras_wheel": {"path": str(wheel), "sha256": digest(wheel.read_bytes())},
        "cohort": {"path": str(manifest), "sha256": digest(manifest.read_bytes())},
        "find_links": {"path": str(links), "sha256": digest(links.read_bytes())},
    }
    pending = {"schema_version": 1, "status": "pending", "inputs": inputs}
    monkeypatch.setattr(
        verify_native,
        "_prepare_inputs",
        lambda *_args: ({}, wheel, links, Path(sys.executable), output, pending),
    )
    monkeypatch.setattr(verify_native, "temp_parent", lambda: tmp_path)

    def fail_during_provision(*_args: Any) -> dict[str, Any]:
        raise OSError("synthetic artifact install failure")

    monkeypatch.setattr(verify_native, "_provision_and_probe", fail_during_provision)
    assert (
        verify_native.main(
            [
                "--wheel",
                str(wheel),
                "--cohort",
                str(manifest),
                "--find-links",
                str(links),
                "--output-json",
                str(output),
            ]
        )
        == 1
    )
    saved = json.loads(output.read_text())
    assert saved["inputs"] == inputs
    assert saved["status"] == "failed"
    assert "synthetic artifact install failure" in saved["error"]


def test_failed_validation_receipt_keeps_prevalidation_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = tmp_path / "arras.whl"
    manifest = tmp_path / "cohort.json"
    links = tmp_path / "find-links.html"
    output = tmp_path / "receipt.json"
    for path in (wheel, manifest, links):
        path.write_text(path.name)
    inputs = {
        "arras_wheel": {"path": str(wheel), "sha256": digest(wheel.read_bytes())},
        "cohort": {"path": str(manifest), "sha256": digest(manifest.read_bytes())},
        "find_links": {"path": str(links), "sha256": digest(links.read_bytes())},
    }
    pending = {"schema_version": 1, "status": "pending", "inputs": inputs}
    monkeypatch.setattr(
        verify_native,
        "_prepare_inputs",
        lambda *_args: ({}, wheel, links, Path(sys.executable), output, pending),
    )
    monkeypatch.setattr(verify_native, "temp_parent", lambda: tmp_path)
    context = {
        "runtime": {"python": "3.11", "sys_platform": "darwin", "machine": "arm64"},
        "downloaded": [{"distribution": "truss-toolkit", "verified_sha256": "a" * 64}],
        "install_inventory": [{"distribution": "truss-toolkit", "version": "1.0"}],
        "venv_python": Path(sys.executable),
        "wheel_paths": {},
        "probe": {"corpus_version": 4, "roles": ["reader", "provider"]},
    }
    monkeypatch.setattr(verify_native, "_provision_and_probe", lambda *_args: context)
    monkeypatch.setattr(
        verify_native,
        "_validate_installed",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("synthetic validation failure")),
    )
    assert (
        verify_native.main(
            [
                "--wheel",
                str(wheel),
                "--cohort",
                str(manifest),
                "--find-links",
                str(links),
                "--output-json",
                str(output),
            ]
        )
        == 1
    )
    saved = json.loads(output.read_text())
    assert saved["inputs"] == inputs
    assert saved["runtime"] == context["runtime"]
    assert saved["native_wheels"] == context["downloaded"]
    assert saved["pip_artifacts"] == context["install_inventory"]
    assert saved["installed_probe"] == context["probe"]
    assert saved["error"].startswith("VerificationError:")
    assert "synthetic validation failure" in saved["error"]


@pytest.mark.skipif(os.name == "nt", reason="process-group SIGINT semantics are POSIX-specific")
def test_owned_process_timeout_interrupts_and_reaps_its_process_group(tmp_path: Path) -> None:
    with pytest.raises(verify_native.ProcessTimeout) as captured:
        verify_native.run_owned(
            [sys.executable, "-c", "import time; print('started', flush=True); time.sleep(30)"],
            cwd=tmp_path,
            env=dict(os.environ),
            timeout=0.1,
        )
    assert "started" in captured.value.stdout
    assert not captured.value.leftovers
