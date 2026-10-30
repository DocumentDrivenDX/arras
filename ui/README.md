# arras-ui

Arras's interfaces (ADR-021, ADR-025): the Operator Console (FEAT-010), the Graph Browser (FEAT-011) and
the shell that offers both, as React component libraries and a standalone host. See "Graph Browser and
shell" below for the second and third; the rest of this file is mostly the console.

The Operator Console (FEAT-010, ADR-021): a React component library and a standalone host. It browses a
module's schema, reads data with its freshness, runs read-only queries as a grid, changes data only by validating and invoking the module's
declared actions, and (when the backend serves it) reads who changed what.

The package stack is React 19, TypeScript 6, Vite 8, Tailwind 4, TanStack Query 5, Vitest 5. The UI draws
its buttons, fields, dropdowns and notices through a design-system seam with a built-in default and no
design-system package to install; a host may supply its own (see "Theme and design system").

## Boundary

The console reaches Arras over HTTP only: GraphQL reads (`/api/console`, CONTRACT-006), JSON actions and
audit and read-only queries (`/api/operate`, CONTRACT-009) and, when the host mounts it, schema import (`/api/schema`, CONTRACT-011).
It holds no credential or token, stores nothing in the browser (a file you choose, and a plan, live in memory
only; so is the query history), and puts no input, person, query or document in a URL (audit filters, queries and documents travel in a POST body); the only values in its fragment are the module, area, type, an entity key, an action name, a key-column filter value, a change group's opaque id, a sort column and direction, two instants and the view words `umf` and `loads` (see "Routes").
A host supplies the viewer's identity (`getHeaders`, `onUnauthorized`); the only writes are invoking a declared
action and, as the viewer, registering a UMF document through the separate schema surface. It imports nothing
from the Python package and checks `GET /version` against the supported HTTP contract versions at load.

## Run

```sh
# from the repository root: the dev host (sandbox fakes, sandbox people, loopback only)
uv run --extra devhost python -m arras.devhost            # http://127.0.0.1:8000
# in ui/: the Vite dev server, proxying /api to 127.0.0.1:8000
npm ci && npm run dev                                        # http://127.0.0.1:5173
```

The dev host also serves the built UI at one origin: `npm run build`, then
`uv run --extra devhost python -m arras.devhost --ui ui/dist`.

**The sandbox toolbar** (top right; `src/dev/`, the standalone host only, never exported from `src/index.ts`; a
test asserts the library's exports do not include it). It reads `GET /api/people` (`{people, roles, default}`)
and has three parts:

- *Person*: one of the sandbox's own people, sent as `x-arras-user`, a header only the dev host reads: alice and
  bob (read, write, journal on catalog; alice also holds `schema`), root (the administrator: it registers modules
  and is refused every user operation, so the console shows it "No access"), carol (read only), dave (no access).
  Or *Custom name and role...*: a made-up name and a role from the server's list (none, viewer, editor, schema
  author, auditor, maintainer), sent as `x-arras-user` and `x-arras-role`. The name is checked in the browser
  with the server's rule (`^[a-z][a-z0-9_-]{0,31}$`, and not one of the fixed people, `root` included) before
  anything is sent; the server mints the person and its grants, and the backends decide what that person may do.
  Each identity remounts the console with a fresh query cache. The "dev host: no sign-in" badge stays.
- *Sandbox* (a disclosure): per backend an *Outage* and a *Mend* button, an *Expire token* and *Restore token*
  for the person being viewed, and *Run the replica's feed*. They call `POST /api/dev/control`
  (`{op: "outage", backend, reason: "unreachable" | null}`, `{op: "expire"|"restore", user}`, `{op: "feed"}`) and
  then the console re-reads, so it shows the state. The backend names are the ones the registry's status reports;
  when the viewed person cannot read it (`root`, role `none`) the last names seen, else the sandbox's documented
  `memory` and `memory_replica`, are used.

`POST /api/dev/control` also breaks and mends the sandbox for tests (and has a `register` op used by the
Playwright tests).

## The Query tab

The Query tab (beside Model, Graph, Entities, Actions and Changes; `#/<module>/query`) runs one read-only Weft SQL
statement (CONTRACT-001) over the module chosen in the console with `POST /api/operate/query` (`{module, sql,
consistency, limit}`) and shows the answer as a grid (OPR-16, OPR-17; US-077, US-078). Arras does not parse the
statement; the serving backend refuses one that writes, and the grid has no editing.

- **Editor.** A monospace textarea (resizable, spellcheck off), a `LATEST` or `BULK` choice, and Run (a button,
  or Ctrl or Cmd with Enter). A counter shows the characters against the surface's **4,000-character bound**; over
  it, Run is disabled with a message and nothing is sent (the server answers 400 for more, and also refuses over
  16 KiB of bytes). "What can I query?" lists the module's types with their columns (required, single-valued
  scalars, which a filter may use), its optional properties (selected, not filtered on), and relationships; choosing a
  type puts `SELECT … FROM "module"."Type" x ORDER BY x."<key>" LIMIT <page + 1>` in the editor (replacing the text)
  without running it: every name a Weft quoted identifier (`weftName`, so a name Weft reserves reads as the name), and
  one row over the page so that `truncated` says when the type holds more.
- **Starters.** Every Model type card has *Entities*, *Graph*, *Actions* (when an action takes or writes the type) and
  *Query* links (accessible names such as "Query Product"; each shows only when its callback prop, `onOpenData`,
  `onShowGraph`, `onOpenActions(type, firstAction?)`, `onOpenQuery(type)`, is given to `SchemaBrowser`). *Query* opens this tab with
  `starter={{ type, id }}` on `QueryArea`: the statement `SELECT u."<key>", u."<first four declared properties>" FROM
  "module"."Type" u ORDER BY u."<key>" LIMIT 50` (`src/lib/starterSql.ts`; only names the registry admits, each a Weft
  quoted identifier) goes in the editor and **is not run**. An empty draft is replaced. A draft with text is never
  overwritten silently: the area keeps it and offers "Replace the draft with the starter" or "Keep my draft". Each
  starter is handled once per session, so coming back to the tab does not apply it again.
- **Grid.** (A table, not an interactive grid: rows take focus, cells do not.) One column per `columns[]` in order, sticky header, the row count, `truncated`, the freshness
  (backend, position, time, consistency; `BULK` names the replica) and the revision. A `null` is shown in italics as
  `null`, apart from empty text (`""`); a relationship column (`RELATED_KEYS`) is its keys joined by commas; integers and
  decimals are right-aligned; long text is clipped, with the value in the cell's title (at most 500 characters) and shown in full while
  its row has focus; a cell shows at most 10,000 characters, then an ellipsis and "[truncated in view]"; rows take focus (Up, Down, Home, End). There is no next-page
  control: a run returns at most the limit (100) and says when it is `truncated`; the next page is a keyset
  predicate (`WHERE x.<key> > :last`) the operator writes in the statement and runs. `QueryArea` takes a
  `pageSize` (1 to 100, default 100) for tests. **Key links.** When the statement that ran reads exactly one type of
  the viewed module (`FROM <module>.<Type>`, quoted or bare; no JOIN, comma list, set operation or second FROM) and
  the result has the type's declared key as a scalar column, each non-empty cell of that column gets an "Open Type key"
  button after its text that calls `onOpenEntity(type, key)` (the console shows the entity in Graph). A statement
  the console cannot resolve this way (`src/lib/queryKeys.ts`, which does not parse SQL) leaves every cell plain
  text. Everything is rendered as text.
- **Errors** are shown as the library states them, never as an empty grid: 400 lists every violation (path, code,
  message), 404 is "Not found: No such module or type, or you cannot read it" (the same for an unknown and an unreadable module), 501 names the
  construct and the supported shapes, 401 asks the host to sign in again (`onUnauthorized`; the history is kept),
  403 gives the reason, 409 says the answer is not yet current, 503 names the backend. A new run clears the grid
  and the error of the previous one.
