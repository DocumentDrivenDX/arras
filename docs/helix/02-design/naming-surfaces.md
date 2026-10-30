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
| Telemetry events/attribute names, logger `arras.telemetry`, tracer `arras`, `arras_event`/`arras_attrs`, internal call/context/thread names; `telemetry.py`, `callscope.py`, `console`, `operate`, `mcp` | Canonical instrumentation identities remain stable by default. The explicit downstream requirement also needs opt-in event, attribute and log namespace projection plus typed host service identity; existing host-owned Resources and formatting alone do not meet it. The scoped, failure-isolated seam has source review and 0.5.1 installed SDK receiver evidence; exact-tag publication and the fresh public-download repetition now pass, with their separate run identities retained. |
| Backend refusal origin `arras`, structured error/source paths, boundary checker messages, native schema/role identifiers (`arras_installer`, `arrasdev_`), `.arras` development state directories | These identify the component, persisted namespace or actual installation being diagnosed. They are not product wordmarks. Role/credential storage compatibility must not depend on display branding. |
| Upstream README/HELIX titles, ADR product decisions, source comments, package descriptions and canonical documentation links | Upstream documentation describes Arras. A downstream supplies its own documentation and package metadata. Governance artifacts are linked or extended by identity rather than copied. |

## B. Host-configurable presentation

| Surface and locations | Configuration/seam |
| --- | --- |
| Console/window/document title, product name, wordmark, tagline, logo; `branding.py`, `ui/__init__.py`, `ui/src/lib/brand.tsx`, provider/shell/browser entry components | Immutable `Brand`; `DistributionConfig.brand` for launcher composition. Runtime metadata is escaped and does not require rebuilding the page. A compiled host passes Brand through the public provider/component props. |
| Console GraphiQL title and operator OpenAPI title; `console.create_app`, `operate.create_app`, composed `ui.create_app` | The host may pass the title explicitly; composed UI forwards its Brand name to child surfaces. |
| Telemetry service identity, attribute namespace, event prefix and log route prefix; `distribution.py`, `telemetry.py`, typed ADR-019 configuration | Implemented and Sol source-reviewed (150 focused tests); 0.5.1 installed qualification passes 20 cases/eight phases/three controls: `DistributionConfig.telemetry: TelemetryNames` supplies explicit names; `TelemetryContext` selects a caller-owned provider and scoped projection. An explicit service name requires a matching provider Resource. Allowlist/redaction precedes projection; canonical defaults remain compatible. |
| MCP initialized server name; `mcp/server.py`, `mcp/config.py`, `mcp/process.py` | `DistributionConfig.mcp_server_name`; typed ADR-019 presentation configuration. Tool names use the separately validated alias below. |
| Devhost UI identity and startup presentation; `devhost.DevHost`, `mcp.config.Config.startup_line` | The `DevHost` constructor and public `devhost.main(argv=None, *, distribution=None)` accept explicit distribution composition. Help and startup presentation use the printable selected Brand; canonical argparse invocation and dependency diagnostics retain actual component identities. Source tests cover forwarding/banner sanitization and the 0.5.1 installed public-launcher proof passes; the public-wheel repetition passes in verification run `39883764998`. |
| Six design-system slots including Mark, theme appearance, light/dark colors, fonts, favicon; `ui/src/ds`, public provider, `ui/assets.py` | Compiled host replaces widgets/Mark. Runtime page theme supplies verified CSS/font/favicon assets and token values; arbitrary JavaScript/widget injection is not a runtime-theme feature. |
| Downstream documentation titles and npm/Python package display metadata | The downstream's own build/package owns them. They do not rename the upstream distribution or its exports. |
| Human-facing product-bearing messages | Use Brand where the message names the host product. Messages explaining actual public modules, version compatibility, installable dependencies or protocol origins name those canonical components. MCP help and argument diagnostics use the selected printable bootstrap Brand, and typed configuration diagnostics use the effective Brand. Source tests cover both custom and default presentation; canonical protocol and dependency diagnostics remain identifiable. |

## C. Explicit aliases supplied by the host

