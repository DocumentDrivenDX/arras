# SPDX-License-Identifier: MIT OR Apache-2.0
"""The endpoint handle of a Truss backend, and the connection source built from it (ADR-019, CONTRACT-007).

A host that configures a backend by handle (the MCP process) gives a libpq URI that carries no
credential: `postgresql://host:5432/dbname` (a remote host is always `sslmode=verify-full`, with
`sslrootcert` an absolute path or `system`, or neither: see `Endpoint.parameters`), or for a local socket
`postgresql:///dbname?host=/path/to/dir`. The credential is the person's own token, handed to the server
as the password of the role named for the person (`Principal.user`), on a new connection per call
(ADR-017). `parse_endpoint` refuses anything else, so no backend credential can sit in configuration,
and its errors never repeat the handle. `connect` takes every connection parameter from the handle
or from a default stated here, so an ambient `PG*` variable has little left to supply, and the process
scrubs them all (`PGSERVICE` has no keyword that switches it off) (`arras.mcp.config.scrub_ambient_connection_environment`).

psycopg is imported inside functions: the base install has none of it.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from typing import Any

from arras.adapters.truss.connection import ConnectionSource
from arras.types import Principal

SCHEMES = ("postgresql://", "postgres://")
CONNECT_TIMEOUT_S = 10
APPLICATION_NAME = "arras"
_KEYS = frozenset(
    {"host", "port", "dbname", "sslmode", "sslrootcert", "connect_timeout", "application_name"}
)
_LOOPBACK = ("localhost", "127.0.0.1", "::1")
_MODES = ("disable", "allow", "prefer", "require", "verify-ca", "verify-full")
_SYSTEM_ROOTS = "system"  # the operating system's trust store
_LIBPQ_FLOOR = 160000  # require_auth, sslcertmode and sslrootcert=system all need libpq 16


def is_endpoint(text: str) -> bool:
    """Whether a handle is a PostgreSQL URI (the form this adapter reads)."""
    return text.lower().startswith(SCHEMES)


@dataclass(frozen=True)
class Endpoint:
    """Where the database is: a host (or a socket directory, when it starts with `/`), a port and
    a database. Never a credential."""

    host: str
    dbname: str
    port: int | None = None
    sslmode: str = "verify-full"
    connect_timeout: int = CONNECT_TIMEOUT_S
    application_name: str = APPLICATION_NAME
    sslrootcert: str | None = None

    def __post_init__(self) -> None:
        import psycopg

        if psycopg.pq.version() < _LIBPQ_FLOOR:
            # without require_auth a trusting or peer/cert pg_hba would connect as the person
            # with the token never checked
            raise ValueError(
                "the installed libpq is older than libpq 16, which a connection that must check "
                "the person's token needs"
            )
        if not self.host or "," in self.host:
            raise ValueError("an endpoint names one host or one socket directory")
        if not self.dbname:
            raise ValueError("an endpoint names a database")
        if (
            self.sslrootcert is not None
            and self.sslrootcert != _SYSTEM_ROOTS
            and not self.sslrootcert.startswith("/")
        ):
            raise ValueError("sslrootcert is an absolute path or system")
        if self.sslmode not in _MODES:
            raise ValueError("sslmode is not one libpq knows")
        if not self.local and self.sslmode != "verify-full":
            raise ValueError(
                "a remote endpoint verifies the server certificate and name: sslmode verify-full"
            )

    @property
    def local(self) -> bool:
        return self.host.startswith("/") or self.host in _LOOPBACK

    def parameters(self) -> dict[str, Any]:
        """The connection keywords with no person in them. Every one an ambient variable could
        supply is given, except the service file, which the process scrubs."""
        found: dict[str, Any] = {
            "host": self.host,
            "dbname": self.dbname,
            "sslmode": self.sslmode,
            "connect_timeout": self.connect_timeout,
            "application_name": self.application_name,
            "options": "",
            "target_session_attrs": "any",
            "gssencmode": "disable",
            "channel_binding": "prefer",
            "hostaddr": "",
        }
        # the token is a password: a server whose pg_hba trusts, or checks a certificate or the
        # operating system user instead, would never ask for it and so never check it
        found["require_auth"] = "scram-sha-256,password"
        found["sslcertmode"] = "disable"
        root = self._root()
        if root is not None:
            found["sslrootcert"] = root
        if self.port is not None:
            found["port"] = self.port
        return found

    def _root(self) -> str | None:
        """The trust roots the server certificate is checked against: the one the handle names, else
        for a remote host the operating system's store. Never read from the environment."""
        if self.sslrootcert is not None:
            return self.sslrootcert
        if self.local:
            return None
        return _SYSTEM_ROOTS


