#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Fixed isolated probe for the installed UMF action-runtime qualification."""

from __future__ import annotations

import argparse
import base64
import csv
import email.parser
import hashlib
import importlib
import importlib.metadata
import json
import platform
import sys
import sysconfig
import zipfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, cast


class ProbeError(RuntimeError):
    def __init__(self, stage: str, code: str) -> None:
        self.stage = stage
        self.code = code
        super().__init__(code)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _read_wheel_members(path: Path) -> dict[str, bytes]:
    try:
        if path.is_symlink() or path.stat().st_size > 64 * 1024 * 1024:
            raise ProbeError("payload", "wheel-input-invalid")
    except OSError as error:
        raise ProbeError("payload", "wheel-input-unavailable") from error
    try:
        with zipfile.ZipFile(path) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if len(infos) > 100_000 or sum(info.file_size for info in infos) > 64 * 1024 * 1024:
                raise ProbeError("payload", "wheel-payload-over-limit")
            members: dict[str, bytes] = {}
            for info in infos:
                member = PurePosixPath(info.filename)
                if (
                    not info.filename
                    or "\x00" in info.filename
                    or "\\" in info.filename
                    or member.is_absolute()
                    or any(part in ("", ".", "..") for part in member.parts)
                    or any(part == "" for part in info.filename.split("/"))
                    or info.filename in members
                    or info.external_attr >> 16 & 0o170000 == 0o120000
                ):
                    raise ProbeError("payload", "unsafe-or-duplicate-wheel-member")
                members[info.filename] = archive.read(info)
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise ProbeError("payload", "wheel-archive-invalid") from error
    return members


def _verify_wheel_record(members: dict[str, bytes]) -> dict[str, str]:
    record_names = [item for item in members if item.endswith(".dist-info/RECORD")]
    if len(record_names) != 1:
        raise ProbeError("payload", "record-inventory-invalid")
    record: dict[str, str] = {}
    try:
        rows = csv.reader(members[record_names[0]].decode("utf-8").splitlines())
        for row in rows:
            if len(row) != 3 or row[0] in record:
                raise ProbeError("payload", "record-row-invalid")
            member, encoded, size = row
            if member not in members:
                raise ProbeError("payload", "record-member-missing")
            if member.endswith(".dist-info/RECORD"):
                if encoded or size:
                    raise ProbeError("payload", "record-self-hash-present")
            else:
                expected = base64.urlsafe_b64encode(hashlib.sha256(members[member]).digest())
                if (
                    not encoded.startswith("sha256=")
                    or encoded.removeprefix("sha256=") != expected.rstrip(b"=").decode("ascii")
                    or size != str(len(members[member]))
                ):
                    raise ProbeError("payload", "wheel-record-content-mismatch")
            record[member] = _sha(members[member])
    except (UnicodeDecodeError, csv.Error) as error:
        raise ProbeError("payload", "record-invalid") from error
    if set(record) != set(members):
        raise ProbeError("payload", "record-inventory-mismatch")
    return record


def _wheel_payload(path: Path, name: str) -> tuple[dict[str, bytes], dict[str, str]]:
    members = _read_wheel_members(path)
    record = _verify_wheel_record(members)
    payload = {key: value for key, value in members.items() if ".dist-info/" not in key}
    if not payload or not any(key.startswith(f"{name}/") for key in payload):
        raise ProbeError("payload", "package-payload-empty")
    return payload, record


def _wheel_distribution_identity(wheel: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(wheel) as archive:
            metadata_names = [
                entry for entry in archive.namelist() if entry.endswith(".dist-info/METADATA")
            ]
            if len(metadata_names) != 1:
                raise ProbeError("payload", "wheel-metadata-inventory-invalid")
            wheel_metadata = email.parser.Parser().parsestr(
                archive.read(metadata_names[0]).decode("utf-8")
            )
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile) as error:
        raise ProbeError("payload", "wheel-metadata-invalid") from error
    return wheel_metadata.get("Name", "").lower().replace("_", "-"), wheel_metadata.get(
        "Version", ""
    )


