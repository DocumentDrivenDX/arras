# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""A development host: the console, the operator surface and the built UI at one origin.

    uv run --extra devhost python -m arras.devhost [--port 8000] [--ui ui/dist]

It serves the sandbox's fakes to the sandbox's people, or, with `--truss`, a real Truss
(`arras.devtruss`). Truss mode attaches to a persistent PostgreSQL server when a connection URL is
available (`--truss-url`, else the environment variable `ARRAS_TRUSS_DEV_URL`, else the same
variable in `~/.arras/truss-dev.env`): the URL names a role that owns a database and has CREATEROLE
and no superuser, and its password; the state then persists across restarts. Starting again reuses
host-owned credentials from `--truss-credentials`, `ARRAS_TRUSS_DEV_CREDENTIALS` or a scoped file
under `~/.arras/truss-dev-credentials/`, preserving existing memberships and expiry. New people
and module roles get the sandbox defaults; explicit role selection reconciles only generated
module and registrar memberships. Seeding runs only when no module holds an entity yet. Closing
drops nothing and stops nothing; `--truss-reset` drops what the dev host
made in that database (Truss's schema and roles, the people) and starts clean. The startup prints the
host, port, database and role to attach `psql` with, and where the password is, never the password.
With no URL it keeps a throwaway local PostgreSQL, removed at exit. Either way it is for developing
and demonstrating the Operator Console, never for a deployed app: it authenticates nobody (a header
names the person) and answers only on the loopback address. A real host maps its own identity to a
`Principal` and mounts `console.create_app` and `operate.create_app` itself (CONTRACT-006,
CONTRACT-009).

The built UI's page carries the default brand's title and `<meta name="arras-brand">`, as
`arras.ui` serves it, and the pages are served under a Content-Security-Policy (`PAGE_CSP`), and the assets of
UMF's schema browser package (built to `ui/dist/umf-explorer`) at `/umf-explorer/` under the same
policy. The console mounts the browser in a `srcdoc` iframe, which inherits the console page's
policy, so that page's policy is the one the browser runs under; the console reads the browser's
catalog itself from the operator surface (CONTRACT-009) with the person's header.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, TypeVar, overload

from arras import console, graphfile, operate, telemetry
from arras.adapters.truss.endpoint import parse_credentialed
from arras.adapters.truss.local import CredentialSource
from arras.devcredentials import FileCredentialSource
from arras.distribution import DistributionConfig
from arras.errors import ArrasError, Invalid
from arras.http import Receive, Request, Scope, Send
from arras.sandbox import ROLES, Box, Sandbox, read_steps
from arras.types import Principal
from arras.ui import (  # noqa: F401  (the policy its page is measured under)
    PAGE_CSP,
    PAGE_HEADERS,
    branded,
    not_built_page,
)

USER_HEADER = "x-arras-user"
ROLE_HEADER = "x-arras-role"  # with a made-up name: the role it holds (`arras.sandbox.ROLES`)
EXPLORER = "/umf-explorer"
DEFAULT_USER = "alice"
# By default the sandbox's operators are the members of the groups `admins` and `builders`
# (CONTRACT-010, section E): root is an admin, alice and bob are builders, and carol and dave are
# readers, so a test sees the refusal as them.
OPERATOR_GROUPS = ("admins", "builders")
# A host or flag may name other groups (`operator_groups`): the sandbox's operators then belong to
# each of them as well, and carol and dave stay outside.
_GROUP_NAME = re.compile(r"[^\s,]{1,64}")
MODES = ("read", "write", "journal", "schema")
DEFAULT_UI = Path(__file__).resolve().parents[2] / "ui" / "dist"
_LOCKED = (
    "apply",
    "apply_batch",
    "import_records",
    "register",
    "validate_register",
    "query",
    "changes",
    "loads",
    "feed",
    "catalog",
    "status",
    "reached",
    "describe",
    "document",
)
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "[::1]")
TRUSS_URL_VARIABLE = "ARRAS_TRUSS_DEV_URL"
TRUSS_URL_FILE = Path("~/.arras/truss-dev.env")
TRUSS_CREDENTIALS_VARIABLE = "ARRAS_TRUSS_DEV_CREDENTIALS"
B = TypeVar("B", bound=Box)


