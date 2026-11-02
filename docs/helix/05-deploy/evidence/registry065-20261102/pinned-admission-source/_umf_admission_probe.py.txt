#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Fixed probes executed only inside the verifier's fresh isolated environments."""

from __future__ import annotations

import argparse
import base64
import configparser
import csv
import hashlib
import importlib.metadata
import json
import os
import stat
import sys
import sysconfig
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, cast

UMF_URL = (
    "https://github.com/DocumentDrivenDX/umf/releases/download/umf-v0.5.4/"
    "umf_core-0.10.0-py3-none-any.whl"
)
UMF_SHA256 = "49633924b45a3c8499d4fcc1a24c30d5a8fcb34d974ab019bbda987cb47da0f9"
CORPUS_SHA256 = "bb008a98b8448050748e65f867e7863475ccad9501a5b9229ae9e6d336691544"
MAX_CORPUS_BYTES = 16 * 1024 * 1024
_GENERATED_DIST_INFO = {"INSTALLER", "REQUESTED", "direct_url.json", "RECORD"}


class VerificationError(RuntimeError):
    """A bounded probe failure that does not echo source or host details."""

    def __init__(self, stage: str, code: str) -> None:
        self.stage = stage
        self.code = code
        super().__init__(f"{stage}: {code}")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_member(name: str) -> None:
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or path.is_absolute()
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise VerificationError("wheel", "unsafe-member-path")


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _validate_corpus(raw: bytes) -> tuple[dict[str, Any], tuple[str, ...]]:
    if len(raw) > MAX_CORPUS_BYTES or _sha256_bytes(raw) != CORPUS_SHA256:
        raise VerificationError("corpus", "fixture-digest-mismatch")
    try:
        corpus = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationError("corpus", "invalid-json") from error
    if not isinstance(corpus, dict) or corpus.get("profile") != "umf.current-conformance/1":
        raise VerificationError("corpus", "unexpected-corpus-profile")
    if corpus.get("currentVersion") != "0.10.0":
        raise VerificationError("corpus", "unexpected-corpus-version")
    cases = corpus.get("cases")
    if not isinstance(cases, list) or len(cases) != 139:
        raise VerificationError("corpus", "unexpected-case-count")
    ids: list[str] = []
    for case in cases:
        if not isinstance(case, dict):
            raise VerificationError("corpus", "invalid-case")
        case_id = case.get("id")
        if type(case_id) is not str or not case_id or not isinstance(case.get("document"), dict):
            raise VerificationError("corpus", "invalid-case-identity-or-document")
        if type(case.get("valid")) is not bool or type(case.get("complete")) is not bool:
            raise VerificationError("corpus", "invalid-case-expectation")
        if not isinstance(case.get("diagnostics"), list):
            raise VerificationError("corpus", "invalid-case-diagnostics")
        ids.append(case_id)
    if len(set(ids)) != len(ids):
        raise VerificationError("corpus", "duplicate-case-id")
    return cast(dict[str, Any], corpus), tuple(ids)


def _metadata_from_installed(name: str) -> tuple[Any, Path]:
    try:
        distribution = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError as error:
        raise VerificationError("probe", "installed-distribution-missing") from error
    root = Path(distribution.locate_file("")).resolve()
    return distribution, root


def _console_script_paths(archive: zipfile.ZipFile, dist_info: str, root: Path) -> dict[str, Path]:
    """Only wheel-declared launchers may live outside site-packages in this venv."""
    try:
        raw = archive.read(f"{dist_info}/entry_points.txt").decode("utf-8")
    except KeyError:
        return {}
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        parser.read_string(raw)
    except configparser.Error as error:
        raise VerificationError("payload", "invalid-entry-points") from error
    if not parser.has_section("console_scripts"):
        return {}
    scripts = Path(sysconfig.get_path("scripts"))
    if scripts.is_symlink() or not _inside(scripts, Path(sys.prefix)):
        raise VerificationError("payload", "scripts-directory-outside-venv")
    allowed: dict[str, Path] = {}
    for name in parser["console_scripts"]:
        _safe_member(name)
        if PurePosixPath(name).name != name:
            raise VerificationError("payload", "invalid-console-script-name")
        script = scripts / name
        relative = Path(os.path.relpath(script, root)).as_posix()
        allowed[relative] = script
    return allowed