- **Accessibility.** Run and Run again use `aria-disabled`, not `disabled`, while a request runs, so focus is never dropped; one polite live region says "Running…" and "M rows". History entries carry `data-dd-privacy="mask"` and Run again's accessible name is generic.
- **History** (newest first, at most 50, the same module, text and consistency twice in a row listed once with the latest
  time) shows each entry's module, consistency, time and row count or the failure's kind and status (not its body).
  Choosing an entry puts its module, text and consistency in the editor and runs nothing; "Run again" runs it now as the
  person now viewed, over the entry's own module (the editor shows the module it reads); "Clear history" empties it. **It is held in memory only**, in the console's shell above the
  tabs (so it survives moving between them, with the editor's draft, consistency and the shell's `QuerySessionProvider`) and is gone on reload and whenever the console's **`identity`** prop changes (a string that changes with the person
  viewed; the dev host passes its toolbar's identity). The history and draft are keyed on it. If `identity` is omitted
  the history lasts the life of the console, so **a host that switches person without mounting the console afresh
  must pass `identity`** (or remount). A host that embeds `QueryArea` alone gets a history of the area's own. Nothing is written to `localStorage`, `sessionStorage`, IndexedDB or a cookie, and the
  route is `#/<module>/query` and no more. **The query text travels only in the POST body**: never in a URL, a log
  line, an error message the console builds, or browser storage.

## Scripts

| Command | What it does |
|---------|--------------|
| `npm run dev` | Vite dev server with the `/api` proxy |
| `npm run build` | Production build of the standalone host into `dist/` (no Python needed) |
| `npm run build:embed` | The page `arras.ui` serves (`embed.html`) into `../src/arras/ui/static/` |
| `npm run build:lib` | The component library into `dist-lib/`: ESM entries for `arras-ui`, `arras-ui/browser` and `arras-ui/shell`, `styles.css`, and declarations |
| `npm run build:wheel` | `build:embed`, `build:lib`, the scoped-CSS check, then `pack:wheel`: the npm tarball the Python wheel carries (ADR-027) |
| `npm run check:css -- <file>...` | Fails if a built stylesheet has a selector outside `.arras-root` (run on `dist-lib/styles.css`) |
| `npm run check:externals` | Fails if the library build imports a package its packed manifest does not declare |
| `npm run check:public-manifest` | Compares the explicit Python package catalog with packed ESM/type exports, export targets and peer metadata; drift and omission controls fail |
| `npm run check:umf` | UMF's schema browser: the exact pin, the lockfile and the installed package (see "UMF source") |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run check` | Biome: lint, format check and import order (the CI gate) |
| `npm run format` | Biome: apply the formatting |
| `npm run lint` | Biome: lint only |
| `npm test` | The unit tier: Vitest with a fetch double (`src/test/fake.ts`); fast, no Python |
| `npm run test:packed-browser` | Build a separate host from the packed public package and verify session/page isolation in Chromium against a real local API |
| `npm run test:integration` | The integration tier: the real components and client against the real dev host (needs `uv` and a prior `npm run build`) |
| `npm run test:all` | Both tiers in one run |
| `npm run coverage` | Both tiers with merged V8 coverage (`coverage/`) |
| `npm run e2e` | Playwright whole-stack tests, four projects in order (one worker, no `dependencies` chain, so a failing project does not skip the next) on dev hosts (port 8123, and 8124 for `schema-admin.spec.ts`, which registers a revision of `catalog`; both serve `ui/dist`): `chromium` (every spec except those of the other projects: the console, the shell, the cross-mode links and Explore's New, Retire and Actions), `schema-admin`, `browser` (the Graph Browser's `browser.spec.ts`, `browse-history.spec.ts` and `routes.spec.ts`) and `visual` (screenshots). Run `npm run build` and `npx playwright install chromium` first |
| `npm run e2e:visual` | The screenshots alone, against the baselines in `e2e/__screenshots__` (0.5% pixel threshold) |
| `npm run e2e:visual:update` | Rewrite the baselines; review each changed PNG against the mockup in `docs/helix/02-design/graph-browser-mockup/` before committing |

### Packed public API catalog

`../src/arras/public-api.json` is the reviewed schema-versioned catalog for Python and the packed UI
boundary. `npm run check:public-manifest` runs during `npm run build:wheel`: it compares every advertised
UI runtime/type symbol and export target with the packed declarations and package metadata, including
React peers and optional AppKit metadata. The check is a drift test; it does not regenerate the catalog
or add package exports. `tests/test_public_api_manifest.py` checks the corresponding Python boundary.

### Downstream acceptance suite

The npm package exposes a portable acceptance testkit for host-owned themes and embedded deployments.
Install the exact `@documentdrivendx/arras-ui` cohort alongside the optional `@playwright/test` 1.63.0
and `@axe-core/playwright` 4.13.0 peers, then import the factory and browser host from the public
subpaths:

```ts
import { createAcceptanceConfig, type AcceptanceConfigOptions } from "@documentdrivendx/arras-ui/testkit";

const options: AcceptanceConfigOptions = {
  baseURL: "http://127.0.0.1:8766",
  schemaBaseURL: "http://127.0.0.1:8777",
  outputDir: "./test-results/arras-acceptance",
  themeId: "neutral-theme",
  expectedBrand: { name: "Neutral Host", title: "Neutral Host Console", logo: "theme" },
  expectedSurface: { light: "rgb(248, 250, 252)", dark: "rgb(2, 6, 23)" },
  // Required on Darwin; points to reviewed, theme-specific snapshots.
  baselineDir: "./tests/arras-baselines/neutral-theme",
};

export default createAcceptanceConfig(options);
```

`createAcceptanceConfig` belongs in the consumer's Node-side `playwright.config.ts`. The host component is
imported separately by the consumer's browser entry and wrapped in its own theme provider; the downstream
example's [host entry](downstream/host.tsx) shows that split. Build that host to a static directory (the
example emits `dist/`) before starting the fixture servers:

```tsx
// Browser entry, compiled into the host's static dist directory.
import { createRoot } from "react-dom/client";
import { AcceptanceHost } from "@documentdrivendx/arras-ui/testkit/host";
import { NeutralThemeProvider } from "@arras-fixtures/neutral-theme";
import "@documentdrivendx/arras-ui/styles.css";
import "@arras-fixtures/neutral-theme/theme.css";

createRoot(document.getElementById("root")!).render(
  <NeutralThemeProvider><AcceptanceHost /></NeutralThemeProvider>,
);
```

`AcceptanceHost` embeds the UMF schema browser, so the compiled host must also serve the installed
`@documentdrivendx/umf-schema-browser` package's `assets/` directory byte-for-byte at `/umf-explorer/`.
The downstream qualification fixture's [Vite config](downstream/vite.config.ts) copies that installed
dependency into the host output and verifies it against the exact dependency pin and wheel-carried assets;
it never copies browser files from the Arras source checkout.

```sh
# From the external host project, using the environment with the selected wheel and devhost extra installed.
python -m arras.devhost --ui ./dist --port 8766
# In a second terminal, start an independent disposable sandbox for schema registration tests.
python -m arras.devhost --ui ./dist --port 8777
```

Both standard dev hosts serve the same compiled `AcceptanceHost` page and provide disposable in-memory
fixture data; the second host is isolated so schema-admin tests cannot affect the main host's state. Point
`baseURL` at port 8766 and `schemaBaseURL` at port 8777. These are acceptance fixtures, not a production
backend or a consumer module endpoint.

Run it with the ordinary Playwright CLI from the consumer project, for example
`npx playwright test --config playwright.config.ts`. The factory verifies the package-carried resource
inventory and every file digest, then materializes that verified suite in a temporary directory under
the consumer project so Node resolves its installed peers and module type normally. A global teardown
removes the materialized copy. It never falls back to an Arras checkout. The canonical suite contains
17 specs and requires all three nonvisual projects (`chromium`, `schema-admin`, `browser`); the `visual`
project runs on Darwin only and compares theme-specific snapshots. Darwin callers must supply
`baselineDir`. Linux reports visual comparison as skipped while still running every nonvisual project.
Snapshot updates are disabled by the factory. Create or change baselines only through an explicit,
reviewed update workflow; do not reuse the default-theme snapshots for a different theme.