def parse_endpoint(text: str) -> Endpoint:
    """The endpoint a handle names. `ValueError` says what is wrong and never repeats the handle."""
    found = _fields(text)
    if "user" in found or "password" in found or "passfile" in found:
        raise ValueError("an endpoint carries no credential: the person's token is the password")
    return _endpoint_of(found)


def parse_credentialed(text: str) -> tuple[Endpoint, str, str]:
    """A host's own handle for the installing role: the endpoint it names, the role and its
    password, for a host that installs Truss itself (the dev host's persistent server). A role with
    no password is refused: the adapter requires a server that asks for one. `ValueError` says what
    is wrong and never repeats the handle."""
    found = _fields(text)
    user, password = found.pop("user", None), found.pop("password", None)
    if "passfile" in found:
        raise ValueError("an endpoint does not take passfile")
    if not user:
        raise ValueError("the connection URL names the installing role")
    if not password:
        raise ValueError("the connection URL carries the installing role's password")
    return _endpoint_of(found), str(user), str(password)


def _fields(text: str) -> dict[str, Any]:
    from psycopg.conninfo import conninfo_to_dict

    if not is_endpoint(text):
        raise ValueError("an endpoint is a postgresql:// URI")
    try:
        return {k: v for k, v in conninfo_to_dict(text).items() if v is not None}
    except Exception:
        raise ValueError("the endpoint is not a valid PostgreSQL URI") from None


def _endpoint_of(found: dict[str, Any]) -> Endpoint:
    extra = sorted(set(found) - _KEYS)
    if extra:
        raise ValueError(f"an endpoint does not take {', '.join(extra)}")
    host = str(found.get("host", ""))
    dbname = str(found.get("dbname", ""))
    local = host.startswith("/") or host in _LOOPBACK
    mode = str(found.get("sslmode", "prefer" if local else "verify-full"))
    root = str(found["sslrootcert"]) if "sslrootcert" in found else None
    try:
        port = int(found["port"]) if "port" in found else None
        timeout = int(found.get("connect_timeout", CONNECT_TIMEOUT_S))
    except ValueError:
        raise ValueError("port and connect_timeout are whole numbers") from None
    if timeout < 1:
        raise ValueError("connect_timeout is at least 1 second")
    return Endpoint(  # refuses what the endpoint rules refuse
        host,
        dbname,
        port,
        mode,
        timeout,
        str(found.get("application_name", APPLICATION_NAME)),
        root,
    )


@contextmanager
def connect(endpoint: Endpoint, user: str, password: str) -> Generator[Any]:
    """A new idle connection as `user`, autocommit off, no options and no session role, closed on
    exit (CONTRACT-005). The keywords override anything in the process's environment."""
    import psycopg

    conn = psycopg.connect(**endpoint.parameters(), user=user, password=password)
    try:
        yield conn
    finally:
        conn.close()


def endpoint_source(endpoint: Endpoint) -> ConnectionSource:
    """The per-person source: the person's role is `principal.user` and their token the password."""

    def source(principal: Principal) -> AbstractContextManager[Any]:
        return connect(endpoint, principal.user, principal.token)

    return source
