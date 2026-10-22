---
ddx:
  id: arras.naming-surfaces
  type: solution-design
  activity: design
  status: draft
  authoring:
    home: repo
  links:
    - id: arras.downstream-extensibility
      kind: informed_by
    - id: CONTRACT-005
      kind: informed_by
    - id: CONTRACT-007
      kind: informed_by
    - id: CONTRACT-008
      kind: informed_by
    - id: ADR-019
      kind: informed_by
---

# Distribution naming surfaces

This inventory distinguishes the upstream library's identity from the product a
host presents. It covers Python source, UI source, the public catalog, packaging,
process configuration and the governed documentation. It is a surface inventory,
not a requirement to substitute every occurrence of a word.

A 2026-10-22 working-tree scan found 913 case-insensitive occurrences in 85 of 90
Python files under `src/arras`, and 810 in 118 of 345 TypeScript/TSX/CSS files under
`ui/src`, including tests and comments. These counts describe that snapshot only;
parallel changes and release builds can change them. Python string-literal review
and targeted UI/process inspection distinguish displayed product text from import,
protocol and developer diagnostics. The machine-checked public surface remains
`src/arras/public-api.json`; these counts are not an API compatibility gate.

## A. Stable upstream identity

| Surface and locations | Policy and downstream guarantee |
| --- | --- |
| `arras` distribution/imports; `Arras`, `ArrasError`, public symbols throughout `src/arras`; `pyproject.toml`; `ui/package.json` | Keep canonical names. A shim explicitly reexports public symbols and pins the upstream package. It does not rewrite `sys.modules` or internal imports. |
| Public entry modules `arras.mcp`, `arras.devhost`, `arras.ui`, `arras.boundary`; help text naming their invocation; package-install instructions in `mcp/backends.py` and `adapters/truss/__init__.py` | Keep actual upstream commands and dependency identities. A downstream command delegates through its own entry point. A display name never becomes a module import path. |
| Contract IDs/runtime keys (`versions.py`), `arras.view` (`view.py` and packaged vocabulary), `arras.graph` (`graphfile.py`, `ui/src/browser/graphFile.ts`), explorer `arras:<module>` IDs (`operate/explorer.py`, `ui/src/areas/umfBrowser.ts`) | Wire/resource identities remain stable and versioned. Product branding never changes stored documents, view vocabulary, correlation IDs or error codes. |
| CSS `.arras-root`, `.arras-*`, `--arras-*`; `ui/src/components/Scope.tsx`, `ui/src/ds`, component CSS/classes, scoping scripts | Stable selectors and eighteen role-token names are part of compatibility. Hosts replace values and widget implementations. No selector-prefix substitution is required or supported. |
| `arras-brand` metadata (`ui/__init__.py`, `ui/src/lib/brand.tsx`), `arras-arrow` internal SVG ID, `x-arras-user`/`x-arras-role` development headers | Integration identifiers remain canonical; metadata carries configurable values. Development headers are not production authentication or branding. |
| Telemetry events/attribute names, logger `arras.telemetry`, tracer `arras`, `arras_event`/`arras_attrs`, internal call/context/thread names; `telemetry.py`, `callscope.py`, `console`, `operate`, `mcp` | Canonical instrumentation identities remain stable by default. The explicit downstream requirement also needs opt-in event, attribute and log namespace projection plus typed host service identity; existing host-owned Resources and formatting alone do not meet it. The scoped, failure-isolated seam is source-reviewed and has corrected temporary installed SDK receiver evidence; final frozen-cohort repetition and delivery remain release gates. |
| Backend refusal origin `arras`, structured error/source paths, boundary checker messages, native schema/role identifiers (`arras_installer`, `arrasdev_`), `.arras` development state directories | These identify the component, persisted namespace or actual installation being diagnosed. They are not product wordmarks. Role/credential storage compatibility must not depend on display branding. |
| Upstream README/HELIX titles, ADR product decisions, source comments, package descriptions and canonical documentation links | Upstream documentation describes Arras. A downstream supplies its own documentation and package metadata. Governance artifacts are linked or extended by identity rather than copied. |

## B. Host-configurable presentation