def _compare_installed_payload(wheel: Path, distribution_name: str) -> int:
    distribution, root = _metadata_from_installed(distribution_name)
    try:
        with zipfile.ZipFile(wheel) as archive:
            files = [info for info in archive.infolist() if not info.is_dir()]
            dist_info = next(
                name.split("/", 1)[0]
                for name in (info.filename for info in files)
                if name.endswith(".dist-info/METADATA")
            )
            console_scripts = _console_script_paths(archive, dist_info, root)
            compared = 0
            for info in files:
                name = info.filename
                if name == f"{dist_info}/RECORD" or (
                    name.startswith(f"{dist_info}/")
                    and name.removeprefix(f"{dist_info}/") in _GENERATED_DIST_INFO
                ):
                    continue
                installed = Path(distribution.locate_file(name)).resolve()
                if (
                    not _inside(installed, root)
                    or not installed.is_file()
                    or installed.stat().st_size != info.file_size
                    or installed.read_bytes() != archive.read(info)
                ):
                    raise VerificationError("payload", "installed-wheel-payload-mismatch")
                compared += 1
    except (OSError, zipfile.BadZipFile, StopIteration) as error:
        raise VerificationError("payload", "installed-payload-unavailable") from error
    _verify_installed_record(distribution, root, console_scripts)
    return compared


def _verify_installed_record(
    distribution: Any, root: Path, console_scripts: dict[str, Path]
) -> None:
    """Check installed bytes, including each wheel-declared venv launcher exactly once."""
    record = distribution.read_text("RECORD")
    if record is None:
        raise VerificationError("payload", "installed-record-missing")
    try:
        rows = list(csv.reader(record.splitlines()))
    except csv.Error as error:
        raise VerificationError("payload", "installed-record-invalid") from error
    seen_console_scripts: set[str] = set()
    for name, digest, size in rows:
        script = console_scripts.get(name)
        if script is not None:
            if name in seen_console_scripts:
                raise VerificationError("payload", "installed-console-script-duplicate")
            seen_console_scripts.add(name)
        located = Path(distribution.locate_file(name))
        if script is None:
            _safe_member(name)
        elif (
            located.is_symlink()
            or located.resolve() != script.resolve()
            or not digest.startswith("sha256=")
            or not size.isdigit()
        ):
            raise VerificationError("payload", "installed-console-script-invalid")
        installed = located.resolve()
        if (script is None and not _inside(installed, root)) or not installed.is_file():
            raise VerificationError("payload", "installed-record-file-missing")
        if installed.stat().st_size > MAX_CORPUS_BYTES:
            raise VerificationError("payload", "installed-record-file-over-limit")
        content = installed.read_bytes()
        if size and (not size.isdigit() or int(size) != len(content)):
            raise VerificationError("payload", "installed-record-size-mismatch")
        if digest:
            if not digest.startswith("sha256="):
                raise VerificationError("payload", "installed-record-digest-unsupported")
            expected = digest.removeprefix("sha256=")
            actual = (
                base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
            )
            if expected != actual:
                raise VerificationError("payload", "installed-record-digest-mismatch")
    if seen_console_scripts != set(console_scripts):
        raise VerificationError("payload", "installed-console-script-missing")


