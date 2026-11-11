# Arras

Arras is an open-source interface to an ontology. Types and actions are defined in UMF; every read states its freshness; a backend contract lets one module span a record store and its replicas. It is a Python library that a host application embeds, and it ships a React operator console and Graph Browser.

- **UMF types and actions.** A module is a UMF document: entity types, relationships and the actions that change them, with typed inputs, preconditions and effects. UMF is the DocumentDrivenDX metamodel.
- **Reads that state their freshness.** Every answer names the backend that served it, its position and the consistency level (`latest` or `bulk`). Statements are Weft SQL, compiled by the serving backend.
- **A backend contract.** Each backend is a reader (serves graph reads), a provider (applies actions) or both. Arras ships a Truss adapter (authoritative, on PostgreSQL), an in-memory adapter for tests and the sandbox, and an experimental Ashlar adapter (a replica on Unity Catalog; see Status).
- **Access is the backends' own.** Every call runs as the person who made it, with that person's token. Arras keeps no service identity and no cache of data or decisions.
- **Three surfaces.** A read-only GraphQL console, an operator surface for validating and invoking declared actions and reading the audit trail, and an MCP stdio server for agents.

Arras is embedded by host apps that supply their own identity and configuration. The host authenticates people and maps them to a principal; Arras never does.

## Status

Beta (`0.x`).

- **Tested in CI** (Linux, Python 3.11): the in-memory backends, the library, the console, operator and
  schema surfaces, the MCP server, the UI, and the Truss adapter against a real PostgreSQL 18.6 (nightly and
  on release).
- **Experimental, not CI-tested:** the Ashlar adapter (`arras.adapters.ashlar`). It is incomplete, it has no
  host factory, and nothing in CI runs it against Unity Catalog. The feed from Truss to Ashlar is not built.
  Do not rely on it.

The backend contract and the packaged conformance corpus (`arras.conformance.run_corpus`) are what a new
adapter is held to. Release history is in [CHANGELOG.md](CHANGELOG.md).

## Install

```bash
pip install arras
```

Python 3.11 or later; CI tests 3.11. The base install needs only `graphql-core`. Extras: `arras[devhost]`
(the development host), `arras[truss]` (the Truss adapter), `arras[umf]` (the official UMF reader) and
`arras[otel]` (OpenTelemetry spans). The wheel carries the built UI; a git or source install does not, so use
the release wheel for the mountable page.

## Quickstart

CI runs these steps against every built wheel (`scripts/smoke_installed.py`).

```bash
python -m venv .venv && . .venv/bin/activate
pip install "arras[devhost]"
arras --version
arras doctor                 # prints a JSON report with "ok": true
arras devhost --port 8765    # open http://127.0.0.1:8765: the console over fake data, on loopback only
```

Serve one of the examples with its seed:

```bash
arras devhost --module examples/catalog/catalog.umf.json --seed examples/catalog/seed.json
```

(The `examples/` folders are in the repository, not the wheel.) With the Truss adapter:

```bash
pip install "arras[truss,umf]"
```

The `devhost --truss` mode needs a local PostgreSQL 18.6 from the `pgserver-pg18` package, which is not yet
on PyPI; see "Working on it".

## Examples

| Example | What it is |
|---------|------------|
| `examples/pizza/` | The Protege tutorial ontology: pizzas, toppings, bases, countries of origin |
| `examples/northwind/` | A slice of the Northwind trading-company sample database |
| `examples/catalog/` | A small software-tools catalog: use cases, solutions, products and how far each covers a use case |

Each folder has a README, a UMF document (`*.umf.json`) and a seed of action steps. The data is invented, apart from the Northwind rows, which come from the public sample database.

## Working on it