def _installed_files(
    name: str,
    expected: dict[str, bytes],
    distribution: importlib.metadata.Distribution,
    files: Any,
) -> dict[str, str]:
    installed: dict[str, str] = {}
    site = Path(sysconfig.get_paths()["purelib"]).resolve()
    for entry in files:
        relative = entry.as_posix()
        if ".dist-info/" in relative:
            continue
        if relative not in expected:
            continue
        target = Path(distribution.locate_file(entry)).resolve()
        if not _inside(target, site):
            raise ProbeError("payload", "installed-member-outside-site")
        try:
            data = target.read_bytes()
        except OSError as error:
            raise ProbeError("payload", "installed-member-unavailable") from error
        digest = _sha(data)
        if digest != _sha(expected[relative]):
            raise ProbeError("payload", "installed-member-mismatch")
        installed[relative] = digest
    if set(installed) != set(expected):
        raise ProbeError("payload", "installed-payload-incomplete")
    return installed


def _verify_installed_record(
    distribution: importlib.metadata.Distribution, files: Any, expected_count: int
) -> int:
    site = Path(sysconfig.get_paths()["purelib"]).resolve()
    record_matches = 0
    for entry in files:
        if entry.hash is None or ".dist-info/" in entry.as_posix():
            continue
        if entry.hash.mode != "sha256":
            raise ProbeError("payload", "installed-record-hash-mode-invalid")
        target = Path(distribution.locate_file(entry)).resolve()
        if not _inside(target, site):
            raise ProbeError("payload", "record-member-outside-site")
        try:
            digest = _sha(target.read_bytes())
        except OSError as error:
            raise ProbeError("payload", "installed-record-member-unavailable") from error
        encoded = base64.urlsafe_b64encode(bytes.fromhex(digest)).rstrip(b"=").decode("ascii")
        if encoded != entry.hash.value:
            raise ProbeError("payload", "installed-record-mismatch")
        record_matches += 1
    if record_matches != expected_count:
        raise ProbeError("payload", "installed-record-incomplete")
    return record_matches


def _payload_artifact_summary(
    name: str,
    version: str,
    expected: dict[str, bytes],
    installed: dict[str, str],
    record_matches: int,
) -> dict[str, Any]:
    resource_rows = [
        (key, _sha(data))
        for key, data in sorted(expected.items())
        if name == "umf-core" and key.startswith("umf/") and not key.endswith((".py", ".pyi"))
    ]
    native_rows = [
        (key, _sha(data))
        for key, data in sorted(expected.items())
        if name == "umf-core" and key.endswith((".so", ".dylib", ".dll", ".pyd"))
    ]
    return {
        "name": name,
        "version": version,
        "payload_files": len(installed),
        "payload_sha256": _sha(
            "\n".join(f"{key}:{installed[key]}" for key in sorted(installed)).encode()
        ),
        "record_matches": record_matches,
        "resource_files": len(resource_rows),
        "resource_manifest_sha256": _sha(
            "\n".join(f"{key}:{digest}" for key, digest in resource_rows).encode()
        ),
        "native_files": len(native_rows),
        "native_manifest_sha256": _sha(
            "\n".join(f"{key}:{digest}" for key, digest in native_rows).encode()
        ),
    }


def _installed_payload(name: str, wheel: Path) -> dict[str, Any]:
    expected, _record = _wheel_payload(wheel, name)
    try:
        distribution = importlib.metadata.distribution(name)
        files = distribution.files or ()
    except importlib.metadata.PackageNotFoundError as error:
        raise ProbeError("payload", "distribution-not-installed") from error
    wheel_name, wheel_version = _wheel_distribution_identity(wheel)
    if wheel_name != name or wheel_version != distribution.version:
        raise ProbeError("payload", "installed-distribution-identity-mismatch")
    installed = _installed_files(name, expected, distribution, files)
    record_matches = _verify_installed_record(distribution, files, len(expected))
    return _payload_artifact_summary(
        name, distribution.version, expected, installed, record_matches
    )


