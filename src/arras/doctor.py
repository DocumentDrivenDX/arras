# SPDX-License-Identifier: MIT OR Apache-2.0
"""Offline, bounded compatibility checks over the carried Arras package catalog."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.resources
import io
import json
import os
import re
import stat
import sys
import tarfile
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, NoReturn, cast

from arras._doctor_types import (
    Diagnostic,
    DistributionInvalid,
    DoctorReport,
    DoctorRequest,
    _telemetry_fields,  # pyright: ignore[reportPrivateUsage]
    distribution_error_report,
    load_json_object,
    pairs,
    request_error_report,
)
from arras.branding import Brand
from arras.distribution import DistributionConfig, TelemetryNames
from arras.mcp.config import (
    _parse_committed_document,  # pyright: ignore[reportPrivateUsage]
    merge_committed,
    validate_committed,
    validate_distribution,
)
from arras.ui.assets import load_manifest, validate_cohort
from arras.umf import UMF_VERSION, parse_module
from arras.versions import CONTRACT_VERSIONS
from arras.view import VERSION as VIEW_VERSION
from arras.view import VOCABULARY as VIEW_VOCABULARY

_MAX_REQUEST = 1024 * 1024
_MAX_CONFIG = 1024 * 1024
_MAX_DOCUMENT = 16 * 1024 * 1024
_MAX_COMBINED = 64 * 1024 * 1024
_SAFE_NAME = re.compile(r"[A-Za-z0-9_./@+-]{1,256}\Z")
_PACKAGES = frozenset({"arras", "@documentdrivendx/arras-ui"})
_RUNTIME_KEYS = frozenset(CONTRACT_VERSIONS)


def _read_regular(path: Path, limit: int) -> bytes:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
    )
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("file type or size is outside the supported bound")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("file type or size is outside the supported bound")
    return data


def _catalog() -> dict[str, Any]:
    with importlib.resources.files("arras").joinpath("public-api.json").open("rb") as stream:
        raw = stream.read(_MAX_REQUEST + 1)
    if len(raw) > _MAX_REQUEST:
        raise ValueError("catalog exceeds its bound")
    data = load_json_object(raw)
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        raise ValueError("catalog schema unsupported")
    contracts = data.get("contracts")
    python = data.get("python")
    distribution = data.get("distribution")
    ui = data.get("ui")
    if any(type(item) is not dict for item in (contracts, python, distribution, ui)):
        raise ValueError("catalog structure unsupported")
    py_data = cast(dict[str, Any], python)
    dist_data = cast(dict[str, Any], distribution)
    ui_data = cast(dict[str, Any], ui)
    npm_data = dist_data.get("npm")
    if (
        type(py_data.get("modules")) is not dict
        or type(py_data.get("root_all")) is not list
        or type(npm_data) is not dict
        or type(cast(dict[str, Any], npm_data).get("exports")) is not dict
        or type(ui_data.get("role_tokens")) is not list
    ):
        raise ValueError("catalog structure unsupported")
    npm = cast(dict[str, Any], npm_data)
    distribution_data = cast(dict[str, Any], distribution)
    host = data.get("host_configuration")
    if (
        not isinstance(distribution_data.get("version"), str)
        or not distribution_data.get("version")
        or not isinstance(npm.get("version"), str)
        or not npm.get("version")
        or type(npm.get("name")) is not str
        or type(npm.get("exports")) is not dict
        or type(ui_data.get("npm_runtime_exports")) is not dict
        or type(ui_data.get("npm_type_exports")) is not dict
        or type(host) is not dict
        or type(cast(dict[str, Any], host).get("environment")) is not dict
    ):
        raise ValueError("catalog structure unsupported")
    environment = cast(dict[str, Any], host)["environment"]
    if (
        not isinstance(environment.get("keys"), list)
        or type(environment.get("pattern")) is not dict
        or not isinstance(environment.get("ignored_prefixes"), list)
        or not all(isinstance(name, str) for name in cast(list[object], environment["keys"]))
    ):
        raise ValueError("catalog environment inventory unsupported")
    contract_data = cast(dict[str, Any], contracts)
    module_data = cast(dict[str, Any], py_data["modules"])
    if any(
        type(spec) is not dict or not isinstance(spec.get("names"), list | str)
        for spec in module_data.values()
    ):
        raise ValueError("catalog module entries unsupported")
    if not all(isinstance(name, str) for name in cast(list[object], py_data["root_all"])):
        raise ValueError("catalog root exports unsupported")
    for spec in module_data.values():
        names = cast(dict[str, Any], spec)["names"]
        if isinstance(names, list) and not all(
            isinstance(name, str) for name in cast(list[object], names)
        ):
            raise ValueError("catalog module exports unsupported")
        if isinstance(names, str) and names != "root_all":
            raise ValueError("catalog module export reference unsupported")
    if any(
        type(spec) is not dict or type(spec.get("version")) is not int or spec.get("version", 0) < 1
        for spec in contract_data.values()
    ):
        raise ValueError("catalog contract entries unsupported")
    return data


def _npm_package() -> tuple[str | None, dict[str, Any] | None]:
    directory = importlib.resources.files("arras").joinpath("ui", "npm")
    candidates = [item for item in directory.iterdir() if item.name.endswith(".tgz")]
    if len(candidates) != 1:
        return None, None
    with candidates[0].open("rb") as stream:
        raw = stream.read(_MAX_COMBINED + 1)
    if len(raw) > _MAX_COMBINED:
        return None, None
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r|gz") as archive:
        seen = 0
        expanded = 0
        package: object | None = None
        for member in archive:
            seen += 1
            expanded += max(0, member.size)
            if seen > 10000 or expanded > _MAX_COMBINED:
                return None, None
            if member.name != "package/package.json":
                continue
            if package is not None or not member.isreg() or member.size > _MAX_REQUEST:
                return None, None
            stream = archive.extractfile(member)
            if stream is None:
                return None, None
            package = json.loads(
                stream.read(_MAX_REQUEST + 1).decode("utf-8"), object_pairs_hook=pairs
            )
        if package is None:
            return None, None
    return hashlib.sha256(raw).hexdigest(), cast(dict[str, Any], package) if isinstance(
        package, dict
    ) else None


def _diagnostic(
    rows: list[Diagnostic],
    code: str,
    severity: Literal["error", "unsupported", "warning", "info"],
    surface: str,
    path: str,
    message: str,
) -> None:
    safe_path = path if _SAFE_NAME.fullmatch(path) else "request"
    rows.append(Diagnostic(code, severity, surface, safe_path, message))


def _check_configs(
    paths: tuple[Path, ...], selected: DistributionConfig, rows: list[Diagnostic]
) -> int:
    merged: dict[str, Any] = {}
    origin: dict[str, str] = {}
    total = 0
    for index, path in enumerate(paths):
        label = f"config_files[{index}]"
        try:
            raw = _read_regular(path, min(_MAX_CONFIG, _MAX_COMBINED - total))
            total += len(raw)
            data = _parse_committed_document(raw)
            problems: list[str] = []
            valid = validate_committed(str(path), data, problems)
            if not valid:
                _diagnostic(
                    rows,
                    "config_invalid",
                    "error",
                    "config",
                    label,
                    "committed configuration contains unsupported keys or values",
                )
            else:
                merge_committed(merged, data, origin, str(path))
        except Exception:
            _diagnostic(
                rows,
                "config_invalid",
                "error",
                "config",
                label,
                "committed configuration could not be safely read or parsed",
            )
    problems: list[str] = []
    try:
        validate_distribution(merged.get("distribution", {}), selected, problems)
    except Exception:
        problems.append("invalid")
    if problems:
        _diagnostic(
            rows,
            "distribution_invalid",
            "error",
            "distribution",
            "distribution",
            "committed distribution settings violate Brand or launcher constraints",
        )
    return total


def _check_environment_names(
    names: tuple[str, ...],
    selected: DistributionConfig,
    catalog: dict[str, Any],
    rows: list[Diagnostic],
) -> None:
    env = catalog.get("host_configuration", {}).get("environment", {})
    canonical = set(env.get("keys", []))
    pattern = env.get("pattern", {}).get("key", "")
    ignored = tuple(env.get("ignored_prefixes", []))
    prefix = selected.env_prefix
    suffixes = {key.removeprefix("ARRAS_") for key in canonical if key.startswith("ARRAS_")}
    token_seen = False
    file_seen = False
    for index, name in enumerate(names):
        custom_alias = prefix != "ARRAS" and name.startswith(prefix + "_")
        suffix = name.removeprefix(prefix + "_") if custom_alias else name.removeprefix("ARRAS_")
        is_canonical = name in canonical
        pattern_name = pattern
        if custom_alias:
            pattern_name = prefix + pattern.removeprefix("ARRAS")
        is_pattern = "<NAME>" in pattern_name and bool(
            re.fullmatch(pattern_name.replace("<NAME>", r"[A-Z][A-Z0-9_]*"), name)
        )
        is_alias = prefix != "ARRAS" and name.startswith(prefix + "_") and suffix in suffixes
        is_ignored = any(name.startswith(item) for item in ignored) or (
            custom_alias
            and any(name.startswith(prefix + item.removeprefix("ARRAS")) for item in ignored)
        )
        if (
            not name.isascii()
            or not name.isupper()
            or not (is_canonical or is_pattern or is_alias or is_ignored)
        ):
            _diagnostic(
                rows,
                "env_name_unknown",
                "error",
                "environment",
                f"env_names[{index}]",
                "environment name is not declared for the selected namespace",
            )
        token_seen |= suffix == "TOKEN"
        file_seen |= suffix == "TOKEN_FILE"
    if token_seen and file_seen:
        _diagnostic(
            rows,
            "credential_sources_possible",
            "warning",
            "environment",
            "env_names",
            "both token and token-file source names are present; values were not read",
        )


def _package_observation(
    observed: dict[str, object], rows: list[Diagnostic]
) -> tuple[str | None, bool, dict[str, Any] | None]:
    version: str | None = None
    installed_origin = False
    try:
        dist = importlib.metadata.distribution("arras")
        version = dist.version
        expected = Path(str(dist.locate_file("arras/public-api.json"))).resolve()
        actual = Path(str(importlib.resources.files("arras").joinpath("public-api.json"))).resolve()
        inventory = dist.files
        recorded = inventory is not None and any(
            str(item).replace("\\", "/") == "arras/public-api.json" for item in inventory
        )
        direct_url = dist.read_text("direct_url.json")
        editable = bool(
            direct_url and json.loads(direct_url).get("dir_info", {}).get("editable", False)
        )
        installed_origin = expected == actual and recorded and not editable
    except importlib.metadata.PackageNotFoundError:
        pass
    except Exception:
        installed_origin = False
        version = None
    if installed_origin and version:
        observed["python_package_version"] = version
        observed["provenance"] = "installed metadata and package resource agree"
    else:
        observed["python_package_source"] = (
            "source or editable resource; not installed-pin evidence"
        )
    try:
        digest, package = _npm_package()
    except Exception:
        digest, package = None, None
        _diagnostic(
            rows,
            "package_missing",
            "unsupported",
            "npm",
            "package",
            "wheel-carried package metadata is not observable",
        )
    if package is None and not any(row.code == "package_missing" for row in rows):
        _diagnostic(
            rows,
            "package_missing",
            "unsupported",
            "npm",
            "package",
            "wheel-carried npm package metadata is not observable",
        )
    if package is not None:
        observed["npm_package"] = {
            "name": package.get("name"),
            "version": package.get("version"),
            "tarball_sha256": digest,
            "provenance": "wheel-carried archive package metadata",
        }
    return version, installed_origin, package


def _check_requested_packages(
    request: DoctorRequest,
    version: str | None,
    installed: bool,
    npm: dict[str, Any] | None,
    rows: list[Diagnostic],
) -> None:
    for name, expected in request.expected_packages.items():
        if name not in _PACKAGES or any(c in expected for c in "<>~=,* "):
            _diagnostic(
                rows,
                "capability_unsupported",
                "unsupported",
                "package",
                "expected_packages",
                "only exact pins for the carried Python and npm packages are supported",
            )
            continue
        actual = (
            version
            if name == "arras" and installed
            else (cast(str | None, npm.get("version")) if name != "arras" and npm else None)
        )
        if actual is None:
            _diagnostic(
                rows,
                "package_missing",
                "unsupported",
                "package",
                name,
                "requested package version is not observable from the loaded package cohort",
            )
        elif actual != expected:
            _diagnostic(
                rows,
                "package_mismatch",
                "error",
                "package",
                name,
                "observed package version does not match the exact requested pin",
            )


def _check_npm_catalog_name(
    catalog: dict[str, Any], npm: dict[str, Any] | None, rows: list[Diagnostic]
) -> None:
    expected = catalog["distribution"]["npm"]
    if npm is None:
        return
    if npm.get("name") != expected["name"] or npm.get("version") != expected["version"]:
        _diagnostic(
            rows,
            "package_mismatch",
            "error",
            "npm",
            "package",
            "wheel-carried npm package name or version differs from the carried catalog",
        )


def _check_python_catalog_version(
    catalog: dict[str, Any], version: str | None, installed: bool, rows: list[Diagnostic]
) -> None:
    expected = catalog["distribution"]["version"]
    if installed and version is not None and version != expected:
        _diagnostic(
            rows,
            "package_mismatch",
            "error",
            "package",
            "arras",
            "installed Python version differs from the carried catalog",
        )


def _check_catalog_requests(
    request: DoctorRequest, catalog: dict[str, Any], rows: list[Diagnostic]
) -> None:
    contracts = catalog["contracts"]
    for key, expected in request.expected_contracts.items():
        actual = (
            CONTRACT_VERSIONS.get(key)
            if key in _RUNTIME_KEYS
            else contracts.get(key, {}).get("version")
        )
        if actual is None:
            _diagnostic(
                rows,
                "capability_unsupported",
                "unsupported",
                "contract",
                key,
                "contract version key is not declared",
            )
        elif actual != expected:
            _diagnostic(
                rows,
                "contract_mismatch",
                "error",
                "contract",
                key,
                "declared contract version differs from the requested version",
            )
    python = catalog["python"]
    for module, names in request.required_python_exports.items():
        spec = python["modules"].get(module)
        if not spec:
            _diagnostic(
                rows,
                "python_export_missing",
                "error",
                "python",
                module,
                "requested Python module is absent from the carried catalog",
            )
            continue
        declared = set(
            python["root_all"]
            if spec and spec["names"] == "root_all"
            else spec["names"]
            if spec
            else ()
        )
        if set(names) - declared:
            _diagnostic(
                rows,
                "python_export_missing",
                "error",
                "python",
                module,
                "requested Python export is absent from the carried catalog",
            )
    _check_npm_requests(request, catalog, rows)
    role_tokens = catalog.get("ui", {}).get("role_tokens", [])
    for index, token in enumerate(request.required_role_tokens):
        if token not in role_tokens:
            _diagnostic(
                rows,
                "role_token_missing",
                "error",
                "theme",
                f"required_role_tokens[{index}]",
                "requested role token is not declared by the carried catalog",
            )


def _check_npm_requests(
    request: DoctorRequest, catalog: dict[str, Any], rows: list[Diagnostic]
) -> None:
    ui = catalog.get("ui", {})
    export_map = catalog["distribution"]["npm"]["exports"]
    for export, names in request.required_npm_exports.items():
        runtime = set(ui.get("npm_runtime_exports", {}).get(export, []))
        types = set(ui.get("npm_type_exports", {}).get(export, []))
        if export not in export_map or set(names) - runtime - types:
            _diagnostic(
                rows,
                "npm_export_missing",
                "error",
                "npm",
                export,
                "requested npm path or symbol is absent from the carried declarations",
            )


def _check_files(
    request: DoctorRequest,
    catalog: dict[str, Any],
    npm: dict[str, Any] | None,
    include_configs: bool,
    observed: dict[str, object],
    rows: list[Diagnostic],
) -> int:
    if request.distribution is not None:
        selected = request.distribution
        observed["distribution"] = {
            "brand": selected.brand.name,
            "mcp_server_name": selected.mcp_server_name,
            "mcp_tool_prefix": selected.mcp_tool_prefix,
            "env_prefix": selected.env_prefix,
            "provenance": "validated typed request",
        }
    chosen = request.distribution or DistributionConfig()
    _check_environment_names(request.env_names, chosen, catalog, rows)
    consumed = (
        _check_configs(request.config_files, chosen, rows)
        if request.config_files and include_configs
        else 0
    )
    page = None
    theme = None
    try:
        page = (
            load_manifest(request.asset_manifest, kind="page") if request.asset_manifest else None
        )
    except Exception:
        _diagnostic(
            rows,
            "asset_invalid",
            "error",
            "assets",
            "asset_manifest",
            "selected page manifest is invalid or unsafe",
        )
    try:
        theme = (
            load_manifest(request.theme_manifest, kind="theme") if request.theme_manifest else None
        )
    except Exception:
        _diagnostic(
            rows,
            "asset_invalid",
            "error",
            "theme",
            "theme_manifest",
            "selected theme manifest is invalid or unsafe",
        )
    if request.theme_manifest and page is None:
        _diagnostic(
            rows,
            "theme_incompatible",
            "error",
            "theme",
            "theme_manifest",
            "a valid page manifest is required to establish the UI cohort",
        )
    if page:
        observed["asset_manifest"] = {
            "sha256": page.manifest_sha256,
            "version": page.version,
            "provenance": "validated selected manifest",
        }
    if theme:
        observed["theme_manifest"] = {
            "sha256": theme.manifest_sha256,
            "version": theme.version,
            "provenance": "validated selected manifest",
        }
    if page:
        try:
            ui_contracts = {
                key: catalog["contracts"][contract]["version"]
                for key, contract in {
                    "console": "CONTRACT-006",
                    "operate": "CONTRACT-009",
                    "schema": "CONTRACT-011",
                    "browser": "CONTRACT-010",
                }.items()
            }
            if npm is None:
                raise ValueError("npm package metadata is unavailable")
            validate_cohort(
                page,
                theme,
                package_name=catalog["distribution"]["npm"]["name"],
                package_version=npm["version"],
                schema_browser_name="@documentdrivendx/umf-schema-browser",
                contracts=ui_contracts,
            )
        except Exception:
            _diagnostic(
                rows,
                "theme_incompatible" if theme else "asset_invalid",
                "error",
                "theme" if theme else "assets",
                "theme_manifest" if theme else "asset_manifest",
                "selected manifests do not match the carried package and contract cohort",
            )
    return consumed


def _check_documents(
    request: DoctorRequest,
    observed: dict[str, object],
    rows: list[Diagnostic],
    *,
    already_read: int = 0,
) -> None:
    if not request.module_documents:
        return
    if request.module_profile is None:
        _diagnostic(
            rows,
            "module_profile_unsupported",
            "unsupported",
            "module",
            "module_profile",
            "select an explicit document validation profile",
        )
        return
    if request.module_profile != "legacy-arras":
        _diagnostic(
            rows,
            "capability_unsupported",
            "unsupported",
            "module",
            "module_profile",
            "the requested document validation profile is unavailable in this package cohort",
        )
        return
    total = already_read
    documents: list[dict[str, object]] = []
    for index, path in enumerate(request.module_documents):
        try:
            data = _read_regular(path, min(_MAX_DOCUMENT, _MAX_COMBINED - total))
            total += len(data)
            module = parse_module(data)
            documents.append(
                {
                    "path": f"module_documents[{index}]",
                    "module": module.name,
                    "revision": dict(module.revision.by_backend),
                    "profile": "legacy-arras",
                    "reader_expected_core": UMF_VERSION,
                    "reader_expected_vocabularies": {
                        "umf.ddd": "0.1.0",
                        VIEW_VOCABULARY: VIEW_VERSION,
                    },
                    "provenance": "existing Arras reader subset",
                }
            )
        except Exception:
            _diagnostic(
                rows,
                "module_invalid",
                "error",
                "module",
                f"module_documents[{index}]",
                "document is invalid under the legacy Arras reader or exceeds a safe bound",
            )
    observed["module_documents"] = documents


def _within_input_budget(request: DoctorRequest) -> bool:
    total = 0
    for path in (*request.config_files, *request.module_documents):
        try:
            total += path.lstat().st_size
        except OSError:
            continue
        if total > _MAX_COMBINED:
            return False
    return True


def check(request: DoctorRequest | None = None) -> DoctorReport:
    selected = request or DoctorRequest()
    rows: list[Diagnostic] = []
    observed: dict[str, object] = {
        "provenance": "declared catalog; package execution not yet qualified"
    }
    try:
        catalog = _catalog()
    except Exception:
        catalog = {}
        _diagnostic(
            rows,
            "catalog_invalid",
            "error",
            "catalog",
            "arras/public-api.json",
            "the carried public catalog is invalid",
        )
    if catalog:
        observed["catalog_schema_version"] = catalog["schema_version"]
        observed["contracts"] = {
            key: value["version"] for key, value in catalog["contracts"].items()
        }
        version, installed, npm = _package_observation(observed, rows)
        _check_npm_catalog_name(catalog, npm, rows)
        _check_python_catalog_version(catalog, version, installed, rows)
        _check_requested_packages(selected, version, installed, npm, rows)
        _check_catalog_requests(selected, catalog, rows)
        within_budget = _within_input_budget(selected)
        consumed = _check_files(selected, catalog, npm, within_budget, observed, rows)
        if within_budget:
            _check_documents(selected, observed, rows, already_read=consumed)
        elif selected.config_files or selected.module_documents:
            _diagnostic(
                rows,
                "config_invalid",
                "error",
                "request",
                "config_files/module_documents",
                "combined selected files exceed the 64 MiB bound",
            )
    errors = any(d.severity == "error" for d in rows)
    unsupported = any(d.severity == "unsupported" for d in rows)
    return DoctorReport(
        not errors and not unsupported, not unsupported, MappingProxyType(observed), tuple(rows)
    )


def _string_list(value: Any, label: str) -> tuple[str, ...]:
    if type(value) is not list:
        raise ValueError(f"{label} must be a string list")
    items = cast(list[object], value)
    if any(not isinstance(item, str) for item in items):
        raise ValueError(f"{label} must be a string list")
    return tuple(cast(list[str], items))


def _export_map(value: Any) -> dict[str, tuple[str, ...]]:
    if type(value) is not dict:
        raise ValueError("export requirements must map names to string lists")
    result: dict[str, tuple[str, ...]] = {}
    for key, raw_names in cast(dict[str, Any], value).items():
        result[key] = _string_list(raw_names, "export requirements")
    return result


def _path_list(value: Any) -> tuple[Path, ...]:
    return tuple(Path(item) for item in _string_list(value, "request file paths"))


def _distribution_request(value: Any) -> DistributionConfig:
    if type(value) is not dict:
        raise ValueError("distribution must be an object")
    fields = cast(dict[str, Any], value)
    allowed = {"brand", "mcp_server_name", "mcp_tool_prefix", "env_prefix", "telemetry"}
    if set(fields) - allowed:
        raise ValueError("distribution has unknown fields")
    brand_value: Any = fields.get("brand", {})
    if type(brand_value) is not dict:
        raise ValueError("brand must be an object")
    brand_fields = cast(dict[str, Any], brand_value)
    if set(brand_fields) - {"name", "title", "wordmark", "tagline", "logo"}:
        raise ValueError("brand has unknown fields")
    for name, raw in brand_fields.items():
        if (name == "name" and not isinstance(raw, str)) or (
            name != "name" and raw is not None and not isinstance(raw, str)
        ):
            raise ValueError("brand fields have invalid types")
    for name in ("mcp_server_name", "mcp_tool_prefix", "env_prefix"):
        if name in fields and not isinstance(fields[name], str):
            raise ValueError("distribution fields have invalid types")
    telemetry_fields = _telemetry_fields(fields.get("telemetry", {}))
    try:
        return DistributionConfig(
            brand=Brand(**brand_fields),
            mcp_server_name=fields.get("mcp_server_name", "arras"),
            mcp_tool_prefix=fields.get("mcp_tool_prefix", ""),
            env_prefix=fields.get("env_prefix", "ARRAS"),
            telemetry=TelemetryNames(**telemetry_fields),
        )
    except (TypeError, ValueError) as exc:
        raise DistributionInvalid from exc


def _request_from_json(raw: bytes) -> DoctorRequest:
    if len(raw) > _MAX_REQUEST:
        raise ValueError("request exceeds bound")
    data = load_json_object(raw)
    allowed = {
        "schema_version",
        "expected_packages",
        "expected_contracts",
        "required_python_exports",
        "required_npm_exports",
        "required_role_tokens",
        "distribution",
        "env_names",
        "config_files",
        "asset_manifest",
        "theme_manifest",
        "module_documents",
        "module_profile",
    }
    if (
        type(data.get("schema_version")) is not int
        or data["schema_version"] != 1
        or set(data) - allowed
    ):
        raise ValueError("request schema unsupported")
    package_values = data.get("expected_packages", {})
    contract_values = data.get("expected_contracts", {})
    if type(package_values) is not dict or type(contract_values) is not dict:
        raise ValueError("expected pins must be objects")
    packages = cast(dict[str, Any], package_values)
    contracts = cast(dict[str, Any], contract_values)
    if any(not isinstance(v, str) for v in packages.values()) or any(
        type(v) is not int for v in contracts.values()
    ):
        raise ValueError("expected pins have invalid value types")
    common: dict[str, Any] = {
        "expected_packages": cast(dict[str, str], packages),
        "expected_contracts": cast(dict[str, int], contracts),
        "required_python_exports": _export_map(data.get("required_python_exports", {})),
        "required_npm_exports": _export_map(data.get("required_npm_exports", {})),
        "required_role_tokens": _string_list(
            data.get("required_role_tokens", []), "required_role_tokens"
        ),
        "env_names": _string_list(data.get("env_names", []), "env_names"),
        "config_files": _path_list(data.get("config_files", [])),
        "asset_manifest": _optional_path(data.get("asset_manifest")),
        "theme_manifest": _optional_path(data.get("theme_manifest")),
        "module_documents": _path_list(data.get("module_documents", [])),
        "module_profile": cast(str | None, data.get("module_profile")),
    }
    # Validate all ordinary request fields before classifying semantic distribution failures.
    DoctorRequest(**common)
    distribution_value = data.get("distribution")
    distribution = (
        _distribution_request(distribution_value) if distribution_value is not None else None
    )
    return DoctorRequest(**common, distribution=distribution)


def _optional_path(value: Any) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("manifest path must be a string")
    return Path(value)


def _exit_status(report: DoctorReport) -> int:
    if any(d.severity == "error" for d in report.diagnostics):
        return 1
    if any(d.severity == "unsupported" for d in report.diagnostics):
        return 3
    return 0


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError("invalid command line")


def main(argv: list[str] | None = None) -> int:
    parser = _ArgumentParser(prog="python -m arras.doctor")
    parser.add_argument("--request", type=str)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if type(exc.code) is int else 2
    except ValueError:
        report = request_error_report()
        sys.stdout.write(json.dumps(report.to_dict(), sort_keys=True, separators=(",", ":")) + "\n")
        return 2
    if args.request is None:
        report = check()
    else:
        try:
            raw = _read_regular(Path(args.request), _MAX_REQUEST)
            report = check(_request_from_json(raw))
        except DistributionInvalid:
            report = distribution_error_report()
        except Exception:
            report = request_error_report()
    sys.stdout.write(json.dumps(report.to_dict(), sort_keys=True, separators=(",", ":")) + "\n")
    return (
        2
        if report.diagnostics and report.diagnostics[0].code == "request_invalid"
        else _exit_status(report)
    )


__all__ = ["DoctorRequest", "Diagnostic", "DoctorReport", "check"]


if __name__ == "__main__":
    raise SystemExit(main())
