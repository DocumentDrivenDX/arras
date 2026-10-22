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

Distribution, typed naming, runtime assets, policy and external-consumer work now
have binding interfaces in [CONTRACT-005](contracts/CONTRACT-005-embedding-and-lifecycle.md).
The policy source has scoped Sol review; optional annotation atomicity uses a
synthetic transaction and does not establish native annotation durability. The
frozen candidate wheel is
`07b3e867bd4ca48b4cd43ad5f13449076e3939f4194c06c297d1ca0171764ed1`, carrying npm
`c29a9f151d9a6a42cce55325e927634cc5713763c0485cc6e02cb63006c78307`.
It passed 20 installed doctor cases, eight SDK phases and three false-pass
controls, plus four fresh installed example tests and 72 applicable memory corpus
cases (seven replica-only cases inapplicable). Its portable themed capture passed
272 cases with no failures/skips; Sol approved all 67 canonical images and all
eight narrower route images. The subsequent ordinary run passed all 272 cases with updates disabled and all 67 approved baselines unchanged.

The [build plan](../04-build/arras-integration-plan-20261022.md) records exact
receipts, source reviews, failed candidates and remaining source/sdist and
public-delivery gates. Local source and fresh installed-native qualification pass
for the selected public tuple; exact-tag Linux execution remains separate. The
[naming inventory](naming-surfaces.md) distinguishes stable identity from host
presentation. The [release checklist](../05-deploy/deployment-checklist.md)
requires exact-tag GitHub assets and fresh public-download consumers. Earlier
[source](../04-build/evidence/arras-source-gate-expanded-20261022.json) and
[distribution](../04-build/evidence/arras-distribution-20261022.json) checkpoints
retain their original Python/platform and old native-pin scope; they do not
qualify this frozen artifact. Real PyPI/npm uploads are explicitly deferred if
existing access is unavailable; GitHub delivery remains mandatory.

Governing sources: [Architecture](architecture.md), [embedding CONTRACT-005](contracts/CONTRACT-005-embedding-and-lifecycle.md),
[typed configuration ADR-019](adr/ADR-019-the-mcp-process-reads-one-typed-configuration.md),
[closed view vocabulary ADR-022](adr/ADR-022-a-modules-presentation-is-declared-in-a-closed-umf-view-vocabulary.md),
[UI packaging ADR-027](adr/ADR-027-the-wheel-carries-the-ui-as-a-mountable-app-and-an-npm-tarball.md)
and [design system ADR-029](adr/ADR-029-the-ui-draws-through-a-pluggable-design-system-seam-with-a-built-in-default.md).
Exact new interfaces belong in the affected contracts before implementation.

## Coverage and remaining specification work

| Concern | Queue / governing specification | Implemented or bound subset | Remaining acceptance gap |
| --- | --- | --- | --- |
| Distribution | EX-01; CONTRACT-005/public catalog | Reviewed catalog including launch-only imports, asset loader/result and lazy native harness; artifact/dependency parity and exact carried npm bytes | Final expanded cohort, mandatory exact-tag gates, GitHub assets and downloaded consumers; registry delivery separately qualified/deferred |
| Naming | EX-02; ADR-018/019, CONTRACT-005/007/008 | Reviewed Brand/tool/env/human launchers and implemented scoped TelemetryNames/TelemetryContext/effective-config provider factory; 150 focused source tests independently pass; packaged ADR-019 config and 20-case frozen-wheel installed consumer with eight SDK phases and three false-pass controls | Exact-tag and fresh-download repetition; native evidence remains separate |
| Theming/UI split | EX-03; ADR-027/029, CONTRACT-005 | Public Node testkit/browser host, 17 shared specs and 83 resources; packed themed capture 272/272; all 67 canonical and eight narrow images reviewed | Ordinary full comparison passed; exact-tag and public-download delivery remain |
| Operator/policy | EX-04; CONTRACT-005/007/009/010/011, ADR-005 | Existing callbacks, composed schema forwarding, PolicyBackend, safe PolicyRefused, optional annotation protocol with synthetic transaction proof | Final installed/cross-surface gates; native annotation support explicitly unavailable until qualified |
| Modules/content | EX-05; CONTRACT-002/003/010, ADR-022 | Explicit custom resource example and no-default composition; final installed example four tests plus memory corpus 72/7 | Tag/download delivery; official-profile/native qualification remains separately scoped |
| Backends/deployment | EX-06/07, A7; CONTRACT-004/005 | Host factories/connections, repaired stable credentials; reviewed packaged harness/verifier source with 17 offline controls | Exact-tag installed-native and public-delivery repetition; deployment-specific qualification remains host-owned |
| Downstream CI | EX-07; TP-001/architecture | External Python/theme fixtures, generic public-content gate, reusable workflow, portable no-copy canonical testkit and actual packed themed capture | Ordinary full comparison passed; final integrated exact-tag/download jobs remain |
| Upgrades | EX-08; CONTRACT-005/catalog | Reviewed offline doctor/report/CLI implementation and compatibility/deprecation policy | Frozen-wheel 20-case positive/breaking/no-I/O and launcher controls pass; finalize per-seam delivery record and repeat on public downloads |

