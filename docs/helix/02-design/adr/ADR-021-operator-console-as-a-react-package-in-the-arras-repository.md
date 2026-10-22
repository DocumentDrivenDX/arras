---
ddx:
  id: ADR-021
  type: adr
  activity: design
  status: proposed
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: FEAT-010
      kind: informed_by
    - id: ADR-010
      kind: informed_by
    - id: ADR-011
      kind: informed_by
    - id: ADR-015
      kind: informed_by
    - id: ADR-017
      kind: informed_by
    - id: ADR-005
      kind: constrained_by
    - id: ADR-016
      kind: informed_by
    - id: CONTRACT-001
      kind: informs
    - id: CONTRACT-003
      kind: informs
    - id: CONTRACT-004
      kind: informs
    - id: CONTRACT-006
      kind: informs
    - id: CONTRACT-009
      kind: informs
---

# ADR-021: The Operator Console is a React package in this repository, reached over HTTP

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-09 | Proposed | Erik LaBianca (architecture lead) | [FEAT-010](../../01-frame/features/FEAT-010-operator-console.md), [ADR-010](ADR-010-python-and-uv-as-the-arras-toolchain.md), [ADR-011](ADR-011-read-only-graphql-generated-from-the-type-registry.md), [ADR-015](ADR-015-writes-are-umf-actions-applied-by-providers.md), [ADR-017](ADR-017-backends-are-reached-with-the-users-own-token.md) | Medium |

Proposed records the direction under review; it does not claim implementation is complete.

## Context

| Aspect | Description |
|--------|-------------|
| Problem | FEAT-010 needs two things: an HTTP surface that binds the library's action and audit operations, and a dense, designed interface over it: tables, a relationship diagram, forms generated from action declarations, and audit views. GraphiQL and hand-written pages cannot carry that, and ADR-011 keeps the read-only console free of a frontend framework. The interface must run inside the embedding host and on its own host, and must not make the Python library carry a JavaScript toolchain or any state. |
| Current State | At the decision date, the read-only console served GraphiQL and Arras used Python 3.11/uv. A reference host supplied the React/TypeScript/Vite/Tailwind/TanStack stack comparison on 2026-10-09. Current package versions belong to this repository's manifests/lockfiles; an embedding host supplies its design system through ADR-029. No downstream frontend package is an upstream authority. |
| Requirements | Embeddable as React components in the embedding host and runnable standalone; only Arras's HTTP surfaces as its boundary (viewer's own token, no credential in the browser); no write path other than actions; typed against the published contracts; built and released from one repository so a contract change and the UI change land together. |
| Decision Drivers | Matching the host's stack avoids a second design system and build chain in the same app. The library has no Node dependency at run time, which keeps ADR-010 intact; the release builds the UI before the wheel (ADR-027). One repository keeps contract and UI changes in one review. |

## Decision

We will build the Operator Console as a React and TypeScript package in a `ui/` directory of this repository, published as the npm package `@documentdrivendx/arras-ui`, on the package-owned React, Vite, Tailwind and TanStack Query stack, with host compatibility governed by the published peer ranges and the replaceable design-system boundary (ADR-029). It exports the whole console and its parts as components for embedding, and a thin standalone host serves the same components. It reaches Arras only over HTTP: GraphQL for reads (CONTRACT-006) and JSON for actions and audit (CONTRACT-009). The Python package gains one module, `arras.operate`, an ASGI binding of `validate`, `invoke`, `invoke_batch`, `changes` and `loads` that accepts no write other than invoking a declared action; this is the change to the library that the decision accepts, and the library is otherwise unchanged. The wheel carries a build of the UI and the npm tarball (ADR-027); the source, the toolchain and the tests stay in `ui/`. A host may pass `authorize_action` to apply its own per-action approval. The Python package imports nothing from `ui/`, and `ui/` imports nothing from the Python package; a check fails the build on a violation, as FR-34 does for the host.