def _check_import_paths(packages: dict[str, Any], repository: Path, site: Path) -> dict[str, str]:
    trusted_tool_dir = Path(__file__).resolve().parent
    origins: dict[str, str] = {}
    for name, module in packages.items():
        origin = Path(cast(str, module.__file__)).resolve()
        if not _inside(origin, site) or _inside(origin, repository):
            raise VerificationError("imports", f"{name}-origin-invalid")
        origins[name] = origin.relative_to(site).as_posix()
    base_prefix = Path(sys.base_prefix).resolve()
    environment_prefix = Path(sys.prefix).resolve()
    for entry in sys.path:
        if not entry:
            raise VerificationError("imports", "empty-sys-path-entry")
        path = Path(entry).resolve()
        allowed = (
            path == trusted_tool_dir
            or _inside(path, environment_prefix)
            or _inside(path, base_prefix)
        )
        shared_site = any(part in ("site-packages", "dist-packages") for part in path.parts)
        if shared_site and not _inside(path, environment_prefix):
            raise VerificationError("imports", "shared-package-site-on-import-path")
        if not allowed or (_inside(path, repository) and path != trusted_tool_dir):
            raise VerificationError("imports", "checkout-on-import-path")
    pth_files = tuple(site.glob("*.pth"))
    for pth in pth_files:
        if pth.name != "distutils-precedence.pth":
            raise VerificationError("imports", "unexpected-pth-file")
        _verify_bootstrap_pth(pth, site)
    return origins


def _verify_bootstrap_pth(path: Path, site: Path) -> None:
    """Accept only the fresh interpreter's setuptools pth with matching RECORD bytes."""
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 4096:
            raise VerificationError("imports", "bootstrap-pth-not-regular")
        payload = path.read_bytes()
        distribution = importlib.metadata.distribution("setuptools")
        files = distribution.files or ()
    except VerificationError:
        raise
    except (OSError, importlib.metadata.PackageNotFoundError) as error:
        raise VerificationError("imports", "bootstrap-pth-unavailable") from error
    if not _inside(path.resolve(), site):
        raise VerificationError("imports", "bootstrap-pth-outside-site")
    for entry in files:
        installed = Path(distribution.locate_file(entry)).resolve()
        if installed != path.resolve() or entry.hash is None:
            continue
        if entry.hash.mode != "sha256":
            break
        expected = base64.urlsafe_b64encode(hashlib.sha256(payload).digest())
        expected = expected.rstrip(b"=").decode("ascii")
        if entry.hash.value == expected:
            return
        break
    raise VerificationError("imports", "bootstrap-pth-record-mismatch")


def _probe_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--_probe", choices=("base", "extra"), required=True)
    parser.add_argument("arguments", nargs="+")
    args = parser.parse_args(argv)
    if args._probe == "base":
        if len(args.arguments) != 3:
            parser.error("base probe requires repository, metadata fixture, and Arras wheel")
        result = _probe_base(
            Path(args.arguments[0]), Path(args.arguments[1]), Path(args.arguments[2])
        )
    else:
        if len(args.arguments) != 5:
            parser.error("extra probe requires repository, corpus, metadata, and both wheels")
        result = _probe_extra(
            Path(args.arguments[0]),
            Path(args.arguments[1]),
            Path(args.arguments[2]),
            Path(args.arguments[3]),
            Path(args.arguments[4]),
        )
    print(json.dumps(result, sort_keys=True))
    return 0


