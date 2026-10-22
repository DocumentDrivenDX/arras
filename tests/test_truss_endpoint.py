# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The endpoint handle of a Truss backend and the source built from it (TR-14, ADR-019).

Always on: a handle is parsed without a connection and a recording `psycopg.connect` shows what the
person's connection is made of. The Truss-marked test connects for real (tests/test_truss_bindings.py).
"""

from __future__ import annotations

import pytest

pytest.importorskip("psycopg")

from arras.adapters.truss import endpoint as endpoint_module  # noqa: E402
from arras.adapters.truss.endpoint import (  # noqa: E402
    Endpoint,
    connect,
    endpoint_source,
    is_endpoint,
    parse_endpoint,
)
from arras.types import Principal  # noqa: E402


def test_a_tcp_handle_and_a_socket_handle_parse() -> None:
    tcp = parse_endpoint("postgresql://db.example:5432/arras?sslmode=verify-full")
    assert (tcp.host, tcp.port, tcp.dbname, tcp.sslmode) == (
        "db.example",
        5432,
        "arras",
        "verify-full",
    )
    sock = parse_endpoint("postgresql:///arras?host=/tmp/ar-1/pg")
    assert (sock.host, sock.dbname, sock.sslmode, sock.local) == (
        "/tmp/ar-1/pg",
        "arras",
        "prefer",
        True,
    )
    assert parse_endpoint("postgres://db.example/h").sslmode == "verify-full"  # a remote default


@pytest.mark.parametrize(
    "handle",
    [
        "postgresql://alice:secret-pw@db.example/h",  # a credential in a handle
        "postgresql://alice@db.example/h",
        "postgresql://db.example/h?password=secret-pw",
        "postgresql://db.example/h?passfile=/x",
        "postgresql://db.example/h?service=svc",
        "postgresql://db.example/h?options=-crole%3Dbob",
        "postgresql://db.example/",  # no database
        "postgresql://db.example/h?sslmode=disable",  # a token over the wire in clear
        "postgresql://db.example/h?sslmode=prefer",
        "postgresql://db.example/h?sslmode=allow",
        "postgresql://db.example/h?sslmode=require",  # encrypted, but the server is not verified
        "postgresql://db.example/h?sslmode=verify-ca",  # the host name is not verified
        "postgresql://db.example/h?sslrootcert=relative/root.crt",
        "postgresql://db.example/h?sslrootcert=",
        "postgresql://db.example/h?sslmode=bogus",
        "postgresql://db.example/h?connect_timeout=0",
        "postgresql://a,b/h",
        "primary.example",
        "https://x/y",
    ],
)
def test_a_handle_that_is_not_an_endpoint_is_refused_and_never_repeated(handle: str) -> None:
    with pytest.raises(ValueError) as e:
        parse_endpoint(handle)
    text = str(e.value)
    assert "secret-pw" not in text and "alice" not in text and handle not in text


def test_a_loopback_handle_may_run_without_tls() -> None:
    assert parse_endpoint("postgresql://localhost/h?sslmode=disable").sslmode == "disable"


def test_a_remote_endpoint_verifies_the_server_certificate_and_name() -> None:
    assert parse_endpoint("postgresql://db.example/h?sslmode=verify-full").sslmode == "verify-full"
    for mode in ("require", "prefer", "allow", "disable", "verify-ca"):
        with pytest.raises(ValueError, match="verify-full"):
            parse_endpoint(f"postgresql://db.example/h?sslmode={mode}")


def test_an_endpoint_built_directly_holds_the_same_rules() -> None:
    assert Endpoint("db.example", "h").sslmode == "verify-full"
    for mode in ("require", "prefer", "allow", "disable", "verify-ca"):
        with pytest.raises(ValueError, match="verify-full"):
            Endpoint("db.example", "h", sslmode=mode)
    with pytest.raises(ValueError, match="sslmode"):
        Endpoint("/tmp/s", "h", sslmode="bogus")
    assert Endpoint("/tmp/s", "h", sslmode="disable").sslmode == "disable"


def test_the_server_must_ask_for_the_token_and_no_certificate_stands_in_for_it() -> None:
    found = Endpoint("db.example", "h").parameters()
    assert found["require_auth"] == "scram-sha-256,password" and found["sslcertmode"] == "disable"


def test_an_old_libpq_is_refused_rather_than_connected_without_checking_the_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import psycopg

    monkeypatch.setattr(psycopg.pq, "version", lambda: 150004)
    with pytest.raises(ValueError, match="libpq 16"):
        Endpoint("db.example", "h")
    with pytest.raises(ValueError, match="libpq 16"):
        Endpoint("/tmp/s", "h", sslmode="disable")
    with pytest.raises(ValueError, match="libpq 16"):
        parse_endpoint("postgresql://db.example/h")
    monkeypatch.setattr(psycopg.pq, "version", lambda: 160000)
    assert Endpoint("db.example", "h").parameters()["require_auth"]


def test_an_endpoint_built_directly_holds_the_parse_rules_for_roots_and_hosts() -> None:
    for root in ("relative/root.crt", "", "./r.crt"):
        with pytest.raises(ValueError, match="sslrootcert"):
            Endpoint("db.example", "h", sslrootcert=root)
    assert Endpoint("db.example", "h", sslrootcert="system").sslrootcert == "system"
    assert Endpoint("db.example", "h", sslrootcert="/r.crt").sslrootcert == "/r.crt"
    for host in ("a.example,b.example", "", "/tmp/a,/tmp/b"):
        with pytest.raises(ValueError, match="one host"):
            Endpoint(host, "h", sslmode="disable")
    with pytest.raises(ValueError, match="database"):
        Endpoint("db.example", "")


def test_sslrootcert_is_an_absolute_path_or_system() -> None:
    pem = parse_endpoint("postgresql://db.example/h?sslrootcert=/etc/ssl/db-root.crt")
    assert pem.sslrootcert == "/etc/ssl/db-root.crt"
    assert pem.parameters()["sslrootcert"] == "/etc/ssl/db-root.crt"
    system = parse_endpoint("postgresql://db.example/h?sslrootcert=system")
    assert system.parameters()["sslrootcert"] == "system"
    assert parse_endpoint("postgresql:///h?host=/tmp/s&sslrootcert=system").sslrootcert == "system"


def test_a_remote_endpoint_without_a_root_trusts_the_system_store() -> None:
    remote = parse_endpoint("postgresql://db.example/h")
    assert remote.parameters()["sslrootcert"] == "system"
    assert (
        parse_endpoint("postgresql://db.example/h?sslrootcert=/r.crt").parameters()["sslrootcert"]
        == "/r.crt"
    )


def test_a_local_endpoint_asks_for_no_root_and_keeps_working() -> None:
    sock = parse_endpoint("postgresql:///arras?host=/tmp/ar-1/pg")
    assert sock.sslmode == "prefer" and "sslrootcert" not in sock.parameters()
    assert parse_endpoint("postgresql://127.0.0.1/h").sslmode == "prefer"
    assert parse_endpoint("postgresql://[::1]/h?sslmode=require").sslmode == "require"


def test_the_scheme_selects_the_adapter() -> None:
    assert is_endpoint("postgresql://h/d") and is_endpoint("POSTGRES://h/d")
    assert not is_endpoint("primary.example") and not is_endpoint("ashlar://x")


def test_the_person_is_the_role_and_the_token_the_password_on_a_fresh_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import psycopg

    seen: list[dict[str, object]] = []
    closed: list[bool] = []

    class Conn:
        def close(self) -> None:
            closed.append(True)

    def fake(**kw: object) -> Conn:
        seen.append(kw)
        return Conn()

    monkeypatch.setattr(psycopg, "connect", fake)
    source = endpoint_source(parse_endpoint("postgresql://db.example/h"))
    with source(Principal("carol@example.com", "tok-1")) as conn:
        assert isinstance(conn, Conn) and not closed
    assert closed == [True]
    (kw,) = seen
    assert (kw["user"], kw["password"], kw["dbname"], kw["host"]) == (
        "carol@example.com",
        "tok-1",
        "h",
        "db.example",
    )
    # nothing ambient is left to supply: every keyword libpq reads from the environment is given
    for key in ("options", "target_session_attrs", "gssencmode", "channel_binding", "hostaddr"):
        assert key in kw
    assert kw["options"] == "" and kw["connect_timeout"] == endpoint_module.CONNECT_TIMEOUT_S
    assert "autocommit" not in kw and "service" not in kw


def test_the_connection_is_closed_when_the_call_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    import psycopg

    closed: list[bool] = []

    class Conn:
        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(psycopg, "connect", lambda **kw: Conn())
    with pytest.raises(RuntimeError), connect(Endpoint("h", "d"), "u", "p"):
        raise RuntimeError("boom")
    assert closed == [True]
