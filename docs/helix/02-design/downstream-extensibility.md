---
ddx:
  id: arras.downstream-extensibility
  type: solution-design
  activity: design
  status: draft
  authoring:
    home: repo
  links:
    - id: architecture
      kind: informed_by
    - id: CONTRACT-005
      kind: informed_by
    - id: ADR-005
      kind: informed_by
    - id: ADR-019
      kind: informed_by
    - id: ADR-022
      kind: informed_by
    - id: ADR-027
      kind: informed_by
    - id: ADR-029
      kind: informed_by
---

# Downstream distribution and extensibility

## Scope and decision

Arras is the reusable upstream source of truth. Downstream distributions consume
pinned artifacts and own their composition, presentation, policy and content.
Arras must not require a downstream package, private registry, customer-specific
configuration or downstream fixture. The same seams must serve independent consumers.

Use the existing public APIs, Brand, design-system provider, configuration and
boundary checks as the starting point. Strengthen their contracts and remove
transport/host coupling as the affected slices change. Making every internal name
configurable or publishing every internal layer separately adds unnecessary APIs.

Reassessed on 2026-10-22 against the working source, deliberate public catalog,
binding contracts and coordinated EX-01–EX-08 execution. `exists` means a named
subset is implemented; `partial` means material qualification or delivery remains;
`missing` identifies an absent implementation. Costs describe the remaining
relative scope. A bound interface, an implemented interface, a qualified cohort
and a published artifact are separate facts.