def _probe_base(repository: Path, metadata_path: Path, arras_wheel: Path) -> dict[str, Any]:
    import importlib.util
    from importlib import resources

    if importlib.util.find_spec("umf") is not None:
        raise VerificationError("base", "optional-engine-present-before-probe")
    arras_payload = _compare_installed_payload(arras_wheel, "arras")
    import arras
    from arras import Arras, Placement, Unsupported
    from arras.testing import InMemory
    from arras.umf_admission import admit_document, project_document

    site = Path(sysconfig.get_paths()["purelib"]).resolve()
    origins = _check_import_paths({"arras": arras}, repository, site)
    legacy_source = resources.files("arras.conformance").joinpath("module.umf.json").read_bytes()
    legacy = InMemory(store="legacy_primary", replica="legacy_replica")
    legacy.register(legacy_source)
    legacy_reader = legacy.person("legacy-reader", "catalog", "read")
    if (
        legacy.arras.session(legacy_reader).document("catalog").text.encode("utf-8")
        != legacy_source
    ):
        raise VerificationError("base", "legacy-document-readback-mismatch")
    rows = legacy.arras.session(legacy_reader).query(
        "catalog", "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 5"
    )
    if rows.rows:
        raise VerificationError("base", "legacy-empty-read-mismatch")

    source = metadata_path.read_bytes()
    for operation in (admit_document, project_document):
        try:
            operation(source)
        except Unsupported as error:
            if error.construct != "official UMF admission":
                raise VerificationError("base", "wrong-missing-engine-refusal") from None
        else:
            raise VerificationError("base", "missing-engine-fallback")
    metadata = InMemory(store="metadata_primary", replica="metadata_replica")
    metadata_host = Arras.start(
        metadata.backends,
        admin=metadata.admin,
        default_placement=Placement("metadata_primary", ("metadata_replica",)),
        metadata_profile="umf-core-metadata/1",
    )
    try:
        metadata_host.session(metadata.admin).registry().register(source)
    except Unsupported as error:
        if error.construct != "official UMF admission":
            raise VerificationError("base", "wrong-host-missing-engine-refusal") from None
    else:
        raise VerificationError("base", "metadata-host-fell-back-to-legacy")
    if importlib.util.find_spec("umf") is not None:
        raise VerificationError("base", "optional-engine-imported")
    inventory = _distribution_inventory()
    if "umf-core" in {name.lower() for name in inventory}:
        raise VerificationError("base", "optional-engine-installed")
    return {
        "status": "passed",
        "mode": "base",
        "arras_version": importlib.metadata.version("arras"),
        "controls": {
            "legacy_registration_document_and_empty_read": True,
            "base_has_no_umf_distribution": True,
            "base_imported_no_umf": True,
            "admission_refuses_missing_engine": True,
            "projection_refuses_missing_engine": True,
            "selected_host_refuses_without_fallback": True,
        },
        "installed_distributions": inventory,
        "payload": {"arras_exact_files": arras_payload},
        "import_origins": origins,
        "pth_reuse": False,
        "source_aliases": False,
    }


def _probe_extra(
    repository: Path,
    corpus_path: Path,
    metadata_path: Path,
    arras_wheel: Path,
    umf_wheel: Path,
) -> dict[str, Any]:
    import importlib.util

    site = Path(sysconfig.get_paths()["purelib"]).resolve()
    arras_payload = _compare_installed_payload(arras_wheel, "arras")
    umf_payload = _compare_installed_payload(umf_wheel, "umf-core")
    import umf

    import arras

    origins = _check_import_paths({"arras": arras, "umf": umf}, repository, site)
    sdk_direct_url = _direct_url("umf-core")
    if sdk_direct_url != {"url": UMF_URL, "sha256": UMF_SHA256}:
        raise VerificationError("extra", "installed-sdk-source-mismatch")
    if importlib.metadata.version("umf-core") != "0.10.0":
        raise VerificationError("extra", "installed-sdk-version-mismatch")
    corpus_raw = corpus_path.read_bytes()
    corpus, ids = _validate_corpus(corpus_raw)
    corpus_result = _run_conformance(corpus, ids)
    controls = _run_metadata_controls(metadata_path, corpus)
    if importlib.util.find_spec("umf") is None:
        raise VerificationError("extra", "optional-engine-import-unavailable")
    return {
        "status": "passed",
        "mode": "extra",
        "arras_version": importlib.metadata.version("arras"),
        "umf_version": importlib.metadata.version("umf-core"),
        "umf_sha256": UMF_SHA256,
        "controls": controls,
        "corpus": corpus_result,
        "payload": {"arras_exact_files": arras_payload, "umf_exact_files": umf_payload},
        "installed_distributions": _distribution_inventory(),
        "import_origins": origins,
        "pth_reuse": False,
        "source_aliases": False,
        "direct_url_verified": True,
    }