| Surface and locations | Alias and precedence rules |
| --- | --- |
| Python shim import and CLI command | Downstream-owned package/entry point explicitly imports public Arras symbols. `arras.mcp.launch(argv=None, *, distribution=...)` supplies composition without executing a hard-coded downstream module. Backend objects and action handlers are registered by calls; no display-name-derived plugin imports. |
| MCP fixed/action tool exposure; `mcp/server.py` | Optional validated `mcp_tool_prefix` plus underscore; check collisions and maximum exposed length. Preserve canonical action IDs/versions/errors. Registry changes require a new tools listing before calls can bind newly exposed names. |
| Process environment (`ARRAS_ENV`, `ARRAS_CONFIG_DIR`, `ARRAS_OPS_FILE`, `ARRAS_TOKEN`, `ARRAS_TOKEN_FILE`, `ARRAS_USER_CLAIM`, `ARRAS_LOG_LEVEL`, `ARRAS_DEV_SANDBOX`, `ARRAS_DEV_USER`, `ARRAS_BACKEND_<NAME>_ENDPOINT`); `mcp/config.py` | Explicit bootstrap `env_prefix` selects `<PREFIX>_*` aliases with nonblank custom values over canonical fallback. Do not infer the prefix from the displayed product name or a config file selected through it. Unknown selected-prefix keys refuse. Conflicting credential values and token/token-file sources across both namespaces refuse before precedence. Any other key set in both namespaces to different nonblank values uses the custom value and records a bounded warning (at most eight lines) that names both variables and the one used. Values never appear in diagnostics. |
| Development-only `ARRAS_TRUSS_DEV_URL`/`ARRAS_TRUSS_DEV_CREDENTIALS`, native/test controls and development state paths | Separate explicit devhost flags/host-owned inputs; not silently included in the MCP prefix alias set. Preserve documented scope. A downstream wrapper maps its own development options explicitly. |
| Logger/event/telemetry attribute aliases | Implemented and source-reviewed, with 0.5.1 installed receiver and fresh public-delivery qualification passing: typed TelemetryNames and TelemetryContext provide scoped event/attribute/log projection through DistributionConfig/ADR-019. Explicit service identity requires a matching host-owned provider Resource. No global provider/logger mutation or fallback from an explicit failed provider is allowed. This requirement has not been waived. |

## Verification boundary

Source/public-catalog/config/MCP/UI tests qualify the implemented names and alias
rules. The external shim, installed-wheel process invocation, themed browser run
and offline doctor provide separate release evidence. This inventory does not
claim registry publication, full official-UMF execution, or arbitrary automatic
plugin discovery. Source review has resolved the human-facing launcher gaps. The packaged ADR-019
`config/default.toml` exists and the final installed consumer covers resource
origin, doctor and public launcher selection. Frozen wheel SHA-256 is
`59827644e2e423980afed1047f75c7130dc5d8c542778df4b62a9e2244cdc24c`;
its carried npm SHA-256 is
`460e1b1037d4965d17af8b3e689c364c22b51a09cc9d3d64c8ddf0296e34c943`.
It passed 20 doctor cases, eight SDK phases and three false-pass controls on
Darwin arm64/27.0.0, CPython 3.13.16 and OpenTelemetry API/SDK 1.45.1. The
[final SDK review](../04-build/evidence/arras-0.5.1-sdk-example-review-20261022.json) matches
receipt SHA-256 `baa9334e26936908bc1fabe6e6e6b3e630c92e1bd9cede907ceb1a6341527b2f`,
verifier SHA-256 `9aa379d1f2b333f855aa9886da7b6e93dcf930bc789a3721e0862ee174c08455`
and generated probe SHA-256
`2dd054ff5b832f279195d8e644027474181ff247d29d6b59ee0e8c2889836e0f`.
Actual phases cover direct/MCP/worker-backed console/Operate, concurrent/nested
hosts, restoration, finish-time snapshots and provider faults. The controls
reject successful empty MCP/HTTP responses and finish-time ambient misrouting.
Selected structured operation/query records witness events; these are not SDK
`Span.events`. Earlier temporary receipts remain historical. This SDK proof does
not qualify native behavior; public Truss 0.0.48/Weft 0.4.51 evidence is separate.
The delivered 17d wheel/76fc npm cohort also passes the actual Linux
Python 3.11.17/OpenTelemetry 1.45.1 doctor/SDK repetition after anonymous download
in run `39883764998`. The [final review](../04-build/evidence/arras-0.5.1-public-verification-review-20261023.json)
retains this separate cohort and the original Mac receipts; no native or live
server claim follows from the mocked development forwarding checks.
