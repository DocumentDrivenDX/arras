# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""`python -m arras.devhost --truss` and the persistent server: where its URL comes from, what the
startup says (never the password), and which arguments go together. No database: `build` and the
server are stand-ins."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

# The attach path builds the Truss adapter, which needs the truss extra.
pytest.importorskip("psycopg")

import arras.devhost as devhost
from arras.devhost import main, truss_attachment, truss_url

PASSWORD = "s3cr3t-pa55"
URL = f"postgresql://arras_installer:{PASSWORD}@localhost:5432/arras_truss"
VAR = devhost.TRUSS_URL_VARIABLE


@pytest.fixture
def fake_uvicorn(monkeypatch) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    mod = types.ModuleType("uvicorn")
    mod.run = lambda app, **kw: runs.append({"app": app, **kw})  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uvicorn", mod)
    return runs


@pytest.fixture
def nowhere(monkeypatch, tmp_path) -> Path:
    """No URL in the environment and none in the default file."""
    monkeypatch.delenv(VAR, raising=False)
    missing = tmp_path / "none.env"
    monkeypatch.setattr(devhost, "TRUSS_URL_FILE", missing)
    return missing


class Boxed:
    people: dict[str, Any] = {}
    closed = False
    seeded = True

    def close(self) -> None:
        self.closed = True


def _stand_in(monkeypatch, missing: list[bool] | None = None) -> list[dict[str, Any]]:
    built: list[dict[str, Any]] = []

    def build(module, seed, **kw):  # noqa: ANN001, ANN003
        built.append(kw)
        return Boxed()

    monkeypatch.setattr(devhost, "build", build)
    monkeypatch.setattr(devhost, "DevHost", lambda box, **kw: box)
    monkeypatch.setattr(
        devhost,
        "_truss_missing",
        lambda persistent=False: missing.append(persistent) if missing is not None else None,
    )
    return built


# -- where the URL comes from
def test_the_argument_beats_the_environment_beats_the_file(tmp_path) -> None:
    file = tmp_path / "truss-dev.env"
    file.write_text(f"{VAR}=postgresql://f:pw@h/db\n")
    env = {VAR: "postgresql://e:pw@h/db"}
    assert truss_url("postgresql://a:pw@h/db", env, file) == (
        "postgresql://a:pw@h/db",
        "the --truss-url you gave",
    )
    assert truss_url(None, env, file) == (
        "postgresql://e:pw@h/db",
        f"the environment variable {VAR}",
    )
    assert truss_url(None, {}, file) == ("postgresql://f:pw@h/db", f"{VAR} in {file}")


def test_the_file_reads_name_equals_value_lines(tmp_path) -> None:
    file = tmp_path / "truss-dev.env"
    file.write_text(f"# the dev server\nOTHER=1\n\nexport {VAR}='postgresql://u:p@h/db'\n")
    assert truss_url(None, {}, file) == ("postgresql://u:p@h/db", f"{VAR} in {file}")
    file.write_text(f'{VAR}="postgresql://u:p@h/db"\n')
    assert truss_url(None, {}, file) is not None
    file.write_text(f"{VAR}=\nOTHER=postgresql://u:p@h/db\n")
    assert truss_url(None, {}, file) is None  # empty, or another variable
    assert truss_url(None, {}, tmp_path / "missing.env") is None


def test_the_source_never_holds_the_url(tmp_path) -> None:
    file = tmp_path / "truss-dev.env"
    file.write_text(f"{VAR}={URL}\n")
    for given, env in ((URL, {}), (None, {VAR: URL}), (None, {})):
        found = truss_url(given, env, file)
        assert found is not None and PASSWORD not in found[1]


# -- what the startup says
def test_the_attachment_names_where_to_connect_and_not_the_password() -> None:
    lines = truss_attachment(URL, f"{VAR} in ~/.arras/truss-dev.env")
    text = "\n".join(lines)
    assert PASSWORD not in text
    assert "localhost, port 5432, database arras_truss" in text
    assert "psql -h localhost -p 5432 -U arras_installer arras_truss" in text
    assert f"{VAR} in ~/.arras/truss-dev.env" in text and "arrasdev_<name>" in text


def test_the_attachment_for_a_socket_and_a_default_port() -> None:
    lines = truss_attachment("postgresql://inst:pw@/db?host=/tmp", "the environment")
    assert "/tmp, port 5432, database db" in lines[0]


