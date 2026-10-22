# SPDX-License-Identifier: MIT OR Apache-2.0
"""The release binder changes only the Arras identity in an exact reviewed template."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).parents[1] / ".github/scripts/bind_native_cohort.py"
_SPEC = importlib.util.spec_from_file_location("bind_native_cohort", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
binder = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(binder)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inputs(
    tmp_path: Path, *, name: str = "arras", version: str = "0.5.0"
) -> tuple[Path, Path, Path, dict[str, Any]]:
    native = [
        ("truss-toolkit", "truss_toolkit-1.0-py3-none-any.whl"),
        ("weft-sql", "weft_sql-1.0-py3-none-any.whl"),
        ("pgserver-pg18", "pgserver_pg18-1.0-py3-none-any.whl"),
    ]
    wheels = [
        {
            "distribution": distribution,
            "version": "1.0",
            "filename": filename,
            "url": f"https://packages.example/{filename}",
            "sha256": (str(index + 1) * 64),
        }
        for index, (distribution, filename) in enumerate(native)
    ]
    links_bytes = "\n".join(
        f'<a href="{wheel["url"]}#sha256={wheel["sha256"]}">{wheel["filename"]}</a>'
        for wheel in wheels
    ).encode()
    template_value: dict[str, Any] = {
        "schema_version": 1,
        "runtime": {"python": "3.11", "sys_platform": "linux", "machine": "x86_64"},
        "find_links": {"sha256": sha(links_bytes)},
        "native_wheels": wheels,
        "corpus": {"version": 4, "roles": ["reader", "provider"], "limits": {}},
    }
    template = tmp_path / "linux-x86_64.json"
    template.write_text(json.dumps(template_value), encoding="utf-8")
    index = tmp_path / "linux-x86_64.find-links.html"
    index.write_bytes(links_bytes)
    wheel = tmp_path / f"{name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            f"{name}-{version}.dist-info/METADATA",
            f"Metadata-Version: 2.3\nName: {name}\nVersion: {version}\n\n",
        )
    return template, index, wheel, template_value


def bind_paths(
    template: Path,
    index: Path,
    wheel: Path,
    tmp_path: Path,
    *,
    expected_version: str = "0.5.0",
    expected_sha: str | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    output = tmp_path / "bound.json"
    receipt = tmp_path / "binding-receipt.json"
    result = binder.bind(
        template,
        index,
        wheel,
        expected_version=expected_version,
        expected_sha256=sha(wheel.read_bytes()) if expected_sha is None else expected_sha,
        output_path=output,
        receipt_path=receipt,
    )
    return output, receipt, result


def test_bind_uses_actual_wheel_identity_and_preserves_every_template_field(
    tmp_path: Path,
) -> None:
    template, index, wheel, original = inputs(tmp_path)
    before = json.loads(template.read_text(encoding="utf-8"))
    output, receipt_path, receipt = bind_paths(template, index, wheel, tmp_path)
    bound = json.loads(output.read_text(encoding="utf-8"))
    assert set(bound) == {*original, "arras"}
    assert {key: value for key, value in bound.items() if key != "arras"} == original == before
    assert bound["arras"] == {"version": "0.5.0", "sha256": sha(wheel.read_bytes())}
    assert receipt["status"] == "bound"
    assert receipt["template"]["sha256"] == sha(template.read_bytes())
    assert receipt["find_links"]["sha256"] == sha(index.read_bytes())
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == receipt


@pytest.mark.parametrize(
    ("expected_version", "expected_sha"),
    [("0.5.1", None), ("0.5.0", "0" * 64)],
)
def test_bind_refuses_wrong_expected_wheel_identity(
    tmp_path: Path, expected_version: str, expected_sha: str | None
) -> None:
    template, index, wheel, _ = inputs(tmp_path)
    with pytest.raises(binder.BindingError):
        binder.bind(
            template,
            index,
            wheel,
            expected_version=expected_version,
            expected_sha256=sha(wheel.read_bytes()) if expected_sha is None else expected_sha,
            output_path=tmp_path / "bound.json",
            receipt_path=tmp_path / "receipt.json",
        )


def test_bind_rejects_non_arras_wheel_metadata(tmp_path: Path) -> None:
    template, index, wheel, _ = inputs(tmp_path, name="other")
    with pytest.raises(binder.BindingError, match="METADATA name"):
        bind_paths(template, index, wheel, tmp_path)


@pytest.mark.parametrize(
    "raw_template",
    [
        b'{"schema_version":1,"schema_version":1}',
        b'{"schema_version":1,"runtime":{},"find_links":{},"native_wheels":[],"corpus":{},"extra":true}',
        b'{"schema_version":1,"runtime":{},"find_links":{},"native_wheels":[],"corpus":{},"arras":{}}',
    ],
)
def test_bind_rejects_duplicate_unknown_and_prebound_template_keys(
    tmp_path: Path, raw_template: bytes
) -> None:
    template, index, wheel, _ = inputs(tmp_path)
    template.write_bytes(raw_template)
    with pytest.raises(binder.BindingError):
        bind_paths(template, index, wheel, tmp_path)


def test_bind_fails_closed_for_missing_template_or_index_and_aliasing(tmp_path: Path) -> None:
    template, index, wheel, _ = inputs(tmp_path)
    with pytest.raises(binder.BindingError, match="template is missing"):
        binder.bind(
            tmp_path / "missing.json",
            index,
            wheel,
            expected_version="0.5.0",
            expected_sha256=sha(wheel.read_bytes()),
            output_path=tmp_path / "bound.json",
            receipt_path=tmp_path / "receipt.json",
        )
    index.unlink()
    with pytest.raises(binder.BindingError, match="index is missing"):
        bind_paths(template, index, wheel, tmp_path)
    index.write_text("", encoding="utf-8")
    with pytest.raises(binder.BindingError, match="alias"):
        binder.bind(
            template,
            index,
            wheel,
            expected_version="0.5.0",
            expected_sha256=sha(wheel.read_bytes()),
            output_path=template,
            receipt_path=tmp_path / "receipt.json",
        )