`baseURL` and `schemaBaseURL` must be distinct credential-free root HTTP(S) origins. `outputDir` is
consumer-owned and should be unique for simultaneous runs. `themeId` defaults to `default`; `expectedBrand` defaults to `{ name: "Arras" }`, and
`expectedSurface` defaults to the built-in light/dark RGB colors. The testkit has no browser-download
step: provision Chromium using the consumer's normal Playwright setup. The `AcceptanceHost` browser
entry is intended for a consumer-owned compiled host; the suite itself exercises its public HTTP
surface and does not depend on private Arras source modules.

`arras-ui-qualify --host-build` (checked by the package's `support/QUALIFICATION.md`) is a separate, narrower
check with its own fixture contract: a first `.arras-root` with six widgets marked `data-theme-*`, a region labelled
`Downstream widget controls` with the four controls in tab order, the public app drawn through the host's widgets, and
no gradient, image or opacity behind the focus rings. The runner names the first requirement a fixture misses; the
contract is the section "Host-build fixture contract" of that file, and `WidgetControls` from
`@documentdrivendx/arras-ui/testkit/host` renders the region from the design system in context.

### Visual baselines

`e2e/visual.spec.ts` screenshots every screen (light and dark, 1280 and 390 wide) and compares each with a
baseline in `e2e/__screenshots__/<screen>-visual-darwin.png` at a 0.5% pixel threshold. **The baselines are
macOS only**: the design is reviewed and maintained on a Mac, and Linux rendering is not a goal. CI runs on
Linux, so it runs `playwright test --project=chromium --project=schema-admin --project=browser` and leaves the visual project out;
on failure it uploads `ui/test-results` (screenshots, traces) as the `playwright-results` artifact.

- **Review.** After a visual change run `npm run build && npm run e2e:visual` on a Mac; a failure leaves
  `test-results/<test>/` with the expected, actual and diff PNGs. Open each and judge it against the mockup in
  `docs/helix/02-design/graph-browser-mockup/`; a difference is either a bug or a deliberate change recorded
  in DESIGN-GB.
- **Update.** `npm run e2e:visual:update` rewrites the baselines. Look at every changed PNG
  (`git diff --stat` lists them) before committing; never accept a rewrite unread.

Wire types are written by hand in `src/api/types.ts` from `openapi.json` and `src/arras/operate/`; there is
no generation step. The drift guard (below) is what keeps them, and the fake, honest.

## Tests

Three tiers, each against more of the real thing:

- **Unit** (`src/test/*.test.ts(x)`, `npm test`): components and the client with a fetch double. The double
  answers with the bodies in `wire` (`src/test/fake.ts`) and projects GraphQL answers to what the query
  selects, as the server does. It is where timing and failure paths that a server cannot be made to produce on
  demand are tested: a held validate answered after a newer one, a 503 then a retry with the same idempotency
  key, a 501 for an Ashlar-authority module, Retry-After timing. `src/test/inputs.vectors.test.ts` checks the
  form against the shared vectors in `tests/vectors/inputs.json`.
- **Integration** (`src/integration/*.int.test.ts(x)`, `npm run test:integration`): no double. Each test file
  starts its own dev host (`uv run --extra devhost python -m arras.devhost --port <free port>`, demo data) in
  `beforeAll`, waits for `GET /api/operate/version`, and kills it in `afterAll`; a host that does not start fails
  the file with its output, and `global-setup.ts` fails the run at once when `uv` or the Python environment is
  missing. The sandbox has no reset, so tests make their own entities with unique keys and mend what they break
  through `POST /api/dev/control` (expired tokens, backend outages). Components get absolute `operateBase` and
  `consoleBase` and a `getHeaders` that sends `x-arras-user` and the server's own `Origin` (Node's fetch may set
  it; the server refuses a POST without it). `drift.int.test.ts` is the drift guard: for every call and error the
  fake models it makes the real call and asserts that the real answer and the fake's have the same key
  structure (keys, JSON types, nulls, array element shapes), and that both satisfy `openapi.json`. When it fails,
  fix the fake to what the server answers, or report the server. `schema-drift.int.test.ts` is the same guard for
  CONTRACT-011: the hand-written `SchemaPlan`, `SchemaChange` and `RegistryResult` (and the error bodies the console
  shows, the enumerations of `kind` and `element`, and the dev host's `/api/people` and control answers) against
  what the live dev host answers, so a change in the surface's JSON fails a test until the types and the fake
  follow (`schemaWire` and `devWire` in `src/test/fake.ts`). The integration tests act as a person with a role
  through `x-arras-role` (`Who` in `harness.tsx`): a schema author imports and applies, a viewer is refused. Set `ARRAS_REPO_ROOT` to run a copy of `ui/`
  against this repository's dev host.
- **End to end** (`e2e/*.spec.ts`, `npm run e2e`): Playwright in Chromium against the built UI on one dev host:
  the operator workflow, validation, batch, audit search, expired tokens and outages (through the control
  endpoint), personas and the person picker, keyboard use, markup in names, 900px and 375px viewports in light
  and dark, the Query tab (`query.spec.ts`: a query run from the keyboard, the grid, `BULK` from the replica, the history and its reuse, another person emptying it, nothing in browser storage, 30 rows fit a 1080p screen), schema import and export under the strict policy (`schema-admin.spec.ts`: a schema author previews
  and applies an optional property, the Blob downloads are saved byte for byte with no CSP violation, the export
  loaded back changes nothing, a viewer is refused, the toolbar breaks and mends a backend), and an axe-core pass (WCAG 2.1 A/AA) over every area in light and dark. axe's "needs review" results
  fail too, except the contrast of SVG `<text>`, `<kbd>` and glyph-only buttons, which axe cannot compute; they use
  the same colour tokens as the rest of the text (pairs >= 4.5:1 in `styles.css`).

```sh
npm ci
npm test                      # unit
npm run test:integration      # integration: needs uv, `uv sync --locked` at the repository root, and `npm run build`
npm run build && npx playwright install chromium && npm run e2e
```

## Embed in a host

Install the scoped release package, with the same version as your Python `arras`
package. The source workspace is named `arras-ui`; downstream applications use
`@documentdrivendx/arras-ui`. Registry publication and installed-consumer evidence
are recorded in the release notes. You can also install the exact `.tgz` carried
by the Python wheel (`python -m arras.ui npm-package`) or the GitHub release.

The published package contains compiled ESM, declarations and compiled scoped
CSS. The host does not need Tailwind, Vite or TypeScript compilation of Arras's
source. It supplies React/ReactDOM matching the published peer ranges (currently
React 19); TanStack Query and the exact UMF schema browser are package dependencies.

```tsx
import { ArrasConsole } from "@documentdrivendx/arras-ui";
import "@documentdrivendx/arras-ui/styles.css";

<ArrasConsole
  identity={`${tenantId}:${userId}:${authorizationSession}`}
  operateBase="/ontology/operate"
  consoleBase="/ontology/console"
  schemaBase="/ontology/schema"
  getHeaders={() => ({ /* current host authentication headers */ })}
  onUnauthorized={signInAgain}
  pageEffects={false}
  route={route}
  onRoute={(next) => setRoute(next)}
/>;
```

| Public entry | Intended consumer |
| --- | --- |
| `@documentdrivendx/arras-ui` | `ArrasConsole`, `ArrasProvider`, client factories, public types, area components and the design-system provider |
| `@documentdrivendx/arras-ui/browser` | `GraphBrowser` and its location types/helpers |
| `@documentdrivendx/arras-ui/shell` | `ArrasApp`, combining Explore and Operate |
| `@documentdrivendx/arras-ui/styles.css` | Import once in the host bundle; styles stay under `.arras-root` |
| `@documentdrivendx/arras-ui/testkit` | Node-side opt-in Playwright configuration, never a production import |
| `@documentdrivendx/arras-ui/testkit/host` | Browser-side opt-in synthetic acceptance host |

The export map is closed: imports from `src/`, `dist/` internals, `kit/`, `ds/`,
`dev/` and private API/context hooks are unsupported. Add a deliberate public
export upstream when a host needs another reusable capability. The reviewed
`arras/public-api.json` catalog and packed-consumer checks enforce the surface.

| Prop | Ownership |
| --- | --- |
| `operateBase`, `consoleBase`, `schemaBase` | Independently mounted API surfaces; changing one replaces the session |
| `identity` | A nonsecret person/tenant/authorization-session identifier; change it whenever that security scope changes |
| `getHeaders`, `onUnauthorized` | Current host authentication, read per request, and host sign-in recovery |
| `pageEffects` | Default true for standalone use. Set false to keep title, window scrolling and global shortcuts with the host; local control keyboard behavior remains |
| `route`, `onRoute` | Host-controlled Operate routing; otherwise the console uses memory, or the fragment with `hashRouting` |
| `location`, `onLocation` | Host-controlled Explore routing on `GraphBrowser`/`ArrasApp`; no fragment/history-state reads or writes, browser Back, or window scroll restoration |
| `explorerBase` | Same-origin URL for UMF schema-browser static assets; default `/umf-explorer` |
| `brand`, `toolbar` | Host presentation and additional header content |
| `queryClient` | Optional cache dedicated to Arras; private by default. Sharing requires identical identity and API bases, never the host application's general cache |

Identity/API changes remount the provider's children before they can render old
cached data, refusals, viewer modes, forms or query drafts. Late reads stay in the
old scope; released scopes no longer acquire headers or deliver sign-in/revision
callbacks to the host. Pending server-side actions may already have committed; changing
identity does not undo them. Credential refresh for the same session need not
change identity. Reset any host-owned `querySession` along with identity.

Prefer one `ArrasProvider` for areas that share a session. It supplies the CSS
root as well as clients and cache. A nested entry component inherits it;
conflicting explicit identity, API bases, headers, cache or page-effect settings
throw. Use an explicit nested provider for an independent session. Supplied
caches are cancelled/cleared when their last Arras owner unmounts. Independent
providers default to private caches, and component labels/SVG IDs and navigation
focus requests are scoped to their instances. Action-input focus handoffs belong
to their provider, form labels use instance-local IDs, and each UMF schema view
observes the theme of its own host.

```tsx
import {
  ArrasProvider, DesignSystemProvider, EntityTable, SchemaBrowser,
} from "@documentdrivendx/arras-ui";

<DesignSystemProvider designSystem={{ Button: HostButton }}>
  <ArrasProvider identity={sessionKey} pageEffects={false}
    consoleBase="/ontology/console" operateBase="/ontology/operate">
    <div className="host-layout">
      <SchemaBrowser module="catalog" />
      <EntityTable module="catalog" type="catalog.Solution" />
    </div>
  </ArrasProvider>
</DesignSystemProvider>;
```

Other exported areas include `SchemaImport`, `SchemaExport`, `ActionForm`,
`AuditView` and `QueryArea`; use their public declaration types for required props.
UI `canEdit` and hidden controls are presentation decisions. Server callbacks and
backend grants enforce authorization on every request. Serve APIs at the host's
origin, or supply the necessary host CORS/auth/proxy policy for another origin;
`allowed_origins` is an origin-admission rule, not a CORS middleware.

The UMF source view additionally needs the exact schema-browser `assets/` copied
and served at `explorerBase`, plus its documented CSP. Building a host UI does not
require mounting `arras.ui` or serving Arras's standalone page. The React views
are browser components; no complete SSR/hydration guarantee is made.

## Narrow screens

Below `md` (768px, `useNarrow`) the console header is one compact row: the title, the module picker (a `Select` in place of
the module rail; absent with a single module) and the host's toolbar (Explore/Operate, the viewer picker), wrapping if it must;
the operate version chip is hidden. The area tabs never shrink below their label: the list scrolls sideways with an edge fade
where more lies beyond. Keyboard hints (`key-hint`, the table's key line) are hidden on a narrow viewport and on a coarse
pointer (`@media (pointer: coarse)`). From `md` up the rail and the full header return.

## Areas

- **Model**: three views (the third only when the host mounts the schema surface). *Live registry* (default): types, properties, one capability line per type (the record store, the backends that serve bulk reads, text search, counts; each backend's full capabilities sit in a collapsed *Details*), relationships
  (list and SVG diagram), actions with inputs, preconditions and effects, the authority, replicas and revision:
  what this deployment serves. *UMF source*: the module's registered UMF document in UMF's own schema browser
  (below): the declared document, with the live registry's backends as badges and its selection able to open a
  type in Entities or Graph. The live cards stay: they show each backend's full capabilities, the actions and
  cross-module stubs, which the browser's badges summarise only. *Import*: choose a UMF file, see its plan, apply
  it (below). *Export* and *Export all* sit beside the views.
- **Graph**: the module's entities in typed lanes (one list read per type, limit 100, at most 150 nodes drawn, with
  a "showing N of M" notice), relationships as curved edges (an end in another module is a stub node), hover or
  focus lights a node's edges, type, relationship and text filters, the entity panel beside it, freshness chip.
  Keys: 1-6 switch areas, arrows move between nodes, Enter opens one. `?` opens the shortcuts help, one dialog headed with the brand that lists both modes' keys (one table, `src/lib/shortcuts.ts`, drives the handlers and the help; Operate's keys are listed only where Operate is offered); Ctrl or Cmd+K opens the command palette from anywhere, and `/` is find (Explore focuses its search box when search is served, otherwise `/` opens the palette; the digits are Operate's only). The shell holds the Single-key shortcuts switch, which turns `1`-`6`, `?` and `/` off until the page is reloaded (memory only) and keeps it across a switch of mode; the keys never act while typing in a field or with a dialog open. Arrow keys, Home and End also move in the Actions mode tabs. Focus rings are an accent outline on `:focus-visible`, drawn inside tabs and the module rail.
- **Entities**: a paged table (25/50/100 rows a page, Next reading the entities after the page's last key through the list field's `afterKey`, Previous returning to a page read), equality filters on declared columns, column chooser
  (capped at 50 field selections), LATEST/BULK, freshness bar with replica lag, entity panel, relationship
  follow (`target` is read only when a relationship is opened). Keys: arrows move, Enter opens, `/` filters
  (the hint shows only on a wide, fine-pointer screen: `useHideKeyHints`, `src/lib/useMediaQuery.ts`).
  A filter cell sits under each shown column the backend declares filterable (the type's key, its declared `columns` and
  `relationships`); the filters of declared columns that are not shown are under *More filters* above the table, so every
  declared filter is reachable. A column header sorts **this page only** (`aria-sort`, a note under the table says so,
  and that other pages stay in key order when the page is partial): the list read orders by key and has no other order
  (CONTRACT-006), so the console asks the server for none and reorders the rows it read. *Query this type* in the toolbar
  opens Query with the type's starter statement (the optional `onQuery` prop of `DataArea`; `ModuleView` holds the starter).
  The first (key) column is sticky, and a shadow on the table's right edge (and on the key column once scrolled) shows
  while columns are clipped (`useScrollCue`, `src/lib/scrollCue.ts`; `CueScroll`).
  Below `md` (768px) the table and the entity panel take turns: opening an entity replaces the table with the panel under a
  *Back to list* bar, and Back returns to the list with the row focused (the table stays mounted: its page, filter and sort
  are kept); from `md` up they sit side by side. Opening an entity pushes a route, so the browser's Back also returns to the list.
  The entity panel (also beside the Graph) takes the focus in its heading when it opens; Escape closes it and returns the focus to the row.
  Its action bar sits at the top: the declared updates of the type (at most three) as buttons, ranked among updates that qualify with the one that changes a property alone before one that changes it together with others, then the fewest properties, then by name,
  the other actions that take the entity in an **Actions** menu (arrow keys, Home, End, Enter, Escape), then History and Graph; each
  opens its form prefilled with the entity's key. A pencil beside a property that a declared action updates opens that action's form
  with the property's input focused (derived from the action's `update` effect, `src/kit/entityActions.ts`; the form stays ordinary).
  Relationship chips show the target's `name`, `title` or `label` with the key beside it (aliased by-key reads of at most 20 targets,
  60 a panel, no `target`), the key alone while it loads or where it cannot be read.