def _distribution_inventory() -> dict[str, str]:
    result = {
        str(distribution.metadata["Name"]): distribution.version
        for distribution in importlib.metadata.distributions()
        if distribution.metadata.get("Name")
    }
    return dict(sorted(result.items(), key=lambda item: item[0].lower()))


def _direct_url(name: str) -> dict[str, str]:
    try:
        raw = importlib.metadata.distribution(name).read_text("direct_url.json")
        value = json.loads(raw) if raw is not None else None
    except (importlib.metadata.PackageNotFoundError, json.JSONDecodeError) as error:
        raise VerificationError("extra", "direct-url-metadata-missing") from error
    if not isinstance(value, dict):
        raise VerificationError("extra", "direct-url-metadata-invalid")
    archive = value.get("archive_info")
    hashes = archive.get("hashes") if isinstance(archive, dict) else None
    if not isinstance(hashes, dict):
        raise VerificationError("extra", "direct-url-digest-missing")
    return {"url": str(value.get("url", "")), "sha256": str(hashes.get("sha256", ""))}


def _case_registry(sdk: Any, spec: dict[str, Any] | None) -> Any:
    registry = sdk.Registry()
    if spec is None:
        return registry

    def validate(payload: dict[str, Any], context: dict[str, Any]) -> list[Any]:
        return [
            sdk.Diagnostic(
                "BASELINE_CALLBACK",
                context["path"],
                f"{context['document']['id']}:{context['scope']}:{payload['kind']}",
                "warning",
            )
        ]

    registry.register(sdk.Extension(spec["id"], spec["version"], (spec["scope"],), True, validate))
    return registry


def _diagnostic_tuples(items: Any) -> list[tuple[str, str, str, str]]:
    return [(item.code, item.path, item.message, item.severity) for item in items]


def _run_conformance(corpus: dict[str, Any], ids: tuple[str, ...]) -> dict[str, Any]:
    import umf

    from arras.umf_admission import admit_document

    api = umf
    reference_matches = 0
    empty_matches = 0
    for case, case_id in zip(corpus["cases"], ids, strict=True):
        source = json.dumps(case["document"], ensure_ascii=True).encode("utf-8")
        raw = api.read_json_value(source.decode("utf-8"), "json")
        reference = api.validate_document(raw, _case_registry(api, case.get("registry")))
        if (
            reference.valid is not case["valid"]
            or reference.complete is not case["complete"]
            or _diagnostic_tuples(reference.diagnostics)
            != [(d["code"], d["path"], d["message"], d["severity"]) for d in case["diagnostics"]]
        ):
            raise VerificationError("corpus", "reference-case-mismatch")
        reference_matches += 1

        admitted = admit_document(source)
        empty = api.validate_document(
            api.read_json_value(source.decode("utf-8"), "json"), api.Registry()
        )
        if (
            admitted.validation_status != "completed"
            or admitted.valid is not empty.valid
            or admitted.complete is not empty.complete
            or _diagnostic_tuples(admitted.diagnostics) != _diagnostic_tuples(empty.diagnostics)
        ):
            raise VerificationError("corpus", "empty-registry-case-mismatch")
        empty_matches += 1
        if case["id"] != case_id:
            raise VerificationError("corpus", "ordered-id-mismatch")
    if reference_matches != 139 or empty_matches != 139:
        raise VerificationError("corpus", "corpus-not-complete")
    return {
        "status": "passed",
        "fixture_sha256": CORPUS_SHA256,
        "case_count": 139,
        "unique_id_count": len(set(ids)),
        "ordered_case_ids": list(ids),
        "reference_matches": reference_matches,
        "empty_registry_matches": empty_matches,
        "skipped": 0,
    }