**Reuse.** Where UMF already has the interface, the console embeds it instead of building a second one. The module's registered UMF document is shown in UMF's own schema browser, the public npm package `@documentdrivendx/umf-schema-browser` (dual-licensed `MIT OR Apache-2.0`, with its bundled third-party notices), on which `ui/package.json` depends at an exact version; `package-lock.json` carries the registry tarball's integrity, and `ui/scripts/umf-schema-browser.ts` checks that the pin, the lockfile, the installed package and the registry agree and that the tarball is the GitHub release's digest. The build copies the installed package's `assets/` unchanged; nothing of the package is committed. The console reads the catalog with its own client from the operator surface (CONTRACT-009), maps it to the package's entries and calls `mountSchemaBrowser` under the package's host contract: the module is a `select`, the live registry's backends are `annotations` (replaced in place as the registry changes), the console's scheme and tokens are its theme, its events drive the console's own router, and its errors are the console's states. The host serves the package's static assets and gives the console's page UMF's strict CSP profile, which needs no `'unsafe-eval'`. The console's own Schema views stay for what the browser cannot show: each backend's full capabilities, the actions and cross-module stubs. UMF's exported property, record-map and comparison components were evaluated against the console's type cards and diagram and are not adopted yet (they drop cross-module endpoints, keep multiplicity only in the edge label, give the property table a fixed caption and one text cell, and their tone colours are not tokens). Improvements go back to UMF as requests, not as a fork.

**Key Points**: One repository, two toolchains, one release carrying both artifacts | HTTP is the only boundary, with the viewer's own token and no credential in the browser | The UI generates its client from CONTRACT-009's OpenAPI document and the meta GraphQL schema, introspects each module's schema at runtime, and checks `GET /version` when it loads | The wheel carries no UI assets; the standalone host is built and released from `ui/`

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| Extend GraphiQL and vanilla pages in the Python package | No new toolchain | Dense tables, a diagram and generated forms in hand-written JavaScript are costly to build well and to keep accessible | Rejected: cannot meet the density and design aim |
| React assets inside the `arras` Python package, built into the wheel | One install | The source would sit in the Python package, putting a Node toolchain and tests in a Python-only project (ADR-010); embedding as components still needs an npm package | Not the home of the source: it stays in `ui/`; the release builds it and the wheel carries the page and the npm tarball (ADR-027) |
| The host owns the HTTP endpoints and calls the library (the pattern ADR-011 names) | Arras ships no HTTP write surface; the host's own routing and approval apply | Every host re-implements validate, invoke, batch, encoding, origin rules and audit; no standalone use; the UI has no one typed surface | Rejected: duplicated and untyped; `authorize_action` gives the host its approval point without this |
| GraphQL mutations on a separate operator schema, beside the read-only one | One protocol, one error shape, one typed client; reuses CONTRACT-006's handler, limits and revision check | Needs a Mutation type in generated schemas, which CONTRACT-006's guarantee excludes for the console, so the schemas must be kept apart; `validate` and receipts fit mutations awkwardly | Rejected for now; reconsider if two error shapes (GraphQL `errors`, JSON `error`) become a burden |
| Human invocations routed through the host's own per-action classification (the host's per-action approval policy) rather than a generic invoke | Reuses the host's approval catalog | ADR-016 rejects a generic invoke because a host cannot classify one action differently; this surface is a generic invoke | Not an alternative to this decision but a constraint on it: met by `authorize_action` and by the host integration owners' agreement (see Risks) |
| A separate repository for the UI | Independent releases and ownership | Contract and UI changes land in two reviews with version skew; no evidence yet of a separate team or cadence | Rejected for now; reconsider if ownership or cadence diverges |
| Server-rendered pages (templates and htmx, a library for HTML-over-the-wire) in Python | No SPA build; small | A second way to host and test UI inside the library; the host integration is HTML fragments, not components; weaker for a diagram and rich tables | Rejected |
| A different framework from the embedding host | Free choice | A second build chain in the reference app and additional integration work | Rejected |
| **React package in `ui/`, HTTP-only, host-compatible public peers** | Native look in Databricks Apps; embeddable and standalone from one codebase; contract-typed; one small binding added to the library | A second toolchain in the repository (Node, npm); versions follow the package manifests and declared peer compatibility | **Selected: meets the embedding and density aims with the least coupling** |

## Consequences