Python 3.11 with [`uv`](https://docs.astral.sh/uv/); everything runs from the repository root.

```bash
uv sync --extra truss --extra umf --extra devhost
uv run pytest -q                                    # the default suite (excludes `truss` and `slow`)
uv run ruff check . && uv run ruff format --check . && uv run pyright
cd ui && npm ci && npm test                         # the UI unit tests
```

- `pytest -m truss` runs the real-Truss suite on PostgreSQL 18.6; it needs `uv sync --group truss-test`
  (`pgserver-pg18`, resolved from `tools/find-links/index.html` because it is not on PyPI yet).
- The Weft parser checks (`tests/test_weft_parser.py` and others) skip when Weft is not installed; CI installs
  it through the `truss` extra and sets `ARRAS_REQUIRE_WEFT=1`.
- CI (`.github/workflows/ci.yml`) is Linux only. Pull requests run the Python and UI tests; a nightly job adds
  the slow tests, the real-Truss suite and the browser tests. A version tag runs `release.yml`.

What exists, against the contracts in `docs/helix/02-design/contracts/`:

| Part | Where |
|------|-------|
| Interface: `Arras`, sessions, router, freshness (statements are Weft SQL, compiled by the serving backend) | `core.py`, `routing.py`, `actions.py` |
| Registry: UMF reader, compatibility rules | `umf.py`, `compat.py`, `model.py` |
| Backend contract and the conformance corpus | `backend.py`, `conformance/` |
| Read-only GraphQL console (ASGI) | `console/`, `gqlschema.py` |
| Operator surface (ASGI): validate and invoke declared actions, read the audit trail, schema administration | `operate/` |
| Operator Console and Graph Browser UI (React), built and carried in the wheel and as an npm tarball | `ui/` |
| MCP stdio server and its configuration | `mcp/`, `config/` |
| Telemetry: events and spans to the host's logger and tracer provider | `telemetry.py` |
| Dev host: console, operator surface and the built UI at one origin | `devhost.py` |
| Truss adapter (authoritative, PostgreSQL) | `adapters/truss/` |
| Ashlar adapter (experimental, not CI-tested) | `adapters/ashlar/` |

## Compatibility

The reviewed host-facing import catalog is the packaged `arras/public-api.json` resource: the Python
imports, the packed `@documentdrivendx/arras-ui` exports, configuration and command names, CSS tokens and
resource versions. Arras is 0.x: a breaking Python or UI public API change increments the minor version; a
patch keeps the declared public surface.

## Mounting the interface in a host

### Serve only the API and bundle the components

The host can embed the core without the prebuilt UI. Mount the independent ASGI
bindings using the same `Arras` instance and the host's principal mapping:

```python
from arras import console, operate

app.mount(
    "/ontology/console",
    console.create_app(
        arras,
        base_path="/ontology/console",
        principal_for_request=principal_for_request,
    ),
)
app.mount(
    "/ontology/operate",
    operate.create_app(
        arras,
        base_path="/ontology/operate",
        principal_for_request=principal_for_request,
        authorize_operator=operate.operators_in_groups("operators"),
    ),
)
# Optional: only mount where schema administration is offered.
app.mount(
    "/ontology/schema",
    operate.create_schema_app(
        arras,
        base_path="/ontology/schema",
        principal_for_request=principal_for_request,
        authorize_operator=operate.operators_in_groups("schema-authors"),
        authorize_schema=authorize_schema,
    ),
)
```

A host owns `Arras.start`/`close`, authentication, connections, grants, API prefixes
and proxy/origin policy. Add `authorize_action` for per-action approval. The core
imports no HTTP handler or UI; its registration checks still require GraphQL
servable types. No Node runtime is needed by these bindings. They can run without
loading `arras.ui` or its static assets.

In the host UI, install the matching `@documentdrivendx/arras-ui` release and import
its compiled components and `styles.css`. `/browser` exports `GraphBrowser` and
`/shell` exports `ArrasApp`; the root exports the console, individual areas,
`ArrasProvider` and the replaceable design-system provider. Supply the API bases,
a person/tenant/session `identity`, host-controlled routes and `pageEffects={false}`.
See the [component integration guide](ui/README.md#embed-in-a-host) for cache,
CSS, routing, visibility and UMF runtime-asset ownership. Public exports are the
supported extension points; internal imports remain private. Python and npm are
separate installable artifacts with one release version, not separate core/API
Python distributions.


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
Starlette and FastAPI keep the mount prefix in the request path and name it in `root_path`; `base_path="/ontology"`
and `base_path=""` both serve the same URLs under `Mount("/ontology", ...)`. The `console`, `operate` and schema
apps resolve their paths the same way.

`authorize_schema(principal, module) -> bool` optionally narrows schema validation and registration
through this same mount. Pass it as `ui.create_app(..., authorize_schema=...)`; it receives the
viewer and parsed module name, and a true result still requires the backend's schema grant.
The schema surface remains absent without `authorize_operator`, even if this callback is supplied.

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

The component package's root also exports `DesignSystemProvider`, `useDesignSystem`,
`defaultDesignSystem`, `ROLE_TOKENS` and the widget prop types. Import them from
`@documentdrivendx/arras-ui` and wrap the components with
`<DesignSystemProvider designSystem={{ Button: HostButton }}>...</DesignSystemProvider>`.
A partial design system inherits the remaining widgets from its outer provider or the built-in
default. Keep one host React/ReactDOM peer pair; widget replacements must preserve their props
and accessibility behavior. See [the UI guide](ui/README.md#theme-and-design-system) for the contract.
The current source build's packed exports are locally verified; registry publication is separate.

## The Truss adapter

`arras.adapters.truss.create_backend(name, source, installing=None, *, module_access=None, tolerated_grantees=())`
builds the Truss backend (reader and provider), with an install-or-verify `migrate()` and `configure_access()`.
The host provides a per-person `ConnectionSource` (each call runs as the person, never a service identity) and,
for `migrate` and `configure_access`, a separate trusted installing connection. The adapter is built against
Truss on PostgreSQL 18.6; the extra pins the Truss release it is tested with. Truss's declared limits are
answered as `Unsupported` or a documented limit by the adapter (text search is `Unsupported`; the audit reads
state their limits).

A new adapter passes `arras.conformance.run_corpus` with its own `Harness` (`tests/truss_harness.py` is the
Truss one). The host registers backends with `Arras.start({"<name>": backend, ...}, placement=...)`.

## Documentation

[CHANGELOG](CHANGELOG.md), [PRD](docs/helix/01-frame/prd.md),
[architecture](docs/helix/02-design/architecture.md), the ADRs in `docs/helix/02-design/adr/`, the contracts
in `docs/helix/02-design/contracts/` and the [glossary](docs/helix/glossary.md). The UI guide is
[ui/README.md](ui/README.md).

## License

First-party software is dual-licensed under MIT OR Apache-2.0, at your option.
See [LICENSE.md](LICENSE.md). Third-party materials retain their original notices.
