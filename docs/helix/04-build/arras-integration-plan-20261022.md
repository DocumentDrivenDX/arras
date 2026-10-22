---
ddx:
  id: PLAN-ARRAS-INTEGRATION-20261022
  type: implementation-plan
  activity: build
  status: draft
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: architecture
      kind: informed_by
    - id: CONTRACT-002
      kind: informed_by
    - id: CONTRACT-003
      kind: informed_by
    - id: CONTRACT-004
      kind: informed_by
    - id: TP-001
      kind: informed_by
    - id: arras.downstream-extensibility
      kind: informed_by
---

# Arras integration build plan

## Scope

Adopt official UMF semantics and the generated client's public transport in
Arras. Arras owns the application interface to the
universal graph: registration, authenticated sessions, placement, execution
coordination and results. UMF owns the metamodel, constraints, action declarations,
generation and reusable conformance vectors. Truss owns native graph transactions;
Weft owns query compilation. Each change must preserve those boundaries.

Active Arras work targets `/Users/erik/Projects/arras`. External historical artifact
IDs, source paths and digests remain historical evidence in their owning sources. This plan sequences
Arras work alongside existing owners; it does not reopen or duplicate their queues.
Downstream applications may supply optional acceptance fixtures; their code,
dependencies, transport glue, deployment and UI changes are outside this scope.
The separate EX queue below accepts generic seam priorities from the coordinated
[downstream extensibility design](../02-design/downstream-extensibility.md).
It sequences future bounded changes; it does not implement those seams or expand
A0–A7's completion criteria.