| Type | Impact |
|------|--------|
| Positive | One UI codebase for the embedding host and standalone; one typed HTTP surface any host can mount; a host-replaceable design system (ADR-029); typed clients catch contract drift in CI; the read-only console and the library stay free of a frontend framework. |
| Negative | The library gains an HTTP write binding that needs its own security review (origin rules, concurrency, error scrubbing); the repository has two toolchains and two sets of release steps; host compatibility changes require checking the published package contract; the HTTP surfaces (CONTRACT-006 and CONTRACT-009) become the UI's compatibility contract. |
| Neutral | Two error shapes exist side by side: GraphQL `errors` (CONTRACT-006) and JSON `error` (CONTRACT-009). FEAT-007's console remains GraphiQL. The development host (console, operator surface and sandbox at one origin) is the sandbox; schema import and the role picker are the console's (ADR-026). The host still owns identity and proxies the viewer's token (ADR-017). |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| The host's React/toolchain versions leave the package's declared compatibility range | M | M | Keep package-owned versions and public peer ranges explicit; verify the selected host cohort and design-system contract (ADR-029) |
| A browser-side call reaches Arras without the viewer's token or through a cross-origin page | M | H | CONTRACT-009 accepts only JSON, requires an allowed `Origin` or `Sec-Fetch-Site: same-origin` on every `POST`, answers preflight only for allowed origins, derives its own origin from a host-set `public_origin`, and takes the principal from the host's hook; the UI holds no token |
| The host integration owners do not agree to mount a write-capable operator surface, which ADR-016 says the embedding host reaches only through stdio MCP | M | H | Raise it as a PRD open question before slice 1 builds; offer `authorize_action` so the host applies its per-action policy; fall back to the standalone host for operators |
| The operator surface is mistaken for a governed-write path (ADR-005 P3) | M | H | No approval or reversal is claimed; widening beyond administrators and builders waits for P3 to have an owner |
| Supply chain: the npm dependency tree and the publish name | M | M | A lockfile and audit in CI; published to npm under the `@documentdrivendx` scope by the release workflow with provenance, alongside the wheel on PyPI |
| The audit reads the record stores and replicas do not yet offer slip, leaving the audit area empty | H | M | Specify them in CONTRACT-004 and in the stores' own contracts first; ship schema, data and action areas without waiting; the audit area states what the backends do not record |
| The UI becomes an unreviewed second write path | L | H | CONTRACT-009 offers only validate, invoke and batch of declared actions; a contract test asserts no other write; the UI has no registry or import call |
| UMF's schema browser as a dependency: a new release can change the host contract or the assets, the deploy footprint of `assets/` is 18.9 MB (66 files, one 14.2 MB validator chunk, fetched only when needed), and its tone colours are not host-settable | M | M | An exact npm version with lockfile integrity, checked against the registry and the release digest in CI; byte-identical assets in the build, checked by test; a bump is a deliberate change that runs every tier against the real dev host; mounted only while the UMF source view is open; axe runs inside the frame in light and dark, and Playwright computes every tone's contrast where the browser draws it (heading, record map, legend) in both schemes and fails below 4.5:1; the remaining gaps are asked of UMF |
| Two toolchains slow contributors | M | L | One `just` entry point for both; Python tests do not need Node; `ui/` builds in its own CI job |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| The same `arras-ui` build runs embedded in the embedding host and standalone, and a builder completes the primary operator workflow (find a type, run a declared correction, read the attributed change) in a whole-stack test | The embedded build needs host-specific forks |
| The boundary check fails a build in which Python imports `ui/` or `ui/` imports Python | The check is bypassed or removed |
| A change to CONTRACT-006 or CONTRACT-009 fails the UI's CI until the client is regenerated | Drift reaches a deployed build |

## Concern Impact

- **Concern selection**: Selects the `frontend-framework` slot (React with Vite, TypeScript, Tailwind and TanStack Query, selected for the package) and the `admin-console` concern for FEAT-010, with the primary operator workflow exercised end to end through the UI. An end-to-end test tool is chosen at build.
- **Practice override**: ADR-011's "no Arras frontend framework" applies to the read-only console (FEAT-007) and the Python package, which remain unchanged. `docs/helix/01-frame/concerns.md` records the slot and the scope.

## References

- [FEAT-010](../../01-frame/features/FEAT-010-operator-console.md), [FEAT-007](../../01-frame/features/FEAT-007-admin-console.md)
- [CONTRACT-006](../contracts/CONTRACT-006-console-graphql-surface.md), [CONTRACT-009](../contracts/CONTRACT-009-operator-action-and-audit-surface.md)
- [ADR-010](ADR-010-python-and-uv-as-the-arras-toolchain.md), [ADR-011](ADR-011-read-only-graphql-generated-from-the-type-registry.md), [ADR-015](ADR-015-writes-are-umf-actions-applied-by-providers.md), [ADR-017](ADR-017-backends-are-reached-with-the-users-own-token.md)