def _trusted_imports() -> dict[str, str]:
    names = ("arras", "umf", "umf.action_runtime", "umf.rust_codegen")
    modules = {name: importlib.import_module(name) for name in names}
    site = Path(sysconfig.get_paths()["purelib"]).resolve()
    repository = Path.cwd().resolve()
    prefix = Path(sys.prefix).resolve()
    if sys.prefix == sys.base_prefix or not _inside(site, prefix):
        raise ProbeError("imports", "fresh-venv-not-isolated")
    config = prefix / "pyvenv.cfg"
    try:
        settings = config.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ProbeError("imports", "fresh-venv-config-unavailable") from error
    setting_rows = [
        line.split("=", 1)[1].strip().lower()
        for line in settings
        if "=" in line and line.split("=", 1)[0].strip().lower() == "include-system-site-packages"
    ]
    if setting_rows != ["false"]:
        raise ProbeError("imports", "system-site-packages-enabled")
    version = str(sysconfig.get_config_var("py_version_short"))
    stdlib = Path(sysconfig.get_paths()["stdlib"]).resolve()
    platstdlib = Path(sysconfig.get_paths()["platstdlib"]).resolve()
    allowed_stdlib = {
        stdlib,
        platstdlib,
        (stdlib / "lib-dynload").resolve(),
        (platstdlib / "lib-dynload").resolve(),
        (Path(sys.base_prefix) / "lib" / f"python{version}.zip").resolve(),
        (Path(sys.base_prefix) / "lib" / f"python{version.replace('.', '')}.zip").resolve(),
        (Path(sys.base_prefix) / "Lib" / f"python{version}.zip").resolve(),
    }
    origins: dict[str, str] = {}
    for name, module in modules.items():
        origin = Path(cast(str, module.__file__)).resolve()
        if not _inside(origin, site) or _inside(origin, repository):
            raise ProbeError("imports", "module-origin-outside-fresh-site")
        origins[name] = origin.relative_to(site).as_posix()
    for entry in sys.path:
        if not entry:
            raise ProbeError("imports", "empty-import-path")
        if not _trusted_sys_path_entry(Path(entry), prefix, allowed_stdlib):
            raise ProbeError("imports", "external-import-path")
        candidate = Path(entry).resolve()
        if _inside(candidate, repository):
            raise ProbeError("imports", "checkout-import-path")
    return origins


def _trusted_sys_path_entry(entry: Path, prefix: Path, stdlib_paths: set[Path]) -> bool:
    candidate = entry.resolve()
    return _inside(candidate, prefix) or candidate in stdlib_paths


def _conformance(path: Path, expected_sha: str) -> dict[str, Any]:
    try:
        info = path.lstat()
        if path.is_symlink() or not path.is_file() or info.st_size > 16 * 1024 * 1024:
            raise ProbeError("corpus", "corpus-input-invalid")
        raw = path.read_bytes()
    except OSError as error:
        raise ProbeError("corpus", "corpus-input-unavailable") from error
    if _sha(raw) != expected_sha:
        raise ProbeError("corpus", "corpus-digest-mismatch")
    try:
        corpus = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ProbeError("corpus", "corpus-json-invalid") from error
    if not isinstance(corpus, dict) or corpus.get("profile") != "umf.current-conformance/1":
        raise ProbeError("corpus", "corpus-profile-invalid")
    cases = corpus.get("cases")
    if type(cases) is not list or len(cases) != 139:
        raise ProbeError("corpus", "corpus-case-count-invalid")
    ids = [case.get("id") for case in cases if type(case) is dict]
    if (
        len(ids) != 139
        or any(type(item) is not str or not item for item in ids)
        or len(set(ids)) != 139
    ):
        raise ProbeError("corpus", "corpus-ids-invalid")
    import umf

    from arras.umf_admission import admit_document

    reference = 0
    empty = 0
    for case in cases:
        document = case.get("document")
        source = json.dumps(document, ensure_ascii=True).encode("utf-8")
        value = umf.read_json_value(source.decode("utf-8"), "json")
        result = umf.validate_document(value, _case_registry(umf, case.get("registry")))
        diagnostic_rows = [
            {
                "code": item.code,
                "path": item.path,
                "message": item.message,
                "severity": item.severity,
            }
            for item in result.diagnostics
        ]
        if (
            result.valid is not case.get("valid")
            or result.complete is not case.get("complete")
            or diagnostic_rows != case.get("diagnostics")
        ):
            raise ProbeError("corpus", "reference-case-mismatch")
        reference += 1
        admitted = admit_document(source)
        empty_result = umf.validate_document(
            umf.read_json_value(source.decode("utf-8"), "json"), umf.Registry()
        )
        empty_diagnostics = [
            {
                "code": item.code,
                "path": item.path,
                "message": item.message,
                "severity": item.severity,
            }
            for item in empty_result.diagnostics
        ]
        if (
            admitted.validation_status != "completed"
            or admitted.valid is not empty_result.valid
            or admitted.complete is not empty_result.complete
            or [
                {
                    "code": item.code,
                    "path": item.path,
                    "message": item.message,
                    "severity": item.severity,
                }
                for item in admitted.diagnostics
            ]
            != empty_diagnostics
        ):
            raise ProbeError("corpus", "empty-registry-case-mismatch")
        empty += 1
    return {"cases": len(ids), "reference_matches": reference, "empty_registry_matches": empty}