The contracts specify the new callable/value/asset/runner seams before code.
Unfinished qualification is not an unbound API proposal. In-flight source is
nevertheless unavailable to a pinned consumer until it is packed, delivered and
verified from that exact artifact.

## Compatibility and qualification matrix

Version declarations define candidate compatibility; the evidence column limits
what is actually qualified. `pgserver-pg18` 18.6.1 is the Python distribution
version; it must not be presented as an observed PostgreSQL server patch version.
The source suite separately asserts client libpq 18.6. The exact release bundle will bind its own wheel,
platform and native cohort rather than merge these component runtimes.

| Component/cohort | Selected versions | Evidence and limit |
| --- | --- | --- |
| Arras Python/UI | `0.5.0`; Python requirement `>=3.11`, declared 3.11/3.12/3.13 | Frozen 07b wheel and c29 npm qualified as named below; declarations alone do not prove every interpreter/platform |
| Native Linux x86_64 | Truss `0.0.48`, Weft `0.4.51`, `pgserver-pg18` `18.6.1`, CPython 3.11 | Actual source suite 199 passes; fresh installed/tagged native gates remain separate |
| Native macOS arm64 | Same public native tuple; CPython 3.11 | Full source suite 199 passes, zero failures/errors/skips. Fresh exact-07b installed CLI corpus: 64 passes/eight declared limits/seven replica-only inapplicable, no failures/harness errors; seven selected distribution payloads verified. No system dynamic-link audit |
| Native distribution floors | Linux x86_64 glibc `2.27`; macOS arm64 `14` | Static maximum dependency floors, not execution on those OS minima; exact seven-archive inputs live under `tests/downstream/native-cohorts/` |
| Installed Python/SDK macOS arm64 | Python `3.13.16`, OpenTelemetry API/SDK `1.45.1`, graphql-core `3.3.0` | Doctor 20 cases/eight phases/three controls and four fresh example tests; memory corpus 72 passes/seven replica-only cases inapplicable; no native inference |
| UI macOS arm64 | Node `26.12.1`, React/ReactDOM `19.3.0`, TypeScript `6.0.3`, Vite `8.3.2`, Playwright `1.63.0`, axe `4.13.0`, Chromium `153.0.8010.12` | Packed themed capture and ordinary comparison each 272 passes; all 67 approved baselines unchanged |
| UI Linux x86_64 | Node 24 and lock-pinned Playwright/Chromium | Nonvisual source/tagged installed suites are separate gates; visual project excluded |
| Document/view/rendering profiles | Selected legacy Arras document/action subset; `arras.view` `0.1.0`; schema-browser npm `2.0.0` | Original bytes retained and explicit profile refusal; official core `0.10.0` (`umf-v0.5.4`) has A1 source-validity evidence only; A2 admission/projection is separately gated |

## 1. Distribution — partial

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