Governing local artifacts: [PRD](../01-frame/prd.md) FR-9/13/14,
[principles](../01-frame/principles.md) 1–6,
[architecture](../02-design/architecture.md#module-boundaries),
[CONTRACT-002](../02-design/contracts/CONTRACT-002-type-registry-and-placement.md),
[CONTRACT-003](../02-design/contracts/CONTRACT-003-actions.md),
[CONTRACT-004](../02-design/contracts/CONTRACT-004-backend-contract.md), and
[TP-001](../03-test/test-plan.md). The installed HELIX 0.18.0 `workflows/`
catalog supplies the plan shape and `artifact-signal` voice; it is not copied here.

Upstream coordination sources:

- Truss's HF-01–HF-07 follow-up plan and semantic pushbacks, held by the native
  runtime/release owner in chat `01a16023-fabd-7fa3-9abf-44d42e7fd673`.
- UMF's [general UMF–Arras plan](/Users/erik/.codex/worktrees/1243/umf/docs/helix/04-build/umf-arras-integration-plan.md),
  coordinated in chat `01a16384-78eb-7b30-82e1-c1f1feacc383`. H1–H7 and HA-0–HA-7
  below refer to that plan and its governing CONTRACT-079/900. Its historical
  identity remains in the upstream artifact unchanged.
- Official [UMF Python support](/Users/erik/.codex/worktrees/7f51/umf/python/README.md).
  Released artifacts and development Rust-backed source are separate cohorts.

## Shared Constraints

- Preserve original source bytes, their digest and unknown content. Retention is
  distinct from interpretation and execution support. Unknown meaning needed by
  an operation must produce an explicit refusal before effects; never strip or
  relabel content to make a document executable.
- Separate official UMF document validity, completeness of interpretation, the
  Arras executable subset and backend capability. PRD FR-13 requires validity and
  diagnostic agreement on shared reference cases; a local parser pass is not proof.
- Core identity must not depend on a DDD annotation. Removing the current reader's
  mandatory DDD classification requires the official core projection and contract
  tests, not a new heuristic. DDD remains an optional semantic extension.
- Reuse official constraint/action meaning. Do not add a Python facet evaluator,
  copied schema catalog, second action parser or SQL compiler. Arras may translate
  a qualified official action plan into backend operations; it owns transaction
  custody and current policy checks, not a competing recipe interpreter.
- Keep omission, explicit null and unset separate. Select graph-write/2 explicitly
  for its optional assignment rule; version1 and required-key negative controls
  retain their original meaning. Reject mixed legacy/current action dialects.
- Reauthorize as the authenticated person on each call, including pooled reuse
  and between validate/apply. Schema identity does not grant mutation authority.
  Handlers are explicitly host-registered implementations; document metadata
  cannot load code or supply an identity, role or executable effect.
- Preserve native errors, exact scalar tokens, no-op/version rules and locked
  prestate. Do not infer a failing operation index for final-state failures,
  reject every unknown stored property, normalize values, or order opaque tokens.
  An absent receipt is not proof of an invalid token; a source acknowledgement is
  not proof of downstream Ashlar commit. Lost settlement responses preserve write
  uncertainty, and replay claims require durable, scoped native evidence.
- Keep every read bounded and state its freshness. Refuse unsupported consistency
  rather than silently translating bulk/latest/at-least. Partial results require
  explicit bounds/continuation; a truncated result is never a complete entity.
- Library implementation remains Python 3.11 with `uv`, `pyproject.toml` and
  `uv.lock`. Backend imports stay inside adapters. No managed-platform claim is
  established by local PostgreSQL, role-fidelity tests or an API's availability.

## Coordination and Dependencies

The primary coordinating chat is `01a163ae-137a-7e13-9220-4f23c2e43bbf`.
The human selected Sol for planning/review and Luna for implementation. Existing
upstream owners retain their scopes; this plan does not authorize duplicate work.

| Scope | Existing owner | Arras responsibility and acceptance dependency |
| --- | --- | --- |
| HF-01 baseline disputes | Find Truss schema migrations, `01a16023-fabd-7fa3-9abf-44d42e7fd673` | Reconcile the current Arras source snapshot below; reproduce adapter discrepancies on the exact public cohort. Correct stale asks before requesting new native behavior. |
| HF-02 typed diagnostics/recovery | Same Truss owner | Map complete public carriers; test nonmember versus broken grants, original input digest, revocation, expiry and uncertain writes. No adapter index or denial inference. |
| HF-03 required-field evolution | Same Truss owner | Pass original paired core/DDD source and document-scoped revision checks. Test empty/populated/racing cases through the adapter; no Arras migration engine. |
| HF-04 descriptors/facts/paging | Same Truss owner; Weft compilation upstream | Map compiler-owned descriptors and selected facts/relationship profiles. H3/HA-4 requires empty/all-null, fanout, continuation and exact-value proof. |
| HF-05 indexed source/performance | Same Truss owner; Weft/runtime upstream | Measure Arras end-to-end overhead on the qualified source path; retain work bounds and unmet targets. No ceiling increase presented as optimization. |
| HF-06 completion/dry run/audit | Same Truss owner | Preserve host-owned savepoints, prior caller work, typed completion, nondurable validation observations and current audit disclosure rules. |
| HF-07 corpus/release | Same Truss owner | Adopt only the delivered exact artifact/native/compiler cohort, then run installed Arras conformance. Candidate/source passes do not establish released support. |
| Managed grants | Evaluate truss requirements ask, `01a16383-183c-7680-9518-f69ff40383e5` | Consume its public admission/grant design. Local acceptance is separate from actual Lakebase qualification. |
| H1–H7 / HA-0–HA-7 | UMF integration owner, `01a16384-78eb-7b30-82e1-c1f1feacc383` | UMF owns shared semantics, wire/generator changes and vectors; this chat coordinates Arras host/runtime implementation. Preserve the upstream plan's original ID in its owning source. |

## Implementation Slices

Before feature work, apply the existing architecture map and run
`uv run pytest tests/test_modules.py tests/test_boundary.py -q`. The map already
assigns UMF integration to `arras.umf`, backend integration to `adapters`, and host
construction to the host. Tests include forbidden imports, lazy-import edges,
cycles and module-size controls; `arras.boundary` checks public host imports.
CI runs these in `.github/workflows/ci.yml`'s complete Python suite. No repository
pre-commit configuration was found; do not claim a pre-commit hook exists.
Review remaining semantic ownership and private-access obligations directly.

| Slice | Owner / governing area | Depends on | Deliverable and validation gate |
| --- | --- | --- | --- |
| A0: baseline and declared version guard | Arras Luna implementation, Sol review; CONTRACT-002, TP-001; HA-0/1 | Existing boundary checks | Require exactly supported `umf.ddd` 0.1.0 when declared; refuse malformed/unknown versions with a path-specific diagnostic. Preserve legacy undeclared-DDD behavior for this narrow change and record its separate admission gap. Parser and register/validate tests prove no changed revision, document, graph or attribution after refusal, plus supported-version positive controls. No facet evaluator or current-action parser in this tranche. |
| A1: official released Python API probe | Arras with UMF owner; FR-13, HA-0/1 | A0 | Inspect/install one checksum-verified released wheel in an isolated environment. Record APIs, package/dependency identities and exact vector results for core-only identity, current DDD, `arras.view`, unknown versions/extensions and the current action fixture. Keep source/Rust candidate results separate. No wholesale dependency replacement until this probe establishes the compatible boundary. |
| A2: official admission/projection contract | UMF semantics; Arras integration; CONTRACT-002/003/004, H1/H7, HA-1 | A1 and upstream vectors | Settle validity/completeness versus executable capability; trusted extension registration, core identity projection, recipe/rule/selector subset, mixed-dialect refusal and legacy transition diagnostics. Reuse the existing `arras.view` checks as consumer-owned validation where the qualified callback API permits. Do not register a permissive schema merely to turn completeness true. Cover unknown-extension preservation and explicit refusal/loss; resolve memory facet execution through official validation or honest refusal of the affected operation. Update contracts/test scenarios before dependent code. |
| A3: registration and ownership | Arras with Truss; CONTRACT-002/004, H1/H4, HA-2 | A2; selected delivered HF-02/03 behavior | Register the same exact current document used by generation. Define owner/module/version/digest identity, equal-version/different-digest and downgrade refusal, atomic upgrade, dependency and retirement policy before implementation. Two owners cannot alter one another's records/actions. Recheck person identity/revocation on pooled calls. Missing ownership/retirement decisions block only their dependent operations. |
| A4: canonical action transport | Arras host implementation; UMF CONTRACT-079/900 vectors; H1/H2, HA-3 | A3 and qualified official action-plan boundary | Public synchronous `execute(request)` binds unchanged generated clients directly for read/apply/apply_batch/validate. Prove declared effects/preconditions, mismatch/unknown-action/unsupported-mode zero effects, advisory validation, current authorization, atomic rollback, partial stop/order, complete changed keys/counts, commit acknowledgement and lost-response uncertainty. Use the entire official wire-code inventory; durable replay requires restart proof. |
| A5: generated reads and native adapter adoption | Arras with Truss/UMF; CONTRACT-001/004, H3, HA-4 | A3; A4 for token checks; selected published HF-04/05/06 | Run bounded generated one-hop traversal and paging on actual Truss. Prove stable ordering, caps, empty/hidden targets, foreign/expired cursors and read-after-receipt. UMF settles edge/link-key projection and bulk consistency before wire extensions. Map native descriptors/errors without parsing SQL or error prose. Reconcile all current source requests before closing their limits. |
| A6: optional and cross-module execution | Arras/Truss execution; UMF profiles/vectors; H6/H7, HA-5 | A4/A5 | Two-module fixture proves qualified dependency keys, permitted links/navigation, forbidden foreign writes, missing/retired targets and collisions. Graph-write/2 proves omitted/create, omitted/set, explicit null and supplied values; retain version1 and required-key negative controls. |
| A7: supported local host and installed qualification | Arras, Truss support; H5, HA-6/7 | A3 for host contract; A4–A6 for final gate; delivered HF-07 cohort | Specify public factory/context lifecycle, cleanup, caller/host transaction ownership and compatibility/deprecation guidance. Run the shared conformance assertions through that public host on clean installed artifacts. Pin actual Truss/Weft/UMF wheel hashes, native inventory and supported subsets. Run local and existing Linux native/lineage gates appropriate to adoption. Package preparation is allowed; publication and merge need their own authorization. |

Ashlar's adapter and source-feed/applied-position integration are absent from the
visible Arras source. They require a separate selected implementation tranche;
A0–A7 do not qualify replica convergence, billion-entity service or managed
Lakebase deployment. Their absence does not block the bounded UMF–Arras local
integration cut and must remain explicit in capabilities and completion reports.

## Current priorities — cross-session review 2026-10-22

**P0 is the scoped Arras release; P1 is official UMF adoption; P2 is the Ashlar
reader/integration lane.** The 2,797-test/default and earlier UI/native/installed
receipts remain historical checkpoints. New telemetry runtime/configuration is
implemented and source-reviewed with 150 independent focused passes; the corrected
SDK verifier and temporary installed consumer have passed scoped review. Final
installed SDK qualification remains open. The public replacement Truss 0.0.48/Weft 0.4.51 pair is verified; coordinated
Arras pin/cohort adoption is underway. Earlier checkpoints use the old pair. The eight extensibility seams do not establish full official UMF or an
Ashlar adapter; release notes must name the supported legacy semantic profiles.

| Release-critical owner | Current blocker/dependency | Smallest closing gate |
| --- | --- | --- |
| P0-1 — release Sol/main Luna, coordinated in `01a16384-78eb-7b30-82e1-c1f1feacc383` | Typed per-host telemetry runtime/config/host/catalog changes are implemented across effective ADR-019 configuration, MCP/direct/ASGI/devhost and worker boundaries. Sol independently approved the runtime source with 150 focused tests and the corrected installed SDK verifier with executed no-op/snapshot counterexamples. The exact final wheel still requires fresh SDK qualification. | Complete this seam; prove actual SDK receivers, distinct Resources, concurrent/nested hosts, copied worker contexts, safe diagnostics and failure isolation. Rebuild and repeat through a fresh installed public consumer. Earlier canonical-only instrumentation is not this evidence. |
| P0-2 — packaged example/doctor Luna under the release owner | Packaged `config/default.toml` exists and is selected through the public reader/launcher in a fresh installed example. A rebuilt temporary wheel passes 20 doctor cases and eight telemetry phases. Sol independently confirmed that successful MCP/ASGI no-ops and incorrect completion-context projection are rejected. Neutral module/seed/graph composition has scoped installed evidence. | Rerun the exact final wheel through effective config, doctor and SDK paths using the reviewed verifier and retain its exact source/probe digests. No second parser or implicit demo content. |
| P0-3 — UI testkit Sol/shared-suite Luna, implementation active | The narrow published checker does not close the original full UI-suite ask. The corrected census is 17 canonical specs plus helpers/resources. Portable contracts and a shared testkit implementation exist. Packed execution is exposing fixture/resource and configured-brand issues; these and reviewed theme baselines remain open. | Reuse canonical assertions/resources through Node configuration and `AcceptanceHost` in source and a versioned public npm testkit. Parameterize host/schema URLs, outputs, theme baselines and Brand; serve the static compiled themed host through existing public `devhost.main --ui` on distinct same-origin ports, with no new origin flags. Run the full applicable a11y/e2e suite without copying tests. An explicitly labeled upstream acceptance fixture may use private Sandbox; public downstream composition is separate. Do not promote Sandbox to a runtime API. |
| P0-4 — Weft/Truss owner `01a16023-fabd-7fa3-9abf-44d42e7fd673`, then Arras adoption lane `01a163ae-137a-7e13-9220-4f23c2e43bbf` | Truss 0.0.48 and Weft 0.4.51 are public and independently verified. Truss exact-tag Linux source/native/migration/corpus/workload/publisher gates pass. Arras source pin/lock/index adoption is underway; final Arras native/installed proof remains open. New entity-facts/native/wheel bytes differ from historical candidates. | Receive the exact public pair and refreshed evidence; adopt pins, lock, find-links, reported versions and reviewed limits together. Materialize the native template/index from those actual assets. Run the full current-source native suite and strict fresh installed native verifier on named platforms. Preserve old hashes as history; no candidate adoption or ETA is inferred. |
| P0-5 — final release owner, after P0-1–4 | Final source/artifact convergence and publication remain open. GitHub assets are mandatory; current PyPI/npm access is unavailable and the human permits explicit deferral. | Freeze/Sol-review source, rerun aggregate Python/UI/native and complete external skeleton/doctor/testkit gates, rebuild wheel/sdist-rebuilt-wheel/npm/assets and compare exact payloads/metadata. Commit/push, pass exact-tag CI, publish GitHub assets, then verify fresh downloaded/installed bytes. Record any registry deferral without claiming registry delivery. |

The smallest immediate tranche is the full packed themed UI suite. The reviewed
SDK verifier is ready for the final exact-cohort wheel. Shared
UI testkit implementation proceeds while upstream native qualification runs.
Native adoption now starts from the delivered public assets. The dependency owner
is serializing additional clean public-Mac checks; full Arras native/UI campaigns
wait for its explicit quiet-window end, while offline source preparation continues.

| After the scoped release | Owner/dependency | Bounded next acceptance |
| --- | --- | --- |
| P1 — remaining A2 official admission/projection | Arras semantic lane + official UMF owner; exact A1 API/vector evidence | Agree the admission result, trusted extension registrations and core-to-Arras projection against public core models. Implement one core-only keyed-record fixture without mandatory DDD; retain exact source/unknown content and separate validity/completeness from executable capability. A2's memory safeguard closes silent unsupported-write safety, not constraint enforcement. Keep unsupported profiles refused. |
| P1 next — registration and one generated action/constraint slice | Arras + UMF + Truss; agreed A2 mapping and authoritative value/action boundary | Define owner/module/version/digest and upgrade/retirement/dependency authority. Run one unchanged generated action through canonical transport with actual constraints, current person authority, dry-run/violation zero effects, atomic rollback and receipt/retry/unknown-settlement behavior. Later generated reads/link keys, optional values and cross-module execution remain A5/A6. |
| P2 design now; bounded reader after shared projection/runtime agreement | Arras + Ashlar owner `01a15c6c-3938-71e2-8a35-bdb7ed8d9867` | Start with the receipt/progress contract, then one authorized publication-pinned lookup/page and zero-wait receipt-inclusion check. Settle complete transactions/no-op progress, epochs and person-scoped disclosure. Implement this reader in parallel with the action lane where dependencies permit; do not wait for every action/cross-module feature. Prove real convergence and false versus unknown freshness. Full managed/production/scale qualification remains separate. |

Official Python core supplies model admission/preservation and explicit registries;
no portable core projection/action-plan API is integrated in Arras. The experimental
official `umf_access.native_actions` host adapter does contain execution/admission
machinery; its existence is not portable core API parity or qualified Arras use.
Select and qualify the authoritative model/API or host-adapter boundary with its
owner rather than copying an evaluator. Current compiler/browser parity work and
pending installed/sdist qualification do not themselves close Arras adoption.

Ashlar already has scoped publication/query/feed work, including older UMF 0.8/
Truss 0.0.22 local evidence and a Python 3.12/Spark 4.2/Delta 4.4.1/JDK 21 current
candidate. These do not qualify Arras or managed authorization. TD-006 proposes
bounded incremental publication as a replacement for whole-history processing.
The owner identifies `resolve_publication`/`read_singleton` with exact snapshot
pins and mandatory policy owners, plus `AshlarTarget` scoped typed reads/pages,
as usable surfaces. An installed Arras-compatible cohort is still unqualified;
the current `.4-xxhash64` managed-page target also conflicts with an older
`AshlarTarget` allowlist and must be reconciled. Opaque Truss feed cursors in
publication progress are not a general `reached(receipt)` API; generic
`minimumProgress`/`reached` remain contract-only. Source ACK never establishes
destination visibility.
Publication/receipt/freshness contract design can proceed now without a new seed,
scale trial or cloud run. Separate seed/scale approvals do not block that design.

Managed Truss 0.0.49/PR 30 is a separate lane awaiting the public Weft 0.4.51/
Truss 0.0.48 base and its own final qualification. Its candidate/local stand-in
passes are not public 0.0.49 or actual Lakebase evidence. Managed roles/ACL/TLS/
token behavior remains unrun; no new public value/action/lowering API is implied.
It is not a dependency of the bounded 0.0.48 local Arras release unless a managed
service deployment is separately selected.

“Subgraph” currently means a placed module; `Backend.query` refuses cross-module
statements. Ashlar is a reader/replica, not a write provider. Arbitrary federation
and cross-backend atomic writes are not promised. GraphQL/schema-admin servability
coupling remains architecture debt; this release does not claim a decoupled pure
kernel. Address it along affected later contract slices, not as a new P0 feature.
The exact authoritative UMF execution boundary and refreshed public native
artifacts remain unresolved; owner reports above are not independently rerun
native evidence.

### A1 installed-release probe — completed locally 2026-10-22

Sol reviewed the [probe](evidence/umf-admission-20261022/probe_umf_admission.py),
[receipt](evidence/umf-admission-20261022/receipt.json) and
[official release metadata](evidence/umf-admission-20261022/release-metadata.json).
The released `umf-v0.5.4` asset `umf_core-0.10.0-py3-none-any.whl`
(asset 664083471, 71,258 bytes) has SHA-256
`49633924b45a3c8499d4fcc1a24c30d5a8fcb34d974ab019bbda987cb47da0f9`.
The runner checked that digest and all 25 installed wheel RECORD entries before
import. It reused the existing isolated upstream CPython 3.11.17 environment
read-only; this was not a fresh/minimal dependency installation. The receipt
inventories its actual dependencies, including unrelated installed tools.

Direct public `validate_document(raw, explicit_registry)` matched all 139 frozen
current-core cases, including complete ordered diagnostic objects and the
fixture-specific callback. Separately, `read_document` admitted 122 cases and
raised structural errors for 17 negative cases; these are distinct API paths,
not validation mismatches. A nonempty core-only record/member/primary-key fixture
was valid and complete. Valid facets and malformed inverted length definitions
received the expected metadata diagnostics. Unknown extension content and both
the untouched official action fixture and legacy Arras actions round-tripped;
the latter profiles remained incomplete, with unknown-content diagnostics.
Neither permissive DDD/view registration nor action execution was introduced.

A1 is complete for this exact released artifact/API probe. It establishes model
admission, preservation and metadata validation, not runtime instance enforcement,
DDD/view interpretation, native Rust support, action planning or execution.
`valid`/`complete` are necessary admission evidence and are not sufficient executor
capabilities. Arras dependencies/pins remain unchanged. The local native R2 wheel
is a separate artifact despite sharing version 0.10.0 and was not executed here.

### Bounded A2 memory profile — implemented/reviewed locally

CONTRACT-002/003/004 now separate admission from memory mutation capability.
The selected interim cut conservatively refuses a whole module's memory writes
when its source declares unserved facets/defaults/allowed values/semantic rules,
without evaluating those constraints. Existing served numeric behavior remains
qualified as the legacy memory subset. Required acceptance covers valid and
invalid candidate values, dry run, both batch modes and import, authorization
precedence, no import iteration, and unchanged graph/journal/load/position/replay
state. Reads and source bytes remain available. Official model projection,
trusted extension registrations and a public authoritative field-value/action
boundary remain dependent on the upstream API decision; consuming public core
models under an explicit Arras projection contract remains an option to review.

The bounded memory safeguard is implemented in `fakes_profile.py` and called at
memory action/dry-run, both batch and import entry points. Sol's final review
found no remaining blocking issue after rules-presence and malformed-carrier
refusals were corrected. The focused profile/fakes/core/sandbox run passed 124
tests; the guard passed focused Pyright and Ruff/format checks. Tests preserve
and read the original constrained catalog bytes, refuse both in-bound and
violating candidate values without state/journal/position/load effects, and
prove import refuses before records are iterated. Generic CRUD tests consciously
select a named plain derivative; product schemas are not stripped or normalized.

This completes only the selected A2 memory capability-refusal cut. It does not
implement official UMF value enforcement, core-only projection or canonical
actions, and does not qualify native/managed backends. Broader aggregate checks
are pending the parallel owners' integration; they are not represented by this
focused receipt. No dependency pin, adapter trait or public semantic API changed.

**Truss dependency checkpoint.** The owning Truss review reports that all 23
exact cases failing on archived Arras `cb64ecd` with Truss 0.0.45/Weft 0.4.49
passed unchanged in 67.85 seconds with the qualified local 0.0.48/0.4.51
candidate pair; see its [replay receipt](evidence/arras-native-baseline-replay-20261022/receipt.json).
The identified cause was `arras.view` 0.1.0 namespace admission, not Arras's
parameter/result carrier mapping or the generic “within its bounds” text.
This is a macOS ARM64 CPython 3.11.17/PostgreSQL 18.6 candidate substitution into
an archived-source scratch copy. It does not qualify the other native cases,
current Arras source, Linux, managed deployment or public release. Public
publication/Arras adoption remain with the owning release and exact-cohort gate;
Arras's dependency pins are unchanged.

## Extensibility Queue

EX-01–EX-08 are accepted work from the coordinated source review. EX-01 now has
scoped local distribution-boundary evidence below; EX-06, EX-04's forwarding phase and EX-03's root-export phase now have scoped local
implementation/review evidence recorded below. Other uncompleted phases are not
implemented capabilities. The [design](../02-design/downstream-extensibility.md)
owns the proposed seams and source findings. Arras owns their contracts and
implementation, with Sol planning/review and Luna implementation when a bounded
tranche is selected. Exact public interfaces and test scenarios enter their
governing contracts before code changes; the design's example layout is not a
verified consumer.

The selected EX-06 credential/grants repair, EX-04 schema-hook forwarding and
EX-03 packed root-export fixes completed in that order with local evidence below.
Their larger policy, assets and split phases remain separately gated. Establish
EX-01's manifest before expanding public config,
exports or compatibility claims; the broad sequence then follows EX-02,
EX-03 assets, EX-05/EX-07 and EX-08.

| Slice / priority | Bounded scope and governing boundary | Depends on | Acceptance before a support claim |
| --- | --- | --- | --- |
| EX-01 distribution/public manifests; implemented/reviewed locally | Extend existing public-API and import manifests to Python exports, CONTRACT-001–011 mappings, packed npm exports, typed config/CLI/env names, CSS tokens and telemetry. Specify artifact semver/deprecation separately from contract/vocabulary versions; retain immutable package pins/digests. | Existing API/boundary checks; A1/A7 only for claims about the official-UMF/native cohort | A generic overlay clean-installs exact Python/npm artifacts and checks public imports/exports. Publish a declared/source-tested/installed-qualified matrix with Python/platform/subset limits; tag/source metadata alone does not qualify publication. |
| EX-02 typed naming/env policy; after manifests | Reuse immutable `Brand` in the existing typed configuration boundary. Define presentation names, optional MCP tool prefix and opt-in environment aliases; retain canonical imports, wire codes, classes, tokens and instrumentation IDs. Separate presentation from credentials/handles. | EX-01; ADR-019, CONTRACT-005/007/008 and affected public config contract | Runtime UI/MCP/process presentation changes without rebuilding or changing protocol identity. Test startup name/prefix/collision bounds, wrapper imports, alias precedence and conflicting token/token-file refusal; configuration values import without environment I/O. No second Brand model. |
| EX-03 UI/provider packaging; root exports implemented/reviewed locally, assets deferred | Expose the advertised `DesignSystemProvider` and required public types through deliberate packed root exports. Later define a versioned frontend asset manifest separating frontend build/release from Python static hosting: host-built widget replacement versus prebuilt same-origin CSS/font/favicon/appearance assets. | Existing ADR-027/029 and UI contract; EX-01 before broader public split/assets | Actual packed public imports, root-hook render/defaults, shared chunk and one host React peer have scoped evidence below. Fresh registry installation/publication remains separate. Later assets/theme gates cover all replacement-widget accessibility props, contrast, host-owned appearance, scoped styles and separate platform visual baselines. |
| EX-04 operator/policy; forwarding implemented/reviewed, policy deferred | Forward the existing standalone schema surface's `authorize_schema` callback through composed UI hosting, preserving backend grants. Define a shared typed write-policy port only after ADR-005's workload, entitlement rule and governed-write prerequisites are met. Policy concepts are not callable signatures yet. | Existing schema-hook contract for forwarding; ADR-005 prerequisites plus amended contracts before the larger policy/audit phase | Composed/standalone forwarding and refusal gates have the scoped evidence below. Any later policy port covers direct Python, HTTP, MCP and administrative mutations, current principal and validate/apply revocation races; durable annotations bind to provider write/audit. Define transactional/version binding or refuse commit-time authority claims. Write hooks alone do not enforce derived-source read entitlement. |
| EX-05 explicit modules/content; after foundation | Document public resource loading, default-content exclusion and trusted host registration. Keep discovery explicit and host-selected; no import-by-string or document-driven execution. Separate source validity, execution profiles and renderer support; version new shared view terms upstream. | EX-01; A1–A3 for official UMF admission/projection, CONTRACT-002/010 | A generic custom module/resource loads without bundled defaults or private fixtures. Original bytes/unknown meaning are preserved and affected unsupported operations refuse. Host-specific screens/content remain host-owned; no new entrypoint registry is required initially. |
| EX-06 persistent backend credentials/grants; implemented/reviewed locally | Repair `LocalTruss.person()` reuse of persistent roles. Use an explicit shared host-owned stable credential source; ordinary attachment must not rotate another host's password, clear expiry or revoke independent memberships. Stale/inconsistent credentials refuse clearly; rotation/grant changes need an explicit coordinated operation. | CONTRACT-005/local lifecycle contract and focused tests first; no branding, official-UMF or upcoming release dependency | Local macOS/PostgreSQL 18.6/Truss 0.0.45 native, focused, reviewed CLI-correction and full-default-suite gates below pass for the selected repair. Preserve per-person credentials and distinguish host-created versus unrelated roles. No service-identity shortcut or silent grant reset. Broader adapter factory/conformance publication remains in EX-01/07. |
| EX-07 public adapters/conformance/CI; after declared surfaces | Support explicit backend factories and existing adapter protocols/public corpus through documented pinned jobs or a versioned reusable workflow. Package only reusable runners/resources; native/browser fixtures must be usable without copying repository tests. | EX-01/05; EX-03 for themed UI jobs; EX-06 for persistent-host safety; A7 for native integration claims | A generic external overlay runs clean-install/import/config/corpus jobs without private registries or copied tests, plus explicitly selected native/theme jobs. Public-repository checks reject private dependencies/sensitive fixtures/forbidden consumer imports using generic rules. Review and generalize legacy host-specific docs and test fixtures; preserve original downstream intake in its owning source, and do not embed customer names in an upstream deny-list. Preserve independent module, adapter and UI boundary controls; do not infer a reusable workflow exists. |
| EX-08 compatibility/offline doctor; after manifests | Document compatibility and changes per Python/contract/config/env/Brand/theme/UMF/backend seam. Add an offline doctor using public manifests/schemas with actionable pin/config/name/theme/module-profile diagnostics; native probes remain explicit separate operations. | EX-01 and the selected EX-02–EX-07 manifests/contracts | Compatible overlay passes; breaking export/config/token/profile cases diagnose without secrets, registration, network access or mutation. Static checks make no rendered-accessibility or native-execution claim; equal source versions/contract integers alone do not prove compatibility. |

Apply boundary cleanup alongside each selected EX/A slice, not as a wholesale
rewrite. Use the design's responsibility map to separate admission from
binding-specific preflight, while preserving current GraphQL collision/servability
refusal before registration becomes visible. Update Architecture and affected
contracts before moving that boundary. Extend the existing Python public-import,
AST/cycle and frontend checks with allowed/forbidden negative controls; do not
create parallel checkers, expose the shared action kit, or publish every widget as
a package. Configuration values must remain free of host I/O and implicit backend
construction.

## Goal execution and release acceptance — 2026-10-22

The human explicitly selected completion, testing, Sol review and release of all
eight generic downstream requirements. This supersedes earlier statements that
unselected EX work or publication were outside the active execution scope. Earlier
checkpoints retain their historical qualification. No downstream application
migration or customer-specific upstream behavior is authorized or required.

The coordinating goal is owned by chat `01a16384-78eb-7b30-82e1-c1f1feacc383`.
Sol plans and reviews; Luna implements. The semantic lane in chat
`01a163ae-137a-7e13-9220-4f23c2e43bbf` owns A1 and the bounded A2 official-UMF
admission/projection/value boundary, coordinating missing official APIs with their
existing upstream owner. The extensibility lane owns config/branding, UI assets,
public manifests, external testing/content hygiene, doctor and release orchestration.
Owners coordinate exact paths before mutation. One owner publishes the final
cohort; dependency lanes do not independently tag, push or publish it.

| Required result | Completion evidence required |
| --- | --- |
| EX-01 distribution | Public exact Python/npm artifacts on GitHub Releases, source/artifact hashes, clean installed consumers and observed dependency/runtime/platform matrix; real PyPI/npm uploads when existing access is available, otherwise explicitly deferred by the human |
| EX-02 naming | One typed Brand-based distribution config through ADR-019; public shim/launchers, process/UI names and explicitly contracted tool/env aliases; identity-conflict, default compatibility and redaction controls |
| EX-03 theming/split boundary | Independent host-built theme and prebuilt runtime-asset routes, versioned frontend asset contract, one React, no required private theme dependency, external contrast/axe/Playwright and theme-specific visual evidence |
| EX-04 policy | Documented operator/schema/action callbacks plus a qualified generic policy/refusal/audit boundary preserving current person/backend authority; ADR-005 never becomes permission for speculative sensitive derived data |
| EX-05 modules/content | Own namespaced module/seed/graph loads through public APIs without bundled defaults or imports from a consumer; exact supported UMF profiles and closed-view refusal explicit |
| EX-06 backend/deployment | Existing multi-host credential/grant regression retained; public backend/factory/conformance delivery usable externally with host-owned connections/roles/wheel supply |
| EX-07 downstream CI/hygiene | Real external generic skeleton runs pinned install/import/config/corpus/theme jobs without copying repository tests; generic dependency/content gates and legacy upstream content disposition |
| EX-08 upgrades | Per-seam changelog and offline installed-pin doctor with compatible and breaking config/export/name/token/profile controls; no hidden registration, credentials or network effects |

The skeleton must be built and run, not left as a directory diagram. Source-only,
synthetic, installed, browser and native evidence stay separate. Every selected
public surface enters its contract and catalog before dependent implementation.
Unknown semantics refuse before effects; no local UMF interpreter is created to
close a dependency gap. Runtime and OS claims follow observed tests, not classifiers.

Final release gate: no required unimplemented row or unresolved blocking Sol
finding; source/unit/static/browser and relevant native suites pass on the final
cohort; wheel/sdist-rebuilt-wheel/npm/asset payloads and metadata agree; full
external skeleton and upgrade checks pass; release notes state exact support and
limits; GitHub Release publication succeeds and clean consumers verify the downloaded
release bytes. Real PyPI/npm uploads and fresh registry installs are also required
when existing access is usable; the human explicitly permits deferral when those
credentials cannot be found, prioritizing GitHub release builds. A deferred registry
upload must remain visible rather than being reported as completed.
The user's release request authorizes the necessary source-control and publication
steps after these gates. Missing external account configuration remains a release
dependency, not a reason to stop independent implementation.

Release preflight found the public GitHub repository and authenticated push/admin
access. At this checkpoint the PyPI/npm package endpoints return HTTP 404 and no
repository publisher secrets or named release environments were found. The human
confirmed real npm/PyPI as intended targets, prefers existing access, and explicitly
authorizes deferring those uploads if access cannot be found while releasing
builds on GitHub. No credential values are requested or read into this record.
No user token ceiling was supplied; estimates remain provisional and review/test
work stays within each bounded tranche rather than an invented enforced budget.

The [naming inventory](../02-design/naming-surfaces.md) classifies canonical
identities, presentation and aliases. The [release checklist](../05-deploy/deployment-checklist.md)
turns the final gate into exact source, native, UI, installed-artifact and downloaded-release
checks. Both are under Sol review; neither claims publication.

The initial policy wrapper refuses nonempty audit annotations on an unsupported
provider. That proves refusal safety, not annotation support. EX-04 completion
therefore also requires an optional typed annotation-provider capability with
transactional synthetic commit/rollback evidence, safe inspectable refusal codes,
and explicit native unsupported behavior until a provider qualifies the seam.
The real policy still executes as the current person with no decision cache.

The [full product UI source receipt](evidence/arras-ui-full-20261022.json) records
1,428 unit tests, 205 real-host integration tests and 272 Playwright tests, including
all existing macOS visual comparisons, passing on the recorded Node/Chromium/
Python cohort. These tests do not qualify a later packaged checker or release;
its fresh npm/wheel/theme/CLI and downloaded-artifact evidence remain separate.


## Execution Contract

The user authorizes coordinated implementation and review in Arras, with UMF and
Truss changes staying with their existing owners. This primary chat does not grant
blanket commit/push, merge, release or publication authority. Existing upstream
release authorizations remain scoped to their owning chats. Do not create a new
chat, tracker, release commitment or date as a substitute for this plan.

A0 is the first code tranche. Then perform the bounded A1 installed-API probe and
record its result before sustained admission/action work. Estimates for the full
integration are unknown: no comparable metered run exists. No user token ceiling
or reliable per-slice runtime meter was supplied. The provisional work boundary is
A0 verification/review plus one A1 cohort probe; re-estimate remaining slices at
that checkpoint using available observations, without claiming an enforced cap.
Ordinary fixes remain authorized; material contract conflicts and missing required
native inputs stop only affected work. Do not call a planned or refused case passed.
The user has selected EX-06 credential/grant safety, followed sequentially by
EX-04 schema-hook forwarding and EX-03 packed provider exports for implementation.
Sol owns bounded contracts/planning and review; Luna owns code/tests. Verify/review
EX-06 before planning/starting the next code tranche. Broader policy, naming,
assets/split and unselected EX work remain planning backlog. Urgent EX-06 is independent
of the A1/upstream-release sequence. Authorization is not native qualification or
permission for merge/publication.

The user next selected EX-01 distribution and public API manifests. The UMF
coordination chat owned that bounded implementation, using Sol for planning/review
and Luna for source/tests. The other Arras chat retained its A1/A2 architecture
review. This selection authorizes local artifact preparation and qualification;
registry publication, merge and downstream migration remain outside scope.

## Continuation Evidence

2026-10-22 baseline reported by the coordinating chat: Arras source identifies
itself as 0.5.0 and pins Truss 0.0.45 with Weft 0.4.49. The ordinary suite returned
2,551 passes and 187 deselections, with one failure and eleven setup errors from
denied local socket binding in `tests/test_devhost_server.py`. The complete HTTP
file separately passed all 13 tests with socket permission. These are baseline
suite results, not native Truss or official-UMF conformance. The Arras checkout
has no committed HEAD; preserve the existing working files and exact tested bytes.

Source inspection finds only the Truss adapter and memory doubles.
Current-source probes reported by the coordinating chat show:

- The official action fixture is refused by the legacy reader. This does not
  qualify current action support or justify weakening UMF's fixture.
- Declared DDD version `999` is accepted and executable; A0 addresses this gap.
- A declared Unicode-scalar length maximum of three accepts/stores a longer name
  in memory. `PropertyInfo` does not retain facets. This is an execution-fidelity
  defect, not evidence against the native Truss facet controls or a reason to copy
  an evaluator. A0 does not close it.

Luna implemented A0's guard and parser/zero-state-mutation tests. The coordinating
chat reports 84 focused tests, Ruff and Pyright passing; a broader selected run
passed 333 core, conformance, module, action, fake and parser tests. Sol inspected
the three changed source/test files and found no blocking issue: declared invalid
versions produce the specified diagnostic before registration, supported fixtures
remain accepted, and undeclared-DDD behavior remains explicit. The unchanged-state
test preserves accepted bytes, catalog revision and existing entities. This proves
the bounded guard; no official admission or facet-execution support is inferred.

The Truss owner acknowledged HF-01–HF-07 in its isolated release checkout, with
80 installed migration cases, 61 corpus cases and a 1,000-object/edge workload
reported passing locally. Final Linux and public release qualification remain
pending. Its compiler currently admits the historical upstream view vocabulary
but not actual `arras.view`: this is a real profile gap requiring qualification.
That owner has started Sol profile review and Luna native model work, followed by
an exact Weft rebuild and native/browser/Truss qualification. Weft 0.4.51 is not
yet published. Arras pins remain unchanged until public adoption gates pass.
The UMF owner is implementing UMF-only shared transport conformance against the
general integration plan; that harness does not implement an Arras runtime.

The UMF owner separately reports the stdlib-only shared wire helper
`python/umf_access/conformance/unified_wire.py` passing nine Python 3.11 selftests,
an 88-module boundary check with zero violations and Sol rereview. It exercises
six synthetic wire cases only. These are source/component results, not a shipped
Arras transport, installed/native executor, replay or release qualification.

The coordinated extensibility review is accepted as EX planning backlog. Direct
source inspection confirms `LocalTruss.person()` generates a new token for an
existing persistent role, alters its password/expiry and calls `_leave_roles()`;
composed UI hosting also lacks schema-hook forwarding and the packed UI lacks the
advertised provider export. These are source findings; no new native, packed
consumer, theme or publication checks were run for this plan update. EX-06 repair,
then the small EX-04/03 fixes, are the next independent candidates. The design note
remains owned by its author; this update changes only plan sequencing and its index.

The four current Arras request files were hashed directly on 2026-10-22:

| Current file under `docs/helix/02-design/` | SHA-256 | Historical upstream snapshot |
| --- | --- | --- |
| `truss-requirements.md` | `0a7be408d15947382f0ab3a5af05a3ff0978c85e597db31ff6acb50caeabed60` | Different |
| `truss-statement-overhead-spec.md` | `caeb0276935514aa05735772fd3653dd9fb6cefaf7145d8f3263d60b6ba4ff15` | Different |
| `truss-registration-evidence-spec.md` | `1a60da1464be4d1b03b0877e27b497551b86782ef55c1776eeaa4c72a3742abf` | Same |
| `truss-query-and-conditions-findings.md` | `d31e36a1fdfa47fb35a0999f22317b410ad22455fb343d80f3362aad3228e777` | Different |

Keep the historical hashes in Truss's source-custody section unchanged. The primary
coordinator compared the files: requirements/overhead change only a 51-record list
to a 30-record list with unchanged timings; findings change the application name
and view vocabulary to Arras/`arras.view`; evidence-spec bytes match. These introduce no new backend
request, but the actual `arras.view` compiler gap above must pass before that
profile's acceptance or queue closure. The Truss owner received this reconciliation.
Next action: A1's installed-API probe, while the existing owners finish their
separate compiler/runtime gates. Record exact artifacts, commands, results and
missing semantic registrations here; coordination/start does not require waiting
for the entire upstream release in this chat.

EX-06 execution preparation: the user authorized the three bounded fixes in the
order above. CONTRACT-005 now specifies the host-owned source
`source(role, *, create: bool) -> str`, lookup-only reuse of existing roles, atomic
creation and unchanged existing password/expiry/memberships. `created_roles`
distinguishes new bootstrap grants from existing authority. `TrussBox` constructor
and `load()` must stop implicit regrants; explicit sandbox role changes reconcile
only the installer's direct known managed grants across hosts. Independent grantors
and inherited rights remain authoritative; a sandbox role label does not promise
exclusive effective privileges. Persistent password override
helpers refuse. The devhost composes a shared private file source; tests use only
owned isolated PostgreSQL and temporary files. TP-001 names two-host/new-connection,
restart, stale/expired credentials, concurrency, independent grants and negative
controls. No native tests were run or implementation passes claimed by this
planning update; Luna may implement this exact contract on the existing pin.

EX-06 verification checkpoint: Sol's final source rereview found no remaining
blocking finding after fresh verification on cached persistent identities,
actual-created-role bootstrap gating, separate auth/outage diagnostics and narrow
role-name conflict recovery. Product source has not changed since that review.
The coordinator reports 79 focused unit tests and Python-path-explicit Pyright
passing. Native gate `34481` passed nine safety cases covering live-host credential
reuse, revocation/expiry preservation, missing/wrong credentials, same/cross-database
creation, unowned roles and cached stale identity. The next stale-host case passed
its second-host grant-preservation assertions, then failed because its same-host
reload repeated nonidempotent seed steps while the existing seed flag was true.
The fixture now repeats `load(document)` without seed steps; grant assertions stay
unchanged. Earlier collection/fixture failures involved a wrong test import and
stale takeover/expiry expectations, not passing product evidence.

EX-06 local acceptance checkpoint: gate `70520` passed all ten remaining cases in
56.04 seconds: two safety cases, six existing persistent cases and two throwaway
cases. Together with the nine safety passes in `34481`, this is 19 native cases
cumulatively on unchanged product source, on local macOS/PostgreSQL 18.6 with
Truss 0.0.45. The captured tuple is Python 3.11.17, Darwin arm64, psycopg 3.3.6
and libpq 180006. Fixture-only corrections addressed original-grantor attribution,
seed-only-first-load behavior, refusal regexes, expiry cleanup and the unowned-role
callback. Preserve the earlier failed attempts; they are not passing evidence.

The coordinating run also reports 79 focused unit passes and zero errors from
`pyright --pythonpath /Users/erik/Projects/arras/.venv/bin/python`. An earlier
unqualified Pyright invocation selected the wrong environment; that failure is
tooling evidence, not a product failure or pass. Sol source rereview found no
blocking findings after the fixes. EX-06's selected repair is implemented and
reviewed for this local cohort. It does not establish Linux, managed-platform or
release/publication qualification; A1 and all dependency pins are unchanged.
EX-04's bounded UI callback patch is now dispatched for Luna implementation, with
Sol review required after its focused checks. No further EX-06 code is selected.

EX-04 source review: the four-line optional callback path forwards unchanged from
`ui.create_app` through `UI` to the existing `SchemaApp`. Existing standalone
schema tests and new composed tests cover both verbs, viewer/module forwarding,
auth/operator/parser precedence, false/error refusal, backend authority,
prefixed/root-path mounts and the unchanged operator-controlled mount gate. The
implementer reports 85 focused UI/schema/embedding/public-boundary passes, Ruff
clean and explicit-venv Pyright with zero errors. The final zero-effects refinement
uses the same compatible action-description change for allow, deny and exception
paths. Allow validates as changed and advances bytes/revision; false and error
preserve original bytes/revision for both verbs. The implementer reports 64 focused
UI/schema tests and Ruff passing after that refinement. Sol rereview found no
blocking findings. EX-04 forwarding is implemented and reviewed; no new policy
port or native behavior is qualified. EX-03 was then dispatched for the packed
root-export tranche; its completed local evidence follows below.

Full-Python checkpoint: 2,589 tests passed, one failed and 198 were deselected in
48.04 seconds. The failure is an EX-06 CLI boundary regression: default credential
path derivation parses a missing-password URL outside the existing scrubbed
startup handler, so `ValueError` escapes before the builder starts. The correction
moves source selection/construction inside the existing handler and preserves
the earlier URL validation/refusal before any source or builder call. Luna reports
29 focused devhost tests and Ruff passing; Sol review found no blocking issue or
new native risk. Final default-Python gate `97934` passes 2,590 tests with 198
deselections in 49.38 seconds on the corrected EX-06/EX-04 source. The database
role/devhost model paths and their 19 native cases are unchanged. No additional
native rerun is required for this error-boundary correction alone. EX-06 and the
selected EX-04 forwarding slice now complete their required local implementation,
verification and Sol review gates. EX-03's final local evidence and aggregate
quality checks follow below. No broader native platform, managed deployment or
release/publication claim follows.

EX-03 local completion: `ui/src/index.ts` now explicitly reexports the existing
four runtime values and twelve contract types. No new context, theme, subpath or
dependency was added. Luna reports `build:lib`, `check:externals`, scoped CSS,
`pack:wheel`, `test:packed-consumer`, TypeScript and Biome checks passing, plus 38
focused design-system/package-manifest/boundary tests. The final packed-consumer
rerun and Biome check over 380 files pass after review corrected runtime file-URL
imports to bare public package imports in an isolated temporary consumer.

The tested local tarball is
`src/arras/ui/npm/documentdrivendx-arras-ui-0.5.0.tgz`, SHA-256
`2cfd1041bcfde64a5353c919865fab81a5039643fbb38819a2b5e2a30c27603e`,
independently rechecked by Sol. The consumer resolves declarations and runtime
root/browser/shell export maps, renders a host widget using the root hook beneath
the public browser palette slot, and proves built-in fallback and eighteen role
tokens. Structural imports show all entries reach the shared context chunk;
React/ReactDOM resolve to the single host peer pair. The consumer links the exact
workspace dependencies around the unpacked tarball; this leaves fresh registry
installation/publication and broader internal-widget/theme qualification separate.
Sol's corrected-script/source review found no blocking findings.

Final aggregate Python quality checks report Ruff check clean, Ruff format clean
for 178 files, and explicit-venv Pyright with zero errors and zero warnings.
Together with default Python 2,590 passes, the scoped 19 native cases and EX-03
packed/UI checks, the three selected priorities are implemented, verified and
reviewed locally. A1–A7, EX-01/02/05/07/08 and broader EX-03/04 phases retain their
existing open scope. No merge or release/publication is claimed.

Sequential follow-ups are now specified in CONTRACT-005 and TP-001. EX-04 adds
only optional `authorize_schema` forwarding through composed UI creation to the
existing standalone schema app, preserving its principal/module, refusal order,
backend authority and absent-schema behavior. EX-03 adds explicit existing
provider/hook/default/token/type root exports and verifies an actual packed
consumer, shared entrypoint context and one host React peer. It changes no
visuals or theme/policy semantics. Dispatch each after its predecessor's tests and
Sol review; broader EX-03/04 phases remain unselected. No follow-up implementation
or passing qualification is claimed by these specifications.

### EX-01 distribution/public API — final local evidence, 2026-10-22

The selected distribution-boundary tranche is implemented and reviewed. One inert,
schema-versioned [public catalog](../../../src/arras/public-api.json) governs the
host-import allowlist and records intentional exports, selected signatures,
eleven contracts mapped to the existing nine runtime keys, process/config/CLI
names, UI symbols/peers/tokens, telemetry and separate compatibility/version rules.
Development and process surfaces remain classified separately from host imports.

[The verifier](../../../tools/verify_distribution.py) checks semantic Python
metadata, licenses/resources/assets, archive integrity and complete Arras payload
identity. It builds a wheel from an extracted sdist, installs each wheel into a
separate fresh environment outside the checkout and runs the wheel-carried npm
package against that same wheel's catalog. CI/release invoke this gate; the JSON
receipt is uploaded separately from the publisher's distribution directory.

| Evidence category | Observed result and limits |
| --- | --- |
| Declared | Python >=3.11, classifiers 3.11/3.12/3.13; these declarations alone are not executed compatibility evidence. |
| Source tests | The full default suite passed 2,600 tests with 198 native deselections and Weft required; initial socket-denied sandbox failures were resolved by a permitted localhost rerun. Final metadata/catalog/verifier controls separately passed 12 focused tests after tool-only amendments. |
| Quality/boundaries | Whole-repository strict Pyright passed with the repository interpreter; final touched-file strict/lint/format checks passed. Existing host/module/cycle checks remain in the default suite. |
| UI | 48 focused tests across four files, 382-file Biome check, typecheck, scoped CSS/externals and actual positive plus eleven catalog-mutation checks passed. |
| Installed Python artifacts | Python 3.11.17 on macOS 27 arm64, GraphQL Core 3.3.0. Original and sdist-rebuilt wheels independently passed public imports, InMemory operation, composed UI/schema callback and packaged resource checks without Truss/psycopg installed. |
| Packed npm artifact | Each wheel's exact tarball passed export/peer/runtime/declaration inventory, isolated typecheck and render checks. JavaScript dependencies are workspace-linked; this is not fresh registry installation. |

The [machine receipt](evidence/arras-distribution-20261022.json) records exact
artifact digests, separate environment paths and capture limits. The
[default Python run](evidence/arras-distribution-python-20261022.txt) retains its
actual output. Wheel and rebuilt wheel SHA-256:
`b66b97874eec0ae367d66a4150d9893e13e39ffa0aff370965026f1ff29bacb0`.
Final sdist: `b819b16fd0862dd6216bcc0ab67c7be6e52b6b64c4614631706384de3099a9eb`.
Embedded npm: `971c9bbd8af453bc1ab30ba1e2b998a8cfc6a4bd1ced9a6f2111e0cdadabc36b`.
The final source sdist also byte-matched the current verifier and its two test files.

Sol approved the scoped source review after metadata/catalog and release-input
findings were closed; the final artifact rerun then passed. No Linux, Python
3.12/3.13, registry publication/installation, native PostgreSQL, managed deployment
or official UMF runtime qualification is added by EX-01. A1/A2 and the separate
Ashlar design queue remain owned by the other session. No downstream application
was edited.

## Integrated source checkpoint — 2026-10-22

The generic extensibility candidate passes the full default Python gate with Weft
required: **2,774 passed, 199 native deselected**, zero failures, 79.47 seconds.
Whole-repository Ruff, format and strict Pyright also pass. The existing 926-line
module ceiling and adapter-only native SDK boundary remain enforced after the
private doctor/conformance splits. The [source receipt](evidence/arras-source-gate-20261022.json)
records interpreter/platform, current source hashes and the old dependency pins.

This is source evidence on Truss 0.0.45/Weft 0.4.49, not native acceptance or final
release evidence. Exact public 0.0.48/0.4.51 adoption, final artifact rebuild and
installed checks, Sol final review, exact-tag Linux gates and downloaded public
assets remain required. Existing publishing access will be used if available;
the human permits deferring PyPI/npm uploads while requiring GitHub release assets.

### Expanded public-surface and release-tool checkpoint

After direct consumer review found catalog/host-boundary gaps, the deliberate
manifest now includes the lazy public TrussHarness and asset validator, with an
exact `arras.mcp: [launch]` launcher subset for thin shims. Concrete consumer
controls cover every selected new seam and actual policy refusal before provider
effects. Source review also clears the installed-native verifier and bounded
APT/locked-browser CI setup. Their offline/fixture controls do not establish
native or hosted execution.

The expanded full default suite passes **2,797 tests, 199 native deselections**,
zero failures, 74.39 seconds. Ruff/format pass all 236 files. The coordinated owner
reports whole strict Pyright zero errors on CPython 3.11.17. The
[expanded source receipt](evidence/arras-source-gate-expanded-20261022.json)
preserves exact current hashes and qualifications; the earlier 2,774-test
checkpoint remains historical. Current native pins are still 0.0.45/0.4.49.
Public 0.0.48/0.4.51 adoption and final release gates remain pending.
The subsequent CI-only hard-kill/job-ceiling amendment is separately recorded in
the receipt with Luna/Sol static validation; it does not replace this source run
or establish hosted browser execution.

### Mandatory installed-native release gate preparation

The release graph now requires `installed-native` before GitHub asset publication,
in addition to the existing source-native and UI gates. Its private binder adds
only the verified build wheel's actual Arras version/SHA to a five-field reviewed
Linux cohort template. Native/runtime/corpus fields remain unchanged. The job
uses a clean Python 3.11 driver, the full installed public conformance CLI and
retained diagnostics; missing data fails closed. Invalid/missing verifier receipts
become failed evidence while valid failed details and the original nonzero exit
are preserved. No database cluster files are published as evidence.

Luna's 26 focused binding/receipt/workflow tests pass; Sol independently reran the
17 binding/receipt cases and cleared the bundle. Quality and syntax checks pass.
The [preparation receipt](evidence/arras-release-native-gate-preparation-20261022.json)
records exact hashes and limits. A subsequent shell fix preserves the saved native
verifier exit even when receipt normalization fails: 29 focused tests pass, and
Sol independently passed three controls executing the actual workflow shell.
These controls prove exit/log retention, not native execution. This is source
preparation, not native execution.
The actual template/index and any limit allowlist remain absent until the public
Truss/Weft pair is delivered and qualified. The owner is rebuilding its selected
cohort after test-source corrections; earlier candidate hashes remain historical
and must not be relabeled or assumed equal to the refreshed public artifacts.

### Requirement-fidelity correction: EX02 telemetry naming remains open

The final clause-by-clause review found a requirement that source checkpoints did
not cover: configurable telemetry service identity, attribute namespace and log/
event prefixes. The current canonical instrumentation plus host-owned Resource
and formatting does not satisfy that ask. The earlier canonical-only policy was
a design choice, not a human waiver. EX02 and the all-eight goal remain open.

Sol has bound a minimal generic typed per-host naming/projection seam in
CONTRACT-005/008, ADR-018/019 and the test plan; Luna implementation is underway.
TelemetryNames feeds DistributionConfig, and TelemetryContext scopes the selected
provider through direct-library, ASGI and MCP operations. Explicit service identity
requires an actual matching provider Resource, rather than a span attribute. Canonical defaults,
host-owned providers/exporters, no global cross-host rename, default-deny
redaction before projection and failure isolation are required. Closure needs an
actual SDK receiver with distinct host Resources plus concurrent/nested context,
redaction and failure controls, followed by Sol review and final installed-artifact
proof. Arras-owned worker submissions must propagate the selected context, and
existing exception-detail logs must conform to the class-only diagnostic rule.
A real packaged ADR-019 example file is also required; generated doctor input
alone does not establish that skeleton deliverable. No prior source or packed-UI
pass is counted as this missing evidence.

### Scoped telemetry source checkpoint — not installed or release qualification

Luna implemented the bound generic naming/context seam. Sol approved its selected
source and independently ran all eight affected test files: **150 passed in
12.68 seconds**, CPython 3.11.17 on Darwin arm64 with OpenTelemetry API/SDK
1.45.1. The [source review capture](evidence/arras-telemetry-source-review-20261022.json)
records the exact command, 25 file hashes and inventory digest. Strict Pyright,
Ruff and formatting passes are owner-reported in that capture. Doctor remains
below the unchanged 926-line ceiling.

The tests exercise separate provider Resources, exact app/callback witnesses,
worker propagation, streamed/awaited work, cancellation/reset, operation snapshots,
projected parent/status/error semantics, class-only diagnostics and sink/provider
failure isolation. A global-call counter proves an explicit provider does not fall
back to a global provider. This is a focused source checkpoint, not a rerun of the
entire default suite or a native qualification.

The previous temporary installed wheel (`cde2cb28...`) and its 20-case receipt do
not close the installed gate: Sol executed a counterexample showing that aggregate
spans could mask missing MCP/ASGI telemetry, and the wheel also predates later
runtime hardening. A corrected per-path public consumer, rebuilt wheel and current
verifier identity are required. The packaged ADR-019 file itself is installed and
selected explicitly; its broader consumer proof remains under review. Final UI,
native, exact-artifact and public-download gates stay open.

### Release workflow and corrected SDK verifier review checkpoint

Sol independently approved the release workflow/public-asset comparator source:
29 focused tests passed, including execution of honest and malicious download
shell controls. The graph preserves the reusable downstream invocation, assembles
16 bounded public assets only after native/UI gates, anchors anonymous downloads
to the trusted assembled sums and build-wheel digest, and runs consumers on the
public bytes. Publishing the final tracked release notes in the GitHub body is a
remaining presentation change; actual hosted execution and publication are open.

The newer installed SDK verifier fixes the earlier aggregate false pass: Sol
independently replaced MCP with a successful empty result and each ASGI path with
HTTP 200, and all three controls fail their own missing-span assertion. A separate
executed counterexample still passes when the installed runtime is deliberately
mutated to finish using ambient rather than entry context. This is a verifier
coverage defect, not evidence of that defect in the actual production source.
Luna is adding completion-attribute/structured-log witnesses, observed logical
event counts and stronger built-in controls. Every changed verifier/probe digest
requires a new receipt; no temporary 20-case receipt closes final qualification.

### Public native dependency handoff — Arras adoption not yet qualified

[Truss 0.0.48](https://github.com/DocumentDrivenDX/truss/releases/tag/v0.0.48)
passed exact-tag run `39838914360` and its public assets were independently
verified against tag source `8e89a068bcb68f1e631388ddc59bc97da748563d`.
Its wheel SHA-256 is
`1aedf614ff3d3ff7a61bd4d91887ede650a7135d1239e8564c1c297c0ddc37c3`;
the checksum-manifest SHA-256 is
`4275c8e7fd2efd7d5ec2a8d25bad4dc9959aed5c2b94a707db1eb63a209b1427`.
[Weft 0.4.51](https://github.com/DocumentDrivenDX/weft/releases/tag/v0.4.51)
has checksum-manifest SHA-256
`62c9d8082eb2f446446d7b94ff7ef7f48769e3cd836e5641c2951069302a6c75`.
Its frozen compiler source is
`557153731e9f5d0583193a1189a07c6ed485d3d3`.

These public dependency gates permit coordinated Arras adoption. They do not
qualify Arras's final source, public harness, installed cohort or release.
Linux ARM remains packaging-only and unadmitted. Additional dependency public-Mac
checks are pending; no Arras native timing run overlaps their quiet window.

### Corrected SDK and release-workflow source review

The [SDK review capture](evidence/arras-sdk-source-review-20261022.json) records
Sol's independent honest and counterexample runs against the exact extracted
temporary wheel. Successful MCP output, operator HTTP 200, console-only HTTP 200
and the former completion-context mutation now fail their own phase assertions.
The owner fresh Python 3.13 twenty-case receipt agrees with the reviewed driver,
generated probe and wheel identities. Eight telemetry phases include explicit
completion-snapshot witnesses. Event counts represent selected structured
operation records, not SDK span events or a count inferred from spans. The
temporary candidate still carries the old native pin; repeat on the frozen wheel.

The [release-workflow review capture](evidence/arras-release-workflow-source-review-20261022.json)
records 30 independent focused passes after adding validated-tag checkout and
the tracked release-notes body. These are source/consumer checkpoints, not actual
hosted native, full portable UI, release or public-download results.

### Requirement-fidelity correction: portable existing UI suite remains open

The published theme checker qualifies tokens, widgets, contrast, axe, keyboard
behavior and selected screenshots, but it does not deliver the existing full
Playwright accessibility/UI suite to a downstream without a checkout. That suite
still depends on source-owned servers, fixed origins, development controls and
fixture paths. The explicit EX-03/EX-07 own-suite portability requirement remains
a release blocker; narrower checker evidence is not a waiver.

Sol is binding a small public npm testkit with a Node configuration entry and a
browser acceptance-host entry. Source and packed consumers must use the same
canonical tests/assertions and standard neutral acceptance resources. The host
supplies explicit URLs, output directories, selected branding and per-theme
macOS baselines; no implicit browser/dependency installation or production-side
Node imports are allowed. Luna implementation must pass a real packed themed
suite run, missing-resource/test-count controls, public-catalog checks and Sol
review. Linux retains the nonvisual suite. The upstream standard development
fixture may use upstream internals; that does not make those internals public
consumer APIs. The separate installed example must retain public-only composition.

### First public candidate and actual qualification failures

The coordinated source candidate is commit
`94c7e58a021941889ee8a2ab438f1f0353cc14ab` on
`codex/arras-distribution-release`, under [draft PR #1](https://github.com/DocumentDrivenDX/arras/pull/1).
It is not tagged or released. Hosted [CI run 39848187520](https://github.com/DocumentDrivenDX/arras/actions/runs/39848187520)
passed the public-content gate, full Ruff/format and Pyright checks, builds, and
exact source/sdist-rebuilt wheel and npm comparisons. The default Python suite,
UI formatting check and fresh installed example exposed stale test assumptions;
those failures remain part of this candidate's record rather than being counted
as successful gates. Luna's four test corrections have Sol approval and 17 doctor
plus three targeted test passes. The two UI formatting corrections are reviewed;
formatting the packed acceptance helper also requires a new resource digest at
repack. The whole candidate must rerun its gates after integration.

The first local native attempt was invalid infrastructure evidence: sandboxed
PostgreSQL startup failed at System V shared-memory allocation before backend
behavior could be tested. The corrected host-permission startup control passed
one real registration/foreign-receipt test in 10.58 seconds. The subsequent
unchanged 199-case suite on public Truss 0.0.48/Weft 0.4.51/PostgreSQL 18.6.1
finished with **192 passed, seven failed, no errors** in 596.14 seconds on macOS.
The Linux CI native job independently finished with **192 passed, seven failed**
in 526.50 seconds. The same seven cases concern multiplicity error mapping,
load audit counts, module-scoped query refusals/conformance, a now-passing
registration-validation limit and historical runtime revision expectations.
Sol is classifying actual carriers and assertions before Luna changes behavior,
expectations or the declared limits. No native qualification, limit relaxation
or publication is established by these failed runs. Owned local PostgreSQL
processes were stopped after the corrected campaign.

The follow-up Sol-reviewed change maps the exact native multiplicity and
unavailable-source diagnostic carriers to the existing public errors, preserves
legacy delete/dependency handling, updates stale audit/revision expectations and
removes only the registration-validation limitation that now passes. The corpus
and its assertions are unchanged. The seven original failing tests then passed
in 119.05 seconds on the same public macOS cohort, with owned PostgreSQL cleanup
confirmed. There are now eight declared limits. This focused result permits the
next candidate and UI build; the whole native suite and final installed-artifact
gates still need to pass. The installed example's stale TOML selector assertion
has a reviewed public-launcher/bootstrap replacement, pending fresh wheel proof.

The subsequent [candidate CI run 39851655422](https://github.com/DocumentDrivenDX/arras/actions/runs/39851655422)
on `72cb53a988683bb67e1e383c81086d0c1be0a3f6` passed all **199 native
Linux tests**, with 2,883 default deselections, in 348.78 seconds. Its source
quality/build, exact artifact comparison and fresh installed-example job also
passed. The default suite still found a historical/current limit-inventory
mismatch and a stale mutation selector; UI unit checks found a duplicated default
brand literal in the Node testkit. These require their own reviewed corrections.

The first actual full packed themed capture was stopped on a common fixture
failure: its compiled host did not mount the schema browser's static assets,
causing iframe 404s. The wheel's prebuilt page contained those assets. No visual
baseline changed and no full-suite qualification was claimed. The reviewed fix
copies the exact installed dependency assets into the compiled host and compares
its complete file inventory and bytes against both the installed dependency and
wheel-carried resources. A pure branding-values module also gives browser and
Node configuration one default without importing React into the Node entry.
Baseline capture must report `updated-unreviewed`; only a visually reviewed,
ordinary comparison run may produce final `compared` evidence.

## Validation Plan

- A0: focused `tests/test_umf.py` and `tests/test_core.py`; existing module/host
  boundary tests; `uv run ruff check .`, `uv run ruff format --check .`, and
  `uv run pyright`. Record actual results after the change.
- A1/A2: shared official admission vectors compare validity, diagnostic code/path
  and completeness with the pinned reference. Prove original-byte preservation,
  required-meaning refusal, consumer callback scope/version and no document-driven
  code loading. Missing or failed native imports never select a semantic fallback.
- A3–A6: real Truss tests cover registration ownership, per-person revocation,
  concurrent duplicate creation, rollback, changed-input conflicts, commit/response
  loss, dry-run completion, bounded authorized paging and optional/cross-module
  effects. Memory passes remain separately labeled and cannot qualify native runs.
- A7: clean installation, exact package/native/compiler manifest and the shared
  conformance runner; fail required missing-backend tests rather than count skips.
  Existing commands include `ARRAS_REQUIRE_TRUSS=1 uv run --no-sync pytest -m truss -q`
  and `ARRAS_REQUIRE_WEFT=1 uv run --no-sync pytest -q`. The ordinary default suite
  excludes Truss; its pass count is not native acceptance.
- Changed portable UMF semantics remain with the UMF owner, including Bun,
  Chromium and installed-binding parity. Arras UI/browser/package acceptance is
  required only if an implementation slice changes those surfaces; the current
  narrow guard introduces no UI feature.
- Preserve CONTRACT-008's allowlisted, host-owned OpenTelemetry signals. If new
  diagnostics are needed, amend the contract before instrumentation, then prove
  redaction/correlation and failure behavior through an actual receiver before a
  diagnostic pilot. Store safe run/attempt references and capture limits here;
  console silence is not evidence and no new receiver integration is claimed.
- Review once with Sol after Luna's change; review fixes and affected dependencies
  again only when new evidence requires it. Record remaining limits explicitly.
- EX items close individually against their table gates after contract/test
  amendments. Record source-only findings, synthetic helpers, packed consumer runs,
  actual native runs and publication evidence separately. Queue acceptance is not
  evidence that any proposed seam is implemented.

## Risks and Rollbacks

| Risk | Response | Rollback |
| --- | --- | --- |
| A permissive registry marks unknown semantics complete | Qualify exact released APIs and trusted extension callbacks; compare shared positive/negative vectors | Retain the matched existing cohort and refuse affected execution |
| New parsing or field checks fork UMF semantics | Keep official admission/plans authoritative; make capability and loss explicit | Disable the new unsupported route without rewriting original documents |
| Adapter adoption outruns native publication | Require exact public assets, compiler/native identities and clean installed runs | Keep the previously qualified pin; do not label candidates supported |
| Ownership, retries or tokens leak authority/overstate settlement | Native revocation, owner separation, commit-loss and cursor-scope controls | Refuse the affected capability and preserve uncertainty/recovery evidence |
| Current requests differ from the historical queue | Reconcile current digests against historical dispositions before closure | Preserve both snapshots; leave unmatched requests open |

## Exit Criteria

Plan readiness means the owners, dependencies, bounded first tranche and observable
gates above are reviewable. It does not establish integration completion.

- [x] A0 passes its guard, unchanged-state, boundary, quality and review gates.
- [x] A1 identifies and probes the exact released official artifact/API cohort,
  with missing semantic/runtime boundaries recorded separately.
- [x] The selected A2 memory capability-refusal safeguard passes focused zero-effect
  and source-fidelity checks; it does not establish constraint enforcement.
- [ ] Remaining A2 official admission/projection and trusted extension contracts
  are settled before their dependent implementation.
- [ ] A3–A7 prove current-source registration, declared execution, ownership,
  generated reads, selected optional/cross-module behavior and installed public-host
  conformance on their named native cohort. Unsupported cases remain explicit.
- [x] The claimed legacy memory mutation subset refuses affected unsupported
  declarations explicitly; broader official facet/rule execution remains open.
- [ ] Current Arras request snapshots are reconciled with HF-01–HF-07 dispositions;
  no stale ask or candidate result is counted as release delivery.
- [ ] Canonical contracts/test scenarios, evidence and Sol review agree with the
  delivered subset. Downstream application migration, Ashlar feed, actual Lakebase qualification,
  merge and publication remain outside this plan's completion claims.