def _case_registry(api: Any, spec: Any) -> Any:
    registry = api.Registry()
    if spec is None:
        return registry
    if type(spec) is not dict:
        raise ProbeError("corpus", "registry-fixture-shape-invalid")

    def validate(payload: dict[str, Any], context: dict[str, Any]) -> list[Any]:
        message = f"{context['document']['id']}:{context['scope']}:{payload['kind']}"
        return [api.Diagnostic("BASELINE_CALLBACK", context["path"], message, "warning")]

    registry.register(api.Extension(spec["id"], spec["version"], (spec["scope"],), True, validate))
    return registry


def _generated_manifest_sha(entries: list[tuple[str, bytes]]) -> str:
    manifest = [
        {"path": path, "sha256": _sha(content)}
        for path, content in sorted(entries, key=lambda entry: entry[0])
    ]
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha(encoded)


def _generate_client(engine: Any, source: bytes, root: Path) -> tuple[Any, ...]:
    generated = engine.generate_python_client(
        {"text": source.decode("utf-8"), "package": "actions_binding"}
    )
    if type(generated) is not dict or type(generated.get("files")) is not list:
        raise ProbeError("generator", "generated-package-shape-invalid")
    files = cast(list[object], generated["files"])
    if not files or len(files) > 256:
        raise ProbeError("generator", "generated-package-inventory-invalid")
    total = 0
    seen: set[str] = set()
    manifest: list[tuple[str, bytes]] = []
    for raw in files:
        if type(raw) is not dict:
            raise ProbeError("generator", "generated-file-shape-invalid")
        row = cast(dict[str, object], raw)
        path, text = row.get("path"), row.get("text")
        if type(path) is not str or type(text) is not str:
            raise ProbeError("generator", "generated-file-shape-invalid")
        relative = PurePosixPath(path)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or "\\" in path
            or "\x00" in path
            or path in seen
        ):
            raise ProbeError("generator", "generated-file-path-invalid")
        data = text.encode("utf-8")
        total += len(data)
        if total > 16 * 1024 * 1024:
            raise ProbeError("generator", "generated-package-over-limit")
        seen.add(path)
        manifest.append((path, data))
        destination = root.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    package_root = str(root)
    sys.path.insert(0, package_root)
    generated_package = importlib.import_module("actions_binding")
    origin = Path(cast(str, generated_package.__file__)).resolve()
    if not _inside(origin, root.resolve()):
        raise ProbeError("generator", "generated-client-origin-invalid")
    return (
        generated_package,
        _generated_manifest_sha(manifest),
    )


