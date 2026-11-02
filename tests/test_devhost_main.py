# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""`python -m arras.devhost`: its arguments and what it serves, with a stand-in `uvicorn` so it
runs without one."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from arras.devhost import DevHost, main
from arras.sandbox import Sandbox


@pytest.fixture
def fake_uvicorn(monkeypatch) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    mod = types.ModuleType("uvicorn")
    mod.run = lambda app, **kw: runs.append({"app": app, **kw})  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uvicorn", mod)
    return runs


def _count(app: DevHost, sql: str) -> int:
    o = app.box.arras.session(app.box.people["alice"])
    return len(o.query("catalog", sql, limit=100).rows)


def test_main_serves_on_the_loopback_with_the_demo_by_default(fake_uvicorn, tmp_path) -> None:
    main(["--port", "8123", "--ui", str(tmp_path)])
    [run] = fake_uvicorn
    assert (run["host"], run["port"], run["log_level"]) == ("127.0.0.1", 8123, "info")
    app = run["app"]
    assert isinstance(app, DevHost) and app.ui == tmp_path
    own = {"http://127.0.0.1:8123", "http://localhost:8123"}
    assert app.own_origins == own | {"http://127.0.0.1:5173", "http://localhost:5173"}  # and Vite's
    assert _count(app, "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100") == 14


def test_main_without_the_demo_serves_the_sandbox_alone(fake_uvicorn, tmp_path) -> None:
    main(["--no-demo", "--ui", str(tmp_path)])
    [run] = fake_uvicorn
    assert run["port"] == 8000
    assert _count(run["app"], "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100") == 2


def test_main_says_how_to_get_uvicorn_when_it_is_missing(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "uvicorn", None)  # import fails
    with pytest.raises(SystemExit) as e:
        main([])
    assert "uvicorn is needed" in str(e.value)


def test_main_refuses_a_port_that_is_not_a_number(fake_uvicorn) -> None:
    with pytest.raises(SystemExit):
        main(["--port", "eighty"])
    assert fake_uvicorn == []


@pytest.mark.parametrize("groups", [(), []])
def test_main_refuses_explicit_empty_operator_groups_before_startup(
    fake_uvicorn, monkeypatch, groups, capsys
) -> None:
    import arras.devhost as devhost

    effects: list[str] = []
    monkeypatch.setattr(devhost, "build", lambda *_a, **_kw: effects.append("build"))
    with pytest.raises(SystemExit) as result:
        main(["--no-demo"], operator_groups=groups)
    assert result.value.code == 2
    assert "operator_groups: one or more names" in capsys.readouterr().err
    assert effects == [] and fake_uvicorn == []


@pytest.mark.parametrize("groups", [(), []])
def test_operator_group_flag_overrides_an_empty_programmatic_default(
    fake_uvicorn, tmp_path, groups
) -> None:
    main(
        ["--no-demo", "--ui", str(tmp_path), "--operator-group", "ops"],
        operator_groups=groups,
    )
    assert fake_uvicorn[0]["app"].operator_groups == ("ops",)


def test_telemetry_factory_runs_after_argument_validation_and_before_build(
    fake_uvicorn, monkeypatch, tmp_path
) -> None:
    import arras.devhost as devhost
    from arras.distribution import TelemetryNames
    from arras.telemetry import TelemetryContext

    order: list[str] = []
    original_build = devhost.build

    def build(*args, **kwargs):
        order.append("build")
        return original_build(*args, **kwargs)

    def factory(names: TelemetryNames) -> TelemetryContext:
        order.append("factory")
        assert names == TelemetryNames()
        return TelemetryContext(names)

    monkeypatch.setattr(devhost, "build", build)
    main(["--no-demo", "--ui", str(tmp_path)], telemetry_factory=factory)
    assert order == ["factory", "build"]
    assert fake_uvicorn[0]["app"].telemetry_context.names == TelemetryNames()


def test_help_and_invalid_arguments_skip_the_telemetry_factory() -> None:
    called: list[bool] = []

    def factory(*_args):
        called.append(True)
        raise AssertionError("factory must not run")

    with pytest.raises(SystemExit) as help_result:
        main(["--help"], telemetry_factory=factory)
    assert help_result.value.code == 0
    with pytest.raises(SystemExit) as invalid_result:
        main(["--port", "invalid"], telemetry_factory=factory)
    assert invalid_result.value.code == 2 and called == []


def test_help_uses_the_effective_programmatic_operator_group_default(capsys) -> None:
    with pytest.raises(SystemExit) as help_result:
        main(["--help"], operator_groups=("maintainers", "reviewers"))
    assert help_result.value.code == 0
    help_text = " ".join(capsys.readouterr().out.split())
    assert "(maintainers, reviewers)" in help_text
    assert "(admins, builders)" not in help_text


def test_invalid_truss_mode_skips_telemetry_factory() -> None:
    called: list[bool] = []

    def factory(*_args):
        called.append(True)
        raise AssertionError("factory must not run for invalid arguments")

    with pytest.raises(SystemExit) as result:
        main(["--truss", "--truss-reset"], telemetry_factory=factory)
    assert result.value.code == 2 and called == []


