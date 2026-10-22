---
ddx:
  id: ADR-027
  type: adr
  activity: design
  status: proposed
  owner: Erik LaBianca
  updated: 2026-10-12
  authoring:
    home: repo
  links:
    - id: ADR-006
      kind: informed_by
    - id: ADR-021
      kind: informed_by
    - id: ADR-025
      kind: informed_by
    - id: CONTRACT-006
      kind: informs
    - id: CONTRACT-009
      kind: informs
---

# ADR-027: The wheel carries the UI as a mountable app and as an npm tarball, which the release also publishes

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-12 | Proposed | Erik LaBianca (architecture lead) | [ADR-006](ADR-006-embedded-library-on-psycopg-and-the-truss-toolkit.md), [ADR-021](ADR-021-operator-console-as-a-react-package-in-the-arras-repository.md), [ADR-025](ADR-025-one-shell-two-modes-and-operate-is-offered-by-the-host.md), [CONTRACT-006](../contracts/CONTRACT-006-console-graphql-surface.md), [CONTRACT-009](../contracts/CONTRACT-009-operator-action-and-audit-surface.md) | Medium |

Proposed records the direction under review; it does not claim implementation is complete.

## Context

| Aspect | Description |
|--------|-------------|
| Problem | An embedding host must serve both the Python surfaces and the React interface. The UI lives in `ui/`, outside the wheel, and only the loopback, unauthenticated dev host serves its build, so a host has the APIs but no interface. |
| Current State | `console.create_app`, `operate.create_app` and `operate.create_schema_app` are separate ASGI apps, each taking the host's `principal_for_request`. `ui/` is an npm project that exports raw TypeScript. The Python package is published to PyPI, which serves Python wheels only; the UI's components are an npm package under the organisation's `@documentdrivendx` scope. |
| Requirements | A host mounts one thing. The UI's version equals the library's. The page works under any path prefix and under UMF's strict policy. A host may instead bundle the components into its own app, so its pages load as one application. No registry of our own to run. |
| Decision Drivers | One release artifact on the index we have (PyPI); lockstep UI and API (the UI already refuses to render unless `contracts.operate` is 1); the host authenticates and Arras never does (CONTRACT-006). |

## Decision

1. **`arras.ui.create_app` is the one mount.** It composes the three surfaces (`/api/console`, `/api/operate`, and `/api/schema` only when the host passes `authorize_operator`) with the page, its assets and UMF's schema browser, under `base_path` or the host's `root_path`. It adds no operation of its own. The page and assets are public files served under `PAGE_CSP` (the policy measured in `ui/e2e/umf-explorer.spec.ts`), only the declared page, `assets/`, `umf-explorer/` and optional manifest-scoped theme assets; every data read and write is a surface that refuses a viewer with no principal. The three apps remain public so a host may still mount them separately.
2. **The page is a second Vite build of the same source.** `ui/src/embed.tsx` mounts the shell without the sandbox toolbar and derives every URL from where the page was loaded (relative asset URLs, `api/...` beside the page), so any prefix works. The dev host keeps its own entry.
3. **The wheel carries the components as an npm tarball, and the release publishes it.** `npm run build:lib` emits ESM, declarations and `styles.css` for `@documentdrivendx/arras-ui`, `@documentdrivendx/arras-ui/browser` and `@documentdrivendx/arras-ui/shell`; `scripts/pack-wheel.ts` packs them with pyproject's version into `src/arras/ui/npm/documentdrivendx-arras-ui-<version>.tgz`. The packed manifest carries the scoped name, the public npm registry, the repository and the licence; the source `ui/package.json` keeps `arras-ui` and stays `private`, so nothing publishes it by accident. `arras.ui.npm_package()` and `python -m arras.ui npm-package [--copy DIR]` give a host the path, so `npm install <path>` needs no registry and the Python pin is the UI pin. On a release tag, after the index has the wheel, a job of its own (`id-token: write`, the `npm` environment's token) runs `npm publish --provenance` on the tarball taken from the wheel, so the two cannot differ, and the GitHub Release carries the wheel, the sdist and the tarball. A host may instead install from the registry (`npm install @documentdrivendx/arras-ui`).
4. **The release builds the UI first.** CI and the release job run `npm run build:wheel` before `uv build`, then check on a clean interpreter that the installed wheel holds the page and the tarball. Hatch lists the build output under `artifacts` for both the wheel and the sdist (`uv build` builds the wheel from the sdist), because git ignores it.
5. **The stylesheet is scoped to a root element.** A host that bundles the components must be able to load `styles.css` without restyling its own page. The library's CSS is compiled by Tailwind and then scoped by `scripts/scope-css.ts` (a PostCSS step on `src/styles.css`): every top-level selector is placed under `.arras-root`; `:root`, `:host`, `html` and `body` mean that element, so the tokens (`--accent`, `--bg`, ...), the font and the reset live on it and never on the host's `<html>`; nested rules, keyframes and `@property` are left as they are; the `@layer`s stay, so the library's own cascade is the one it was written for. `check:css` fails the build if a selector reaches outside the root. Each entry component (`ArrasApp`, `ArrasConsole`, `GraphBrowser`) renders inside `<Scope>`, which provides the root; one inside another shares it. The root never chooses a colour scheme (ADR-029). The dark tokens apply when the nearest ancestor that gives an appearance says dark, by `data-appearance="dark"` (the host's switch) or an inline `color-scheme: dark` (`light` or `dark`, alone or with `only`; the two-value `light dark` says none), or by the system's preference when no ancestor says one. Page-level rules (`html, body, #root` at full height) are `src/page.css`, imported only by the stand-alone entries. UMF's schema browser is themed from the root's tokens and scheme, not the page's.
6. **One wheel, `arras.ui` isolated.** Nothing but `devhost` imports it (the module rules check this), so a later split into a separate distribution is a move, not a rewrite. Splitting now would add a second wheel, version pins between them and Node in two release paths for one consumer.