**Gap:** the expanded final source needs a new complete artifact receipt and
compatible Truss/Weft/UMF/Python/platform matrix. A tag alone proves source
identity, not installability. GitHub Release wheel/sdist/npm/receipt/SHA256SUMS
are required delivery; real PyPI/npm uploads are separately qualified or
explicitly deferred if configured access is absent. Do not advertise an
unavailable registry install or unrun platform.

**Gate/cost:** small/medium remaining delivery work, plus separately owned native
cohort qualification. Exact-tag source/native/UI/downstream gates must precede
publication; fresh public downloads must pass digests and installed consumers.
CONTRACT-005 now binds separate build-input transport, a mandatory safe evidence
assembler and a complete anonymous public-download job. The existing hosted
reusable-consumer invocation remains required alongside that full-bundle job.
Compare public sums/assets against the trusted current-run assembled stage and
build wheel identity, then rerun existing artifact, doctor/SDK, fresh consumer
and full themed UI tools on public bytes. Optional registry jobs wait for those
results. The assembler has scoped source approval with ten tests; the workflow and public
comparison helper have independent source approval with 30 focused tests, including
executed malicious-download controls. The [workflow source review](../04-build/evidence/arras-release-workflow-source-review-20261022.json)
records the frozen file identities. Assembly, tag/Linux gates and anonymous public
download qualification still require actual execution; source approval is not a
release result. The
[release checklist](../05-deploy/deployment-checklist.md) owns that closure.

## 2. Naming — partial

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
| Telemetry Resource `service.name` | (b) Typed host-owned attribution | Source-reviewed TelemetryNames + explicit matching host provider Resource; final 07b installed receiver proof passes; exact-tag/download repetition pending |
| Event/attribute/log namespace prefixes | (b) Explicit host-scoped projection | Source-reviewed per-context output aliases after default-deny validation; final 07b installed witnesses pass; canonical definitions/origin keys/defaults preserved; exact-tag/download repetition pending |
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

The [frozen-wheel SDK review](../04-build/evidence/arras-sdk-07b-review-20261022.json)
qualifies the 07b wheel on Darwin arm64/27.0.0, Python 3.13.16 and OpenTelemetry
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

## 3. UI split and theming — partial

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
its exact packed bytes with one React. On the 07b wheel, all four narrower
Explore/Operate routes compare against eight
[reviewed macOS images](../04-build/evidence/arras-narrow-eight-visual-review-20261022.json).
Their token/contrast/axe/focus/provider/palette controls remain intact. The full
portable capture then passed 272/272 (132 Chromium, three schema-administration,
70 browser, 67 visual), with zero failures/skips and four successful negative
controls. Sol [reviewed all 67 canonical images](../04-build/evidence/arras-neutral-theme-67-visual-review-20261022.json).
The capture receipt reports `updated-unreviewed`. After review, the ordinary run
with updates disabled passed 272/272 and compared all 67 unchanged baselines; its
receipt SHA-256 is `91f1a5af1c2b78b187d1726d66c96a3682251e189abd2834f9c2531beb17a819`. Existing volatile-content masks
qualify the visual review's coverage.

Recorded tools are Node 26.12.1, React/ReactDOM 19.3.0, TypeScript 6.0.3,
Vite 8.3.2, Playwright 1.63.0, axe 4.13.0 and Chromium 153.0.8010.12 on Darwin
arm64. The acceptance host owns its viewport geometry and targets Chrome 123 CSS
or newer to preserve native `light-dark()` role values during minification.
That fixture target is not a general browser-support promise. Linux retains the
205 nonvisual cases and skips the visual project. Canonical CSS identifiers,
accessibility behavior and assertion thresholds remain unchanged.

## 4. Operator and policy configuration — partial

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

**Gap/cost:** small/medium final installed and aggregate gates. Do not call
unsupported annotation refusal proof actual native audit support. Import load IDs
retain their existing provenance meaning. The generic callback introduces no
sensitive derived workload. ADR-005 still requires the deployment's real written
workload, source-entitlement enforcement point and governed-write owner before
actual sensitive derived state. Write hooks alone do not prove commit-time source
authority or derived-source read entitlement; those deployment claims remain open.

## 5. Modules and content — partial

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

