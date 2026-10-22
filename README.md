# Arras

Arras is an open-source interface to an ontology. Types and actions are defined in UMF; every read states its freshness; a backend contract lets one module span a record store and its replicas. It is a Python library that a host application embeds, and it ships a React operator console and Graph Browser.

- **UMF types and actions.** A module is a UMF document: entity types, relationships and the actions that change them, with typed inputs, preconditions and effects. UMF is the DocumentDrivenDX metamodel.
- **Reads that state their freshness.** Every answer names the backend that served it, its position and the consistency level (`latest` or `bulk`). Statements are Weft SQL, compiled by the serving backend.
- **A backend contract.** Each backend is a reader (serves graph reads), a provider (applies actions) or both. Arras ships a Truss adapter (authoritative, PostgreSQL or Lakebase), an in-memory adapter for tests and the sandbox, and defines the contract an Ashlar adapter (a replica on Unity Catalog) meets.
- **Access is the backends' own.** Every call runs as the person who made it, with that person's token. Arras keeps no service identity and no cache of data or decisions.
- **Three surfaces.** A read-only GraphQL console, an operator surface for validating and invoking declared actions and reading the audit trail, and an MCP stdio server for agents.

Arras is embedded by host apps such as praxis, a Databricks app. The host authenticates people and maps them to a principal; Arras never does.

## Status

Beta (`0.x`). The in-memory adapter and the Truss adapter are built and pass the conformance corpus. The Ashlar adapter and the feed from Truss to it are not built; the backend contract and the conformance corpus (`arras.conformance.run_corpus`) are what a new adapter is held to.

## Install

```bash
pip install arras                                            # from PyPI
pip install "arras @ git+https://github.com/DocumentDrivenDX/arras"   # or from GitHub
```

The base install needs only `graphql-core`. Extras: `arras[otel]` (OpenTelemetry spans), `arras[devhost]` (the development host), `arras[truss]` (the Truss adapter; the Truss and Weft wheels are not on a package index, so resolve them from `tools/find-links/index.html`, as `pyproject.toml` does).

## Quick start

