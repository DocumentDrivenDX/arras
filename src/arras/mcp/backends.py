# SPDX-License-Identifier: MIT OR Apache-2.0
"""Where the MCP process builds its backends: the one place a handle becomes an adapter.

A handle that is a PostgreSQL URI (`postgresql://`) is a Truss backend, built over the person's own
token on a new connection per call (`arras.adapters.truss.endpoint`). The process holds no
installing connection (it cannot migrate, register or import: CONTRACT-007), so it cannot read the
store's install state and `Arras.status()` (which `describe` reports) says what the last per-person
call showed: `not_configured` ("no installing connection") before any call, then available, or
unavailable with the reason when the call could not reach the database. Reads and writes are served
and refused by the database as the person whatever the status says. A handle that no adapter reads, or whose extra is not
installed, gets no backend and is returned in `unbuilt` with the reason; the process then starts
degraded and says why, rather than pretending a handle is a connection (CONTRACT-005: `start` never
raises for availability). A handle that is a PostgreSQL URI but not a usable endpoint is a
`ConfigError` naming the key, never the value. The adapters are constructed here and nowhere else.
"""

from __future__ import annotations

from arras.backend import Backend
from arras.mcp.config import Config, ConfigError


def build_backends(config: Config) -> tuple[dict[str, Backend], dict[str, str]]:
    """The backends to start with, and the configured handles that have none, with the reason."""
    from arras.adapters.truss import EXTRA, create_backend, require_toolkit
    from arras.adapters.truss.endpoint import endpoint_source, is_endpoint, parse_endpoint

    built: dict[str, Backend] = {}
    unbuilt: dict[str, str] = {}
    problems: list[str] = []
    for name, handle in sorted(config.endpoints.items()):
        key = f"ARRAS_BACKEND_{name.upper()}_ENDPOINT"
        if not is_endpoint(handle):
            unbuilt[name] = "no adapter reads this handle"
            continue
        try:
            require_toolkit()
        except ImportError:
            unbuilt[name] = f"the {EXTRA} extra is not installed (pip install arras[{EXTRA}])"
            continue
        try:
            endpoint = parse_endpoint(handle)
        except ValueError as e:
            problems.append(f"{key}: {e}")
            continue
        built[name] = create_backend(name, endpoint_source(endpoint))  # type: ignore[assignment]
    if problems:
        raise ConfigError(problems)
    return built, unbuilt