### Asset contract separates frontend consumption from Python hosting

The compiled npm package is the widget-extension route; the prebuilt page is the
runtime CSS/font/favicon route. Both use CONTRACT-005's versioned inert asset
manifest and exact package/contract cohort. Generate the page manifest after the
build, include it in wheel/sdist assets, and validate it before hosting. A host
may supply a compatible external page bundle or theme manifest; loading one never
imports downstream code. The first release remains one Python/UI version pin;
future independent frontend versions need explicit manifest compatibility and
installed-consumer evidence. This seam enables a later source/distribution split
without requiring another repository or Python wheel now.

The chosen runtime theme is same-origin, hash/size/MIME-checked and host-owned.
Arbitrary JavaScript widget injection or remote theme origins would expand the
execution/security boundary without helping the CSS-only consumer; they are
excluded. A compiled host uses the existing provider for executable widgets.
HTML is uncached, only digest-addressed assets are immutable, and a source file
change cannot silently replace already validated bytes. Exact format, callable
and refusal details belong to CONTRACT-005. Missing/incompatible manifests or a
second uncontrolled React runtime are drift signals.

### Portable tests are opt-in artifacts, not production dependencies

The first reusable release also ships CONTRACT-005's two explicit testkit
subpaths: Node configuration for the existing canonical Playwright suite and a
browser acceptance host reusing the existing development shell. Package the same
specs/resources used by the source suite; a downstream builds the standard
synthetic host with its own theme/provider and runs the tests without copying
them. This complements the narrower public theme checker. It does not put
Playwright, Node utilities or development controls into production entrypoints.
The host explicitly starts fresh acceptance fixtures and provisions optional
tools/browser. Exact artifact inventory and an actual packed themed full run are
required before claiming suite portability; source file presence is insufficient.

GitHub Release asset delivery is mandatory for this selected first release.
PyPI/npm uploads use existing configured access and may be explicitly deferred
under the human's instruction; a missing registry upload is never advertised as
available. Registry jobs consume the same verified bytes and do not precede or
replace mandatory source/native/UI/consumer gates.

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| Publish only to the registry | The usual route | Two artifacts to keep in step | Kept as a second route; the tarball in the wheel is the pin |
| Serve only a prebuilt page | No host build | A separate SPA: its own React, theme and navigation, and page loads that differ from the host's | Kept for hosts with no Node build; not the host's choice |
| A separate `arras-ui` wheel | Python-only users skip about 3 MB; no Node in the core release | Two wheels, version pins, a larger release | Deferred (decision 5) |

## Consequences

| Type | Impact |
|------|--------|
| Positive | One mount, or a bundled component, from one pin; the strict policy and the schema browser's iframe are tested with the page. |
| Negative | The wheel grows by about 2.7 MB; the release job needs Node; a host that bundles the components must serve `/umf-explorer` (by mounting `arras.ui` on the same origin) and allow `frame-src 'self'`. A host's unlayered element rule (`button { ... }`) outranks the library's layered rules inside the root; the stylesheet adds about 6 KB of selector prefixes. |
| Neutral | The npm package keeps its subpath entries and `sideEffects: ["**/*.css"]`, so a host's bundler includes only what it imports. |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| A host bundles the components and the tarball's UMF schema browser version differs from its own copy | Low | Medium | The package depends on the browser at the exact pin; `scripts/umf-schema-browser.ts` checks it |
| The built UI is missing from a wheel | Low | High | The release job asserts the page and tarball are in the installed wheel; a source checkout answers 503 and says how to build |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| `tests/test_ui.py` and the clean-interpreter wheel check pass; the page works under a path prefix with no policy violation | A host needs the page under a different policy, or a second consumer wants the core without the UI |

## Concern Impact

- **Selected**: `frontend-framework` stays unselected: the UI is a component of one package, not a framework for hosts.
