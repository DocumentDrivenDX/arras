# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""`python -m arras.devhost`: its arguments and what it serves, with a stand-in `uvicorn` so it
runs without one."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

from arras.devhost import DevHost, main


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