| Surface and locations | Configuration/seam |
| --- | --- |
| Console/window/document title, product name, wordmark, tagline, logo; `branding.py`, `ui/__init__.py`, `ui/src/lib/brand.tsx`, provider/shell/browser entry components | Immutable `Brand`; `DistributionConfig.brand` for launcher composition. Runtime metadata is escaped and does not require rebuilding the page. A compiled host passes Brand through the public provider/component props. |
| Console GraphiQL title and operator OpenAPI title; `console.create_app`, `operate.create_app`, composed `ui.create_app` | The host may pass the title explicitly; composed UI forwards its Brand name to child surfaces. |
| Telemetry service identity, attribute namespace, event prefix and log route prefix; `distribution.py`, `telemetry.py`, typed ADR-019 configuration | Implemented and Sol source-reviewed (150 focused tests); corrected temporary 20-case/eight-phase installed SDK receiver qualification passes; final frozen-cohort repetition remains required: `DistributionConfig.telemetry: TelemetryNames` supplies explicit names; `TelemetryContext` selects a caller-owned provider and scoped projection. An explicit service name requires a matching provider Resource. Allowlist/redaction precedes projection; canonical defaults remain compatible. |
| MCP initialized server name; `mcp/server.py`, `mcp/config.py`, `mcp/process.py` | `DistributionConfig.mcp_server_name`; typed ADR-019 presentation configuration. Tool names use the separately validated alias below. |
| Devhost UI identity and startup presentation; `devhost.DevHost`, `mcp.config.Config.startup_line` | The `DevHost` constructor and public `devhost.main(argv=None, *, distribution=None)` accept explicit distribution composition. Help and startup presentation use the printable selected Brand; canonical argparse invocation and dependency diagnostics retain actual component identities. Source tests cover forwarding and banner sanitization; final installed-artifact proof is a separate release gate. |
| Six design-system slots including Mark, theme appearance, light/dark colors, fonts, favicon; `ui/src/ds`, public provider, `ui/assets.py` | Compiled host replaces widgets/Mark. Runtime page theme supplies verified CSS/font/favicon assets and token values; arbitrary JavaScript/widget injection is not a runtime-theme feature. |
| Downstream documentation titles and npm/Python package display metadata | The downstream's own build/package owns them. They do not rename the upstream distribution or its exports. |
| Human-facing product-bearing messages | Use Brand where the message names the host product. Messages explaining actual public modules, version compatibility, installable dependencies or protocol origins name those canonical components. MCP help and argument diagnostics use the selected printable bootstrap Brand, and typed configuration diagnostics use the effective Brand. Source tests cover both custom and default presentation; canonical protocol and dependency diagnostics remain identifiable. |

## C. Explicit aliases supplied by the host

| Surface and locations | Alias and precedence rules |
| --- | --- |
| Python shim import and CLI command | Downstream-owned package/entry point explicitly imports public Arras symbols. `arras.mcp.launch(argv=None, *, distribution=...)` supplies composition without executing a hard-coded downstream module. Backend objects and action handlers are registered by calls; no display-name-derived plugin imports. |
| MCP fixed/action tool exposure; `mcp/server.py` | Optional validated `mcp_tool_prefix` plus underscore; check collisions and maximum exposed length. Preserve canonical action IDs/versions/errors. Registry changes require a new tools listing before calls can bind newly exposed names. |
| Process environment (`ARRAS_ENV`, `ARRAS_CONFIG_DIR`, `ARRAS_OPS_FILE`, `ARRAS_TOKEN`, `ARRAS_TOKEN_FILE`, `ARRAS_USER_CLAIM`, `ARRAS_LOG_LEVEL`, `ARRAS_DEV_SANDBOX`, `ARRAS_DEV_USER`, `ARRAS_BACKEND_<NAME>_ENDPOINT`); `mcp/config.py` | Explicit bootstrap `env_prefix` selects `<PREFIX>_*` aliases with nonblank custom values over canonical fallback. Do not infer the prefix from the displayed product name or a config file selected through it. Unknown selected-prefix keys refuse. Conflicting credential values and token/token-file sources across both namespaces refuse before precedence. Values never appear in diagnostics. |
| Development-only `ARRAS_TRUSS_DEV_URL`/`ARRAS_TRUSS_DEV_CREDENTIALS`, native/test controls and development state paths | Separate explicit devhost flags/host-owned inputs; not silently included in the MCP prefix alias set. Preserve documented scope. A downstream wrapper maps its own development options explicitly. |
| Logger/event/telemetry attribute aliases | Implemented and source-reviewed, with corrected temporary installed receiver qualification passing and final frozen-cohort release qualification pending: typed TelemetryNames and TelemetryContext provide scoped event/attribute/log projection through DistributionConfig/ADR-019. Explicit service identity requires a matching host-owned provider Resource. No global provider/logger mutation or fallback from an explicit failed provider is allowed. This requirement has not been waived. |

## Verification boundary

Source/public-catalog/config/MCP/UI tests qualify the implemented names and alias
rules. The external shim, installed-wheel process invocation, themed browser run
and offline doctor provide separate release evidence. This inventory does not
claim registry publication, full official-UMF execution, or arbitrary automatic
plugin discovery. Source review has resolved the human-facing launcher gaps. The packaged ADR-019
`config/default.toml` exists and the corrected temporary installed consumer covers
resource origin, doctor and public launcher selection. The superseding wheel is
`cdc7ec0d7b5c907ef079ed9f41f60aa07656951dea60be685a8ff049764c8261`, qualified
by 20 cases and eight SDK phases on CPython 3.13.16/macOS arm64 with OTel API/SDK
1.45.1. The [SDK source review](../04-build/evidence/arras-sdk-source-review-20261022.json)
binds verifier source SHA-256
`356fe79ed6ea060ae48a9e90af33d16bd20a884b580ac937bec579a4e6c317c4` and generated
probe SHA-256 `2dd054ff5b832f279195d8e644027474181ff247d29d6b59ee0e8c2889836e0f`
to that fresh receipt and records independent successful-response no-op and
finish-time misrouting controls. Selected structured operation/query records
supply phase event witnesses; these are not SDK `Span.events`. The candidate
retains historical native pins. Final frozen-cohort launcher/configuration/SDK
repetition, tag/Linux/public downloads and delivery remain pending; this evidence
does not qualify a final native cohort or the full themed UI suite.