- **Actions**: action list (a filter on name and description with a live count, sections by the type the effects act on, the actions
  for the entity in context first when opened from an entity, arrow keys to move), form and an Impact view side by side: a validated change is drawn on the neighbourhood
  it touches (created, updated with before and after, deleted, linked and unlinked), kept in an applied state after
  the invoke, with "View in graph" and only the declared actions that could reverse it. A form from `inputSpecs`; validate on blur and before confirmation, effects preview, explicit
  confirmation, idempotency key, `expected_revision`, receipt, conflict rebuild; batch of up to 100 from JSON.
- **Command palette** (`src/console/CommandPalette.tsx`, OPR-19): `/` outside a text field or Ctrl/Cmd+K anywhere opens a modal that
  searches the module in view: its entities (the `_search` read, `src/api/search.ts`, debounced 250 ms, keyed by module, revision, text, types and limit under
  `["gb", "search"]`, POST body only; the same read serves Explore's search box and link picker with limit 50, the palette with 8) and its commands (areas, types, declared actions; `src/lib/paletteCommands.ts`). Up/Down, Home/End move, Enter opens the
  entity in Entities, Shift+Enter in Graph, Alt+Enter its History; Escape closes and returns focus. A `/` that a control handles first (an Entities row focusing the filter) is left to it. It imports nothing from `src/browser/`.
- **Entity context bar**: whenever the route names an entity (an open entity in Entities, a selection in Graph, an
  entity's History, or an action prefilled with an entity's key) the module header shows `<Type> · <key>` with the
  entity's name where it is already known (the entity panel's read, else one cached label read), links to its Entities,
  Graph, History (when Changes is served) and Actions views with the current one `aria-current`, and a control that
  returns to the area's list. It is a `nav` named "Entity context" and renders nothing with no entity in context.