class _Capture:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def execute(self, request: Any) -> dict[str, object]:
        current = dict(request)
        self.requests.append(current)
        if current.get("kind") == "validate":
            return {"schema": current["schema"], "valid": True}
        return {
            "schema": current["schema"],
            "status": "committed",
            "created": [],
            "changed": [],
            "counts": {"created": 0, "updated": 0, "deleted": 0, "linked": 0, "unlinked": 0},
            "consistency_token": "capture-token",
        }


def _rows(session: Any) -> tuple[dict[str, Any], ...]:
    answer = session.query(
        "catalog", "SELECT item.* FROM catalog.item item ORDER BY item.item_id LIMIT 10"
    )
    return cast(tuple[dict[str, Any], ...], answer.rows)


def _is_valid_validation_result(value: Any, generated_name: str = "actions_binding") -> bool:
    runtime = importlib.import_module(f"{generated_name}._runtime")
    validation_type = getattr(runtime, "ValidationResult", None)
    return type(value) is validation_type and getattr(value, "valid", None) is True


def _token(value: Any) -> str:
    token = getattr(value, "consistency_token", None)
    if type(token) is not str or not token:
        raise ProbeError("host", "consistency-token-missing")
    return token


def _action_host(source: bytes, vectors: dict[str, Any], generated: Any) -> None:
    from arras.testing import InMemory

    world = InMemory(action_profile="arras-umf-set/1")
    world.register(source)
    seeded = world.import_records(
        "catalog",
        [{"type": "item", "key": "item-1", "properties": {"label": "held"}}],
        load_id="installed-action-verification",
    )
    if seeded.created != 1 or seeded.skipped != 0 or seeded.rejected:
        raise ProbeError("host", "public-seed-import-mismatch")
    writer = world.person("writer", "catalog", "read", "write")
    reader = world.person("reader", "catalog", "read")
    actions = generated.SyncActions(world.arras.session(writer))
    item = generated.ItemKey(item_id="item-1")
    reader_session = world.arras.session(reader)
    _validate_without_effect(world, writer, reader_session, actions, item, vectors, generated)
    _apply_and_replay(actions, reader_session, item)
    _uncertain_response(world, generated, writer, reader_session, item)
    _current_denial(world, generated, writer, reader_session, actions, item, vectors)


def _validate_without_effect(
    world: Any,
    writer: Any,
    reader_session: Any,
    actions: Any,
    item: Any,
    vectors: dict[str, Any],
    generated: Any,
) -> None:
    before = _rows(reader_session)
    valid = actions.set_label_validate(item=item, label_value="ready")
    if (
        not _is_valid_validation_result(valid, generated.__name__)
        or _rows(reader_session) != before
    ):
        raise ProbeError("host", "validate-not-read-only")
    request = {
        **vectors["generatedRequests"]["validate"],
        "inputs": {"item": {"item_id": "item-1"}, "label_value": "pending"},
    }
    invalid = world.arras.session(writer).execute(request)
    if not isinstance(invalid, dict) or invalid.get("error", {}).get("code") != "INVALID":
        raise ProbeError("host", "disallowed-value-not-refused")
    if _rows(reader_session) != before:
        raise ProbeError("host", "invalid-value-mutated-state")


def _apply_and_replay(actions: Any, reader_session: Any, item: Any) -> None:
    applied = actions.set_label(item=item, label_value="ready", idempotency_key="installed-apply")
    token = _token(applied)
    visible = reader_session.query(
        "catalog",
        "SELECT item.* FROM catalog.item item ORDER BY item.item_id LIMIT 10",
        at_least=token,
    )
    if len(visible.rows) != 1 or visible.rows[0].get("label") != "ready":
        raise ProbeError("host", "apply-not-visible-at-least")
    before_noop = _rows(reader_session)
    first_receipt = actions.set_label(
        item=item, label_value="ready", idempotency_key="installed-noop"
    )
    second_receipt = actions.set_label(
        item=item, label_value="ready", idempotency_key="installed-noop"
    )
    first_token, second_token = _token(first_receipt), _token(second_receipt)
    after_noop = reader_session.query(
        "catalog",
        "SELECT item.* FROM catalog.item item ORDER BY item.item_id LIMIT 10",
        at_least=first_token,
    )
    if (
        not _is_noop_receipt(first_receipt)
        or not _is_noop_receipt(second_receipt)
        or first_token != second_token
        or before_noop != _rows(reader_session)
        or before_noop != after_noop.rows
    ):
        raise ProbeError("host", "replay-not-stable")