Arras 0.5.1 is [published on GitHub](https://github.com/DocumentDrivenDX/arras/releases/tag/v0.5.1)
with all sixteen assets (fifteen covered by SHA256SUMS). The eight EX seams below are **exists —
qualified and delivered for the recorded subset**. Publication run
[`39879533273`](https://github.com/DocumentDrivenDX/arras/actions/runs/39879533273)
passed all prepublication gates and created the immutable assets; its later
consumer orchestration failed. Reviewed verification-only run
[`39883764998`](https://github.com/DocumentDrivenDX/arras/actions/runs/39883764998)
then passed the fixed reusable installed consumer and complete anonymous
public-download qualification. These are separate runs; original receipts and
`not_run_at_assembly` remain unchanged. See the
[final independent review](../04-build/evidence/arras-0.5.1-public-verification-review-20261023.json).

The delivered wheel is
`17d50dedeaf9d4f7d27e0eb30cb16539bfa75de3a138dc9351284c2e2f390d4b`, carrying npm
`76fc29a5a24747ef26d0e04263f1f8924034244b1169a41fb865e02274485e1f`;
the source archive is
`541aa91ae970ac16644679614d74b858f1a46e303b6429e0c10804c24bc0dd45`.
Public SUMS digest is
`43c41e44c3634724f0bccd0b92ee882f0771138044b5abbbde097890c839503c`;
aggregate digest is
`a84811a71b0180de8e3f2c225732c9c47410476d0389c229ef92090bf6314d7c`.
Actual downloaded bytes pass distribution parity, 20 doctor/SDK cases with eight
phases and three false-pass controls, four fresh example tests and 72 applicable
memory corpus cases, and all 205 Linux nonvisual themed UI cases and controls.

The separate Mac component wheel `59827644e2e423980afed1047f75c7130dc5d8c542778df4b62a9e2244cdc24c`
and npm `460e1b1037d4965d17af8b3e689c364c22b51a09cc9d3d64c8ddf0296e34c943`
retain their original receipts: 272 ordinary themed cases, unchanged 67 canonical
and eight narrow reviewed baselines, and the named installed SDK/native cohorts.
The [reviewed payload bridge](../04-build/evidence/arras-0.5.1-binary-bridge-peer-review-20261023.json)
proves identical decompressed npm payloads; compressed container bytes differ.
This is not Mac execution of the delivered Linux-built wheel. Native annotations,
official UMF adoption and managed deployments retain their explicit limits below.
PyPI/npm uploads are deferred under the human instruction; GitHub assets are the
delivery route. The [build plan](../04-build/arras-integration-plan-20261022.md)
retains failed attempts and all scoped evidence; the
[naming inventory](naming-surfaces.md) keeps canonical identity separate from host presentation.

Governing sources: [Architecture](architecture.md), [embedding CONTRACT-005](contracts/CONTRACT-005-embedding-and-lifecycle.md),
[typed configuration ADR-019](adr/ADR-019-the-mcp-process-reads-one-typed-configuration.md),
[closed view vocabulary ADR-022](adr/ADR-022-a-modules-presentation-is-declared-in-a-closed-umf-view-vocabulary.md),
[UI packaging ADR-027](adr/ADR-027-the-wheel-carries-the-ui-as-a-mountable-app-and-an-npm-tarball.md)
and [design system ADR-029](adr/ADR-029-the-ui-draws-through-a-pluggable-design-system-seam-with-a-built-in-default.md).
Exact new interfaces belong in the affected contracts before implementation.

## Embedded composition ownership

CONTRACT-005's embedded API/compiled UI surface governs the 0.6.4 candidate.
Python core, independent ASGI bindings and public React entrypoints remain one
release cohort. Hosts can serve only the APIs and bundle only their selected UI
components. Runtime assets for UMF source viewing remain an explicit host task.

Identity/API changes replace all Arras-owned UI state before new-session render;
shared caches are allowed only within the same identity/API scope. Controlled
Explore owns no host history state. Page effects can be disabled, and individual
areas receive a CSS root through the provider. Accessibility IDs, focus requests
and edit-dialog portals must remain within their component instance.

The supported distribution boundary is the deliberate public catalog, Python
boundary checker and npm export map. Publishing extra internal modules or
separate Python core/API wheels is not required for flexibility. The
[component guide](../../../ui/README.md#embed-in-a-host) demonstrates composition;
qualification and publication status belong in the build plan and release notes.

## Coverage and remaining boundaries

| Concern | Queue / governing specification | Delivered seam and acceptance | Remaining boundary |
| --- | --- | --- | --- |
| Distribution | EX-01; CONTRACT-005/public catalog | Public catalog, wheel/sdist/npm parity, sixteen GitHub assets and complete anonymous installed-consumer proof | Registry delivery deferred; unrun platforms unqualified |
| Naming | EX-02; ADR-018/019, CONTRACT-005/007/008 | Typed Brand/config, shim launchers, environment aliases and scoped telemetry; public-wheel doctor/SDK 20 cases/eight phases/three controls pass | Canonical import/wire/CSS/signal identities remain stable |
| Theming/UI split | EX-03; ADR-027/029, CONTRACT-005 | Host-built six-slot theme and runtime assets; public 17-spec testkit; downloaded Linux 205 and separate Mac 272 with payload bridge | Visual baselines qualify Mac only; theme packages remain host-owned |
| Operator/policy | EX-04; CONTRACT-005/007/009/010/011, ADR-005 | Callbacks, schema forwarding, PolicyBackend/refusal and optional annotation port delivered and reviewed | Annotation atomicity proof is synthetic; native annotations/source entitlement unqualified |
| Modules/content | EX-05; CONTRACT-002/003/010, ADR-022 | Downloaded explicit module/seed/graph example passes four tests and memory 72/seven replica-only inapplicable cases | Official profiles and new view terms require separate upstream work |
| Backends/deployment | EX-06/07, A7; CONTRACT-004/005 | Stable per-person credentials, host factories/connections and packaged conformance harness; Linux source 199/native corpus 64/eight limits/seven inapplicable | Deployment-specific qualification and production credential custody remain host-owned |
| Downstream CI | EX-07; TP-001/architecture | Fixed reusable job and full anonymous consumer pass; no-copy Python/UI testkits and generic content gate delivered | Optional native/theme targets qualify only when explicitly run |
| Upgrades | EX-08; CONTRACT-005/catalog | Offline doctor, compatibility/deprecation rules and per-seam release notes; positive/breaking/no-I/O public-wheel checks pass | Static checks cannot establish runtime capability or deployment compatibility |

All eight delivery rows close against the actual public cohort. Additional
semantic/provider/deployment capabilities remain separate work, not implied by
an implemented extension port.

## Compatibility and qualification matrix

Version declarations define candidate compatibility; the evidence column limits
what is actually qualified. `pgserver-pg18` 18.6.1 is the Python distribution
version; it must not be presented as an observed PostgreSQL server patch version.
The source suite separately asserts client libpq 18.6. The exact release bundle binds its own wheel, platform and native cohort;
component runtimes remain separate.

| Component/cohort | Selected versions | Evidence and limit |
| --- | --- | --- |
| Arras Python/UI | `0.5.1`; Python requirement `>=3.11`, declared 3.11/3.12/3.13 | Delivered 17d wheel/76fc npm; separate Mac 598/460 payload-equivalent cohort. Declarations alone do not qualify every interpreter/platform |
| Native Linux x86_64 | Truss `0.0.48`, Weft `0.4.51`, `pgserver-pg18` `18.6.1`, CPython 3.11 | Actual publication source 199 and installed corpus64/eight declared limits/seven replica-only inapplicable pass; seven native archive identities are bound |
| Native macOS arm64 | Same public native tuple; CPython 3.11 | Historical source suite 199 passes, retained by reviewed native-source equivalence. Fresh exact-0.5.1 installed CLI corpus: 64 passes/eight declared limits/seven replica-only inapplicable, no failures/harness errors; seven selected distribution payloads verified. No system dynamic-link audit |
| Native distribution floors | Linux x86_64 glibc `2.27`; macOS arm64 `14` | Static maximum dependency floors, not execution on those OS minima; exact seven-archive inputs live under `tests/downstream/native-cohorts/` |
| Installed SDK macOS arm64 | Python `3.13.16`, OpenTelemetry API/SDK `1.45.1`, graphql-core `3.3.0` | Doctor 20 cases/eight phases/three controls; no native inference |
| Fresh installed example macOS arm64 | Python `3.11.17`; example-extension-host `0.1.0` | Four tests; memory corpus 72 passes/seven replica-only cases inapplicable; no native inference |
| UI macOS arm64 | Node `26.12.1`, React/ReactDOM `19.3.0`, TypeScript `6.0.3`, Vite `8.3.2`, Playwright `1.63.0`, axe `4.13.0`, Chromium `153.0.8010.12` | Historical capture approvals retained; current 0.5.1 ordinary comparison 272 passes, all 67 approved baselines unchanged |
| Public SDK/example Linux x86_64 | Python `3.11.17`, OpenTelemetry API/SDK `1.45.1`, graphql-core `3.3.0` | Downloaded doctor 20/eight phases/three controls, fresh example 4 and memory 72/seven replica-only inapplicable pass |
| UI Linux x86_64 | Node `24.21.0`, npm `11.19.0`, React `19.3.0`, TypeScript `6.0.3`, Vite `8.3.2`, Playwright `1.63.0`, axe `4.13.0`, Chromium `153.0.8010.12` | Actual downloaded packed consumer 205 nonvisual cases and controls pass; visual project explicitly skipped on Linux |
| Document/view/rendering profiles | Selected legacy Arras document/action subset; `arras.view` `0.1.0`; schema-browser npm `2.0.0` | Original bytes retained and explicit profile refusal; official core `0.10.0` (`umf-v0.5.4`) has A1 source-validity evidence only; A2 admission/projection is separately gated |

## 1. Distribution — exists for the recorded 0.5.1 subset

**Current state:** `src/arras/public-api.json` is the schema-versioned deliberate
catalog for selected Python modules/symbols, CONTRACT-001–011 mappings, UI
runtime/types/styles, config/CLI/env names, canonical CSS/tokens and telemetry.
`arras.boundary` derives its host allowlist from the carried catalog. Source and
packed parity tests fail on drift rather than widening the surface. The selected
host catalog now explicitly covers `arras.ui.assets.load_manifest`/`AssetManifest`
and lazy `arras.conformance.truss.TrussHarness`; a separate launcher map admits
only `arras.mcp.launch` to host-owned commands. Broader MCP exports and private
asset/native/value helpers remain forbidden. A concrete consumer smoke imports
the promised seams, constructs inert values, exercises policy refusal before
provider delegation and validates a synthetic theme; independent no-SDK controls
keep native construction lazy. This closes the source catalog gaps, not final
installed/native qualification. The exact
artifact verifier checks source-derived dependency metadata, complete `arras/`
payload equality, carried npm bytes and separate clean installed source-wheel /
sdist-rebuilt-wheel consumers. Earlier local proof is scoped to its recorded
interpreter/platform and linked-JS dependency method.

**Decision/seam:** retain the reviewed catalog and separate package, catalog,
contract and vocabulary version domains. At 0.x a breaking package API change
increments the minor version; patches preserve it. Existing contract-specific
deprecation grace remains. The wheel carries the exact scoped npm tarball, so a
host can consume artifacts without requiring a registry upload.

**Gap/cost:** scoped distribution delivery is complete. Public wheel, source archive,
carried npm and all sixteen assets pass pinned digests, source/sdist parity and
fresh anonymous consumers. Registry delivery is explicitly deferred. Future
platform qualification or additional public surfaces need their own bounded work.
The release checklist and CONTRACT-005 distinguish original single-run
prepublication assembly from the reviewed, read-only supplemental verification;
no evidence is relabelled or reassembled across those runs.

## 2. Naming — exists for the recorded 0.5.1 subset

**Current state:** `arras.branding.Brand` is the same class reexported by
`arras.ui.Brand`. `arras.distribution.DistributionConfig` composes Brand,
`mcp_server_name`, optional `mcp_tool_prefix` and explicit bootstrap `env_prefix`
without ambient I/O. ADR-019's typed reader merges committed presentation fields
and selected aliases. Nonblank custom values override canonical fallback;
conflicting credentials across both namespaces refuse before source selection.
MCP validates exposed names on initialization and registry changes; last-listed
aliases never silently retarget another action. `arras.mcp.launch` is the callable
shim entrypoint. Both MCP and development launchers use the selected printable
Brand for human help/banner labels while preserving canonical invocation names.
`arras.devhost.main` is explicitly public as a development-only seam; unrelated
development internals are not promoted.

| Surface | Classification and guarantee | Current seam / qualification |
| --- | --- | --- |
| Python/package identities, types, contract/vocabulary/action IDs and wire codes | (a) Canonical Arras identity | Explicit public shim reexports; no import rewriting |
| `.arras-root`, component classes and eighteen `--arras-*` tokens | (a) Stable namespace | Host supplies values/widgets; renaming is a breaking upstream change |
| Titles, wordmark, tagline, Mark and product-bearing UI text | (b) Host presentation | Shared Brand and escaped runtime injection; no page rebuild |
| MCP server display name and exposed tool prefix | (b)/(c) Explicit typed presentation/alias | Canonical qualified actions/version meanings remain unchanged |
| Telemetry Resource `service.name` | (b) Typed host-owned attribution | Source-reviewed TelemetryNames + explicit matching host provider Resource; 0.5.1 installed receiver proof passes; public-wheel repetition passes |
| Event/attribute/log namespace prefixes | (b) Explicit host-scoped projection | Source-reviewed per-context output aliases after default-deny validation; 0.5.1 installed witnesses pass; canonical definitions/origin keys/defaults preserved; public-wheel repetition passes |
| Tracer instrumentation scope | (a) Canonical library identity | `arras` scope unchanged; host provider owns service Resource and exporters |
| Human error/help/banner product label | (b) Host presentation | Bootstrap Brand before config, effective Brand after load; printable/redacted; canonical invocation/dependency names remain truthful |
| Downstream docs and package display metadata | (b) Consumer-owned | Upstream docs and actual npm/Python identities stay canonical |
| Own import/command name | (c) Thin downstream shim | Public MCP/development callables, explicit host factories; no `sys.modules` or import-by-string loader |
| Environment prefix | (c) Explicit alias with fallback | `<PREFIX>_*` plus canonical `ARRAS_*`, preserving identity conflict checks and key provenance |

**Decision/seam:** the exact fields/signatures and bounds are now bound in
CONTRACT-005/007 and catalogued deliberately. Reuse one effective configuration
across host surfaces, keep credentials/handles separate, and never derive an
identity or import path from a display name. The [naming census](naming-surfaces.md)
records source locations and qualified snapshot counts; token counts are not API
compatibility tests.

**Gate/cost:** small remaining exact-tag/public-download delivery. The implemented
CONTRACT-005/008 and ADR-018/019 seam supplies immutable `TelemetryNames`, public
`TelemetryContext.activate`/`wrap_asgi`, and a launcher provider factory receiving
validated effective configuration. Explicit service names require an exactly
matching host-owned provider Resource. Existing allowlists/redaction precede
projection; no global provider mutation or fallback is permitted. Executor
submissions carry fresh copied context and diagnostics retain class-only errors.

The [0.5.1 SDK review](../04-build/evidence/arras-0.5.1-sdk-example-review-20261022.json)
qualifies the current wheel on Darwin arm64/27.0.0, Python 3.13.16 and OpenTelemetry
API/SDK 1.45.1: 20 cases, eight phases and three false-pass controls. The phases
cover direct calls, MCP, worker-backed console/Operate, concurrent/nested hosts,
nested restoration, finish-time snapshots and provider faults. Current verifier
SHA-256 is `9aa379d1f2b333f855aa9886da7b6e93dcf930bc789a3721e0862ee174c08455`;
generated probe SHA-256 is
`2dd054ff5b832f279195d8e644027474181ff247d29d6b59ee0e8c2889836e0f`.
Selected structured operation/query records witness phase events; they are not
SDK `Span.events`. Earlier temporary SDK receipts remain historical.

The same installed proof exercises packaged ADR-019 `config/default.toml` and
public MCP/development launcher selection, custom help/refusal, alias fallback,
override and credential-conflict controls. The fresh four-test example separately
proves public launcher/config/module composition. `arras.mcp.config.Config`
remains private. Mocked development forwarding/banner checks qualify wiring,
not live server/native behavior or development argparse value redaction. The
SDK receipt's conservative historical native-pin boilerplate establishes no
native behavior; the public 48/51 native tuple has separate qualification.

## 3. UI split and theming — exists for the recorded 0.5.1 subset

**Current state:** six widgets including Mark, eighteen role tokens, default
light/dark appearance and packed public provider/types exist. The mountable page
now accepts page/theme asset manifests; validation is bounded, same-origin,
canonical-path/hash/MIME/cohort checked and revalidated before serving. Theme
assets use digest-addressed routes and correct mounted paths. The exact contract
is in CONTRACT-005 and ADR-027/029. Independent consumption does not require a
new repository or another Python wheel; the first release keeps component
versions in one tested cohort.

**Decision/seam:** both routes are supported:

1. A host builds from public UI/provider/types plus its packed theme package,
   replacing widgets/Mark and supplying CSS/fonts/favicon.
2. A prebuilt page consumes an inert runtime theme manifest for CSS/font/favicon
   and Brand. It retains stock widgets; arbitrary React replacement requires
   the host-build route.

Arras retains layout, routing, dialogs/focus orchestration and API behavior.
Widgets must preserve labels, descriptions, refs, busy/disabled/error and keyboard
props. One host React/ReactDOM serves the package and theme; an upstream private
design-system dependency is unnecessary. CSS/token identifiers stay canonical.

**Gate/cost:** small remaining exact-tag/public-download delivery work.
The public Node-only `./testkit` exports `createAcceptanceConfig`; browser-only
`./testkit/host` exports `AcceptanceHost`. They share all 17 canonical specs and
83 hash-verified resources with upstream source. Explicit standard/schema URLs,
expected Brand/surfaces, output and per-theme baseline directories remove checkout
and fixed-origin assumptions. Neither Arras nor the checker requires a private
theme registry, application data, copied tests or implicit browser installation.

The [real theme package](../../../tests/downstream/theme-package/package.json)
exports compiled JS/declarations, CSS and favicon. The two installed routes use
its exact packed bytes with one React. On the historical 0.5.0 07b wheel, all four narrower
Explore/Operate routes compare against eight
[reviewed macOS images](../04-build/evidence/arras-narrow-eight-visual-review-20261022.json).
Their token/contrast/axe/focus/provider/palette controls remain intact. The full
portable capture then passed 272/272 (132 Chromium, three schema-administration,
70 browser, 67 visual), with zero failures/skips and four successful negative
controls. Sol [reviewed all 67 canonical images](../04-build/evidence/arras-neutral-theme-67-visual-review-20261022.json).
The capture receipt reports `updated-unreviewed`. After review, the ordinary run
with updates disabled passed 272/272 and compared all 67 unchanged baselines; its
receipt SHA-256 is `91f1a5af1c2b78b187d1726d66c96a3682251e189abd2834f9c2531beb17a819`. Existing volatile-content masks
qualify the visual review's coverage. The fresh 0.5.1 ordinary comparison also
passes 272/272 and all four routes, with unchanged baseline hashes; its receipt
SHA-256 is `2538efc8242bec4390865953e6d575b00439fff7134bc566f07a880374071b78`.
[Sol's current review](../04-build/evidence/arras-0.5.1-ui-review-20261022.json)
binds the exact wheel/npm/theme and successful negative controls. Comparison
approval does not imply byte identity of volatile output screenshots.

Recorded tools are Node 26.12.1, React/ReactDOM 19.3.0, TypeScript 6.0.3,
Vite 8.3.2, Playwright 1.63.0, axe 4.13.0 and Chromium 153.0.8010.12 on Darwin
arm64. The acceptance host owns its viewport geometry and targets Chrome 123 CSS
or newer to preserve native `light-dark()` role values during minification.
That fixture target is not a general browser-support promise. Linux retains the
205 nonvisual cases and skips the visual project. Canonical CSS identifiers,
accessibility behavior and assertion thresholds remain unchanged.

## 4. Operator and policy configuration — exists for the recorded 0.5.1 subset

**Current state:** generic `operators_in_groups`, `authorize_operator`,
`authorize_action` and composed `authorize_schema` remain host callbacks/config.
Backend grants remain authoritative. The implemented public `arras.policy` port
now covers direct Python/MCP/HTTP and administrative backend mutation methods,
including dry run, batch, import, registration and catalog attachment.

**Decision/seam:** `PolicyBackend` presents immutable resolved request snapshots
with the exact Principal, actual plans/records/document/module and operation
options. `WritePolicy` returns `PolicyDecision`; every actual apply/replay checks
current policy, with no service identity or decision cache. Isolated native-shape
copies preserve approved values and valid many-valued properties. Typed
`PolicyRefused` carries a bounded safe `policy_code`; existing wire refusal types,
reasons and authority are unchanged. Malformed/throwing callbacks fail closed.

Optional `PolicyAnnotationCapabilities`/`PolicyAnnotationProvider` advertises exact
operations and atomically binds annotations to the same native write/audit group.
Absent capability refuses before ordinary mutation, with no log/trace/second-
transaction fallback. A synthetic controlled payload transaction has scoped
commit/rollback, batch-group, replay, concurrency and exact-principal evidence.
That is generic port qualification, not production durability or full backend
conformance. Native Truss annotations remain unsupported until independently
implemented and qualified.

**Gap/cost:** scoped generic policy delivery is complete; further native/provider
annotation support requires separate implementation and qualification. Do not call
unsupported annotation refusal proof actual native audit support. Import load IDs
retain their existing provenance meaning. The generic callback introduces no
sensitive derived workload. ADR-005 still requires the deployment's real written
workload, source-entitlement enforcement point and governed-write owner before
actual sensitive derived state. Write hooks alone do not prove commit-time source
authority or derived-source read entitlement; those deployment claims remain open.

## 5. Modules and content — exists for the recorded 0.5.1 subset

**Current state:** registration takes explicit document bytes, and trusted host
calls bind handlers/resources. The [neutral Python extension host](../../../examples/extension_host/README.md)
selects its own packaged module/seed/graph resource, loads no Arras demo by default,
and exercises public registration/import/query APIs. Its graph envelope is its
own format, not a new Arras graph-file API. Original document bytes are retained.
ADR-022's closed `arras.view` 0.1.0 refuses unknown view terms; no document can
request execution/import of a host component.

**Decision/seam:** explicit registration/resource selection is sufficient;
entrypoint discovery adds no necessary framework. Separate official source
validity, admitted executable profile and renderer support. The selected legacy
Arras projection/action subset is explicitly qualified; official UMF adoption,
unknown-meaning preservation and additional native semantics remain separately
owned A1/A2 gates. Equal version strings are not conformance. Shared view terms
need upstream vocabulary versioning; independent host screens remain host-owned.

**Gate/cost:** explicit-content delivery is complete against downloaded artifacts;
official semantic adoption remains a separate medium/high-cost workstream. The fresh 0.5.1
[installed example proof](../04-build/arras-integration-plan-20261022.md)
passed four tests including the public launcher, custom graph/seed console
composition and all 72 applicable memory corpus cases, with seven replica-only
cases inapplicable and no limits/errors. Dependencies came from the public index
in a new venv; imports were isolated outside the checkout, with no shared site or
source-referencing PTH files. Earlier
[consumer receipts](../04-build/evidence/ex05-ex07-20261022/fresh-installed-consumer.json)
retain their older snapshot scope. Preserve explicit attribution, no-default demo
loading, unsupported-profile refusal and consumer-owned resource provenance.

## 6. Backends and deployment — exists for the recorded 0.5.1 subset

**Current state:** `Arras.start(backends, ...)` accepts explicit host-built
backends; process composition constructs known adapters rather than importing a
configured class. ConnectionSource, installing connection, module roles, wheel
supply/pins, credentials and deployment timing belong to the host. The packaged
corpus/runner and explicit memory/native conformance helpers now have source;
installed native helper/cohort proof is tracked by EX-07/A7.
The [installed native verifier](../../../tools/verify_native.py) has completed
source review and 17 offline controls. Those controls qualify verifier preparation
and failure/report behavior only. Current Linux source passes all 199 native tests on public Truss 0.0.48/Weft
0.4.51/pgserver-pg18 18.6.1. The prior Mac source 199-test result is retained with
[explicit source equivalence](../04-build/evidence/arras-0.5.1-native-source-final-delta-20261022.json).
The fresh installed 0.5.1 helper passes its CLI/corpus gate: 64 passes,
eight exact declared limits and seven replica-only cases inapplicable, with no
failures/harness errors. Receipt SHA-256 is
`026a935e4bb39323db13e56dff0ce4837e0062675497efb8e9b677d4ad43ca72`.
[Independent Sol review](../04-build/evidence/arras-0.5.1-installed-native-review-20261022.json)
checks the actual receipt, binding, ordered outcomes and cleanup.
All seven selected native distributions and 92 installed runtime payload files
match verified archives on Darwin arm64/CPython 3.11. This is not a system
dynamic-link audit, minimum-OS execution or another platform qualification.

**Resolved defect:** persistent LocalTruss uses an explicit shared stable
credential source. Existing-role lookup cannot mint a replacement credential;
startup/module loading preserves independent memberships and expiry. Bounded
file storage, process locking and atomic replacement have scoped multi-host/
restart/revocation native evidence. Previously unretained credentials require
explicit administrator recovery; do not silently reset/reissue. Managed-host
qualification and production credential custody are separate.

**Decision/seam:** retain person-owned connections, explicit factories and
role/grant operations; never insert a production service identity or automatic
grant reset. Preserve reader/provider roles from `describe`, not Python method
presence. Optional lifecycle/annotation capabilities are advertised only within
their explicit qualified contracts.

**Gap/cost:** selected Linux installed-native and public-delivery gates pass.
Additional provider/deployment work has its own cost and acceptance. Retain two-host/restart/stale-credential/independent-grant tests. The local
installed native receipt is distinct from source passes and static package checks.

## 7. Downstream testing and CI — exists for the recorded 0.5.1 subset

**Current state:** upstream source/native/UI pipelines, a reusable
[downstream workflow](../../../.github/workflows/downstream.yml), explicit Python
and theme fixtures, and a [generic public-content gate](../../../tools/check_public_content.py)
with dependency/fixture provenance policy now have source. Named downstream prose/fixtures have been generalized under retained artifact
identities; the gate does not embed customer names as a deny-list. The final cohort passed the content and provenance checks.
Reviewed CI/release source uses the official HTTPS APT helper, checked effective
network bounds, bounded browser setup and a real pinned Chromium launch/close;
its source/fixture controls do not substitute for an actual Arras hosted run.
All existing source/native/UI/downstream jobs remain required before their
corresponding release claims.

**Decision/seam:** consumers run pinned wheel/import/config/corpus jobs and
explicit native/theme profiles without copying repository tests. The packaged
`arras-ui-qualify` CLI supports external themed URLs; its host-build probe contract
and optional test peers are documented. The public `./testkit` and `./testkit/host` share the
canonical suite and resources without copying tests; the actual 272-case themed
capture and complete image review are described under Theming. The ordinary Mac comparison and separate tagged/downloaded Linux consumers pass. The reusable workflow reports selected
consumer test outcomes, not blanket native/rendered certification. The host owns
its setup scripts and explicit test targets. Link HELIX authority and author
local decisions rather than copying methodology or downstream source upstream.

**Gate/cost:** selected tag/public-download integrated jobs pass; new optional
consumer targets require their own execution.
The final generic content/provenance gate and component reviews pass. A mocked workflow, source-only runner, dependency reuse or
unexecuted optional job cannot close the corresponding release claim. Verify the
exact tagged cohort, retain outputs and make skip/unsupported states explicit.

## 8. Upgrades — exists for the recorded 0.5.1 subset

**Current state:** version/deprecation rules and the deliberate catalog exist.
The exact `arras.doctor` request/report/CLI contract is bound in CONTRACT-005.
Its implementation completed scoped source review and is included in the
integrated default-source checkpoint above, including strict input, bounded
regular-file reads, redacted CLI errors and unavailable-capability controls. The fresh 0.5.1 installed doctor proof passes 20 cases, including positive function/
CLI, breaking/no-I/O, public launcher help/refusal, alias blank fallback/override/
identical-value/conflict and mocked development forwarding/banner controls.
[Sol's review](../04-build/evidence/arras-0.5.1-sdk-example-review-20261022.json) binds the
current verifier, generated probe, wheel and carried npm hashes. Earlier
[19-case receipts](../../../tests/downstream/evidence/doctor-installed.json) remain
historical. Static checks and mocked forwarding do not qualify live servers,
native writes or development argparse value redaction.

**Decision/seam:** one offline typed `DoctorRequest` / `check` / `DoctorReport`
and `python -m arras.doctor --request <path>` use existing catalog/config/Brand/
asset/profile validators. Inputs are explicit and bounded; no environment secret,
token-file, network, registration or native effect is read/executed. Stable codes
and exits separate incompatibility, malformed input and unavailable capability.
Names-only environment checks make no credential identity claim. Legacy document
checks are legacy subset/readability only; missing official or native-write proof
is unsupported with no fallback.

**Gate/cost:** public-wheel repetition passes. Release
notes record changes/action/deprecations per Python/contract/config/env/
Brand/theme/UMF/backend/runner seam. A static doctor cannot qualify rendered
a11y, native semantics or compatibility merely from matching version integers.

## System decomposition and modularity

Extend the existing architecture map, AST/cycle tests, public-import allowlist
and frontend rules. The current core imports GraphQL schema construction and
registration/schema administration use it to establish servability. Separate
pure admission from binding-specific preflight while retaining all current
collision/servability refusal before an accepted registration becomes visible.
Update Architecture and the governing contracts before changing that boundary.

| Responsibility | Allowed dependencies | Forbidden dependencies |
| --- | --- | --- |
| Values/model/errors | Standard library, lower value types | Kernel, config I/O, transports, engines, UI |
| Module admission/projection | Official UMF API, model, declared profiles | GraphQL construction, credentials, host I/O |
| Action planning | Model, shared official action semantics | Native clients, HTTP/MCP/UI, downstream imports |
| Kernel/session/registration | Model, ports, admission/planning, current principal/policy | Concrete adapters, UI assets, CLI/env readers |
| Public transport binding | Kernel public API, versioned serialization | Engine internals or downstream implementation |
| Backend adapters | Public ports, owned engine SDKs | Kernel internals, HTTP/MCP/UI, test doubles |
| Typed configuration values | Schema/value types | Kernel state, implicit backend construction |
| Config I/O/host composition | Public config/API, explicit factories, optional UI host | Kernel-private access, implicit plugins |
| Browser UI | Versioned clients and design-system contract | Python/native runtime or private theme dependencies |
| Downstream theme/content | Public UI and registration APIs | Arras internal modules |

Use `uv run pytest tests/test_boundary.py tests/test_public_api.py` for the
existing Python import/cycle/public-API controls. In `ui/`, retain the existing
`npm run check:externals` and `npm run check:css` plus frontend import-rule tests.
Extend these enforcement paths with allowed/forbidden negative controls for each
new boundary; verify local/CI wiring before declaring a new gate adopted. Keep configuration value types importable without reading environment.
Keep the shared action kit internal; neither it nor each widget needs a package.
The generated-client binding remains a separate integration tranche, not a
delivered API inferred from this design.

## Prioritized action plan and traceability

| Priority | Queue / work | Current disposition and acceptance |
| --- | --- | --- |
| Closed | EX-01 delivery | GitHub wheel/sdist/npm and exact sixteen-file bundle independently reviewed; anonymous consumers pass; registries deferred |
| Closed | EX-02 naming/config | Public-wheel doctor/SDK/config/launcher controls pass; canonical identity remains stable |
| Closed | EX-03 theme/assets/public runner | Downloaded Linux 205 and separate Mac 272/payload bridge pass; reviewed baselines unchanged |
| Closed | EX-05/07 skeleton/content/CI | Actual fixed reusable job, fresh example/memory and anonymous full-bundle consumers pass |
| Closed subset | EX-04 policy/audit | Generic callback/refusal/optional transaction port delivered; synthetic annotation proof only, native annotations unsupported |
| Closed | EX-08 upgrades/doctor | Public-wheel positive/breaking/no-I/O checks pass; per-seam notes delivered |
| Closed subset | EX-06 host safety | Credential/grant regression retained and selected Truss 0.0.48/Weft 0.4.51 native cohort qualified |
| Separate next work | A1/A2/A7 | Official admission/projection/action and additional adapter/deployment capabilities remain separately governed |

The canonical [EX queue](../04-build/arras-integration-plan-20261022.md#extensibility-queue)
owns execution. [Release acceptance](../05-deploy/deployment-checklist.md) requires
all selected rows, final source freeze and downloaded-artifact evidence. This
note records completed scoped delivery and preserves the unqualified boundaries.

## Minimal generic downstream proof target

```text
example-distribution/
  pyproject.toml                 # exact Arras pin; own command
  src/example_distribution/
    __init__.py                  # explicit supported reexports
    __main__.py                  # callable launcher/composition
    app.py                       # public factories/session/UI
    configuration.py             # DistributionConfig + shared Brand
    policy.py                    # PolicyBackend callback; capabilities explicit
    resources/module.umf.json    # own namespace; selected qualified profile
    resources/seed.json
    resources/graph.json         # explicitly named host or Arras graph format
  config/default.toml            # [distribution]/[distribution.brand] + existing keys
  theme/
    package.json                 # public exports; React + public UI peers
    src/index.tsx                # six widget overrides/Mark/provider
    src/theme.css                # canonical tokens; light/dark
    assets/                      # own fonts/favicon
    dist/                        # compiled JS/declarations/assets
  ui/src/main.tsx                # bare UI + packed theme public imports
  runtime-theme.json             # generated v1 manifest from same packed theme
  doctor-request.json            # EX08 request; public-wheel proof
  tests/                         # own overlay assertions + packaged corpus/CLI
  .github/workflows/verify.yml   # pinned reusable jobs / explicit native/theme targets
  docs/helix/                    # local decisions and upstream authority links
```

The real [Python fixture](../../../examples/extension_host/README.md) demonstrates
the explicit module/resource half; the [theme package](../../../tests/downstream/theme-package/package.json)
and [browser fixture](../../../tests/downstream/README.md) demonstrate packed
appearance and the two UI routes. Together they define the integrated external
proof target; the released 17d/76fc cohort now passes both public consumer routes.
Runtime manifests are explicit UI arguments, not an invented TOML theme schema.
The doctor entrypoint is implemented, source-reviewed and qualified against the
current 0.5.1 public wheel, including the fresh anonymous-download repetition.

Acceptance pins exact wheel/npm/theme bytes, checks public shim imports, compiles
theme/host against packed declarations with one React, qualifies actual internal
replacement controls and runtime assets, loads only the selected custom module/
resource, runs installed corpus and selected native/browser jobs, then exercises
compatible/breaking doctor requests. Repeat required checks on fresh public
release downloads and record actual profile/tool/runtime/platform limits.

## Verified limits and unresolved facts

- The scoped eight-seam release is delivered and independently reviewed. Original
  publication and supplemental verification are separate, explicit runs; the
  immutable aggregate still says `not_run_at_assembly`.
- GitHub delivery is qualified. PyPI/npm publication remains deferred; no registry
  install or unavailable account access is claimed.
- Mac SDK/native/272-case visual evidence retains original component hashes.
  The reviewed container/payload bridge does not claim Mac execution of 17d.
  Linux 205 excludes the Mac-only visual project. Dependency floors and Python
  classifiers do not establish execution on every supported-looking version.
- Canonical CSS/import/signal identities stay stable; public-wheel scoped naming,
  environment aliases, provider attribution and telemetry controls pass.
- Native policy annotations remain unsupported. Synthetic transaction proof does
  not establish production durability, native audit or source entitlement.
- Legacy document/read/action evidence is not general official-UMF adoption.
  Remaining A2–A7, managed deployment, replica convergence and additional storage
  adapter work retain their own contracts, ownership and qualification gates.