- **Vocabulary**: **Actions** are the invocable things, **History** is one entity's changes and **Changes** is a
  module's whole journal, in every label, heading, link name and receipt.
- **Changes**: Changes (the module's journal by person, action and time), Receipt by group and Import loads, shown unless `POST /audit/changes` answers 501 for the module (an Ashlar-authority module keeps
  the tab so it can state that there is no change history, with the feed position and lag). An entity's History is a
  removable filter chip ("History of <Type> <key>") over Changes, not a mode. Each changed entity (type and key) links to
  its Entities view and its History, and a group id links to its receipt; a deleted entity is text. The receipt of an apply
  links each changed entity to Entities and History, the group to Changes ("View in Changes"), and "Edit and apply again" returns
  to the form with the same inputs and no request (the next apply is a new change with a new idempotency key).

## Vocabulary

The interface's words live in `src/lib/vocabulary.ts`: the modes (Explore, Operate), the areas (Model, Graph,
Entities, Actions, Changes, Query), History (one entity's changes), Edit mode, Export graph and Export model, and
the instance and model words (entity and link; entity type and relationship). Tabs, links, the palette, the
shortcuts help and the tests read their labels from it; a unit test fails when one label names two things or when
a label says node, edge or vertex. The Operate address uses the same ids (`#/operate/<module>/model|graph|entities|actions|changes|query`);
`schema`, `data` and `audit` are accepted and rewritten (CONTRACT-010 D).

## Schema import and export (OPR-12 to OPR-14)

**Import** (the Model area's *Import* view; `src/areas/SchemaImport.tsx`, client `createSchemaApi` in
`src/api/client.ts`). Shown only when `GET {schemaBase}/version` answers contract 1 (the default base is
`/api/schema`, `schemaBase` moves it). The console reads the chosen file as text in the browser and holds it in
memory only; nothing is stored and the document is sent only in a POST body.

1. *Validate* (`POST validate`) shows the plan beside the module's registered document (read from the schema
   catalog): what it would add, change or retire, grouped by element (types, properties, relationships, actions),
   and every violation with its code, path and message. A plan with `ok: false` (an incompatible change names its
   rule and the count of records) offers no Apply; one with `changed: false` says nothing would change. A document
   that does not parse (400, with violations), a 413 (over 1 MiB) and a 501 ("import is not offered for this
   module": its record store has no dry run) are said in words.
2. *Apply* is enabled only for a plan that is `ok` and `changed`. It registers (`POST register`) with the plan's
   `revision` as `expected_revision`, shows the new revision, and refreshes the schema views (the console's `meta`
   and the schema catalog are invalidated). A 409 shows the conflict, applies nothing and offers *Validate again*.
3. Whether the viewer may is the backend's answer (`schema` grant) and the host's `authorize_schema`: a 403 shows
   the reason and **disables Validate, Apply and the file choice for that console view** (the refusal is held in
   the provider like a refused action: it is cleared when the console is mounted again, for example by choosing
   another person); a 401 is the host's sign-in. The console grants nothing (OPR-07).

**Export** (`src/areas/SchemaExport.tsx`, `exportFiles.ts`). From the catalog the console already reads
(`GET {operateBase}/explorer/schema-catalog.json`, as the viewer): *Export* saves the module's document exactly as
the catalog holds it, named `<module>.umf.json`; *Export all* saves `{version: 1, entries: [...]}` as
`arras-schema-catalog.json`, the entries that carry real documents (`schemaFormat: "umf"`). A "not shown" note
entry (`schemaFormat: "json-schema"`, for a document over the catalog's limits) is never saved: the module shows
"Too large to export", and "Export all" says in its tooltip how many it left out. A module with no catalog entry
(an attached module, or one the viewer cannot read) offers no Export. The download is a `Blob` behind an object
URL saved by clicking an `<a download>` (`src/lib/download.ts`), and the URL is revoked afterwards: no
`localStorage`, no server round trip, nothing in the URL. Measured under the dev host's strict policy
(`default-src 'none'; ... connect-src 'self'`, see "Content-Security-Policy" below) with
`e2e/schema-admin.spec.ts`: both downloads save, byte for byte, with no CSP violation or page error.

## UMF source (UMF's schema browser)

The Schema area's *UMF source* view shows the module's registered UMF document in UMF's own schema browser
instead of a second one (FEAT-010 OPR-11, ADR-021 "Reuse"). The browser is UMF's public npm package
`@documentdrivendx/umf-schema-browser`, pinned exactly at **2.0.0** in `package.json` (licensed
`MIT OR Apache-2.0`; bundled third-party licences in its `THIRD_PARTY_NOTICES.md`), so
`import { mountSchemaBrowser } from "@documentdrivendx/umf-schema-browser"` resolves in any bundler and
`package-lock.json` carries the tarball's sha512 integrity. Nothing of it is committed here.

`scripts/umf-schema-browser.ts` states the pin's release facts (tag `schema-browser-v2.0.0`, tarball
`documentdrivendx-umf-schema-browser-2.0.0.tgz`, 2,178,040 bytes, sha256
`03e13341c79f29fe891fa6d97a3e504b36a483ba51c98b2e1bcb557b6036e8e1`, byte-identical to the npm tarball) and checks
them:

```sh
npm run check:umf                    # offline: exact pin, lockfile entry, installed version, licence files
npm run check:umf -- --download      # and the registry: its integrity is the lockfile's, its tarball the release's sha256
npm run check:umf -- --dist dist     # and the build's copy of the assets, byte for byte
```

CI runs the first two after `npm ci` and the third after `npm run build`; `src/test/umf-package.test.ts` runs the
offline checks and the build copy in the unit tier. `npm run build` copies the installed package's `assets/` to
`dist/umf-explorer/` byte for byte (a small plugin in `vite.config.ts`, never through the bundler), and
`npm run dev` serves the same directory at `/umf-explorer`. Playwright compares every served asset with the
installed package.

**To bump it:** `npm install @documentdrivendx/umf-schema-browser@<version> --save-exact`, set `RELEASE` in
`scripts/umf-schema-browser.ts` to the GitHub release's tarball digest and size, run
`npm run check:umf -- --download`, then every tier (`npx vitest run`, `npm run test:integration`,
`npm run build`, `npx playwright test`). Read the package's `CHANGELOG.md` and `HOST_CONTRACT.md` first, and
`src/test/umf-package.test.ts` pins the lockfile's sha512 and the release sha256, so update both there too.

**How the console uses it.** When the view opens, the console reads the viewer's catalog (again, if Export read it already),
`GET {operateBase}/explorer/schema-catalog.json` (CONTRACT-009), with its own client, so `getHeaders`, the
expired-token signal (`onUnauthorized`, "Sign in again") and the bound of four requests in flight apply. It maps
the entries to the package's `Entry` (`schemaFormat: "umf"` is what makes the browser draw the record map) and
calls `mountSchemaBrowser(container, options)` from an effect (host contract 1.1) with:

- `entries`, `categories: [{id: "domain", label: "Registered modules"}]` (the one category the operator surface
  sets), `selection: {schema: "arras:<module>"}`, `title: "UMF schema browser"`;
- `readOnlyLocalFiles: true` (the view shows registered documents only) and `hideHero: true`;
- `theme` and `themeVariables` from the console's own scheme and tokens (`--paper` = `--surface`, `--ink` =
  `--fg`, `--muted` = `--fg-muted`, `--line`, `--accent`, `--umf-font` = the body font): the frame matches the
  console in light and dark. `themeVariables` is fixed at mount, so a scheme change remounts the browser;