def serialized(sandbox: B) -> B:
    """The fakes are not thread-safe and the apps run requests in worker threads: one lock."""
    lock = sandbox.lock

    def locked(fn: Callable[..., Any]) -> Callable[..., Any]:
        def run(*a: Any, **k: Any) -> Any:
            with lock:
                return fn(*a, **k)

        return run

    for backend in sandbox.backends.values():
        for name in _LOCKED:
            if hasattr(backend, name):
                setattr(backend, name, locked(getattr(backend, name)))
    return sandbox


def _host_name(host: str) -> str:
    """The name in a `Host` header without its port, for a name, an IPv4 address or `[::1]:8000`."""
    if host.startswith("["):
        return host[: host.index("]") + 1] if "]" in host else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def checked_operator_groups(groups: Sequence[str]) -> tuple[str, ...]:
    """The operator groups as a tuple of distinct names, or `ValueError`: a bare string, no name, or
    a name that is empty, has white space or a comma, or is over 64 characters."""
    if isinstance(groups, str):
        raise ValueError("operator_groups: a sequence of group names, not one string")
    names = tuple(dict.fromkeys(groups))
    if not names or not all(isinstance(n, str) and _GROUP_NAME.fullmatch(n) for n in names):
        raise ValueError(
            "operator_groups: one or more names of 1 to 64 characters, no white space or comma"
        )
    return names