From a source checkout (Python 3.11 or later, with [`uv`](https://docs.astral.sh/uv/)):

```bash
uv sync --extra truss
uv run pytest -q
uv run --extra devhost python -m arras.devhost      # the console over fake data, on loopback only
```

Serve one of the examples with its seed:

```bash
uv run --extra devhost python -m arras.devhost --module examples/pizza/pizza.umf.json --seed examples/pizza/seed.json
```

## Examples

| Example | What it is |
|---------|------------|
| `examples/pizza/` | The Protege tutorial ontology: pizzas, toppings, bases, countries of origin |
| `examples/northwind/` | A slice of the Northwind trading-company sample database |
| `examples/catalog/` | A small software-tools catalog: use cases, solutions, products and how far each covers a use case |

Each folder has a README, a UMF document (`*.umf.json`) and a seed of action steps. The data is invented, apart from the Northwind rows, which come from the public sample database.

## Documentation

Work is governed by HELIX artifacts under `docs/helix/`, indexed in [`docs/helix/README.md`](docs/helix/README.md):

- [Product vision](docs/helix/00-discover/product-vision.md) and [PRD](docs/helix/01-frame/prd.md)
- [Concerns](docs/helix/01-frame/concerns.md) and [principles](docs/helix/01-frame/principles.md)
- [Architecture](docs/helix/02-design/architecture.md), the ADRs in `docs/helix/02-design/adr/` and the contracts in `docs/helix/02-design/contracts/` (`CONTRACT-001` to `CONTRACT-011`)
- [Glossary](docs/helix/glossary.md)

## Working on it

Python 3.11 with `uv` (ADR-010); everything runs from the repository root.

```bash
uv sync --extra truss            # create the environment from uv.lock, with the Truss adapter's libraries
uv run pytest -q                 # the suite, including the conformance corpus
uv run ruff check . && uv run ruff format --check . && uv run pyright
```

The `--extra truss` sync brings the Truss adapter's libraries (`truss-toolkit`, psycopg and Weft, resolved from
the committed find-links page, whose digests come from the releases' `SHA256SUMS` and which `uv sync --locked` verifies); without it strict pyright cannot resolve the adapter's imports. The base install
needs none of them, and the tests marked `truss` run only with `uv run --extra truss pytest -m truss`.

The checks that hold Arras's statements and the memory adapter to Weft's own parser
(`tests/test_weft_parser.py`, `test_weft_relational.py`, `test_reserved_names.py`) need Weft's
`weft-sql` 0.4.49 wheel, a test tool and a dependency of the optional `truss` extra, never of the base install. Without it they skip and
say so; CI installs it and sets `ARRAS_REQUIRE_WEFT=1`, which turns the skip into a failure. To run
them locally, take the wheel for your platform from Weft's public release, check it against the
release's `SHA256SUMS` and install it after `uv sync` (which would remove it), then run with
`--no-sync`:

```bash
gh release download v0.4.49 --repo DocumentDrivenDX/weft --dir /tmp/weft \
  --pattern SHA256SUMS --pattern 'weft_sql-0.4.49-*-<platform>.whl'
(cd /tmp/weft && grep ' weft_sql-' SHA256SUMS | shasum -a 256 -c --ignore-missing)
uv pip install /tmp/weft/weft_sql-0.4.49-*.whl
ARRAS_REQUIRE_WEFT=1 uv run --no-sync pytest -q
```

What exists, built against the contracts in `docs/helix/02-design/contracts/` with the in-memory adapter
(`memory` and `memory_replica`, `src/arras/fakes.py`, which evaluate a declared subset of Weft SQL,
joins and aggregates included, behind `src/arras/fakes_weft.py`) as the backends:

| Part | Where |
|------|-------|
| Interface: `Arras`, sessions, router, freshness (statements are Weft SQL, compiled by the serving backend) | `core.py`, `routing.py`, `actions.py` |
| Registry: UMF reader (stand-in), compatibility rules | `umf.py`, `compat.py`, `model.py` |
| Backend contract and the conformance corpus | `backend.py`, `conformance/` |
| Read-only GraphQL console (ASGI), and its schema builder | `console/`, `gqlschema.py` |
| Operator surface (ASGI): validate and invoke declared actions, read the audit trail, serve the UMF schema browser's catalog (CONTRACT-009) | `operate/` |
| UMF's schema browser for the console's UMF source view: the npm package `@documentdrivendx/umf-schema-browser`, pinned exactly at 2.0.0 with lockfile integrity; its `assets/` are served at `/umf-explorer` under UMF's strict CSP (no `'unsafe-eval'`). Bump: `npm install @documentdrivendx/umf-schema-browser@<v> --save-exact`, update `ui/scripts/umf-schema-browser.ts`, run the tests (`ui/README.md`, "UMF source") | `ui/package.json`, `ui/scripts/umf-schema-browser.ts`, `ui/src/areas/UmfSource.tsx` |
| Operator Console UI (React, `arras-ui`), HTTP-only | `ui/` (its own `package.json`); built and carried in the wheel (below) |
| One mount for a host: the built page, UMF's schema browser and the three surfaces; and the `@documentdrivendx/arras-ui` npm tarball | `ui/` (`arras.ui`) |
| MCP stdio server and its configuration: `python -m arras.mcp` | `mcp/` (`config/` holds the committed files, `.env.example` the environment keys) |
| Telemetry: events and spans to the host's logger and tracer provider | `telemetry.py` (`arras[otel]` for spans) |
| Dev host: console, operator surface and the built UI at one origin: `python -m arras.devhost` | `devhost.py` (`uv run --extra devhost`) |

## Mounting the interface in a host

The wheel carries the UI two ways (ADR-027), built from `ui/` at release, so the UI's version is the
library's. A host that pins the wheel pins both.

**Mount one ASGI app.** The host authenticates and maps its identity to a `Principal`; Arras never does.

```python
from arras import operate, ui

app.mount(
    "/ontology",
    ui.create_app(
        arras,
        base_path="/ontology",
        principal_for_request=lambda request: (
            ...
        ),  # the host's identity -> Principal, or None (401)
        authorize_operator=operate.operators_in_groups("admins", "builders"),
    ),
)
```

It serves the page (`/ontology/`), its assets, UMF's schema browser (`/umf-explorer/`) and the three
surfaces the page calls: `/api/console` (CONTRACT-006), `/api/operate` (CONTRACT-009) and `/api/schema`
(CONTRACT-011; mounted only with `authorize_operator`). The page and assets are public files under a strict
Content-Security-Policy (`ui.PAGE_CSP`); every read and write is answered by a surface, which refuses a
viewer with no principal. `/ontology` redirects to `/ontology/`, because the page's URLs are relative so
that any prefix works. Behind a proxy that rewrites `Host`, pass `public_origin`.

**Or bundle the components into the host's own React app.** The package is `@documentdrivendx/arras-ui`. The
wheel carries it as a tarball, so the version follows the Python pin and nothing else is needed:

```bash
npm install "$(python -m arras.ui npm-package)"     # or `--copy vendor/` to keep a copy in the repo
```

```tsx
import { ArrasApp } from "@documentdrivendx/arras-ui/shell";   // also "@documentdrivendx/arras-ui" (the console) and ".../browser"
import "@documentdrivendx/arras-ui/styles.css";
<ArrasApp operateBase="/ontology/api/operate" consoleBase="/ontology/api/console"
            schemaBase="/ontology/api/schema" explorerBase="/ontology/umf-explorer"
            getHeaders={...} onUnauthorized={...} />
```

The stylesheet is scoped to the components' own root element, so it can sit in a host's page. Every
entry component renders inside one. The tokens, the reset, the utilities and the classes are all under it,
and nothing is set on `html`, `body` or `:root`, so a host's own `--accent` or `button` rule is neither
changed nor read. The root also carries what a page would give `body`: `100%` height, the font and the
background. Colour scheme: the host's. The components take no
`appearance` prop and install no `ThemeProvider`; the root follows the host's theme tokens and the nearest
ancestor's `data-appearance="light" | "dark"` (what the design system's `ThemeProvider` sets) or inline
`color-scheme` (a provider given only its tokens), then the system's
`prefers-color-scheme`, and re-themes when the host switches at run time. One caveat: the library's rules are in cascade layers (Tailwind's),
as a host's usually are; a host's *unlayered* element rule such as `button { color: red }` outranks them
inside the root.