- `annotations` from the live registry (the meta query): on the module's entry `authority: truss` (positive),
  `replica: ashlar` (neutral) and any backend the status reports unavailable (`ashlar · unavailable`, warning);
  on each record that is an entity type, one annotation per backend, `truss · mutable` (positive) and
  `ashlar · read-only` (neutral), each with that backend's capabilities in its tooltip (the record map reserves a
  line for each since 1.1.2); on each relationship the backends that follow it (`follows: truss, ashlar`, info,
  or `not followed`, warning). Keys are the contract's: the entry id, `["catalog","UseCase"]`,
  `["relationship","catalog","solution-addresses"]`. *Refresh badges* re-reads the registry, and a change is
  `handle.setAnnotations(...)` on the same frame (an Ashlar outage turns a record's second annotation into
  `ashlar · unavailable`, warning). The tones are the same in light and dark: 1.1.2 draws each at 4.5:1 or more
  on both papers (measured below);
- `height: "100%"` in a container with an explicit height (`max(640px, 100dvh - 260px)`); no positioning
  workaround and no `onContentHeight`;
- `onSelect`/`onNavigate`: the console's line above the frame says `Selected: catalog › UseCase`, and when the
  definition is a record that is an entity type of this module (`[M, E]` is the type `M.E`, by name) it offers
  *Open UseCase in Data* and *Show UseCase in Graph*, which switch areas through the console's router (Graph shows
  that type with the others toggled off, for that visit);
- `onCatalogError`/`onError` and `ready`: a catalog error with `status: 401` is the console's "Sign in again"; any
  other, or `ready` rejecting (a failure or the package's 30 s bound), is the failed state with Retry; a later
  `onError` (a source that fails to render) is a notice. No markup inside the frame is read.

Another module of the same catalog is `handle.select({schema})` on the same frame, not a remount; the console
remounts only when the catalog, the asset base, the colour scheme or Retry changes. Opened with the keyboard,
the view calls `handle.focus()` once ready, so focus moves to the inspector's heading. `destroy()` runs when the
view closes, the catalog no longer lists the module, or the mount is replaced (the rejection `destroy()` gives an
unready `ready` is expected and ignored). The browser's hash routes, filters and styles stay inside its frame.

There is no "Open in new tab" link. The standalone page now accepts `?catalogUrl=` and an origin-checked
configure protocol, but neither can carry this console's credentials: a new tab fetching
`{operateBase}/explorer/schema-catalog.json` sends cookies only, and the dev host (like any host that
authenticates by header through `getHeaders`) would answer as someone else or refuse. The configure protocol
needs a parent window, which a new tab does not have. A host whose session is a same-origin cookie could link
`/umf-explorer/index.html?catalogUrl=...` itself; the console does not claim that it works everywhere.

The registry has no history to give `revisions`: `Ontology.document` returns the current registered text only,
so the console supplies none rather than inventing it (CONTRACT-001, open questions).

**What a host must do.** Serve the package's `assets/` directory (all of it: `index.html`, `explorer.js`,
`explorer.css`, `style.css`, `components.css`, `schema-catalog.json` and the `chunk-*.js` files the browser loads
lazily) at `explorerBase` (default `/umf-explorer`), JavaScript as `text/javascript` and CSS as `text/css`, on the
console's origin; mount the operator surface for the catalog. No catalog route and no credential for the frame
are needed.

**Content-Security-Policy.** Export's Blob download needs no allowance in this policy (measured, not assumed:
`e2e/schema-admin.spec.ts` saves `<module>.umf.json` and the catalog file under it and fails on any violation);
a host with a different policy should check `default-src 'none'` still admits an `<a download>` on a `blob:` URL.
The package mounts a `srcdoc` iframe, which inherits the policy of the page that
holds the console, so that page's policy is what the browser runs under. The dev host serves the console's
pages and the assets with UMF's strict profile plus `frame-ancestors 'self'`:

`default-src 'none'; base-uri 'none'; script-src 'self'; style-src 'self'; img-src 'self'; frame-src 'self' about:; connect-src 'self'; frame-ancestors 'self'`

(plus `X-Frame-Options: SAMEORIGIN`, `nosniff`, `Referrer-Policy: no-referrer`); `npm run dev` sets it on the
assets only (Vite's own page needs inline scripts). **No `'unsafe-eval'`**: the browser's validators
are compiled at UMF's build (1.1.0 on), so the embedding CSP allows no `'unsafe-eval'` on the console's page. Measured under Playwright (`e2e/umf-explorer.spec.ts` fails on any violation in the page or the frame):

- `script-src 'self'`: the console's bundle, the browser's `explorer.js` and its chunks. Narrowed to the
  console's own `/assets/`, the browser's script is refused, `ready` rejects after 30 s and the console shows its
  failure state (a test narrows the real policy to prove it, and checks no `'unsafe-eval'` is asked for).
- `style-src 'self'`: the console's stylesheet and the browser's `style.css`, `explorer.css`, `components.css`.
- `connect-src 'self'`: the console's API calls; the browser makes none, since it is given the entries.
- `base-uri 'none'`: the srcdoc has no `<base>`; nothing in the console sets one.
- `frame-src 'self' about:`: UMF's profile names it. Chromium does not need it for a srcdoc frame (the browser
  starts with `frame-src` removed or `'self'` only); it is kept as UMF tests it.
- `img-src 'self'`: the mark, which the console draws inline. A brand whose wordmark is an `https://` image adds that one origin (`Brand.csp()`).
- Not needed: `font-src`, `worker-src`.
- `frame-ancestors 'self'`: kept, so no other origin frames the console.

**Measured** (2.0.0, headless Chromium, loopback dev host): the npm tarball is 2,178,040 bytes and unpacks to
about 19 MB, of which `assets/` is 18.6 MB in 56 files (one validator chunk alone is 14.8 MB); `explorer.js` is
850,984 bytes (119,629 gzipped at level 9). axe finds no
WCAG 2.1 A/AA violation inside the frame in light or dark with the source pane open (`e2e/a11y.spec.ts`; 1.1.1
failed `scrollable-region-focusable` there). Computed contrast, light / dark, on the frame's `--paper`
(`e2e/umf-explorer.spec.ts`, every tone in a probe frame): entry heading 7.80-17.44 / 8.58-14.46 (1.1.1: `info`
4.35 and `warning` 4.49 in light, 3.56-3.97 in dark); legend 6.86-17.15 / 6.86-11.85; record map, where every
tone is drawn in `--ink`, 17.44 / 14.46 (1.1.1: 2.0-2.2 in dark); relationship numbers 17.44 / 14.65 (1.1.1:
1.00, invisible). Two or three record annotations overlap neither each other nor the property count.

**Remaining gaps**, asked of UMF: tones not visible in the
record map (all `--ink`) and legend badges as fixed light pills in dark; heading badges at heading size; theme
variables fixed at mount and not per scheme, `--accent` accepted but unused, surface tokens not settable;
`onSelect`/`onNavigate` indistinguishable, error codes unlisted, the 30 s bound; the deploy footprint of
`assets/`.


## Theme and design system

The UI draws through a design-system seam (ADR-029, `src/ds/`). The widgets are `Button`, `TextField`,
`TextArea`, `Select`, `Notice` and `Mark`; the role tokens are CSS custom properties. The built-in
implementation is plain React and CSS in `src/ds/default.tsx` and `src/ds/default.css`, so there is no
design-system package to install, no registry to reach and no peer dependency for it. Surfaces import the
widgets from `src/ds` (`import { Button, Notice } from "../ds"`) and never from a package.