class DevHost:
    def __init__(
        self,
        sandbox: Box,
        *,
        port: int,
        ui_dir: Path = DEFAULT_UI,
        distribution: DistributionConfig | None = None,
        telemetry_context: telemetry.TelemetryContext | None = None,
        operator_groups: Sequence[str] = OPERATOR_GROUPS,
    ) -> None:
        self.operator_groups = checked_operator_groups(operator_groups)
        self.distribution = distribution or DistributionConfig()
        self.telemetry_context = telemetry._context_for(telemetry_context, distribution)
        self.box: Any = serialized(sandbox)
        self.ui = ui_dir
        origins = [f"http://127.0.0.1:{port}", f"http://localhost:{port}"]
        dev = ("http://127.0.0.1:5173", "http://localhost:5173")  # the Vite dev server
        self.own_origins = {*origins, *dev}  # the proxy keeps the page's Origin on the control
        kw: dict[str, Any] = {"principal_for_request": self.who}
        self.console = console.create_app(
            sandbox.arras,
            base_path="/api/console",
            public_origin=origins[0],
            allowed_origins=(origins[1], *dev),
            **kw,
        )
        self.schema = operate.create_schema_app(
            sandbox.arras,
            base_path="/api/schema",
            public_origin=origins[0],
            allowed_origins=(origins[1], *dev),
            authorize_operator=operate.operators_in_groups(*self.operator_groups),
            **kw,
        )
        self.operate = operate.create_app(
            sandbox.arras,
            base_path="/api/operate",
            public_origin=origins[0],
            allowed_origins=(origins[1], *dev),
            authorize_operator=operate.operators_in_groups(*self.operator_groups),
            **kw,
        )

    def who(self, request: Request) -> Principal | None:
        """A sandbox person by name, or, with a role, a made-up one (`Sandbox.person`)."""
        name = request.headers.get(USER_HEADER, DEFAULT_USER)
        role = request.headers.get(ROLE_HEADER)
        try:
            who = self.box.principal(name) if role is None else self.box.person(name, role)
        except (KeyError, ValueError):
            return None
        if self.operator_groups != OPERATOR_GROUPS and set(OPERATOR_GROUPS) & set(who.groups):
            # the sandbox's operators are the default groups' members: they join the named ones
            who = replace(who, groups=tuple(dict.fromkeys((*who.groups, *self.operator_groups))))
        return who

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        with self.telemetry_context.activate():
            await self._dispatch(scope, receive, send)

    async def _dispatch(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        path = scope["path"]
        headers = dict(scope.get("headers", []))
        host = headers.get(b"host", b"").decode("latin-1")
        if _host_name(host) not in LOOPBACK_HOSTS:
            # a rebound hostname reaches this server too: answer only for its own address
            return await self._send(send, 403, "text/plain", b"unexpected Host")
        if path.startswith("/api/console"):
            return await self.console(scope, receive, send)
        if path.startswith("/api/operate"):
            return await self.operate(scope, receive, send)
        if path.startswith("/api/schema"):
            return await self.schema(scope, receive, send)
        if path == EXPLORER or path.startswith(EXPLORER + "/"):
            name = path[len(EXPLORER) :].strip("/") or "index.html"
            status, ctype, body = self.static(f"{EXPLORER}/{name}", fallback=False)
            return await self._send(send, status, ctype, body, PAGE_HEADERS)
        if path == "/api/dev/control":
            return await self.control(scope, receive, send, headers)
        if path == "/api/people":
            people = {
                "people": sorted(self.box.people),
                "roles": list(ROLES),
                "default": DEFAULT_USER,
            }
            body = json.dumps(people).encode()
            return await self._send(send, 200, "application/json", body)
        status, ctype, body = self.static(path)
        await self._send(send, status, ctype, body, PAGE_HEADERS)

    async def control(
        self, scope: Scope, receive: Receive, send: Send, headers: dict[bytes, bytes]
    ) -> None:
        """Break and mend the sandbox, so a test can see an expired token or a backend outage
        through the real surfaces: POST {op: expire|restore, user} | {op: outage, backend,
        reason|null} | {op: feed} | {op: register, document} (another module, which the people
        hold as they hold `catalog`) | {op: grant|revoke, user, module, modes?} (a person's access
        to a module: `grant` adds the modes, default `["read"]`; `revoke` removes them, default
        all of `read`, `write` and `journal`) | {op: search, backend, type, mode} (what search
        the backend declares for a type, `none` or `substring`, `null` to restore). A browser must
        come from this server's own origin."""
        origin = headers.get(b"origin", b"").decode("latin-1")
        if scope["method"] != "POST" or (origin and origin not in self.own_origins):
            return await self._send(send, 403, "text/plain", b"refused")
        raw = b""
        while True:
            msg = await receive()
            raw += msg.get("body", b"")
            if not msg.get("more_body"):
                break
        try:
            body = json.loads(raw or b"{}")
            op = body["op"]
            if op in ("expire", "restore"):
                self.box.set_token(body["user"], live=op == "restore")
            elif op == "outage":
                reason = body.get("reason")
                if reason not in (None, "unreachable", "access_denied", "migration_failed"):
                    raise ValueError(reason)
                self.box.set_outage(body["backend"], reason)
            elif op in ("grant", "revoke"):
                self.change_access(op, body)
            elif op == "search":
                self.box.declare_search(body["backend"], body["type"], body["mode"])
            elif op == "feed":
                self.box.feed()
            elif op == "register":
                document = body["document"]
                if not isinstance(document, str):
                    raise TypeError(document)
                try:
                    self.box.load(document)
                except Exception as e:  # the registry's refusal, as a 400 that says why
                    msg = json.dumps({"error": "not registered", "reason": str(e)}).encode()
                    return await self._send(send, 400, "application/json", msg)
            else:
                raise ValueError(op)
        except (KeyError, ValueError, TypeError, ArrasError):
            return await self._send(send, 400, "application/json", b'{"error": "unknown control"}')
        await self._send(send, 200, "application/json", b'{"ok": true}')

    def change_access(self, op: str, body: dict[str, Any]) -> None:
        """`grant` or `revoke` modes on a module for a person the box knows."""
        user, module = body["user"], body["module"]
        if user not in self.box.people or not isinstance(module, str) or not module:
            raise ValueError(user)
        default = ["read"] if op == "grant" else list(MODES)
        modes = body.get("modes", default)
        if not isinstance(modes, list) or not set(modes) <= set(MODES):
            raise ValueError(modes)
        self.box.set_access(user, module, modes, grant=op == "grant")

    @staticmethod
    async def _send(
        send: Send,
        status: int,
        ctype: str,
        body: bytes,
        extra: tuple[tuple[bytes, bytes], ...] = (),
    ) -> None:
        headers = [(b"content-type", ctype.encode()), (b"cache-control", b"no-store"), *extra]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    def static(self, path: str, *, fallback: bool = True) -> tuple[int, str, bytes]:
        """A file of the built UI, or its index for a route of the app; never a path outside it.
        Without `fallback` a missing file is a 404, not the app's page."""
        index = self.ui / "index.html"
        if not index.is_file():
            return (
                200,
                "text/html; charset=utf-8",
                not_built_page(self.distribution.brand, _NOT_BUILT_HINT),
            )
        target = (self.ui / path.lstrip("/")).resolve()
        if path not in ("", "/") and target.is_file() and self.ui.resolve() in target.parents:
            ctype = _TYPES.get(target.suffix) or mimetypes.guess_type(target.name)[0]
            return 200, ctype or "application/octet-stream", target.read_bytes()
        if not fallback or "." in path.rsplit("/", 1)[-1]:
            return 404, "text/plain", b"not found"
        return 200, "text/html; charset=utf-8", branded(index.read_bytes(), self.distribution.brand)


_TYPES = {  # not left to the platform's table, which differs (a .js as text/plain breaks nosniff)
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json",
}


_NOT_BUILT_HINT = (
    b"Run <code>npm ci &amp;&amp; npm run build</code> in <code>ui/</code>, then reload. "
    b"The API is at <code>/api/operate</code> and <code>/api/console</code>.</p>"
)


DEMO_AREAS: dict[str, tuple[str, ...]] = {
    "data": ("Pipeline review", "Schema review", "Capacity check", "Release checklist"),
    "operations": ("Alert screening", "Incident minutes", "Runbook audit", "Service onboarding"),
    "finance": ("Cloud cost memo", "Dependency study", "Quota eligibility", "Usage review"),
}
DEMO_SOLUTIONS: tuple[tuple[str, str, str, str | None], ...] = (
    # (code, name, use case code, coverage level); the declared AddSolution links one use case
    ("sol-extract", "Pattern extractor", "uc-pipeline-review", "full"),
    ("sol-schema", "Schema summariser", "uc-schema-review", "partial"),
    ("sol-capacity", "Capacity lookup", "uc-capacity-check", None),
    ("sol-alerts", "Alert triage", "uc-alert-screening", "full"),
    ("sol-minutes", "Minutes drafter", "uc-incident-minutes", "partial"),
    ("sol-runbook", "Runbook reconciler", "uc-runbook-audit", None),
    ("sol-cost", "Comparables finder", "uc-cloud-cost-memo", "partial"),
    ("sol-deps", "Dependency mapper", "uc-dependency-study", "full"),
    ("sol-quota", "Quota screener", "uc-quota-eligibility", None),
    ("sol-pipeline-risk", "Pipeline risk scorer", "uc-pipeline-review", "partial"),
)


def seed_demo(sandbox: B) -> B:
    """A richer catalog through the declared actions, as alice: 12 use cases across 3 work areas
    and 10 solutions, each addressing one use case (AddSolution links exactly one)."""
    o = sandbox.arras.session(sandbox.people["alice"])
    for area, names in DEMO_AREAS.items():
        for name in names:
            code = "uc-" + name.lower().replace(" ", "-")
            o.invoke("catalog.AddUseCase", {"code": code, "name": name, "workArea": area})
    for code, name, use_case, level in DEMO_SOLUTIONS:
        o.invoke("catalog.AddSolution", {"code": code, "name": name, "useCase": use_case})
        if level:
            o.invoke("catalog.CorrectSolution", {"solution": code, "level": level})
    sandbox.settle()
    return sandbox


@overload
def build(
    module: Path | None,
    seed: Path | None,
    *,
    demo: bool = ...,
    records: Path | None = ...,
    also: Sequence[tuple[Path, Path | None]] = ...,
) -> Sandbox: ...
@overload
def build(
    module: Path | None,
    seed: Path | None,
    *,
    demo: bool = ...,
    records: Path | None = ...,
    also: Sequence[tuple[Path, Path | None]] = ...,
    truss: bool,
    truss_url: str | None = ...,
    credential_source: CredentialSource | None = ...,
    truss_reset: bool = ...,
) -> Box: ...
def build(
    module: Path | None,
    seed: Path | None,
    *,
    demo: bool = False,
    records: Path | None = None,
    also: Sequence[tuple[Path, Path | None]] = (),
    truss: bool = False,
    truss_url: str | None = None,
    credential_source: CredentialSource | None = None,
    truss_reset: bool = False,
) -> Box:
    """The box to serve: the one in `module` with the steps in `seed` and the graph in `records`
    (a file the interface's Export wrote), or the sandbox's own (with the richer demo catalog when
    `demo`). With `truss` the same, over a real Truss (`arras.devtruss`): on a throwaway local
    PostgreSQL that `close` removes, or, with `truss_url`, on the persistent server it names, where
    the seed and the demo run only when no module holds an entity yet, `close` drops nothing and
    `truss_reset` starts clean, and a graph file loads after the seed only then too. A module the
    registry refuses is `Invalid`; a misshapen seed or graph file, or a file for another module, is
    a `ValueError`."""
    if truss:
        from arras.devtruss import TrussBox

        tbox = TrussBox(url=truss_url, credential_source=credential_source, reset=truss_reset)
        try:
            if module is not None:
                steps = read_steps(seed) if seed is not None else []
                graph = graphfile.loads(records.read_text(encoding="utf-8")) if records else None
                tbox.load(module.read_text(encoding="utf-8"), steps, graph)
                for path, extra_seed in also:
                    more = read_steps(extra_seed) if extra_seed is not None else []
                    tbox.load(path.read_text(encoding="utf-8"), more)
                tbox.finish()
            else:
                tbox.seed()
                tbox.finish(seed_demo if demo else None)
        except BaseException:
            tbox.close()
            raise
        return tbox
    if module is not None:
        steps = read_steps(seed) if seed is not None else []
        graph = graphfile.loads(records.read_text(encoding="utf-8")) if records else None
        sandbox = Sandbox().load(module.read_text(encoding="utf-8"), steps, graph)
        for path, extra_seed in also:  # more modules beside it: the interface offers a choice
            more = read_steps(extra_seed) if extra_seed is not None else []
            sandbox.load(path.read_text(encoding="utf-8"), more)
        return sandbox
    plain = Sandbox().seed()
    return seed_demo(plain) if demo else plain


def truss_url(
    given: str | None,
    environ: Mapping[str, str] | None = None,
    file: Path | None = None,
) -> tuple[str, str] | None:
    """The persistent server's connection URL and where it came from, or None for a throwaway:
    `--truss-url`, else `ARRAS_TRUSS_DEV_URL` in the environment, else that variable in the file
    (`NAME=value` lines, `export` and quotes allowed). The source names a place, never the URL."""
    if given:
        return given, "the --truss-url you gave"
    env = os.environ if environ is None else environ
    if env.get(TRUSS_URL_VARIABLE):
        return env[TRUSS_URL_VARIABLE], f"the environment variable {TRUSS_URL_VARIABLE}"
    named = file or TRUSS_URL_FILE
    path = named.expanduser()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        text = line.strip().removeprefix("export ").strip()
        name, eq, value = text.partition("=")
        if eq and name.strip() == TRUSS_URL_VARIABLE:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            if value:
                return value, f"{TRUSS_URL_VARIABLE} in {named}"
    return None


def default_truss_credentials_path(url: str) -> Path:
    """Credential namespace for a host, port and installer; deliberately exclude the database."""
    endpoint, installer, _ = parse_credentialed(url)
    identity = f"{endpoint.host}\0{endpoint.port or 5432}\0{installer}"
    digest = hashlib.sha256(identity.encode()).hexdigest()
    return Path.home() / ".arras" / "truss-dev-credentials" / f"{digest}.json"


def truss_attachment(url: str, source: str) -> list[str]:
    """What to say at startup about the persistent server: where it is and which role to attach
    `psql` as (the installing role, which owns the database), and where its password is. The URL's
    password is never in it. `ValueError` for a URL the adapter refuses, without repeating it."""
    from arras.adapters.truss.endpoint import parse_credentialed

    endpoint, role, _ = parse_credentialed(url)
    host = endpoint.host
    port = endpoint.port or 5432
    return [
        f"attached to the persistent Truss at {host}, port {port}, database {endpoint.dbname}",
        f"  psql -h {host} -p {port} -U {role} {endpoint.dbname}",
        f"  the password of {role} is in {source}; the people are the roles arrasdev_<name>",
    ]


def _truss_missing(persistent: bool = False) -> str | None:
    """Why `--truss` cannot run here (the extra, the test group), or None. A persistent
    server needs no local PostgreSQL, so not the test group."""
    import importlib.util

    if importlib.util.find_spec("truss") is None or importlib.util.find_spec("psycopg") is None:
        return "the truss extra: uv run --extra devhost --extra truss --group truss-test ..."
    if not persistent and importlib.util.find_spec("pgserver") is None:
        return "the truss-test group (a local PostgreSQL): uv run --group truss-test ..."
    return None


def _module_and_seed(arg: str) -> tuple[Path, Path | None]:
    module, colon, seed = arg.partition(":")
    return Path(module), Path(seed) if colon else None


def _announce_truss(attach: tuple[str, str] | None, *, reset: bool) -> None:
    """Refuse a Truss mode that cannot run here before anything starts, then say what starts."""
    missing = _truss_missing(persistent=attach is not None)
    if missing:
        raise SystemExit(f"--truss needs {missing}")
    if attach is None:
        print(
            "starting a throwaway local Truss: installing, registering and seeding takes a "
            f"while (a persistent one: --truss-url or {TRUSS_URL_VARIABLE})",
            flush=True,
        )
        return
    try:
        lines = truss_attachment(*attach)
    except ValueError as e:
        raise SystemExit(f"--truss: the connection URL is refused: {e}") from None
    note = "reset, " if reset else ""
    print(
        *lines,
        f"{note}installing or verifying Truss, registering and seeding an empty "
        "database takes a while",
        sep="\n",
        flush=True,
    )


def _display_brand_name(distribution: DistributionConfig | None) -> str:
    selected = distribution or DistributionConfig()
    return (
        " ".join(
            "".join(char if char.isprintable() else " " for char in selected.brand.name).split()
        )
        or "Arras"
    )


def _parser(distribution: DistributionConfig | None = None) -> argparse.ArgumentParser:
    description = (
        __doc__
        if (distribution or DistributionConfig()).brand.name == "Arras"
        else f"{_display_brand_name(distribution)} development host for a locally composed Arras app."
    )
    p = argparse.ArgumentParser(prog="python -m arras.devhost", description=description)
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--ui", type=Path, default=DEFAULT_UI, help="the built UI (ui/dist)")
    p.add_argument(
        "--demo",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="seed a richer demo catalog (default on; not with --module)",
    )
    p.add_argument(
        "--module", type=Path, help="a UMF module document to serve in place of the demo"
    )
    p.add_argument("--seed", type=Path, help="a JSON list of action steps to run; needs --module")
    p.add_argument(
        "--truss",
        action="store_true",
        help="serve a real Truss instead of the sandbox's fakes: on the persistent PostgreSQL "
        "server a connection URL names (--truss-url, else $ARRAS_TRUSS_DEV_URL, else "
        "~/.arras/truss-dev.env; needs --extra truss), otherwise on a "
        "throwaway local PostgreSQL (also needs --group truss-test)",
    )
    p.add_argument(
        "--truss-url",
        metavar="URL",
        help="the persistent server's connection URL, with the installing role's password; "
        "prefer the environment variable or the file, which keep it off the command line",
    )
    p.add_argument(
        "--truss-reset",
        action="store_true",
        help="drop what the dev host made in the persistent database (Truss's schema and roles, "
        "the people's roles) and start clean; never a role or database it did not make",
    )
    p.add_argument(
        "--truss-credentials",
        type=Path,
        metavar="PATH",
        help="host-owned file for stable persistent person credentials (or "
        f"${TRUSS_CREDENTIALS_VARIABLE})",
    )
    p.add_argument(
        "--operator-group",
        action="append",
        dest="operator_groups",
        metavar="NAME",
        help="a group the operator surface is offered to; repeatable, and replaces the default "
        f"({', '.join(OPERATOR_GROUPS)}). The sandbox's operators belong to each group named",
    )
    p.add_argument(
        "--records",
        type=Path,
        help="a graph file (the interface's Export) to load after the seed; needs --module",
    )
    p.add_argument(
        "--also",
        action="append",
        default=[],
        metavar="MODULE[:SEED]",
        help="another module (and the steps that seed it) to serve beside --module; repeatable",
    )
    return p


def main(
    argv: list[str] | None = None,
    *,
    distribution: DistributionConfig | None = None,
    telemetry_factory: Callable[[telemetry.TelemetryNames], telemetry.TelemetryContext]
    | None = None,
    operator_groups: Sequence[str] | None = None,
) -> None:
    """The development host's command line. `operator_groups` is the distribution's default for the
    groups the operator surface is offered to (`--operator-group` overrides it)."""
    p = _parser(distribution)
    args = p.parse_args(argv)
    try:
        args.operator_groups = checked_operator_groups(
            args.operator_groups or operator_groups or OPERATOR_GROUPS
        )
    except ValueError as e:
        p.error(str(e))
    needs_module = [("--also", args.also), ("--seed", args.seed), ("--records", args.records)]
    for flag, value in needs_module:
        if value and args.module is None:
            p.error(f"{flag} needs --module")
    if (args.truss_url or args.truss_reset or args.truss_credentials) and not args.truss:
        p.error("--truss-url, --truss-reset and --truss-credentials need --truss")
    attach = truss_url(args.truss_url) if args.truss else None
    if args.truss_credentials and attach is None:
        p.error("--truss-credentials needs a persistent server URL")
    if args.truss_reset and attach is None:
        p.error(
            "--truss-reset needs a persistent server: give --truss-url or set "
            f"{TRUSS_URL_VARIABLE} (a throwaway starts clean anyway)"
        )
    if attach is not None:
        try:
            parse_credentialed(attach[0])
        except (TypeError, ValueError):
            p.error("--truss-url is refused")
    also = [_module_and_seed(item) for item in args.also]
    selected = distribution or DistributionConfig()
    try:
        context = telemetry._make_context(selected.telemetry, telemetry_factory)
    except Exception:
        raise SystemExit("telemetry configuration refused") from None
    _run_host(args, selected, context, attach, also)


def _run_host(
    args: argparse.Namespace,
    distribution: DistributionConfig,
    context: telemetry.TelemetryContext,
    attach: tuple[str, str] | None,
    also: list[tuple[Path, Path | None]],
) -> None:
    with context.activate():
        credential_source: CredentialSource | None = None
        try:
            import uvicorn
        except ImportError:
            raise SystemExit(
                "uvicorn is needed: uv run --extra devhost python -m arras.devhost"
            ) from None
        if args.truss:
            _announce_truss(attach, reset=args.truss_reset)
        try:
            if attach is not None:
                path = args.truss_credentials or (
                    Path(os.environ[TRUSS_CREDENTIALS_VARIABLE]).expanduser()
                    if os.environ.get(TRUSS_CREDENTIALS_VARIABLE)
                    else default_truss_credentials_path(attach[0])
                )
                credential_source = FileCredentialSource(path)
            box = build(
                args.module,
                args.seed,
                demo=args.demo,
                records=args.records,
                also=also,
                truss=args.truss,
                truss_url=attach[0] if attach else None,
                credential_source=credential_source,
                truss_reset=args.truss_reset,
            )
        except Invalid as e:
            lines = [f"  {v.path}: {v.code}: {v.message}" for v in e.violations]
            raise SystemExit("\n".join([f"{args.module} was refused:", *lines])) from None
        except (OSError, ValueError, ArrasError) as e:
            raise SystemExit(f"could not load: {e}") from None
        if attach is not None:
            seeded = getattr(box, "seeded", None)
            print(
                "the database holds nothing yet: seeded it"
                if seeded
                else "the database holds entities already: left them as they are",
                flush=True,
            )
        try:
            app = DevHost(
                box,
                port=args.port,
                ui_dir=args.ui,
                distribution=distribution,
                telemetry_context=context,
                operator_groups=args.operator_groups,
            )
            print(
                f"{_display_brand_name(distribution)} development host at http://127.0.0.1:{args.port}",
                flush=True,
            )
            uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")
        finally:
            close = getattr(box, "close", None)
            if close is not None:
                close()


if __name__ == "__main__":
    main()