def _is_noop_receipt(receipt: Any) -> bool:
    counts = getattr(receipt, "counts", None)
    expected = {"created": 0, "updated": 0, "deleted": 0, "linked": 0, "unlinked": 0}
    return (
        getattr(receipt, "status", None) == "committed"
        and getattr(receipt, "created", None) == ()
        and getattr(receipt, "changed", None) == ()
        and isinstance(counts, Mapping)
        and counts == expected
    )


def _uncertain_response(
    world: Any, generated: Any, writer: Any, reader_session: Any, item: Any
) -> None:
    # A response-loss transport executes the same public wire path once, then hides the result.
    class LostResponse:
        calls = 0

        def execute(self, request: Any) -> object:
            self.calls += 1
            world.arras.session(writer).execute(request)
            raise RuntimeError("unobservable transport response")

    lost = LostResponse()
    uncertain_actions = generated.SyncActions(generated.SyncClient(lost))
    try:
        uncertain_actions.set_label(
            item=item, label_value="abcdefgh", idempotency_key="lost-response"
        )
    except generated.WriteOutcomeUnknown:
        pass
    else:
        raise ProbeError("host", "lost-response-not-uncertain")
    if lost.calls != 1:
        raise ProbeError("host", "uncertain-write-retried")
    lost_rows = _rows(reader_session)
    if len(lost_rows) != 1 or lost_rows[0].get("label") != "abcdefgh":
        raise ProbeError("host", "lost-response-outcome-not-readable")

    class MalformedResponse:
        calls = 0

        def execute(self, request: Any) -> object:
            self.calls += 1
            world.arras.session(writer).execute(request)
            return {"schema": request["schema"], "status": "committed"}

    malformed = MalformedResponse()
    malformed_actions = generated.SyncActions(generated.SyncClient(malformed))
    try:
        malformed_actions.set_label(
            item=item, label_value="held", idempotency_key="malformed-response"
        )
    except generated.WriteOutcomeUnknown:
        pass
    else:
        raise ProbeError("host", "malformed-committed-response-not-uncertain")
    if malformed.calls != 1:
        raise ProbeError("host", "malformed-response-write-retried")
    final_rows = _rows(reader_session)
    if len(final_rows) != 1 or final_rows[0].get("label") != "held":
        raise ProbeError("host", "uncertain-write-outcome-not-readable")


def _current_denial(
    world: Any,
    generated: Any,
    writer: Any,
    reader_session: Any,
    actions: Any,
    item: Any,
    vectors: dict[str, Any],
) -> None:
    world.expire(writer)
    before_denial = _rows(reader_session)
    try:
        actions.set_label(item=item, label_value="ready", idempotency_key="expired-writer")
    except generated.AccessError as error:
        if error.code != "DENIED":
            raise ProbeError("host", "unexpected-access-refusal") from error
    else:
        raise ProbeError("host", "expired-writer-not-refused")
    if (
        world.arras.session(writer).execute(vectors["generatedRequests"]["apply"])
        != {"schema": vectors["source"]["sha256"], "error": {"code": "DENIED"}}
        or _rows(reader_session) != before_denial
    ):
        raise ProbeError("host", "raw-current-denial-mismatch")