**The contract** (`src/ds/contract.ts`, exported from the packed
`@documentdrivendx/arras-ui` root):

| Widget | Props beyond the element's own |
|--------|-------------------------------|
| `Button` | `variant` (`primary` default, `secondary`, `text`), `size` (`sm`, `md`), `busy` (marks it `aria-busy`, shows a spinner and ignores clicks; the caller also sets `disabled` where the control should leave the tab order), `type` (`"button"` when omitted), `ref` |
| `TextField`, `TextArea` | `label` (visible; a field without one carries an `aria-label`), `hint` and `error` (each tied to the control by `aria-describedby`; an `error` sets `aria-invalid`), `ref` |
| `Select` | `label`, `hint`, `error`, `options` (`{value, label, disabled?}[]`), `placeholder` (a first entry with the empty value), `ref` |
| `Notice` | `tone` (`info` default, `success`, `warning`, `error`), `title`, `role` (`alert` for `error` and `warning`, else `status`, when omitted) |
| `Mark` | `label` (the accessible name; without it the mark is decorative), `size` |

**The role tokens** (`ROLE_TOKENS`). Each has a built-in value in light and in dark, so none is required, and the
stylesheet reads each as `var(--arras-..., <built-in>)` (`src/styles.css`, which `src/test/design-system.test.tsx`
checks against the list):

| Group | Tokens |
|-------|--------|
| Colour | `--arras-color-text`, `-text-muted`, `-surface`, `-surface-sunken`, `-ground`, `-border`, `-accent`, `-on-accent` |
| Shape | `--arras-radius-control`, `--arras-radius-card` |
| Type | `--arras-font-body`, `--arras-font-mono`, `--arras-font-size-small`, `--arras-font-size-heading` |
| State | `--arras-state-live`, `-limited`, `-closed`, `-purchasing` |

**A host's own widgets.** Wrap the components in `DesignSystemProvider` with any of the widgets above; a widget
the host does not supply is the built-in one. Embedded components (`ArrasApp`, `ArrasConsole`, `GraphBrowser`)
install no theme of their own and use the provider's implementation, or the built-in one when there is no provider:

```tsx
import { ArrasApp } from "@documentdrivendx/arras-ui/shell";
import { DesignSystemProvider, type ButtonProps } from "@documentdrivendx/arras-ui";
import "@documentdrivendx/arras-ui/styles.css";

const HostButton = ({ variant = "primary", busy, children, ...rest }: ButtonProps) => (
  <MyButton kind={variant} loading={busy} {...rest}>{children}</MyButton>
);

<DesignSystemProvider designSystem={{ Button: HostButton }}>
  <ArrasApp getHeaders={...} />
</DesignSystemProvider>;
```

A host that only wants its colours sets the role tokens on an ancestor of the interface, in its own stylesheet
(`.my-app { --arras-color-accent: #0b5; }`). `useDesignSystem()` returns the implementation in context. The
built-in widgets read the same tokens, so a host that replaces only some widgets keeps the rest in its colours.

The package root explicitly exports `DesignSystemProvider`, `useDesignSystem`,
`defaultDesignSystem`, `ROLE_TOKENS` and the contract's twelve types; no design-system
subpath or second context is needed. After `npm run build:lib` and `npm run pack:wheel`,
`npm run test:packed-consumer` checks the actual tarball's public TypeScript and runtime
imports from a temporary consumer, using the workspace's exact installed dependencies.
Its render proves a root-hook host widget and built-in fallback beneath the public browser's
palette slot; a structural check proves all three entrypoints reach the shared context chunk.
It also checks the eighteen tokens and host React/ReactDOM peer identity. This local artifact
check leaves fresh registry installation and publication qualification separate.

**Light and dark.** The built-in values follow the page's `prefers-color-scheme`, unless an ancestor says
`data-appearance="light"` or `"dark"` (see "Styles in a host page"). The stand-alone pages (`src/main.tsx`, the
dev host, and `src/embed.tsx`, the page `arras.ui` serves) use the built-in design system and load no
theme. Nothing in the library sets an attribute, a class, a style or a storage entry on the host's document.

**Accessibility.** The built-in text and control colours meet WCAG 2.1 AA in both appearances (4.5:1 for text, 3:1
for control borders and the focus ring); every control has a visible focus ring on `:focus-visible`; a field's
label, hint and error are tied to it by `for`, `id` and `aria-describedby`; a `Notice` carries a role and a glyph
that does not rely on colour; a busy `Button` is `aria-busy`. The axe suite (`e2e/a11y.spec.ts`) covers every
area in both appearances.

## Graph Browser and shell