@pytest.mark.parametrize(
    "url",
    [
        f"postgresql://:{PASSWORD}@localhost/db",  # no role
        "postgresql://arras_installer@localhost/db",  # no password: the server must ask for one
        f"postgresql://r:{PASSWORD}@localhost/db?passfile=/x",
        f"postgresql://r:{PASSWORD}@localhost/db?options=-c",
        f"mysql://r:{PASSWORD}@localhost/db",
        f"postgresql://r:{PASSWORD}@remote.example/db?sslmode=disable",  # a remote host verifies
    ],
)
def test_a_url_the_adapter_refuses_is_refused_without_repeating_it(url) -> None:
    with pytest.raises(ValueError) as e:
        truss_attachment(url, "x")
    assert PASSWORD not in str(e.value)


# -- the arguments
def test_truss_attaches_to_the_url_in_the_environment(
    fake_uvicorn, monkeypatch, nowhere, tmp_path, capsys
) -> None:
    monkeypatch.setenv(VAR, URL)
    asked: list[bool] = []
    built = _stand_in(monkeypatch, asked)
    main(["--truss", "--ui", str(tmp_path)])
    [kw] = built
    assert (kw["truss"], kw["truss_url"], kw["truss_reset"]) == (True, URL, False)
    assert asked == [True]  # a persistent server needs no local PostgreSQL
    out = capsys.readouterr().out
    assert PASSWORD not in out and "psql -h localhost -p 5432 -U arras_installer" in out
    assert f"the environment variable {VAR}" in out and "left them as they are" not in out
    assert "seeded it" in out
    assert [r["port"] for r in fake_uvicorn] == [8000]


def test_truss_reads_the_file_when_the_environment_has_nothing(
    fake_uvicorn, monkeypatch, nowhere, tmp_path, capsys
) -> None:
    nowhere.write_text(f"{VAR}={URL}\n")
    built = _stand_in(monkeypatch)
    main(["--truss", "--ui", str(tmp_path)])
    assert built[0]["truss_url"] == URL
    out = capsys.readouterr().out
    assert PASSWORD not in out and str(nowhere) in out


def test_truss_reports_a_database_it_left_alone(
    fake_uvicorn, monkeypatch, nowhere, tmp_path, capsys
) -> None:
    monkeypatch.setenv(VAR, URL)
    monkeypatch.setattr(Boxed, "seeded", False)
    _stand_in(monkeypatch)
    main(["--truss", "--ui", str(tmp_path)])
    assert "holds entities already: left them as they are" in capsys.readouterr().out


def test_truss_without_a_url_is_the_throwaway(
    fake_uvicorn, monkeypatch, nowhere, tmp_path, capsys
) -> None:
    asked: list[bool] = []
    built = _stand_in(monkeypatch, asked)
    main(["--truss", "--ui", str(tmp_path)])
    assert built[0]["truss_url"] is None and asked == [False]
    out = capsys.readouterr().out
    assert "throwaway" in out and "seeded it" not in out
    assert all(r["app"].closed for r in fake_uvicorn)  # the box is closed with the server


def test_the_argument_url_is_used_and_reset_is_passed(
    fake_uvicorn, monkeypatch, nowhere, tmp_path, capsys
) -> None:
    built = _stand_in(monkeypatch)
    main(["--truss", "--truss-url", URL, "--truss-reset", "--ui", str(tmp_path)])
    assert (built[0]["truss_url"], built[0]["truss_reset"]) == (URL, True)
    out = capsys.readouterr().out
    assert PASSWORD not in out and "reset, " in out and "--truss-url you gave" in out


def test_reset_needs_a_persistent_server(fake_uvicorn, monkeypatch, nowhere) -> None:
    built = _stand_in(monkeypatch)
    with pytest.raises(SystemExit) as e:
        main(["--truss", "--truss-reset"])
    assert e.value.code == 2 and built == [] and fake_uvicorn == []


@pytest.mark.parametrize("flags", [["--truss-reset"], ["--truss-url", URL]])
def test_the_truss_flags_need_truss(fake_uvicorn, monkeypatch, nowhere, flags) -> None:
    built = _stand_in(monkeypatch)
    with pytest.raises(SystemExit) as e:
        main(flags)
    assert e.value.code == 2 and built == []


def test_a_refused_url_stops_before_anything_starts(
    fake_uvicorn, monkeypatch, nowhere, capsys
) -> None:
    built = _stand_in(monkeypatch)
    with pytest.raises(SystemExit) as e:
        main(["--truss", "--truss-url", "postgresql://arras_installer@localhost/db"])
    assert "connection URL is refused" in str(e.value) and built == [] and fake_uvicorn == []


def test_a_persistent_truss_needs_no_local_postgresql(monkeypatch) -> None:
    import importlib.util

    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda n, *a: None if n == "pgserver" else real(n, *a)
    )
    if real("truss") is None:
        pytest.skip("the truss extra is not installed")
    assert "truss-test group" in (devhost._truss_missing() or "")
    assert "truss-test group" not in (devhost._truss_missing(persistent=True) or "")