**Gate/cost:** small remaining exact-tag/public-download delivery; official
semantic adoption is a separate medium/high-cost workstream. The final 07b
[installed example proof](../04-build/arras-integration-plan-20261022.md)
passed four tests including the public launcher, custom graph/seed console
composition and all 72 applicable memory corpus cases, with seven replica-only
cases inapplicable and no limits/errors. Dependencies came from the public index
in a new venv; imports were isolated outside the checkout, with no shared site or
source-referencing PTH files. Earlier
[consumer receipts](../04-build/evidence/ex05-ex07-20261022/fresh-installed-consumer.json)
retain their older snapshot scope. Preserve explicit attribution, no-default demo
loading, unsupported-profile refusal and consumer-owned resource provenance.

## 6. Backends and deployment — partial

**Current state:** `Arras.start(backends, ...)` accepts explicit host-built
backends; process composition constructs known adapters rather than importing a
configured class. ConnectionSource, installing connection, module roles, wheel
supply/pins, credentials and deployment timing belong to the host. The packaged
corpus/runner and explicit memory/native conformance helpers now have source;
installed native helper/cohort proof is tracked by EX-07/A7.
The [installed native verifier](../../../tools/verify_native.py) has completed
source review and 17 offline controls. Those controls qualify verifier preparation
and failure/report behavior only. Separate actual Linux and Mac source runs each pass all
199 native tests on public Truss 0.0.48/Weft 0.4.51/pgserver-pg18 18.6.1. The separate fresh installed 07b helper passes its CLI/corpus gate: 64 passes,
eight exact declared limits and seven replica-only cases inapplicable, with no
failures/harness errors. It verifies all seven selected native distributions and
their installed payloads on Darwin arm64/CPython 3.11. This is not a system
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

**Gap/cost:** small remaining exact-tag Linux installed-native and public-delivery
gates. Retain two-host/restart/stale-credential/independent-grant tests. The local
installed native receipt is distinct from source passes and static package checks.

## 7. Downstream testing and CI — partial

**Current state:** upstream source/native/UI pipelines, a reusable
[downstream workflow](../../../.github/workflows/downstream.yml), explicit Python
and theme fixtures, and a [generic public-content gate](../../../tools/check_public_content.py)
with dependency/fixture provenance policy now have source. Named downstream prose/fixtures have been generalized under retained artifact
identities; the gate does not embed customer names as a deny-list. The final
cohort must rerun the content and provenance checks.
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
capture and complete image review are described under Theming. The ordinary full comparison passed; tagged/downloaded consumers remain separate gates. The reusable workflow reports selected
consumer test outcomes, not blanket native/rendered certification. The host owns
its setup scripts and explicit test targets. Link HELIX authority and author
local decisions rather than copying methodology or downstream source upstream.

**Gate/cost:** medium remaining integrated installed jobs and final content/
provenance review. A mocked workflow, source-only runner, dependency reuse or
unexecuted optional job cannot close the corresponding release claim. Verify the
exact tagged cohort, retain outputs and make skip/unsupported states explicit.

## 8. Upgrades — partial; public-delivery qualification pending