def _admit_metadata_source(source: bytes) -> tuple[Any, Any]:
    from arras.umf_admission import admit_document, project_document

    admitted = admit_document(source)
    projection = project_document(source)
    if (
        admitted.source != source
        or admitted.validation_status != "completed"
        or admitted.valid is not True
        or admitted.complete is not True
        or not projection.supported
        or projection.module is None
    ):
        raise VerificationError("projection", "core-fixture-not-supported")
    return admitted, projection


def _metadata_host_control(source: bytes, projection: Any) -> None:
    from arras import Arras, Placement
    from arras.testing import InMemory

    world = InMemory(store="metadata_primary", replica="metadata_replica")
    host = Arras.start(
        world.backends,
        admin=world.admin,
        default_placement=Placement("metadata_primary", ("metadata_replica",)),
        metadata_profile="umf-core-metadata/1",
    )
    host.session(world.admin).registry().register(source)
    module_name = projection.module.name
    reader = world.person("metadata-reader", module_name, "read")
    reader_session = host.session(reader)
    if reader_session.document(module_name).text.encode("utf-8") != source:
        raise VerificationError("projection", "source-byte-readback-mismatch")
    [description] = reader_session.describe(module_name)
    if description.metadata_profile != "umf-core-metadata/1":
        raise VerificationError("projection", "metadata-profile-lost")
    entity = description.entity_types[0]
    caps = entity.capabilities.get("metadata_primary")
    if caps is None:
        raise VerificationError("projection", "memory-capability-missing")
    if caps.mutable is not False:
        raise VerificationError("projection", "metadata-capability-mutable")
    entity = projection.module.entity_types[0]
    query = f'SELECT e."{entity.key}" FROM "{module_name}"."{entity.local_name}" e LIMIT 5'
    before_query = reader_session.query(module_name, query)
    if before_query.rows:
        raise VerificationError("projection", "metadata-query-not-empty")
    _metadata_write_refusals(source, world, reader_session, module_name, query, before_query)


def _metadata_write_refusals(
    source: bytes, world: Any, reader_session: Any, module_name: str, query: str, before_query: Any
) -> None:
    from dataclasses import replace
    from types import SimpleNamespace

    from arras import Invalid, Unsupported

    before_document = reader_session.document(module_name).text.encode("utf-8")
    before_description = reader_session.describe(module_name)[0]
    provider = world.backends["metadata_primary"]
    try:
        provider.apply(
            world.admin,
            SimpleNamespace(action=f"{module_name}.Create"),
            idempotency_key="installed-proof",
        )
    except Unsupported as error:
        if "metadata-only profile" not in str(error):
            raise VerificationError("projection", "wrong-direct-write-refusal") from None
    else:
        raise VerificationError("projection", "metadata-direct-write-accepted")
    if (
        reader_session.document(module_name).text.encode("utf-8") != before_document
        or reader_session.describe(module_name)[0].revision != before_description.revision
        or reader_session.query(module_name, query) != before_query
    ):
        raise VerificationError("projection", "write-refusal-had-effects")

    changed_profile = replace(before_description, metadata_profile="legacy-arras/1")
    try:
        provider.register(world.admin, source, changed_profile, unknown_endpoint="reject")
    except Invalid as error:
        if not any(item.path == "metadata_profile" for item in error.violations):
            raise VerificationError(
                "projection", "profile-transition-refused-for-wrong-reason"
            ) from None
    else:
        raise VerificationError("projection", "profile-transition-accepted")
    if (
        reader_session.document(module_name).text.encode("utf-8") != before_document
        or reader_session.describe(module_name)[0].revision != before_description.revision
        or reader_session.query(module_name, query) != before_query
    ):
        raise VerificationError("projection", "profile-transition-changed-source")