def run_probe(arguments: list[str]) -> dict[str, Any]:
    if len(arguments) != 5:
        raise ProbeError("arguments", "probe-argument-count-invalid")
    arras_wheel, umf_wheel, source_path, vector_path, corpus_path = map(Path, arguments)
    expected_source = "5b79b3dba5ebc52ac9452f85a75411dab5edaa34154adda76f872a53c21d0818"
    expected_vectors = "c811eefac81c4f5ff3a7aa60cbe7f7657f7599040cd0869b2616c450931a950e"

    def read_fixture(path: Path, cap: int) -> bytes:
        try:
            info = path.lstat()
            if path.is_symlink() or not path.is_file() or info.st_size > cap:
                raise ProbeError("fixtures", "fixture-input-invalid")
            return path.read_bytes()
        except OSError as error:
            raise ProbeError("fixtures", "fixture-input-unavailable") from error

    source, vectors_raw = (
        read_fixture(source_path, 16 * 1024 * 1024),
        read_fixture(vector_path, 16 * 1024 * 1024),
    )
    if _sha(source) != expected_source or _sha(vectors_raw) != expected_vectors:
        raise ProbeError("fixtures", "action-fixture-digest-mismatch")
    try:
        vectors = json.loads(vectors_raw)
    except json.JSONDecodeError as error:
        raise ProbeError("fixtures", "action-vectors-json-invalid") from error
    if type(vectors) is not dict or vectors.get("claims", {}).get("executionVerified") is not False:
        raise ProbeError("fixtures", "action-vectors-shape-invalid")
    arras_identity = _installed_payload("arras", arras_wheel)
    umf_identity = _installed_payload("umf-core", umf_wheel)
    origins = _trusted_imports()
    import umf.action_runtime as runtime

    engine = runtime.create_action_engine()
    generated, generated_sha = _generate_client(engine, source, Path.cwd() / "generated-client")
    capture = _Capture()
    generated_actions = generated.SyncActions(generated.SyncClient(capture))
    generated_actions.set_label(
        item=generated.ItemKey(item_id="item-1"), label_value="ready", idempotency_key="fixture-key"
    )
    generated_actions.set_label_validate(
        item=generated.ItemKey(item_id="item-1"), label_value="ready"
    )
    if capture.requests != [
        vectors["generatedRequests"]["apply"],
        vectors["generatedRequests"]["validate"],
    ]:
        raise ProbeError("generator", "generated-request-vectors-mismatch")
    _action_host(source, vectors, generated)
    corpus = _conformance(
        corpus_path, "bb008a98b8448050748e65f867e7863475ccad9501a5b9229ae9e6d336691544"
    )
    if (
        _installed_payload("arras", arras_wheel) != arras_identity
        or _installed_payload("umf-core", umf_wheel) != umf_identity
    ):
        raise ProbeError("payload", "installed-payload-changed-during-probe")
    return {
        "status": "passed",
        "skipped": 0,
        "arras_wheel_sha256": _sha(arras_wheel.read_bytes()),
        "umf_wheel_sha256": _sha(umf_wheel.read_bytes()),
        "source_sha256": _sha(source),
        "vectors_sha256": _sha(vectors_raw),
        "runtime": {
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "machine": platform.machine(),
            "implementation": platform.python_implementation(),
        },
        "origins": origins,
        "installed": {"arras": arras_identity, "umf_core": umf_identity},
        "generated_client_sha256": generated_sha,
        "controls": {
            "arras_payload_record_parity": True,
            "umf_payload_record_parity": True,
            "imports_from_fresh_environment": True,
            "generated_client_apply_validate_vectors": True,
            "public_registration_and_import": True,
            "validate_has_no_public_state_change": True,
            "apply_and_read_at_least": True,
            "allowed_value_rejected_without_effect": True,
            "no_op_and_replay_stable": True,
            "current_access_denial_without_effect": True,
            "uncertain_response_not_retried": True,
            "corpus_reference_and_empty_registry_139": True,
        },
        "corpus": corpus,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--probe", action="store_true", required=True)
    parser.add_argument("arguments", nargs="+")
    args = parser.parse_args(argv)
    try:
        result = run_probe(args.arguments)
    except ProbeError as error:
        print(
            json.dumps({"status": "failed", "failure": {"stage": error.stage, "code": error.code}})
        )
        return 1
    except Exception:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "failure": {"stage": "probe", "code": "unexpected-internal-error"},
                }
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