React, React DOM and (optionally) `@databricks/appkit-ui` are peers; the host still mounts `ui.create_app`
for the three surfaces and `/umf-explorer` (the component's iframe loads from `explorerBase`, so the
host's policy must allow `frame-src 'self'` and `script-src 'self'` there). In a source checkout, build
both with `npm run build:wheel` in `ui/`.

`python -m arras.devhost` serves the console on the loopback address only, over fake data: pick a
role (viewer, editor, schema author, auditor, maintainer) and any name, take a backend down, feed the
replica, run one Weft statement at a time against a chosen module at either consistency level (paging
is written in the statement), invoke actions, and import and export UMF schemas. `ARRAS_DEV_SANDBOX=1 python -m arras.mcp` serves the same sandbox over MCP.

The sandbox has a `catalog` module and five people, named in the `x-arras-user` header and the toolbar: `alice` (read, write, journal and schema on `catalog`; group `builders`), `bob` (read, write and journal; group `builders`), `carol` (read only), `dave` (no access to `catalog`) and `root` (the administrator, group `admins`, who registers modules and is refused every user operation). The operator surface is offered to the groups `admins` and `builders`, so `alice`, `bob` and `root` are operators and `carol` and `dave` are not. By default the dev host also seeds a demonstration catalog of 12 use cases across the work areas `data`, `operations` and `finance`, and 10 solutions (`--no-demo` leaves it out). `--module` and `--seed` replace it with a module of your own, such as `examples/catalog` (see its README) or `examples/pizza`.

With `--truss` the dev host serves a real Truss instead of the fakes: the same people, but their roles and grants are database roles, `expire` is `VALID UNTIL`, `grant` and `revoke` are role membership and `outage` is a real unreachable (or, on a throwaway, refused) connection. A control with no meaning on Truss (`feed`, `search`) answers 400. It needs the `truss` extra.

By default Truss mode attaches to a persistent PostgreSQL 18.6 server and keeps its state across restarts. The connection URL is `--truss-url`, else `ARRAS_TRUSS_DEV_URL` in the environment, else the same variable in `~/.arras/truss-dev.env` (keep it there, mode 600, so the password is not on a command line). It names a role that owns an empty database, has `CREATEROLE` and is not a superuser (Truss's supported installation path), and whose password `pg_hba` asks for (a connection that skips the password is refused):

```bash
uv run --extra devhost --extra truss python -m arras.devhost --truss
```

Starting is safe to repeat. Truss is installed or verified, the modules are registered again (an unchanged document stays unchanged), the people's roles are made when absent and get new token passwords, the grants are given again, and the demo (or `--seed`) runs only when no registered module holds an entity yet (one row is asked of each entity type). Seeding is decided across every registered module, so a database that already holds entities from one module is not seeded for a module added later; `--truss-reset` is the way to reseed. Closing the host drops nothing and stops nothing. The people are database roles the dev host names with its own fixed prefix (one per person, and a reader and a writer role per module): role names are cluster-wide, so a developer's own role named `alice` is never touched. The startup prints the host, port, database and role to attach `psql` with and where the password is, never the password. `--truss-reset` drops what the dev host made in that database (Truss's schema, its owner and registrar roles, and the person and module roles the installing role administers) and starts clean; it never drops a role or a database it did not create. The `access_denied` outage (a revoked `CONNECT`) is for the throwaway only, because it could lock the installing role out of its own database.

With no URL, Truss mode is a throwaway local PostgreSQL started for the run and removed at exit; it needs the `truss-test` group as well, and installing, registering and seeding the default catalog takes a few seconds:

```bash
uv run --extra devhost --extra truss --group truss-test python -m arras.devhost --truss
```

The console browses every type of the three samples on Truss: a list read is about 0.3 s and a write about 0.4 s against a persistent PostgreSQL, and a start that finds the database seeded serves in about 1.3 s.

The MCP process reads three layers of configuration, highest first: ops-injected values (environment
variables, and an optional ops file named by `ARRAS_OPS_FILE`: backend endpoints and the token, never
committed), `config/<env>.toml` (`ARRAS_ENV` names it; developer-owned, such as where each module
lives) and `config/default.toml`. `ARRAS_CONFIG_DIR` moves the directory. Each key has one owner, and a
committed file that carries an endpoint or a token is refused, naming the file and key. See
`config/example.toml` for every table. A backend's endpoint is a PostgreSQL URI with no credential (`postgresql://host:5432/db`); a remote host is always verified (`sslmode=verify-full`, the default and the only mode accepted, against the system trust store or the PEM file named by `sslrootcert=/absolute/path`), and a local socket or loopback host may use any `sslmode`; the person's token is the password of the role the token's user claim names, so a Truss backend needs the `truss` extra. The process clears the libpq environment (`PG*`) before it connects. The process stops cleanly on SIGTERM or SIGINT.

To work on a schema of your own, give the dev host your module and, optionally, steps that seed it:

```bash
uv run --extra devhost python -m arras.devhost --module examples/catalog/catalog.umf.json --seed examples/catalog/seed.json
```

The Schema section draws the module's entity types and relationships and lists each type's fields,
its relationships and the actions that write to it. A module the registry refuses is printed with
every violation and nothing is served, so edit the file and start it again. `examples/catalog/` is
a small catalog: use cases, solutions that say how they are delivered, products and how far
each covers a use case. Its data is invented; see its README.
The catalog registers on Truss 0.0.45 and serves with `--truss --module examples/catalog/catalog.umf.json`: Truss prepares it,
and the 92 steps of `examples/catalog/seed.json` run against it as the people in atomic batches of up to 32 steps of one
action. Registration and preparation take the same path, and the evidence of a document is under 2.4 KB
(`truss-registration-evidence-spec.md`).

Checks beyond the unit tests: `tests/test_modules.py` holds the library's module rules,
`tests/test_properties.py` checks the contracts' rules against a model over random sequences, and
`tests/test_telemetry.py` and `tests/test_config.py` hold the telemetry and configuration contracts.

## The Truss adapter

`arras.adapters.truss.create_backend(name, source, installing=None, *, module_access=None)` builds the Truss backend (reader and provider). It is built, with its install-or-verify `migrate()`, `configure_access()` (a module's reader, writer and, optionally, auditor roles) and `install_roles()`, and a credential-free endpoint handle for the MCP process. Truss 0.0.45 is pinned (`truss-toolkit[native,query]==0.0.45` under the `truss` extra); it is experimental, and the adapter is the only place that imports it.

What the host provides:

- A per-person `ConnectionSource` (each call runs as the person, never a service identity) and, for `migrate` and `configure_access`, a separate trusted installing connection and the module roles.
- Truss 0.0.45 qualifies PostgreSQL 18.6 with psycopg 3.3.6 (binary, libpq 18.6) on Linux x86_64 and macOS arm64, and declares Python 3.11 or later; the runtime set (truss, psycopg-binary 3.3.6 with cp311 to cp315 wheels, weft as cp39-abi3) covers Python 3.11 and later; the local test PostgreSQL (`pgserver-pg18`, test group only) has wheels for 3.11 to 3.13. Installation needs `CREATEROLE` and database `CREATE` with grant option (or ownership) and a `statement_timeout` of 1 to 60,000 ms.
- No Bun, Node or other process on the machine: Truss 0.0.45 prepares a module in an embedded V8 (about 0.4 s of preparation per registration, `register` and the `validate_register` dry run of a changed document) and derives a key in PostgreSQL. A host can register as a deploy-time job and keep the registrar's connection out of the process that serves.
- The pinned Truss and Weft wheels. They are on no package index, and a release carries only the base dependencies, so the host vendors them from `tools/find-links/index.html` (digests from each release's `SHA256SUMS`).

Declared limits, all Truss's and answered as `Unsupported` or a documented limit by the adapter: text search is `Unsupported`; the audit reads (`changes`, `loads`) are served from Truss's audit pages under its own audit grant, and state their limits (observed time, no key or version in an op, load discovery: CONTRACT-004, ask R20); a type over 10,000 rows is not queryable; an import is sent in calls of 128 records, each its own transaction, and is not atomic; and nine corpus cases end at a documented limit (R16.5, R17.2 and R18.3 in `docs/helix/02-design/truss-requirements.md`); an export of a type over 10,000 rows, or of an entity with over 100 related keys on a relationship, is `Unsupported` (R17.2, R17.5).

```bash
uv run --extra truss --group truss-test pytest -m truss   # about 30 minutes; CI's job cap is 60
```

CI runs it as the `truss` job, and the release workflow runs it before it publishes, both with `ARRAS_REQUIRE_TRUSS=1` (a harness that cannot run is a failure, not a skip).

Not built: the Ashlar adapter and the feed from Truss to it. A new adapter passes `arras.conformance.run_corpus` with its own `Harness` (`tests/truss_harness.py` is the Truss one). The host registers backends with `Arras.start({"<name>": backend, …}, placement=…)`.

## License

First-party software is dual-licensed under MIT OR Apache-2.0, at your option.
See [LICENSE.md](LICENSE.md). Third-party materials retain their original notices.
