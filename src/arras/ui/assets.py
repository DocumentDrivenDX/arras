# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""Validation for inert page and downstream theme asset manifests."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal

MAX_MANIFEST = 1024 * 1024
MAX_FILES = 10_000
MAX_FILE = 32 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MIMES = {
    ".html": "text/html",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


class _Pairs(dict):
    def __init__(self, pairs):
        super().__init__()
        for key, value in pairs:
            if key in self:
                raise ValueError(f"duplicate key {key!r}")
            self[key] = value


@dataclass(frozen=True, slots=True)
class AssetManifest:
    kind: Literal["page", "theme"]
    version: int
    package: Mapping[str, str]
    contracts: Mapping[str, int]
    files: Mapping[str, Mapping[str, object]]
    entry: Mapping[str, object]
    manifest_sha256: str
    root: Path
    schema_browser: Mapping[str, str] | None = None
    ui_versions: tuple[str, ...] = ()


def _fail(path: Path, why: str) -> ValueError:
    return ValueError(f"invalid asset manifest {path}: {why}")


def _mapping(value: object, keys: set[str], path: Path, name: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise _fail(path, f"{name} must contain exactly {sorted(keys)}")
    return value


def _relpath(value: object, path: Path, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or ":" in value
        or "?" in value
        or "#" in value
        or value.startswith("/")
    ):
        raise _fail(path, f"{name} is not a canonical relative POSIX path")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise _fail(path, f"{name} is not a canonical relative POSIX path")
    return value


def load_manifest(path: Path, *, kind: Literal["page", "theme"]) -> AssetManifest:  # noqa: C901, PLR0915
    """Read, validate and snapshot one manifest and only its declared regular files."""
    path = Path(path)
    try:
        manifest_stat = path.stat()
        if not stat.S_ISREG(manifest_stat.st_mode):
            raise _fail(path, "manifest is not a regular file")
        if manifest_stat.st_size > MAX_MANIFEST:
            raise _fail(path, "manifest exceeds 1 MiB")
        with path.open("rb") as stream:
            raw = stream.read(MAX_MANIFEST + 1)
        if len(raw) > MAX_MANIFEST:
            raise _fail(path, "manifest exceeds 1 MiB")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_Pairs)
    except ValueError as exc:
        if str(exc).startswith("invalid asset manifest"):
            raise
        raise _fail(path, "invalid UTF-8 JSON or duplicate keys") from None
    except (OSError, UnicodeError):
        raise _fail(path, "cannot read manifest") from None
    if not isinstance(data, dict):
        raise _fail(path, "top level must be an object")
    extras = {"schema_browser"} if kind == "page" else {"ui_versions"}
    required = {"format", "version", "kind", "package", "contracts", "entry", "files"} | extras
    if set(data) != required:
        raise _fail(path, f"top level keys must be exactly {sorted(required)}")
    if (
        data["format"] != "arras.ui.assets"
        or type(data["version"]) is not int
        or data["version"] != 1
        or data["kind"] != kind
    ):
        raise _fail(path, "format, version or kind is incompatible")
    package = _mapping(data["package"], {"name", "version"}, path, "package")
    if any(
        not isinstance(v, str) or not v or len(v) > 128 or not v.isascii() for v in package.values()
    ):
        raise _fail(
            path, "package name and version must be nonempty ASCII strings up to 128 characters"
        )
    contracts = data["contracts"]
    if not isinstance(contracts, dict) or any(
        not isinstance(k, str) or type(v) is not int or v < 1 for k, v in contracts.items()
    ):
        raise _fail(path, "contracts must map names to positive integers")
    files = data["files"]
    if not isinstance(files, dict) or len(files) > MAX_FILES:
        raise _fail(path, "files must be an object with at most 10000 entries")
    root = path.parent.resolve()
    checked: dict[str, Mapping[str, object]] = {}
    total = 0
    for name, metadata in files.items():
        rel = _relpath(name, path, "file path")
        if kind == "theme" and Path(rel).suffix.lower() not in {
            ".css",
            ".woff",
            ".woff2",
            ".svg",
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".ico",
        }:
            raise _fail(path, f"files[{rel}] is not an allowed theme stylesheet, font or image")
        item = _mapping(metadata, {"sha256", "size", "mime"}, path, f"files[{rel}]")
        size, digest, mime = item["size"], item["sha256"], item["mime"]
        if (
            type(size) is not int
            or size < 0
            or size > MAX_FILE
            or not isinstance(digest, str)
            or not _DIGEST.fullmatch(digest)
        ):
            raise _fail(path, f"files[{rel}] has invalid size or sha256")
        if not isinstance(mime, str) or _MIMES.get(Path(rel).suffix.lower()) != mime:
            raise _fail(path, f"files[{rel}] has unsupported or mismatched MIME")
        total += size
        if total > MAX_TOTAL:
            raise _fail(path, "declared files exceed 64 MiB total")
        target = path.parent / rel
        try:
            resolved = target.resolve(strict=True)
            st = resolved.stat()
            if not resolved.is_relative_to(root) or not stat.S_ISREG(st.st_mode):
                raise _fail(
                    path, f"files[{rel}] escapes the manifest root or is not a regular file"
                )
            if st.st_size != size or st.st_size > MAX_FILE:
                raise _fail(path, f"files[{rel}] declared size does not match file size")
            with resolved.open("rb") as stream:
                content = stream.read(MAX_FILE + 1)
        except (OSError, RuntimeError):
            raise _fail(path, f"files[{rel}] is missing or unsafe") from None
        if len(content) != size or hashlib.sha256(content).hexdigest() != digest:
            raise _fail(path, f"files[{rel}] size or digest mismatch")
        checked[rel] = MappingProxyType({"sha256": digest, "size": size, "mime": mime})
    entry = data["entry"]
    if not isinstance(entry, dict):
        raise _fail(path, "entry must be an object")
    if kind == "page":
        _mapping(entry, {"html"}, path, "entry")
        html_path = _relpath(entry["html"], path, "entry.html")
        if (
            html_path not in checked
            or Path(html_path).suffix.lower() != ".html"
            or checked[html_path]["mime"] != "text/html"
        ):
            raise _fail(path, "entry.html must name a declared HTML file")
        sb = _mapping(
            data["schema_browser"], {"name", "version", "integrity"}, path, "schema_browser"
        )
        if any(not isinstance(v, str) or not v for v in sb.values()):
            raise _fail(path, "schema_browser values must be nonempty strings")
        schema_browser = MappingProxyType(sb)
        ui_versions: tuple[str, ...] = ()
    else:
        allowed = {"stylesheet", "fonts", "favicon"}
        if not set(entry) <= allowed or "stylesheet" not in entry:
            raise _fail(path, "theme entry requires stylesheet and allows only fonts/favicon")
        stylesheet = _relpath(entry["stylesheet"], path, "entry.stylesheet")
        if stylesheet not in checked or Path(stylesheet).suffix.lower() != ".css":
            raise _fail(path, "entry.stylesheet must name a declared CSS file")
        fonts = entry.get("fonts", [])
        if not isinstance(fonts, list):
            raise _fail(path, "entry.fonts must be a list")
        for font in fonts:
            p = _relpath(font, path, "entry.fonts")
            if p not in checked or Path(p).suffix.lower() not in (".woff", ".woff2"):
                raise _fail(path, f"entry.fonts path {p} must name a declared font")
        favicon = entry.get("favicon")
        if favicon is not None:
            p = _relpath(favicon, path, "entry.favicon")
            if p not in checked or Path(p).suffix.lower() not in (
                ".svg",
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
                ".ico",
            ):
                raise _fail(path, "entry.favicon must name a declared image")
        versions = data["ui_versions"]
        if (
            not isinstance(versions, list)
            or not versions
            or any(not isinstance(v, str) or not v for v in versions)
            or len(set(versions)) != len(versions)
        ):
            raise _fail(path, "ui_versions must be a nonempty unique string list")
        schema_browser = None
        ui_versions = tuple(versions)
    frozen_entry = {
        key: tuple(value) if isinstance(value, list) else value for key, value in entry.items()
    }
    return AssetManifest(
        kind,
        1,
        MappingProxyType(package),
        MappingProxyType(dict(contracts)),
        MappingProxyType(checked),
        MappingProxyType(frozen_entry),
        hashlib.sha256(raw).hexdigest(),
        root,
        schema_browser,
        ui_versions,
    )


def read_verified(manifest: AssetManifest, name: str) -> bytes | None:
    """Read one declared member again, defending the response path from post-validation swaps."""
    metadata = manifest.files.get(name)
    if metadata is None:
        return None
    try:
        target = (manifest.root / name).resolve(strict=True)
        if not target.is_relative_to(manifest.root) or not stat.S_ISREG(target.stat().st_mode):
            return None
        if target.stat().st_size != metadata["size"]:
            return None
        with target.open("rb") as stream:
            body = stream.read(MAX_FILE + 1)
    except (OSError, RuntimeError):
        return None
    if len(body) != metadata["size"] or hashlib.sha256(body).hexdigest() != metadata["sha256"]:
        return None
    return body


def validate_cohort(
    page: AssetManifest,
    theme: AssetManifest | None,
    *,
    package_name: str,
    package_version: str,
    schema_browser_name: str,
    contracts: Mapping[str, int],
) -> None:
    """Require page and optional theme manifests to describe one declared UI cohort."""
    expected = dict(contracts)
    if (
        page.kind != "page"
        or page.package.get("name") != package_name
        or page.package.get("version") != package_version
        or dict(page.contracts) != expected
        or page.schema_browser is None
        or page.schema_browser.get("name") != schema_browser_name
        or not str(page.schema_browser.get("integrity", "")).startswith("sha512-")
    ):
        raise ValueError("page manifest does not match the selected package cohort")
    if theme is not None and (
        theme.kind != "theme"
        or dict(theme.contracts) != expected
        or page.package.get("version") not in theme.ui_versions
    ):
        raise ValueError("theme manifest does not match the selected page cohort")