def test_custom_service_without_factory_refuses_before_build(monkeypatch, fake_uvicorn) -> None:
    import arras.devhost as devhost
    from arras.distribution import DistributionConfig, TelemetryNames

    effects: list[str] = []
    monkeypatch.setattr(devhost, "build", lambda *_a, **_k: effects.append("build"))
    selected = DistributionConfig(telemetry=TelemetryNames(service_name="tenant-service"))
    with pytest.raises(SystemExit, match="telemetry configuration refused"):
        main([], distribution=selected)
    assert effects == [] and fake_uvicorn == []


def test_the_default_ui_is_the_repositorys_build() -> None:
    from arras.devhost import DEFAULT_UI

    assert DEFAULT_UI == Path(__file__).resolve().parents[1] / "ui" / "dist"


def test_truss_says_what_is_missing_before_it_starts_anything(fake_uvicorn, monkeypatch) -> None:
    import arras.devhost as devhost

    monkeypatch.setattr(devhost, "_truss_missing", lambda **_: "the truss extra")
    started: list[object] = []
    monkeypatch.setattr(devhost, "build", lambda *a, **k: started.append(k))
    with pytest.raises(SystemExit) as e:
        main(["--truss"])
    assert "--truss needs the truss extra" in str(e.value)
    assert started == [] and fake_uvicorn == []


def test_truss_serves_its_box_and_closes_it_when_the_server_ends(
    fake_uvicorn, monkeypatch, tmp_path
) -> None:
    import arras.devhost as devhost
    from arras.sandbox import Sandbox

    class Boxed(Sandbox):
        closed = False

        def close(self) -> None:
            self.closed = True

    box: Any = Boxed().seed()
    seen: dict[str, Any] = {}

    def build(module, seed, *, demo=False, truss=False, **_):  # noqa: ANN001, ANN003
        seen.update(truss=truss, demo=demo)
        return box

    monkeypatch.setattr(devhost, "_truss_missing", lambda **_: None)
    monkeypatch.setattr(devhost, "build", build)
    main(["--truss", "--no-demo", "--ui", str(tmp_path)])
    [run] = fake_uvicorn
    assert seen == {"truss": True, "demo": False} and run["app"].box is box
    assert box.closed  # the throwaway database goes with the server


def test_truss_needs_the_extra_the_test_group(monkeypatch) -> None:
    import importlib.util

    import arras.devhost as devhost

    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda n, *a: None if n == "pgserver" else real(n, *a)
    )
    if real("truss") is None:
        assert "truss extra" in (devhost._truss_missing() or "")
    else:
        assert "truss-test group" in (devhost._truss_missing() or "")


def test_devhost_uses_distribution_brand_for_not_built_banner(tmp_path: Path) -> None:
    from arras.distribution import DistributionConfig
    from arras.sandbox import Sandbox

    brand = __import__("arras.ui", fromlist=["Brand"]).Brand(name="Local Catalog")
    app = DevHost(
        Sandbox().seed(),
        port=8123,
        ui_dir=tmp_path,
        distribution=DistributionConfig(brand=brand),
    )
    status, content_type, body = app.static("/")
    assert status == 200 and content_type == "text/html; charset=utf-8"
    assert b"Local Catalog" in body


def test_main_forwards_distribution_brand_to_the_served_ui(fake_uvicorn, tmp_path) -> None:
    from arras.branding import Brand
    from arras.distribution import DistributionConfig

    selected = DistributionConfig(brand=Brand(name="Extension Host"))
    main(["--ui", str(tmp_path)], distribution=selected)
    [run] = fake_uvicorn
    assert run["app"].distribution is selected
    assert b"Extension Host" in run["app"].static("/")[2]


def test_main_uses_printable_brand_for_help_and_startup_banner(
    fake_uvicorn, tmp_path: Path, capsys
) -> None:
    from arras.branding import Brand
    from arras.distribution import DistributionConfig

    selected = DistributionConfig(brand=Brand(name="  Host\nCatalog  "))
    with pytest.raises(SystemExit) as help_exit:
        main(["--help"], distribution=selected)
    assert help_exit.value.code == 0
    help_text = capsys.readouterr().out
    assert "Host Catalog development host" in help_text
    assert "python -m arras.devhost" in help_text

    main(["--ui", str(tmp_path)], distribution=selected)
    assert capsys.readouterr().out.splitlines() == [
        "Host Catalog development host at http://127.0.0.1:8000"
    ]
    [run] = fake_uvicorn
    assert run["app"].distribution is selected


def _theme_manifest(tmp_path: Path, name: str, css: str) -> Path:
    from arras.ui.assets import build_theme_manifest

    source = tmp_path / f"{name}.css"
    source.write_text(css, encoding="utf-8")
    return build_theme_manifest(
        tmp_path / name,
        stylesheet=source,
        package_name=name,
        ui_versions=(importlib.metadata.version("arras"),),
    )