**Current state:** version/deprecation rules and the deliberate catalog exist.
The exact `arras.doctor` request/report/CLI contract is bound in CONTRACT-005.
Its implementation completed scoped source review and is included in the
integrated default-source checkpoint above, including strict input, bounded
regular-file reads, redacted CLI errors and unavailable-capability controls. The final 07b installed doctor proof passes 20 cases, including positive function/
CLI, breaking/no-I/O, public launcher help/refusal, alias blank fallback/override/
identical-value/conflict and mocked development forwarding/banner controls.
[Sol's review](../04-build/evidence/arras-sdk-07b-review-20261022.json) binds the
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

**Gate/cost:** small remaining exact-tag/public-download installed repetition and aggregate gates. Final release
notes must record changes/action/deprecations per Python/contract/config/env/
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
| 1 | EX-01 delivery | Rebuild final wheel/sdist/npm; mandatory exact-tag gates, GitHub bundle and fresh downloaded consumers; registry proof/defer explicit |
| 2 | EX-02 naming/config | Scoped telemetry implementation/source review and packaged ADR-019 config exist; frozen-wheel 20-case/eight-phase SDK/config and public launcher proof passes; exact-tag/download repetition remains |
| 3 | EX-03 theme/assets/public runner | Portable shared testkit and actual themed 272-case capture exist; all images reviewed; ordinary comparison passed; finish exact-tag/download gates |
| 4 | EX-05/07 skeleton/content/CI | Fresh installed example/memory proof, theme fixtures, reusable jobs and generic source gates exist; final integrated tag/downloaded artifact/native gates remain |
| 5 | EX-04 policy/audit | Source-reviewed generic wrapper/safe reasons/optional synthetic transaction capability; final installed gates; native annotations unsupported |
| 6 | EX-08 upgrades/doctor | Source-reviewed implementation and frozen-wheel 20-case installed proof pass; finalize per-seam release record and public-download repetition |
| Retained urgent subset | EX-06 host safety | Preserve native two-host/restart/expiry/grant regression; final exact cohort requalifies |
| Parallel semantic dependency | A1/A2/A7 | Owning lane qualifies explicit UMF/profile and native cohort; no second interpreter or silent meaning loss |

The canonical [EX queue](../04-build/arras-integration-plan-20261022.md#extensibility-queue)
owns execution. [Release acceptance](../05-deploy/deployment-checklist.md) requires
all selected rows, final source freeze and downloaded-artifact evidence. This
note updates the implemented/bound/gap map; it is not publication approval.

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
  doctor-request.json            # EX08 request; frozen-wheel proof, delivery pending
  tests/                         # own overlay assertions + packaged corpus/CLI
  .github/workflows/verify.yml   # pinned reusable jobs / explicit native/theme targets
  docs/helix/                    # local decisions and upstream authority links
```

The real [Python fixture](../../../examples/extension_host/README.md) demonstrates
the explicit module/resource half; the [theme package](../../../tests/downstream/theme-package/package.json)
and [browser fixture](../../../tests/downstream/README.md) demonstrate packed
appearance and the two UI routes. Together they define the integrated external
proof target; separate successes do not establish a single released cohort.
Runtime manifests are explicit UI arguments, not an invented TOML theme schema.
The doctor entrypoint is implemented, source-reviewed and qualified against the
07b frozen wheel; exact-tag and public-download repetitions remain required.

Acceptance pins exact wheel/npm/theme bytes, checks public shim imports, compiles
theme/host against packed declarations with one React, qualifies actual internal
replacement controls and runtime assets, loads only the selected custom module/
resource, runs installed corpus and selected native/browser jobs, then exercises
compatible/breaking doctor requests. Repeat required checks on fresh public
release downloads and record actual profile/tool/runtime/platform limits.

## Verified limits and unresolved facts

- Earlier artifact/native receipts retain their exact snapshot limits; final
  source and changed tools/tests require rebuilt distributions and new receipts.
- The release checklist records the owner's preflight and first-release intent.
  Earlier web-reader cache misses were never evidence of HTTP 404 or registry
  absence. This note does not independently recheck remote publication.
- Human launchers, packed runner and doctor have source/candidate qualification;
  final integrated skeleton/doctor/native compatibility and public delivery remain
  tracked gaps, not finished merely because interfaces are bound or source files
  exist.
- Canonical CSS/import identities, signal definitions/origin keys and default
  telemetry output stay stable. Required scoped attribute/event/log projections
  and typed host Resource naming have frozen-wheel installed qualification;
  exact-tag/public-download delivery remains pending; canonical
  instrumentation policy is not a waiver of the downstream naming requirement.
- Native policy annotations remain unsupported. Synthetic transaction evidence
  is not production durability, native audit qualification or source entitlement.
- Legacy document/read/action subset evidence is not general official-UMF
  adoption or semantic execution. Other profile/native/managed deployment claims
  remain explicitly owned and separately qualified.
- No all-eight release completion is declared here. GitHub delivery, exact assets,
  fresh downloaded consumers and the final per-seam support record remain the
  release owner's evidence gate; optional registry deferral is named explicitly.