def _metadata_source_controls(source: bytes, corpus: dict[str, Any]) -> None:
    from arras.umf_admission import project_document

    complete_case = next(c for c in corpus["cases"] if c["id"] == "defaults/present-null-applies")
    complete_raw = json.dumps(complete_case["document"], ensure_ascii=True).encode("utf-8")
    outside = project_document(complete_raw)
    if (
        outside.admission.valid is not True
        or outside.admission.complete is not True
        or outside.supported
    ):
        raise VerificationError("projection", "complete-unsupported-control-mismatch")
    incomplete_case = next(
        c for c in corpus["cases"] if c["id"] == "unknown/current-extension-and-fields"
    )
    incomplete_raw = json.dumps(incomplete_case["document"], ensure_ascii=True).encode("utf-8")
    incomplete = project_document(incomplete_raw)
    if (
        incomplete.admission.valid is not True
        or incomplete.admission.complete is not False
        or incomplete.supported
    ):
        raise VerificationError("projection", "incomplete-source-control-mismatch")
    if incomplete.admission.source != incomplete_raw:
        raise VerificationError("projection", "incomplete-source-not-preserved")

    _metadata_repr_control(source)


def _metadata_repr_control(source: bytes) -> None:
    from importlib import resources

    from arras.umf_admission import project_document

    legacy_source = resources.files("arras.conformance").joinpath("module.umf.json").read_bytes()
    if "UNKNOWN-SENTINEL" in repr(project_document(legacy_source)):
        raise VerificationError("projection", "repr-leaked-source")

    document = json.loads(source)
    document["title"] = "PRIVATE-ADMISSION-SENTINEL-ONLY"
    sentinel_source = json.dumps(document, ensure_ascii=True).encode("utf-8")
    sentinel_projection = project_document(sentinel_source)
    if (
        sentinel_projection.admission.source != sentinel_source
        or "PRIVATE-ADMISSION-SENTINEL-ONLY" in repr(sentinel_projection)
        or "PRIVATE-ADMISSION-SENTINEL-ONLY" in repr([sentinel_projection])
    ):
        raise VerificationError("projection", "source-only-repr-leaked-content")


def _legacy_profile_control(source: bytes) -> None:
    from arras import Arras, Invalid, Placement
    from arras.testing import InMemory

    world = InMemory(store="legacy_primary", replica="legacy_replica")
    host = Arras.start(
        world.backends,
        admin=world.admin,
        default_placement=Placement("legacy_primary", ("legacy_replica",)),
    )
    try:
        host.session(world.admin).registry().register(source)
    except Invalid:
        return
    raise VerificationError("projection", "default-profile-auto-detected-core-source")


def _unqualified_provider_control(source: bytes) -> None:
    from dataclasses import replace

    from arras import Arras, Invalid, Placement
    from arras.testing import InMemory

    world = InMemory(store="unqualified_primary", replica="unqualified_replica")
    backends = dict(world.backends)
    primary = backends["unqualified_primary"]

    class UnqualifiedBackend:
        def __getattr__(self, name: str) -> Any:
            return getattr(primary, name)

        def describe(self) -> Any:
            return replace(primary.describe(), metadata_profiles=("legacy-arras/1",))

    backends["unqualified_primary"] = UnqualifiedBackend()
    host = Arras.start(
        backends,
        admin=world.admin,
        default_placement=Placement("unqualified_primary", ("unqualified_replica",)),
        metadata_profile="umf-core-metadata/1",
    )
    try:
        host.session(world.admin).registry().register(source)
    except Invalid:
        if world.backends["unqualified_primary"].catalog(world.admin):
            raise VerificationError("projection", "unqualified-provider-accepted-module") from None
        return
    raise VerificationError("projection", "unqualified-provider-accepted-module")


def _run_metadata_controls(metadata_path: Path, corpus: dict[str, Any]) -> dict[str, bool]:
    source = metadata_path.read_bytes()
    _admitted, projection = _admit_metadata_source(source)
    _metadata_host_control(source, projection)
    _metadata_source_controls(source, corpus)
    _legacy_profile_control(source)
    _unqualified_provider_control(source)
    return {
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


if __name__ == "__main__":
    raise SystemExit(_probe_main(sys.argv[1:]))