def _devhost_ui(tmp_path: Path) -> Path:
    from arras.ui import STATIC

    if (STATIC / "asset-manifest.json").is_file():
        return STATIC
    root = tmp_path / "built-ui"
    root.mkdir()
    page = b'<!doctype html><html lang="en"><head><title>Arras</title></head></html>'
    (root / "embed.html").write_bytes(page)
    (root / "asset-manifest.json").write_text(
        json.dumps(
            {
                "format": "arras.ui.assets",
                "version": 1,
                "kind": "page",
                "package": {
                    "name": "@documentdrivendx/arras-ui",
                    "version": importlib.metadata.version("arras"),
                },
                "contracts": {"console": 2, "operate": 2, "schema": 1, "browser": 1},
                "schema_browser": {
                    "name": "@documentdrivendx/umf-schema-browser",
                    "version": "test",
                    "integrity": "sha512-test",
                },
                "entry": {"html": "embed.html"},
                "files": {
                    "embed.html": {
                        "sha256": hashlib.sha256(page).hexdigest(),
                        "size": len(page),
                        "mime": "text/html",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return root


def _asgi_get(app: Any, path: str) -> tuple[int, dict[bytes, bytes], bytes]:
    async def run() -> tuple[int, dict[bytes, bytes], bytes]:
        messages: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict[str, Any]) -> None:
            messages.append(message)

        raw_path = path.encode("ascii")
        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": raw_path,
                "query_string": b"",
                "headers": [(b"host", b"127.0.0.1:8000")],
                "server": ("127.0.0.1", 8000),
                "client": ("127.0.0.1", 50000),
            },
            receive,
            send,
        )
        start = next(item for item in messages if item["type"] == "http.response.start")
        headers = dict(start["headers"])
        body = b"".join(
            item.get("body", b"") for item in messages if item["type"] == "http.response.body"
        )
        return start["status"], headers, body

    return asyncio.run(run())


def test_cli_theme_manifest_overrides_distribution_and_themes_built_ui(
    fake_uvicorn, tmp_path: Path
) -> None:
    from arras.devhost import DevHost
    from arras.distribution import Brand, DistributionConfig

    default_manifest = _theme_manifest(tmp_path, "default-theme", ":root { --surface: pink; }")
    selected_manifest = _theme_manifest(tmp_path, "cli-theme", ":root { --surface: teal; }")
    ui_dir = _devhost_ui(tmp_path)
    selected = DistributionConfig(
        brand=Brand(name="Example Host"), theme_manifest=str(default_manifest)
    )
    main(
        ["--no-demo", "--ui", str(ui_dir), "--theme-manifest", str(selected_manifest)],
        distribution=selected,
    )
    [run] = fake_uvicorn
    app = run["app"]
    assert app.theme_manifest == selected_manifest

    status, headers, page = _asgi_get(app, "/")
    assert status == 200
    assert b"<title>Example Host</title>" in page
    assert b"/theme-assets/" + app._themed_ui.theme_manifest.manifest_sha256.encode() in page
    assert b"cli-theme.css" in page and b"default-theme.css" not in page
    assert b"style-src 'self'" in headers[b"content-security-policy"]

    digest = app._themed_ui.theme_manifest.manifest_sha256
    status, headers, body = _asgi_get(app, f"/theme-assets/{digest}/cli-theme.css")
    assert status == 200 and body == b":root { --surface: teal; }"
    assert headers[b"cache-control"] == b"public, max-age=31536000, immutable"
    assert b"style-src 'self'" in headers[b"content-security-policy"]

    direct_manifest = _theme_manifest(tmp_path, "direct-theme", ":root { --surface: navy; }")
    direct = DevHost(
        Sandbox().seed(),
        port=8000,
        ui_dir=ui_dir,
        distribution=selected,
        theme_manifest=direct_manifest,
    )
    assert direct.theme_manifest == direct_manifest
    assert b"direct-theme.css" in direct.static("/")[2]


def test_theme_manifest_refuses_missing_and_changed_manifests_with_csp(tmp_path: Path) -> None:
    from arras.devhost import DevHost
    from arras.distribution import DistributionConfig

    missing = tmp_path / "missing.json"
    with pytest.raises(ValueError, match="invalid asset manifest"):
        DevHost(
            Sandbox().seed(),
            port=8000,
            distribution=DistributionConfig(theme_manifest=str(missing)),
        )

    manifest = _theme_manifest(tmp_path, "mutable-theme", ":root { color: green; }")
    app = DevHost(
        Sandbox().seed(),
        port=8000,
        distribution=DistributionConfig(theme_manifest=str(manifest)),
    )
    assert app._themed_ui is not None
    digest = app._themed_ui.theme_manifest.manifest_sha256
    manifest.write_text("not valid JSON", encoding="utf-8")
    status, headers, body = _asgi_get(app, f"/theme-assets/{digest}/mutable-theme.css")
    assert status == 503 and body == b"theme manifest invalid"
    assert b"style-src 'self'" in headers[b"content-security-policy"]