`arras-ui/browser` exports `GraphBrowser` (FEAT-011): an interface for people who use the ontology. It reads as the viewer; an operator can also edit and export (below).
An Entry (the module's title, the type chips (a single choice: `All` first, then one per type, a radio group with `aria-checked`), a type's entities in pages of 50, search), a node page (the resolved
view's sections and formats, attribution and freshness), the relationship groups and a neighbourhood picture.
It reads the console GraphQL surface (`/api/console`), holds no credential, stores nothing in the browser
and writes only by a declared action, for an operator (below). `arras-ui/shell` exports `ArrasApp`, which puts `GraphBrowser` and `ArrasConsole`
behind one top bar (ADR-025). `src/index.ts` (the console) exports neither, and `src/browser/` never imports the
console's areas (Biome `overrides` and `src/test/boundaries.test.ts`). Import `arras-ui/styles.css` once. A host may pass its own widgets with `DesignSystemProvider` (see "Theme and design system").

```tsx
<ArrasApp getHeaders={...} onUnauthorized={...} defaultMode="user" toolbar={...} />
<GraphBrowser getHeaders={...} location={loc} onLocation={setLoc} />   // a host that owns the location
```

- **Editing and export (operators).** `ArrasApp` sets `canEdit` when the viewer has the `admin` mode; a host
  using `GraphBrowser` alone sets it itself. With it, a lock at the top right of a node card turns edit mode
  on (it opens, and a pencil appears beside each editable property). A property is editable when the module
  declares an action that updates it (one `update` effect on the type, keyed by a reference input): alone,
  where the action's other inputs are optional, or together with the others it can only change with, in a
  popup form; a relationship group offers **Add** (a search-and-pick popup) and a remove control on each member where the module declares a `link` or `unlink` action for it. A change is that action, `validate` then `invoke`, as the viewer (`useAction.ts` over the kit's `useActionCore`, the browser's one
  write path; CONTRACT-010 F). **Export graph** on a module's page (also needs `canEdit`) pages `POST /export`
  and saves `<module>.graph.json`, the canonical graph file (CONTRACT-003, Export), the same bytes
  `arras.graphfile` writes; `python -m arras.devhost --records <file>` loads it again.
- **Modes.** `ArrasApp` asks `GET {operate}/viewer` once. A failure means Explore only: it never assumes an
  operator. With `admin` among the modes an Explore/Operate switch (`aria-pressed`, a check mark) sits in the top
  bar; otherwise no control, link or text refers to Operate and the operate surface is not called again.
  `defaultMode` applies to an operator opening with no fragment.
- **Hash grammar.** `#/explore/<module>/<type>/<key>` (Explore; `#/explore/<module>` the entry, `#/explore` the
  chooser), `#/operate/<module>/<area>/...` (the console; see "Routes"); `#/browse` and `#/admin` are accepted for them and rewritten in place; `admin` is also the host-protocol id of Operate (`/viewer`'s `modes`, `defaultMode`), never a label. A fragment with no prefix
  (`#/<module>/<area>`) is read as Operate for an operator, rewritten with the prefix, and is the Explore entry for
  anyone else. Switching carries what is open both ways, and each switch is a history entry: Operate opens Entities on
  the node's module and type with its entity open; Explore opens the node page for the entity open in the console,
  else its type's list, else the module's entry. Segments are percent-encoded; no search text or person is in a
  path or query string. The search text, chosen types and scroll position are in `history.state`, never the URL.
  With `location`/`onLocation` the host owns the location and the browser neither reads nor writes the URL; the
  shell then keeps the console's route in memory and hands the host the Explore location when Explore is pressed.
  `onLocation` also says `{replace: true}` where the entry is rewritten rather than added (Show next). For an operator the
  shell hands each mode one link primitive (`shell/links.ts`): Explore's **Open in Operate** (Entities, History, Actions) and
  **Model**, Operate's **View in Explore**. They are anchors in the fragment, and where the host owns the location they
  switch mode and set the other mode's route; a viewer who is not an operator gets none.
- **Routes.** The console's place is its fragment, `#/operate/<module>/<area>/...` (no prefix when `hashPrefix` is
  unset), every segment and value percent-encoded. The areas are `model[/<type>][?view=umf]` (the model, a type
  selected in it, or its UMF source); `entities/<type>[/<key>]` (the first type is written explicitly, so the
  address is the screen) with `?f.<column>=<key>` (the table's filter, written for a key column only),
  `after=<key>` (the key the page starts after) and `sort=<column>:<asc|desc>`; `graph/<type>/<key>`;
  `changes[/<type>/<key>]` (a module's changes, or that entity's History) with `?group=<id>` (the receipt of one
  change group; the id is opaque and carries no person or input), `action=<name>`, `since=<instant>`,
  `until=<instant>` (ISO 8601) and `view=loads` (the import loads); `actions/<action>[?in.<input>=<key>&...]`
  (ref inputs prefilled from entity keys, never another value); and `query` (the area alone). `schema`, `data`
  and `audit` are accepted for `model`, `entities` and `changes` and rewritten in place. A fragment that does not
  fit falls back to the module's area; one that parses but names nothing the viewer can open shows one Not found
  page that links to the module's Model. `entityHref(module, area, type, key)`,
  `actionHref(module, action, input?)` and `groupHref(module, group)` from `route.ts` build these addresses for every link. Navigation
  (area, module, type, opening or closing an entity, History, Graph, an action) pushes a history entry; Back and
  Forward restore the console from the fragment; redirects (the first module, the default type) replace the entry.
  The open entity, the graph selection, the changes entity and the action prefill are read from the route, so a
  refresh or a pasted link restores them. `document.title` is `<entity or action> · <area> · <module> · <brand>`
  while the console is mounted. The area tabs and Entities' type tabs follow the WAI-ARIA tabs pattern (Left and
  Right, Home, End, one tab stop).
- **Embedding note: `authorize_operator`.** A host that serves the Graph Browser to people who are not
  operators MUST pass `authorize_operator` to `arras.operate.create_app`; without it every accepted viewer is
  an operator (CONTRACT-010's default). The dev host's operators are the members of the groups `admins` and
  `builders` (the host's operator groups are configuration); the sandbox's read-only and no-access people are not.
- **The view is the server's.** Titles, summaries, icons, tones, sections, formats, relationship labels and
  order come from the resolved view on the meta schema (`Module.view`, `EntityTypeInfo.view`); the browser
  derives no default. Text is always rendered as React text (no `dangerouslySetInnerHTML`); a `link` is shown as
  one only for `http`, `https` or `mailto`, with `rel="noopener noreferrer"`.
- **Requests.** A node page is planned (`src/browser/planner.ts`): the page request reads properties, attribution,
  freshness and relationship keys; labels come in chunks of at most 20 targets and 50 selections, per module
  endpoint. A refused or failed label is a retry row, an absent or unreadable one is "Not available".
  Search is hidden when no backend of the module declares `search: "substring"`.
- **Tests.** Unit tests use `src/test/browserFake.ts` (a fetch double for views, `/viewer`, by-key and list
  reads and `_search`, enforcing the 50-selection limit); the layout has golden vectors in
  `src/test/layout.vectors.json` (`UPDATE_VECTORS=1 npm test -- layout` rewrites them for review); the
  integration tier compares the double's answers with the real host (drift guard); `e2e/browser.spec.ts` is the
  whole-stack suite (workflow, modes, refusals, request recorder, keyboard, axe in both schemes, hubs of 25 and
  120 made through the operate surface); `e2e/visual.spec.ts` registers the example catalog as `atlas` and
  screenshots every screen (see "Visual baselines").
- **Sandbox people for tests.** The operate surface refuses carol and dave, so tests that need an operator with
  less access revoke part of bob's access through `POST /api/dev/control` (`grant`/`revoke`) and grant it back.

## Branding

The interface's name is configuration (SD-013, FR-73). `ArrasApp`, `GraphBrowser` and `ArrasConsole`
take `brand={{ name, wordmark?, title?, tagline? }}`; `useBrand()` (`src/lib/brand.tsx`) reads it, with
`{ name: "Arras" }` when none is given. The name is the top bar's wordmark, the suffix of the document title,
and the product name in labels and notices. A wordmark that starts with `https://` is shown as an image
(its alt text is the name); any other wordmark, and the name itself, is shown as text, never as markup. The
served page (`arras.ui.create_app(brand=...)`, and the dev host with the default brand) carries the brand in
`<meta name="arras-brand">`, which `embed.tsx` and `main.tsx` read with `readBrandMeta(document)`. No other
source file writes the product name in a user-visible string; `src/test/brand-strings.test.ts` fails when one does.


## Styles in a host page

`styles.css` is built so that loading it in a host page styles only the console's own subtree (ADR-027):
Tailwind compiles it, then `scripts/scope-css.ts` puts every top-level selector under `.arras-root` and maps
`:root`, `html` and `body` onto that element. The tokens (`--accent`, `--bg`, ...), the preflight reset, the
utilities and the `.arras-*` classes all live under it; nothing is set on the host's `html`, `body` or `:root`,
so a host's own custom property of the same name is neither changed nor read. `npm run check:css -- <file>`
fails if a built stylesheet has a selector outside the root; CI runs it on the library build.

- **Roots.** `ArrasApp`, `ArrasConsole` and `GraphBrowser` each render inside `<Scope>`, which makes the
  `.arras-root` element (one entry inside another shares it). The root has the height, font and background a
  page would have given `body`. `src/page.css` (`html, body, #root` at full height) is for the stand-alone
  entries only (`main.tsx`, `embed.tsx`).
- **Colour scheme.** The host's, always (ADR-029). `ArrasApp`, `ArrasConsole` and `GraphBrowser` take no
  `appearance` prop, install no theme, and never set `color-scheme`, `data-theme`,
  `data-appearance` or a class on the host's `html`, `body` or elements, nor store a choice. The root's
  tokens are the `--arras-*` role variables a host sets, each with a built-in light and dark value; the
  scheme follows the nearest ancestor that says one, by `data-appearance="light" | "dark"` (what a host's switch
  sets on its element) or by an inline `color-scheme` of exactly `light` or `dark` (`light dark` says none), so a
  light region inside a dark one decides for what is inside it; then the system's `prefers-color-scheme` where no ancestor says. A host toggling light, dark or auto at run time
  re-themes the components with no call into them. The UMF schema browser's frame is told the host's
  effective scheme and tokens when it mounts, and the view watches the page's root element and the console's ancestors
  (their `data-appearance`, `data-theme`, `class` and inline `style`, attributes only, and the system's
  preference; resolved again on every change and once after mount) and mounts the frame again when the scheme or the theme variables change, because the package fixes its
  theme at mount. No entry, the stand-alone pages included, installs a
  theme: they use the built-in design system and the system's preference.
  Tests: `src/test/host-theme.test.tsx` (the three components mounted in a host that switches, with no write
  to the host's attributes or storage, and no theme installed by any source), `src/test/design-system.test.tsx`
  (each built-in widget, a host's own implementation, no side effects on the host document),
  `src/test/umf-source.test.tsx` (the frame follows the host's switch) and `e2e/host-isolation.spec.ts`.
- **Cascade.** The rules stay in Tailwind's layers, with the `.arras-*` classes unlayered above them.
  A host's layered rules (its own Tailwind) do not override the root's, which are the more specific; a host's
  *unlayered* element rule (`button { ... }`) outranks the layered ones inside the root.
- **Tests.** `src/test/scope-css.test.ts` for the scoper; `e2e/host-isolation.spec.ts` for the built page
  with a host's markup and rules planted around the root: the host's elements keep their browser defaults,
  its same-named tokens do not reach the root, the appearance follows the host's `data-appearance`, then the OS,
  and a host's own switch flipped at run time re-themes the root while nothing is written to the page.
