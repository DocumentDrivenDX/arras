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

**P0 is closed for the scoped Arras 0.5.1 generic distribution release. P1 is
remaining official UMF adoption; P2 is the separately governed reader/integration
lane.** The immutable source is `8b786bb7629a6425e5a2b3b528378f0d92f0b847`.
[Publication run `39879533273`](https://github.com/DocumentDrivenDX/arras/actions/runs/39879533273)
passed source/native/build/SDK/installed-native/UI/assembly and published all
sixteen assets. Its postpublication shell failure remains in history. The reviewed
read-only [verification run `39883764998`](https://github.com/DocumentDrivenDX/arras/actions/runs/39883764998)
then passed all three jobs: original-anchor checks, fixed reusable installed
consumer, and full anonymous asset/distribution/doctor/example/theme qualification.
The [final Sol review](evidence/arras-0.5.1-public-verification-review-20261023.json)
binds actual receipts and preserves the separate runtime/platform limits.

| Release-critical owner | Completed P0 evidence | Retained boundary |
| --- | --- | --- |
| P0-1 — release Sol/main Luna | Public 17d wheel doctor 20/eight SDK phases/three false-pass controls pass; host-scoped naming/config/MCP/HTTP/worker attribution reviewed | Separate Mac SDK and native cohorts; no global provider or service identity |
| P0-2 — example/doctor Luna | Downloaded-wheel fresh example 4 and memory 72 pass; seven replica-only cases inapplicable; fixed reusable consumer passes | Explicit module/seed/graph only; official semantic admission remains P1 |
| P0-3 — UI Sol/Luna | Downloaded Linux 205 nonvisual cases, four route comparisons and four negative controls pass; separate Mac 272 and unchanged 75 reviewed baseline hashes retained through payload bridge | No Linux visual or Mac 17d execution claim |
| P0-4 — native ownership lane | Publication Linux source 199 and installed native 64/eight declared limits/seven replica-only inapplicable pass on public Truss 0.0.48/Weft 0.4.51; seven distributions bound | Mac installed proof remains separate; no managed deployment or system-link audit |
| P0-5 — release owner | GitHub16 assets/SUMS/aggregate and fresh anonymous consumers independently reviewed; all selected EX delivery gates close | Registry uploads deferred under human instruction; original failed postpublication run not relabelled |

The delivered wheel/npm/sdist identities are recorded in the design note and
public aggregate. Mac 598/460 component receipts retain original bytes and are
linked by an independently reviewed container/payload equivalence bridge.
The release is available at [v0.5.1](https://github.com/DocumentDrivenDX/arras/releases/tag/v0.5.1).
P0 closure changes no package, tag, asset or semantic support claim. Remaining
A2–A7 and P1/P2 contracts, native capabilities and deployments stay open below.

| After the scoped release | Owner/dependency | Bounded next acceptance |
| --- | --- | --- |
| P1 — bounded A2 implemented; broader semantics remain open | Arras semantic lane; exact released API/vector evidence and CONTRACT-002/003/004 | Source and fresh installed checks passed on the unreleased 0.5.1 candidate for immutable admission, fresh-empty official Registry and explicit memory-only core metadata projection. This historical receipt is not a 0.6.0 wheel result. Preserve distinct validity/completeness, projection, provider qualification and execution. Trusted extension registration and value/action runtime semantics remain later work. |
| P1 next — registration and one generated action/constraint slice | Arras + UMF + Truss; agreed A2 mapping and authoritative value/action boundary | Define owner/module/version/digest and upgrade/retirement/dependency authority. Run one unchanged generated action through canonical transport with actual constraints, current person authority, dry-run/violation zero effects, atomic rollback and receipt/retry/unknown-settlement behavior. Later generated reads/link keys, optional values and cross-module execution remain A5/A6. |
| P2 design now; bounded reader after shared projection/runtime agreement | Arras + Ashlar owner `01a15c6c-3938-71e2-8a35-bdb7ed8d9867` | Start with the receipt/progress contract, then one authorized publication-pinned lookup/page and zero-wait receipt-inclusion check. Settle complete transactions/no-op progress, epochs and person-scoped disclosure. Implement this reader in parallel with the action lane where dependencies permit; do not wait for every action/cross-module feature. Prove real convergence and false versus unknown freshness. Full managed/production/scale qualification remains separate. |

Official Python core supplies model admission/preservation and explicit registries;
no portable core projection/action-plan API is integrated in Arras. The experimental
official `umf_access.native_actions` host adapter does contain execution/admission
machinery; its existence is not portable core API parity or qualified Arras use.
Before the next execution slice, pin a released authoritative action/value
extension API and its conformance vectors with the UMF owner. That boundary
remains unresolved; private constraint/literal kernels are not a substitute.
Qualify the selected model/API or host-adapter boundary rather than copying an
evaluator. Current compiler/browser parity work and
pending installed/sdist qualification do not themselves close Arras adoption.

Ashlar already has scoped publication/query/feed work, including older UMF 0.8/
Truss 0.0.22 local evidence and a Python 3.12/Spark 4.2/Delta 4.4.1/JDK 21 current
candidate. These do not qualify Arras or managed authorization. TD-006 proposes
bounded incremental publication as a replacement for whole-history processing.
The owner identifies `resolve_publication`/`read_singleton` with exact snapshot
pins and mandatory policy owners, plus `AshlarTarget` scoped typed reads/pages,
as usable surfaces. An installed Arras-compatible cohort is still unqualified.
Current `AshlarTarget` source explicitly maps the managed
`0.2.0-managed-current-core-xxhash64-pages-candidate` target to
`ashlar-delta/0.4-xxhash64` and `spark-xxhash64-typed-key/0.1`; the earlier
allowlist conflict is no longer a source blocker. This source inspection does
not qualify an installed Arras/Ashlar cohort. Opaque Truss feed cursors in
publication progress are not a general `reached(receipt)` API; generic
`minimumProgress`/`reached` remain contract-only. Source ACK never establishes
destination visibility.
Publication/receipt/freshness contract design can proceed now without a new seed,
scale trial or cloud run. Separate seed/scale approvals do not block that design.

Public Truss 0.0.49 and Weft 0.4.51 are available. The separate Arras adoption
branch pins those exact artifacts; its [local qualification](evidence/truss049-adoption-20261023/local-qualification.json)
records 199 adapter cases and two transaction-mode cases on editable source
`40ed2481507f11a61ed81260fbfffbfc8ff91eba`. These local results do not qualify
fresh installed artifacts or actual Lakebase behavior. Managed roles/ACL/TLS/
token acceptance remains `not_run`; no new public value/action/lowering API is
implied. This adoption leaves the earlier bounded 0.0.48 release evidence intact.

“Subgraph” currently means a placed module; `Backend.query` refuses cross-module
statements. Ashlar is a reader/replica, not a write provider. Arbitrary federation
and cross-backend atomic writes are not promised. GraphQL/schema-admin servability
coupling remains architecture debt; this release does not claim a decoupled pure
kernel. Address it along affected later contract slices, not as a new P0 feature.
The exact authoritative UMF execution boundary and Arras qualification of later
native capabilities remain open. Public artifact availability alone does not
close either integration obligation.

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

### A2 — bounded implementation and remaining semantics

P0 publication and supplemental public verification are closed; this is separate
P1 work. A2-0 adopted the bounded API/default/order/subset in CONTRACT-002/003/004,
the programmatic keyword in CONTRACT-005, architecture and TP-001 before code.
The ordered source slices below are implemented and Sol reviewed; the execution
checkpoint binds their local source and fresh installed-feature evidence.

Use only released pure `umf-core` 0.10.0 from `umf-v0.5.4`, exact wheel SHA-256
`49633924b45a3c8499d4fcc1a24c30d5a8fcb34d974ab019bbda987cb47da0f9`.
No Rust/codegen candidate, permissive DDD/view registry or second evaluator is
part of this cut. `admit_document` preserves source and official ordered results;
not-run/null status is distinct from completed official invalidity. Projection
uses source afresh, exposes no mutable official authority and explicitly refuses
unserved meaning. `umf-core-metadata/1` is programmatic opt-in, default legacy,
and requires every placed store/replica's exact tuple qualification before
acceptance/CAS. Only qualified memory advertises it; all writes remain refused.
The source-taking Arras routes rederive the admitted projection. Direct provider
registration retains the existing trusted host-supplied source/ModuleInfo boundary
and does not independently attest official validity; no memory-to-admission edge
is added.

| Order / owner | Exact bounded source scope for Luna | Gate before dependent work |
|---|---|---|
| A2-1 / semantic Luna; dependency/content owners | New `umf_admission.py`, `_umf_engine.py`, admission tests; exact optional `umf` extra/lock; official fixture/provenance/notices | Fresh EMPTY production Registry; immutable source/status/ordered diagnostics; exact 139 reference vectors with TEST-ONLY callbacks, separate production expectations |
| A2-2 / semantic Luna | `_umf_projection.py`, core projection tests and neutral originals/STRING-key derivative fixtures | Identity/all-members/nullability/key subset, valid-but-unsupported controls, no loss or mutable authority |
| A2-PRE / semantic Luna with module-map owner | New `_catalogs.py`, delegated catalog portion of `core.py`, catalog tests and exact edge/negative controls | Preserve token/failure/order/placement behavior and public identities; keep unchanged 926-line ceiling before constructor wiring |
| A2-3 / semantic Luna | `model.py`, `results.py` (BackendInfo), `core.py`, `registration.py`, `schema_admin.py`, registration tests; defensive Truss registry guard/scripted tests only | Legacy default/order unchanged; profile dispatch in `registration.placed`, not legacy `umf.py`; provider-not-called and profile-transition negatives |
| A2-4 / semantic Luna | Memory registry/profile/capability integration and policy descriptor tests | Metadata-only readback; mutable=false; direct/dry-run/both batches/import Unsupported before iteration/replay/effects and complete zero-state-change proof |
| A2-5 / coordinated catalog, boundary, CI and distribution owners | Public module catalog, module maps/provenance, required extra-enabled static/semantic CI and fresh installed probes | Whole strict quality/boundaries, exact 139-ID/no-skip gate, base-without-engine plus extra-enabled fresh wheel proofs outside checkout |

The public module is `arras.umf_admission`, without automatic root re-exports.
The optional-engine bridge alone imports official UMF. Base imports remain usable
without it; explicit new routes refuse missing support rather than falling back.
CI quality/semantic environments must include `--extra truss --extra umf` and a
required `ARRAS_REQUIRE_UMF=1` gate. A1's reused-environment probe does not satisfy
the two fresh installed environments. Vendoring the independently verified public
139-case fixture requires its exact tag/blob/digest, derived/correction metadata
and license/notices, not a new owner approval gate. TP-001 records these controls.

Sol froze/reviewed governing decisions before Luna implemented each bounded
slice. The public catalog, signatures, module edges and contract revisions agree:
type registry 2, actions 2, backend 6 and lifecycle 3; interface remains 2.
Release preparation now carries package version 0.6.0; this feature checkpoint
creates no tag or released receipt and does not establish Truss49 adoption, a new
native/UI campaign or a new registry publication. Canonical
actions/transport, official value enforcement and broader registration ownership
remain A3–A7; Ashlar's authorized publication/progress seam remains separate.

### Candidate release qualification

Source commit `8f8097ab0bebb3f8eda6d76568c62ee5e84d33ef` is the release-preparation
checkpoint for the same A2 scope as merged source `df923164`. Immutable tag
object `686886c7ed2425e4e9e496b70fcc39272b8a52d9` identifies the tagged source.
PR 7 main CI run `39960762557` passed all four checks. The 0.6.0 release adds
optional official source admission and bounded core-metadata projection relative
to published 0.5.1. Legacy parsing remains default; hosts opt into
`umf-core-metadata/1`, supported only by the memory adapter in this tranche. It
allows schema registration/dry-run, description, document readback and authorized
empty-graph reads; writes refuse before effects, and Truss refuses the profile
before acceptance. It does not qualify value/constraint execution, canonical
actions, general native metadata, Ashlar or managed deployment. Truss 0.0.48,
Weft 0.4.51 and UMF core 0.10.0 pins are unchanged.

| Candidate evidence | Result and boundary |
| --- | --- |
| Source quality | Full default Python suite: 3,064 passed, 199 Truss tests deselected. Content, Ruff, format and full Pyright checks pass. |
| UI source | Lint/type, 1,449 unit tests, audit, build and external checks pass. |
| Integration suite | 205 checks pass on the named local candidate cohort. |
| Exact artifacts | Candidate Mac wheel SHA-256 `03959567e77a547ed94014f55bd312630a276827753aafbb5615da0b216366ec`; candidate wheel-carried npm SHA-256 `cfdd2da7a13f088df2146322e14eba202e78b8def3afc86690e550a44d845749`. These are component identities, not public asset identities unless byte equality is established. Final amended source/sdist parity passes. |
| Installed UMF gate | On macOS arm64 / CPython 3.11.17: 139 ordered reference and 139 fresh-empty production Registry comparisons, zero skips; six base and ten extra-enabled controls pass, with cleanup. |
| Installed doctor/example | Doctor passes 20 cases, eight SDK phases and three controls using Python 3.13.16. Fresh extension example passes four tests and 72 memory cases. |
| Native and packed UI | Full native suite passes 199; fresh-native run passes 64 with eight declared limits and seven replica-only cases inapplicable. Packed browser passes 272, including comparison of 67 canonical baselines. |
| Public qualification | Published v0.6.0 from the pinned tag; release run `39963352238` and all required jobs passed. The 17-asset schema-v2 public bundle, exact public artifact identities, anonymous Linux UMF repeat, installed consumer, Linux native and UI checks are recorded in the deployment checklist and release notes. Final independent review is complete in the linked review receipt. |

The candidate results above remain evidence for their named local macOS cohorts;
they are distinct from the public Linux release gates. The immutable
[v0.6.0 release](https://github.com/DocumentDrivenDX/arras/releases/tag/v0.6.0)
uses source `8f8097ab0bebb3f8eda6d76568c62ee5e84d33ef` and tag object
`686886c7ed2425e4e9e496b70fcc39272b8a52d9`. Its
[publication run `39963352238`](https://github.com/DocumentDrivenDX/arras/actions/runs/39963352238)
passed all required jobs. The anonymous public-download UMF repeat passed on
Linux x86_64 / CPython 3.11.17 with 139/139 ordered reference cases, 139/139
fresh-empty production Registry cases, zero skips, six base and ten extra-enabled
controls, and cleanup. Public installed doctor passed 20 cases, eight SDK phases
and three controls; the fresh extension example passed four tests and 72 memory
cases. Public UI qualification passed all 205 nonvisual cases without skips, and
the Linux native adapter job passed. Registries remained deferred. The final
independent public review is complete; the raw [public-repeat review](evidence/arras-0.6.0-release-20261023/public-repeat-review.json)
has SHA-256 `1d38a416e3b161c2d769ca749267c57b56614f9d97a0cba28ff5a5e8ffef814d`.
The [consolidated closeout manifest](evidence/arras-0.6.0-public-verification-review-20261023.json)
indexes the release proof and supporting reviews.
The official admission gate establishes admission-result parity,
not 139 executable metadata cases.

The exact public Arras wheel SHA-256 is
`c3ace4273f483fbf41af3f70a71a65a6d0f9c963c5b1c71eb79c5bf1bd299a3d`; the sdist
is `1e533d666b664cc99b1d3b8dedc8120e825988e7d997d69189a3507bc9e53ce2`, and the
published npm archive is
`73819275d2b784295e471c8b81fe251acb127b274cc9567946cdce9824ef9a71`. The
independent local/tag payload comparison found all 321 unpacked npm files equal;
the npm archive compression and wheel `RECORD` differ. It establishes payload
correspondence only and does not claim macOS execution of the Linux release
wheel. The public bundle carries 17 assets (16 SHA256SUMS entries plus
`SHA256SUMS`) and release-evidence schema v2.

### Bounded A2 execution checkpoint

**Historical 0.5.1 candidate proof.** The bounded feature passed local source and
fresh installed checks on unreleased source candidate
`11c3dd0711ff6d556fed4fbea99cff1951506588`, package version 0.5.1. Those bytes
are distinct from immutable public v0.5.1 and do not qualify the 0.6.0 package. The
[installed receipt](evidence/umf-admission-projection-20261023/installed-proof.json)
is preserved byte-for-byte, with a separate
[independent review](evidence/umf-admission-projection-20261023/installed-proof-review.safe.json).

| Evidence | Observed result and boundary |
| --- | --- |
| Required source suite | 3,031 passed; 199 Truss tests deselected; 60.36 seconds. Configured strict `src/tests` Pyright with the explicit quality interpreter, Ruff, formatting and content checks pass. No native campaign ran. |
| Exact built Arras wheel | `arras-0.5.1-py3-none-any.whl`, SHA-256 `948666bc38cc1ac00c0739d47da7b5a395c7a0b89721eb12b11456f61bbcb112`; 173 RECORD entries. Independent review verifies every recorded payload hash. |
| Exact official SDK | Released pure `umf-core` 0.10.0, SHA-256 `49633924b45a3c8499d4fcc1a24c30d5a8fcb34d974ab019bbda987cb47da0f9`, default pinned-public-URL mode; 26 RECORD entries. No Rust/codegen candidate is used. |
| Fresh installed attempt 01 | Passed on CPython 3.11.17, Darwin ARM64. Two new environments; six base controls and ten extra-enabled controls pass. Receipt records installed payload/origin checks before API use, no shared site packages/source aliases, and completed cleanup. |
| Official fixture parity | Exact 139 unique ordered IDs, fixture SHA-256 `bb008a98b8448050748e65f867e7863475ccad9501a5b9229ae9e6d336691544`; 139 reference-registry matches and 139 separate fresh EMPTY production-registry matches; zero skips. This is admission-result parity, not 139 executable metadata cases. |
| Feature controls | Base legacy registration/read works with no SDK installed; explicit new routes refuse. Extra-enabled public admission/projection and Arras-to-memory registration/readback pass. Unknown/incomplete and valid-but-unsupported cases, unqualified providers, profile transitions, repr privacy and direct-write zero effects are checked. |
| Source binding | Frozen verifier/probe match the candidate commit. Independent archive review matches 106 tracked packaged members to that commit and 61 generated members to working-build bytes; this is not a whole-tree immutable-build attestation. |

Receipt SHA-256 is
`c7a7c0b98f5bafd4f7356cdfaf1d0e7f281fffc9a46c391ddfb9ddc4161fd13b`.
Verifier SHA-256 is
`87bccd0a5639681923b1539918593601090bbd8cf8cd870c5a922d128992d3e3`;
fixed probe SHA-256 is
`3185ee3a4a52f991ab7da87e5c252c4ebcd9f8a48900a994eddc8966abcae4be`.
The installed receipt contains safe observed dependency versions and relative
import origins, without raw document text, host paths or private command logs.

**Failure history.** The preceding full source attempt passed 3,028 tests and
failed two MCP subprocess cases. The child rejected `ARRAS_REQUIRE_UMF` as an
unknown Arras configuration key. The narrow ignored-test-flag/catalog fix retains
unknown-key refusal; the two original regressions and final complete source run
pass. The first actual installed proof then passed; no failed installed attempt
is hidden. The verifier's 17 offline controls pass. An optional standalone strict
typing run over dynamic-JSON tools reported 113 issues; it is not represented as
passing the configured strict `src/tests` gate.

This proves official source admission and a reduced, explicitly immutable memory
metadata profile. It enables no value/constraint or canonical action execution,
qualifies no native backend or UI, and is not public release/download evidence.
Truss remains legacy-only and refuses the new metadata profile before acceptance.
Trusted extension registration, broader projection/ownership and Ashlar's
authorized reader/progress work remain open.

## Extensibility Queue

EX-01–EX-08 are closed for the recorded 0.5.1 generic release subset. The
[design note](../02-design/downstream-extensibility.md) records current state,
seams, remaining boundaries and future costs. Luna implemented and Sol reviewed
these changes; actual public artifacts and fresh consumers establish delivery.
Earlier local checkpoints below remain historical and are not relabelled.

| Slice / priority | Delivered boundary | Actual acceptance | Remaining scope |
| --- | --- | --- | --- |
| EX-01 distribution/public manifest — closed | Deliberate Python/UI/config/env/CSS/telemetry catalog, contract mapping, semver/deprecation policy, wheel-carried npm and source archive | Actual sixteen GitHub assets, source/sdist parity, fixed reusable consumer and full anonymous comparison pass | PyPI/npm deferred; additional platform matrices need actual evidence |
| EX-02 naming/env — closed | Typed Brand/DistributionConfig, thin public launchers, runtime presentation, explicit aliases and scoped telemetry | Public-wheel doctor 20/eight SDK phases/three false-pass controls pass; canonical defaults and identity-conflict refusal retained | Canonical imports/wire/CSS/signal identities stay stable |
| EX-03 theme/UI packaging — closed | Six replacement slots including Mark, runtime CSS/font/favicon assets, public testkit and one React peer | Downloaded Linux 205 plus routes/controls pass; separate Mac 272 and unchanged 75 reviewed baseline hashes with payload bridge | Mac visuals remain platform-scoped; no private theme dependencies upstream |
| EX-04 operator/policy — closed generic subset | Configured operator/role/schema/Operate callbacks, composed schema forwarding, PolicyBackend/refusal and optional annotation protocol | Source/cross-surface controls and public catalog/consumer checks pass; annotation transaction proof is synthetic | Native annotations unsupported; sensitive-state workload/entitlement/write-owner prerequisites remain mandatory |
| EX-05 modules/content — closed | Host-selected module bytes, seeds/graph/resources and trusted handlers without automatic demo loading | Fresh downloaded example 4 and applicable memory 72 pass, seven replica-only cases inapplicable; no copied upstream tests | Closed view vocabulary extends upstream; official admission/projection and broader semantics remain A2–A7 |
| EX-06 credentials/backend — closed selected subset | Stable person credentials and explicit host factories/connections/role ownership | Selected Truss 0.0.48/Weft 0.4.51 Linux source 199/native corpus 64 with eight declared limits/seven inapplicable; retained multi-host/restart/grant evidence | Production custody, managed hosts and additional adapters separately qualified |
| EX-07 public conformance/CI — closed | Packaged Python corpus/native harness, Node/browser testkit, fixed reusable workflow and generic public-content gate | New same-run reusable installed consumer and full anonymous bundle/SDK/example/theme checks pass; independent safe-bundle review | Optional downstream native/theme jobs prove only explicit targets; HELIX authority links remain upstream |
| EX-08 upgrades/doctor — closed | Per-seam release notes, exact pin policies and bounded offline doctor | Positive/breaking/no-I/O public-wheel checks pass without ambient credential access or registration/mutation | Static diagnostics do not qualify runtime semantics or managed deployment |

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
unchanged 199-case suite on public Truss 0.0.48/Weft 0.4.51/pgserver-pg18 18.6.1
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

### Full themed candidate findings and reviewed corrections

The next hosted [CI run 39853529762](https://github.com/DocumentDrivenDX/arras/actions/runs/39853529762)
on `ad099d8be295a461073e23a3d5fc706390085601` passed the default Python,
full 199-case native Linux, source quality/build, exact artifact and fresh
installed-example gates. UI checks passed 1,449 unit tests and 205 integration
tests, plus its type, build, CSS scope and external-import checks. The job then
failed during effective APT configuration verification, before dependency
installation or Chromium execution. Source rewriting and its fixture check had
succeeded; the three display-format matches require replacement with the release
workflow's exact effective-value query. Expected retries/timeouts remain 2/20/20.

The subsequent macOS packed capture used wheel
`8c8d37cb0af89b57d77493a8819e07bc147eff4be684b2d8fbee3d3e61dbed26`
and npm tarball
`c4d1b3b2890352d5226994cfb1a6fea6c15e9fc285da6d9c504f4f6a9d37fc39`.
It executed all 272 canonical cases: **241 passed, 31 failed, none skipped**.
It created 67 unreviewed visual images and established no successful UI receipt.
The compiled-host schema assets now loaded successfully. Its four-test fresh
installed Python example also passed on that wheel, with all 72 applicable memory
conformance cases passing and seven replica-only cases inapplicable. This is a
historical artifact result; later wheel changes require a new installed proof.

The full themed suite exposed two upstream behavior defects. Runtime page
branding appended metadata to a page already containing a brand, leaving multiple
conflicting tags. Graph Browser's native-control reset overrode an external
widget's foreground, producing measured 2.15:1 contrast. Sol approved Luna's
single-metadata HTML transformation and lower-specificity control reset. The
HTML transformation preserves unrelated source and has 50 passing focused tests.
Three canonical visible-name assertions now use the supplied profile, retaining
their assertions. The neutral acceptance fixture's 18 root role properties use
the host's resolved light/dark color scheme, and its launcher supplies the public
distribution branding explicitly. Contrast thresholds and accessibility checks
are unchanged. A subsequent unchanged canonical keyboard test reproduced the
body-click failure. Its post-authentication trace recorded body bounds
`x=8,y=8,width=1264,height=274` and the actual viewport click at `(13,308)`:
the body ended at y=282. Sol approved a fixture-owned external stylesheet giving
`html`, `body` and `#root` full height and removing the body margin; library CSS
and the canonical test remain unchanged. The corrected canonical case and full
capture still require execution. Failed private run diagnostics are preserved
before owned-host cleanup. No images from the failed capture are accepted
baselines, and the final ordinary comparison remains outstanding.

The reviewed fixture correction then passed the same unchanged canonical
keyboard case in 2.5 seconds. After selecting the same person, body and host bounds
were `(0,0,1280,720)` and the actual `(5,300)` click hit the graph-browser element.
All owned fixture ports were closed after the probe. This one-case result permits
another full capture; it does not qualify the full suite.

Hosted [CI run 39856356661](https://github.com/DocumentDrivenDX/arras/actions/runs/39856356661)
on `f7e0015807fb2c26cc1719b19683daf16a2b13ab` passed source/build and exact
installed-artifact gates. Its Python run passed 2,771 tests with one failure,
41 skips and 199 native deselections: the new HTML helper had changed bare
fragment output. Sol approved preserving the prior byte-for-byte fragment behavior
when neither real head nor title anchor exists; UI plus the original operate
regression then passed 51 tests with zero Pyright errors. The APT semantic query
also established actual effective values of 1/15/15 despite the intended 2/20/20
drop-in. Configuration precedence, rather than display matching alone, therefore
requires correction across CI and both release browser-install blocks. Exact
required bounds remain unchanged, and this failed UI job never ran Chromium.

The next candidate passed all four narrow theme routes after the compiled host
set `build.cssTarget: "chrome123"`. Without that fixture target, Vite lowered
`light-dark()` role values to invalid concatenated alternatives. Both the exact
Vite 8.3.2 runner and an isolated 8.3.5 reproduction preserve the native function
with that CSS target and minification retained. The resulting eight light/dark
images were captured as `baselines-updated`, then individually inspected and
[approved by Sol](evidence/arras-narrow-eight-visual-review-20261022.json).
Actual Chromium was 153.0.8010.12. Ordinary comparison remains required.

Wheel `eeb787b836c4fa6f4309bd33a1119d51883ab2fd53d75a89b34893d509644e80`
passed 20 installed doctor cases, eight SDK telemetry phases and three false-pass
controls on Darwin arm64/27.0.0, Python 3.13.16 and OpenTelemetry API/SDK 1.45.1.
Receipt SHA-256 is
`0d19174753c42f01a63bece20a72bb28c162ca026592846b8a9461cbbeef65b7`;
current verifier/probe identities are respectively
`9aa379d1f2b333f855aa9886da7b6e93dcf930bc789a3721e0862ee174c08455` and
`2dd054ff5b832f279195d8e644027474181ff247d29d6b59ee0e8c2889836e0f`.
Sol independently verified the receipt identities and the existing assembler's
trusted doctor validator accepted it. Its fresh installed example separately
passed four tests and all 72 applicable memory corpus cases, with seven
replica-only cases inapplicable. Consumer receipt SHA-256 is
`073139cae16bf45ac0884aef6cc561c86dedb98736005295968efa3fae1456e9`.
These exact candidate results remain distinct from native or full-UI proof.

[CI run 39857567776](https://github.com/DocumentDrivenDX/arras/actions/runs/39857567776)
on `cacc90acc0d8af8bbc3cc1bf07747ef7fcdc0289` passed default Python, all
199 native Linux cases, source/build and installed artifact gates. The effective
APT checks, dependency installation and pinned Chromium launch passed. Its actual
nonvisual UI suite passed 203 cases and failed two existing brand assertions that
selected an Operate-only header after opening Explore. A separate source-selected
regression had seven passes and the same first selector failure; it is source
proof, not packed overlay qualification. Sol scoped a canonical test correction
to assert the exact visible wordmark in each actual banner while preserving
metadata, title and both-mode coverage. Because canonical test bytes are carried,
this correction requires a new manifest/npm/wheel and repeated installed proofs.
No full 272-case success or reviewed canonical visual comparison is established.

The theme-logo profile exposed a further test-only distinction: a rendered Mark
adds its own glyph beside the exact product-name text. Sol approved an exact
visible text-node witness outside semantic image content, plus the exact named
image assertion. Actual browser controls accept the exact visible sibling and
refuse prefixed, suffixed, display-hidden, visibility-hidden, transparent and
image-label-only names. Plain-text and HTTPS wordmark priority remain unchanged.
The resulting wheel
`07b3e867bd4ca48b4cd43ad5f13449076e3939f4194c06c297d1ca0171764ed1`
carries npm
`c29a9f151d9a6a42cce55325e927634cc5713763c0485cc6e02cb63006c78307`
and acceptance manifest
`bfb6ed43ff0accdb170b60cc7095365f2a7cc287a66b7dfcab31918106042f78`.
All 83 resource bytes and the unchanged 17-spec/project inventory were verified.
Its selected packed run passed all nine cases with no unexpected, skipped or
flaky result, and all four ordinary narrow routes passed. The private command
still failed overall: the controlled-negative config lived outside the installed
host's module-resolution tree, and its output directory overlapped its own inputs.
Sol independently reproduced the module-resolution error and approved placing the
control under the installed host with a separate child results directory. The
standard full capture must still prove its canonical cases and all four negative
controls; the passing selected subset is not a complete qualification.

The standard packed capture then passed **272/272 cases with zero failures or
skips** on wheel `07b3e867bd4ca48b4cd43ad5f13449076e3939f4194c06c297d1ca0171764ed1`:
132 Chromium, three schema-administration, 70 browser and 67 visual cases. It
retained all 17 canonical specs and 83 verified resources. Missing/tampered
resources and unsafe options were refused; the real canonical controlled-brand
assertion produced the required exit 1 and failed-test JSON. All four narrow
routes compared successfully. The capture receipt SHA-256 is
`23a40f538c1c34d14a54a408d35f5b2d94d183bb66bdb70b2b167606f4895f79` and reports
`updated-unreviewed`, not a canonical comparison. Sol individually covered all
67 images and approved them as initial baselines in the
[complete visual review](evidence/arras-neutral-theme-67-visual-review-20261022.json).
Existing volatile-content masks remain explicit review limits. An ordinary full
comparison with updates disabled is still required.

The same final wheel repeated all 20 installed doctor cases, eight SDK phases and
three false-pass controls on the recorded Darwin/Python 3.13.16/OpenTelemetry
1.45.1 cohort. Receipt SHA-256 is
`1c12ee78f0d2c0c2c63d9f92f0dc8cc244294cb9b0bacfe743a633e0f83697ea`;
[Sol's identity review](evidence/arras-sdk-07b-review-20261022.json) independently
matches wheel, current verifier, generated probe and carried npm hashes. The
fresh installed example also passed four tests and memory corpus 72/7 with no
limit/error; its reviewed receipt SHA-256 is
`fbdce0dc76e11a1457f05a18e5ae40169050ef379242b76c2874047c45595dc7`.
These results supersede the earlier EEB installed proofs for release planning.
The doctor's conservative candidate/native-pin boilerplate does not establish
native behavior: the selected public 48/51 tuple requires its separate native
receipts. Final source/sdist parity, Mac native and tag/download gates remain.

The ordinary packed comparison subsequently passed **272/272 cases with zero
failures or skips**, with baseline updates disabled. All 67 individually reviewed
baseline hashes remained unchanged; the receipt reports `compared` with 67
screenshots. All four narrow routes compared, and all four missing/tampered
resource, unsafe-option and actual controlled-failure checks passed. Receipt
SHA-256 is `91f1a5af1c2b78b187d1726d66c96a3682251e189abd2834f9c2531beb17a819`;
[Sol's comparison review](evidence/arras-neutral-theme-comparison-review-20261022.json)
independently verifies the receipt, three resource/report sidecars, exact wheel,
carried npm, theme and current driver identities. All owned browser/UI ports
closed after the run. This closes the local ordinary-comparison gate; native,
source/sdist and tagged/public-download gates remain separate.

Hosted [CI run 39860182771](https://github.com/DocumentDrivenDX/arras/actions/runs/39860182771)
passed all four source Python, check/build/installed-consumer, native and UI jobs
on commit `6136e288a64af510a94fd4837655b47f745b5414`. Subsequent changes record
reviewed baselines/evidence and final documentation, plus an evidence-assembler
correction for the producer's closed four-digest cohort shape. Final source CI
must run again; the earlier green run is not a final-tag result.

The evidence-assembler correction then passed 11 focused tests, Ruff/format and
strict Pyright. Sol independently accepted the unchanged final SDK and UI receipts
against the actual closed flat four-digest producer shape. Nested, extra/missing,
non-digest and each mismatched identity remain refused. The correction changes
only evidence validation; it does not normalize receipts, relax cohort matching
or require another UI run. Full bundle assembly remains a separate actual gate.

The final Mac source suite passed **199 tests, zero failures/errors/skips**, with
2,897 deselected in 620.37 seconds on the selected public 48/51/PostgreSQL tuple.
JUnit and the actual terminal output agree; owned temporary PostgreSQL resources
were closed before the sequential fresh installed-native phase. Unrelated
pre-existing clusters were left untouched. The private process inventory is not
public release evidence. Actual log SHA-256 is `754b5a48932183d5ddf052cbca5b35a8a1e955bc680ca4b5702bdc26b5baa387` and JUnit SHA-256 is
`7d22b3268b0bd4ef7a8f71fe0bfa880c255f9d13badbb9e355b66ee0fe7eff39`. These source results do not qualify the separate installed helper.
The run began at `3199dffb7f20d8e40f9b1c9fbbd22f3fe9292c50`; `ff2b83a`
landed during execution. Sol verified that the intervening diff touches only the
assembler, its tests, documentation and UI evidence: native adapter/tests,
conformance, cohort, pins, lock and declared limits are unchanged. This is stable
native-relevant source evidence across those refs, not an immutable whole-checkout
snapshot. The [safe independent source review](evidence/arras-native-source-review-20261022.json)
records assertion-backed dependency versions and capture limits: no standalone
source-run Python/OS metadata snapshot or complete native payload inventory was
recorded, and cleanup is a scoped worker-attested result. The separate installed
verifier must supply its actual runtime and payload binding.

The separate fresh installed native verifier then passed on the exact 07b wheel.
Receipt SHA-256 is
`a5d45cf642c760d6467de47cac0897b941c8cc567bac77558fb84180ae87b995`.
The actual isolated CLI reports corpus 13 reader/provider with **64 passes, eight
exact declared limits and seven replica-only cases inapplicable**, zero
failures/harness errors/host-specific outcomes, and exit 0. All seven selected
native distribution identities and installed payloads match the bound public
archives; Sol independently reviewed the 92 current-platform native inventory
entries, Arras payloads, pip digests and manifest/index/binding identities in the
[safe installed review](evidence/arras-installed-native-review-20261022.json).
The receipt captures CPython 3.11/Darwin/arm64, not the Python patch or OS release;
no SDK runtime metadata is substituted. It does not perform a system dynamic-link
audit. The worker confirms owned PostgreSQL cleanup; raw process inventories stay
private. No native rerun is required for subsequent documentation/assembly work.

Final source-archive parity passed after the packaged changelog was finalized as
`0.5.0` dated 2026-10-22. Sdist SHA-256 is
`ac97cdef7ddd951734e654ab94e25972b60860ce79828db92141dc46293a203e`;
its rebuilt wheel is byte-for-byte the frozen 07b wheel, with the exact c29 npm
archive, complete package payload, API manifest and dependency metadata unchanged.
Both clean installed-consumer paths pass their memory operation, schema callback
and packed npm export checks on macOS 27.0.1 arm64/Python 3.11.17. Receipt SHA-256
is `9c9dfe7cdda7d037418df48468103241cc3979a74359d104c2d69a8783db9bcf`.
Its JavaScript consumer uses explicitly workspace-linked dependencies; the
separate fully fresh packed themed UI evidence remains required and recorded
above. Both commands exit 0 and the verifier temporary directory is removed.
The earlier attempt-01 receipt remains historical; only this finalized-changelog
archive enters the local assembled bundle. Sol approved the final docs and
source/runtime scope qualifications, and the public-content gate and diff checks
pass. No packaged runtime/test/tool source changed after the last green CI.

The first actual complete assembly then passed its strict validators and emitted
exactly 16 files, with all 15 checksum-covered assets verified. Aggregate SHA-256
was `aa1ad3b2bc096db436fb23ff731b21ecbe9aca42bed7b361f56a8adea1be4937`;
`SHA256SUMS` SHA-256 was
`44ca60e9711856760b9e60c661cab6b188668f122e0a924ab926cfdfafdaeb07`.
Sol's independent publication review withheld approval: the raw doctor receipt
contained 11 absolute diagnostic paths and the distribution receipt two nested
consumer package paths. These successful executions remain valid private input
evidence, but their raw diagnostic receipts cannot be public release assets.
The bounded repair preserves three exact binary artifacts and projects the two
receipts through typed public-v1 allowlists with original raw receipt digests;
CONTRACT-005 now binds raw and emitted identities explicitly. No SDK, UI or native
rerun is needed. A separate actual-output check also found the public comparison
helper expected an obsolete top-level wheel key instead of the assembler's
canonical `release_artifacts.wheel`. That strict schema agreement must be corrected
and exercised before tag/publication. These are release reporting/integration
blockers, not additional runtime feature scope. Final corrected assembly, review,
source-archive coherence and tag/download gates remain open.

The reporting repair was source-reviewed and pushed at `a28b93b` for remote CI
while the shared Mac slot remained exclusive to other coordinated native work.
That run correctly held release on the new doctor's function complexity/statement
limits and two wording mismatches: an unsafe-token negative test's expected error
text and the release-notes test's explicit registry-access phrase. Its default
suite recorded 2,784 passes, 41 skips and 199 native deselections, with only those
two failures. Luna split the reporting function into cohesive helpers without
raising limits or adding ignores, corrected the negative's expected bounded error,
and formatted the affected checker/test files. The release notes retain the
accurate explicit phrase that registry access has not been established.

After the quiet handoff, all **40 release-tool tests and the exact documentation
test pass**; Ruff format/check and selected-interpreter Pyright pass across all
six relevant assembler/input/public-projection/checker/test files. Sol independently
approved the extraction's predicate/output equivalence. Safe doctor projection
retains its five observed Python distribution versions and extension-host wheel
identity, SDK versions/phases/controls and capture limits. It omits local diagnostic
paths and explicitly omits unrelated tool/theme labels, preserving raw evidence
immutably. Final coherent source archive, actual corrected assembly/public-checker
execution, full hosted CI and tag/public-download gates remain required. No
runtime library, wheel/npm payload, SDK, UI or native proof changed in this repair.

### Immutable first tag failure and 0.5.1 fix forward

The reviewed source head `5269986f35834229daffe7a07f97b6c17c98d52c` passed
[all four source CI jobs](https://github.com/DocumentDrivenDX/arras/actions/runs/39867960866).
PR #1 merged at `33aa9973e1daeb0ac15c31dbcbcb5010c0120aed` with the same tree.
The immutable `v0.5.0` tag then started
[release run 39869369841](https://github.com/DocumentDrivenDX/arras/actions/runs/39869369841).
Its Linux native job passed all 199 tests, but the build stopped before artifact
creation: the Truss-extra environment activated a stale CLI-refusal assertion.
The parser correctly exited 2 with `--truss-url is refused`; no backend or server
started. The tag produced no release assets and is not a delivered release.

The coordinated patch changes only that assertion and regular Python CI's extra
selection before a 0.5.1 version bump. The assertion checks the bounded diagnostic,
exit status, credential non-disclosure and zero startup effects. Source native
behavior and the selected Truss 0.0.48/Weft 0.4.51 cohort remain unchanged.
The other session's Sol approved the repair. Its focused devhost pair passes 37
tests; an interrupted full attempt is supporting evidence, not a full pass. The
interrupted manifest case separately passes after the run is terminal.

Every exact-artifact gate must rerun on the new wheel: SDK doctor, fresh example,
installed native corpus, full packed UI ordinary comparison, source/sdist parity
and final safe assembly. Existing visual approvals carry forward only by unchanged
baseline image hashes. A machine-checked native-source delta may retain the prior
Mac 199-test source evidence; new source CI and exact-tag Linux native gates remain
mandatory. Historical receipts and hashes above stay bound to their old artifacts.
The version bump exposed current-runtime UI test fixtures that hard-coded 0.5.0:
a scoped run reported 23 failures and 74 passes, all failures refusing the stale
fixture manifest before serving a page. Those current-cohort fixtures now derive
the installed version; deliberate incompatible-cohort controls remain intact.
The doctor-request fixture provenance digest is refreshed for its new pin.
The [378-file source-delta attestation](evidence/arras-0.5.1-native-source-delta-20261022.json)
records unchanged native production/conformance sources and normalized dependency
identities, with the metadata, test and CI exceptions reviewed by Sol.
No 0.5.0 tag or artifact bytes are replaced. Real registry publishing remains
explicitly deferred; GitHub delivery and fresh anonymous download checks are required.

### Fresh 0.5.1 component qualification

Frozen wheel SHA-256 is
`59827644e2e423980afed1047f75c7130dc5d8c542778df4b62a9e2244cdc24c`;
its only carried npm tarball is `documentdrivendx-arras-ui-0.5.1.tgz`, SHA-256
`460e1b1037d4965d17af8b3e689c364c22b51a09cc9d3d64c8ddf0296e34c943`.
Source [CI 39871984841](https://github.com/DocumentDrivenDX/arras/actions/runs/39871984841)
passes all four jobs at `ad67ed48515325da2cbbc598512e97a51a1d3fb2`: Python
2,907 passes/199 native deselected; native 199 passes/2,907 deselected; UI 205
nonvisual passes; lint/types/build passes. Affected local fixtures/verifiers pass
106 tests after the version-coupled fixture repair.

The [fresh SDK/example review](evidence/arras-0.5.1-sdk-example-review-20261022.json)
checks actual receipts, exit statuses, driver/probe identities and artifact bytes.
Doctor receipt `baa9334e26936908bc1fabe6e6e6b3e630c92e1bd9cede907ceb1a6341527b2f`
passes all 20 cases, eight phases and three false-pass controls on Darwin arm64,
Python 3.13.16 and OpenTelemetry 1.45.1. The separate example receipt
`f997f651181ef6e5221dedd2faa6e36d7b618c335b49c62f6fdb3764ca892890`
passes four fresh installed tests and all 72 applicable memory corpus cases,
with seven replica-only cases inapplicable, on Python 3.11.17. Its consumer wheel
is `fe4c419114045ba9ccb393dc2a931eb4bb34cafa96a5c46b94cb4c62476dbd03`.
These component runtimes are not merged into an invented single-platform claim.

The [fresh ordinary UI review](evidence/arras-0.5.1-ui-review-20261022.json)
checks receipt `2538efc8242bec4390865953e6d575b00439fff7134bc566f07a880374071b78`:
272 passed (132 Chromium/3 schema-admin/70 browser/67 visual), no failures/skips,
four compared routes and four successful negative controls. All 67 canonical
and eight narrow reviewed baseline hashes are unchanged. New theme hash is
`f5248a8774512ef722ea76046fa550797b0eaa510649db622fd750e0e008e086`;
public checker hash remains
`67633a3dcfbc5e1130e1135d7c3192f612370078882ac98e247c732f03f753b9`.
The outer private driver has its own version-default change. Output screenshots
may differ within the existing masks/tolerances; baseline identity and successful
ordinary comparison are the acceptance evidence. All owned UI hosts/ports and
temporary directories were confirmed cleaned before native execution began.

The [distribution checkpoint review](evidence/arras-0.5.1-distribution-checkpoint-review-20261022.json)
records sdist `7962d91e0f0d8f122fc1b79e9253d5a9ae1904ebf1ef72f587ba99aa443d5b1c`
and receipt `6b99e81874b8435a6d6a8ebf5230ef6bca21b3ec23a1d25a2858b865c75ac340`.
The source and sdist-rebuilt wheels are byte-identical to 598, and both installed
consumers pass operations/schema callbacks/public npm exports. Python dependencies
are fresh; JavaScript dependencies in this verifier are workspace-linked. The
UI proof above separately installs its public JavaScript peers into a fresh host.
The final CHANGELOG and current evidence require a final archive/parity refresh;
this checkpoint is not relabelled as that final archive.

Fresh 0.5.1 installed-native receipt
`026a935e4bb39323db13e56dff0ce4837e0062675497efb8e9b677d4ad43ca72`
passes with 64 corpus cases, eight exact declared limits and seven replica-only
cases inapplicable, no failures/harness errors/host-specific outcomes. All seven
selected native distributions and 92 runtime payload files match verified inputs.
Bound cohort SHA-256 is
`1185171ddda8bc2014a99fed70c0f68e9d022fa0a624e9a9640b72163bf03ba1`;
binding receipt is
`f50f02a8176a3991a2d75629666a83b1ab741cbf0e1e68227649b140c22d3c91`.
[Sol independently accepted the installed result](evidence/arras-0.5.1-installed-native-review-20261022.json).
The runtime records CPython 3.11/Darwin/arm64 only; no Python patch/OS-release or
system dynamic-link audit is inferred. Actual terminal exit is 0 and scoped owned
PostgreSQL process count is zero. No duplicate local Mac 199-test campaign ran.
The [final source-delta attestation](evidence/arras-0.5.1-native-source-final-delta-20261022.json)
retains the original attestation and adds exactly three generated UI-evidence
exceptions, with all 75 reviewed baseline hashes unchanged.

The [final archive review](evidence/arras-0.5.1-final-archive-review-20261022.json)
qualifies sdist `e8c8636d43a1392fa5f30c2b1adf86cff9e1c0e999be88008a8aa1f13994864d`
and receipt `8a64e1a7ed81fc225c2ea9132d56d269f6114d3516ee8da9d1ea90bf64896721`.
Source and rebuilt wheels remain byte-identical to 598/npm 460. The finalized
CHANGELOG, current UI evidence, release scripts and tests match the sealed archive.
HELIX docs are excluded from the sdist; later documentation reconciliation does
not replace the sealed archive. Both installed consumers pass and temporary
environments are cleaned. Final safe-bundle review, final source CI, tag delivery
and actual anonymous public-download checks remain distinct pending gates.

Actual 0.5.1 safe assembly exits 0 with exactly 16 files, 15 SHA256SUMS entries
and all 11 published component hashes verified. Aggregate SHA-256 is
`831283c8f3b2921c0d8e9d36971a0bdbe1f5135103a827cdf658528c55cdc79f`;
public SUMS SHA-256 is
`c2ce264eded6c84482fcabbc96bcb096f02384254e2680acf684b75c1e3d85a7`.
The typed public doctor/distribution projections have hashes
`13ffb6b749ef1050d9b427c350e92c3b5ddae45427c09333d8afe5924ea993b5`
and `1855ee66180e29de554a458becf37353bde363a530fb3e0629ddb2e1220180c8`;
they preserve original raw receipt hashes without publishing local diagnostics.
The JSON/HTML privacy scan passes. Actual public-checker plan and verify commands
both exit 0 against separate offline local copies, validating all 15 assets and
the exact wheel-carried npm bytes. Verification receipt SHA-256 is
`00b85d529862c6fc9fd1ff2492d6cfd0604f256b0af6caf1e84c1482bd2e6f88`.
These are local prepublication checks; no anonymous download is claimed. Final
safe-bundle Sol review, final source CI, tag and actual public-download gates
remain required before the P0 release closes.

### Tag 0.5.1 driver-order failure and immutable-source recovery

PR #2 merged at `8b786bb7629a6425e5a2b3b528378f0d92f0b847`, with a tree
identical to qualified head `9993364967983889a96463a848254f0e06ce2637`.
[Tag run 39874964466](https://github.com/DocumentDrivenDX/arras/actions/runs/39874964466)
passed source native (199), full Python (2,907), artifact/source parity, installed
SDK doctor (20) and installed Linux native qualification. Its UI job stopped before
publication: `npm run test:integration` preceded `npm run build`, so the two
branding integration assertions could not find `ui/dist/index.html` or served
brand metadata. Regular source CI builds before integration and passes. No
GitHub Release assets or public-download qualification were produced.

The Linux tag build produced wheel
`17d50dedeaf9d4f7d27e0eb30cb16539bfa75de3a138dc9351284c2e2f390d4b`,
npm `76fc29a5a24747ef26d0e04263f1f8924034244b1169a41fb865e02274485e1f`
and sdist `541aa91ae970ac16644679614d74b858f1a46e303b6429e0c10804c24bc0dd45`.
Its archive hashes differ from local Mac component artifacts solely because npm's
compressed DEFLATE bytes differ. All 321 npm files, the complete decompressed
20,401,664-byte TAR stream and every TAR header are identical; both wheel RECORDs
validate. The only other wheel/sdist differences are the embedded archive and
regenerated RECORD binding. Python, API, runtime assets, testkit, declarations,
dependencies and file modes are unchanged. [Sol accepted this bounded equivalence](evidence/arras-0.5.1-tag-payload-equivalence-review-20261023.json);
original Mac 598/460 receipts retain their exact identities and are never
relabelled as direct Mac execution of the Linux 17d/76fc archives.

The orchestration-only recovery is bound in CONTRACT-005: a reviewed default-branch
driver accepts the existing immutable tag plus expected source commit, validates
both and pins every payload/downstream checkout to that commit. It records driver
and source identities separately and rechecks the remote tag before publication.
Every mandatory gate runs freshly in one new current run; failed-run receipts are
not joined or relabelled. The driver builds the UI before integration. No runtime,
package/API version or tag changes are needed. Driver implementation, focused
selector/order/identity tests, Sol review and new driver CI are required before
manual dispatch. No release or anonymous-download result is inferred yet.

The local corrective-order regression runs `npm run build` before the unchanged
integration suite and passes all 205 tests in 23 files, including both built-page
branding assertions. Build log SHA-256 is
`9405c85546f370ab080817ddc250045868fc8302be6a7576d0c9557c6bed6570`;
integration log SHA-256 is
`6b1668754fa9da8489ed4aed018e41badb7e67a734900cf19d007c3c9341602d`.
Both commands exit 0; spawned hosts are confirmed stopped. No UI/Python source,
package artifact, dependency environment or baseline changes were made.

The recovery driver is frozen after Luna’s current-byte verification: 77 focused
release tests pass, Ruff and formatting pass, the selector has zero Pyright
errors, both workflow YAML files parse, and the diff has no whitespace errors.
Root Sol approves the full implementation; the coordinating session’s Sol
independently approves source identity, CONTRACT-005, current-run evidence,
reusable-workflow binding and publication permissions. Reviewed SHA-256 values:
release workflow `a8048b50dd8ce8c7eab728d254ab06d68b612e26a7648c86464da75bc67df4e2`,
downstream workflow `f0f997fd7f93ea3ea08b001505dd246ea016520c6921e0f2b5ce42ad0e274e5d`,
and selector `c34faf412d684ec01f292f5a786aac0e01818013bde4213e3013f8d3f4ff3cab`.
These are driver checks; fresh remote qualification and publication remain pending.
The first driver CI found an unresolved static import in its new test; Luna
replaced that import with the existing explicit importlib test pattern. Full
repository Pyright now passes with zero errors, the 77 focused checks pass again,
and Sol approves the unchanged test behavior. Workflow and selector digests above
remain unchanged; the corrected commit requires a fresh green CI run.
The broad Python job also found its embedded-workflow fixture still expected
ten Python blocks. Its reviewed correction accounts for eleven, exercises the
new source-SHA guard with valid and malformed inputs, and retains all existing
consumer-path controls. All 89 public-content/release checks and full repository
Pyright/Ruff/format/YAML checks pass. This test-only follow-up changes no payload
or workflow bytes.

The reviewed recovery driver merged as `c02bca2b5417227f8f28d72171be0f7378c9b0bf`
after all four CI jobs passed in run `39878533951`. Fresh release run
`39879533273` validated immutable source `8b786bb7629a6425e5a2b3b528378f0d92f0b847`,
passed source/native/build/installed-native/UI/assembly gates and published the
sixteen GitHub assets at `2026-10-23T01:02:46Z`. Its wheel, npm and sdist are
byte-identical to the earlier tag-built 17d/76fc/541aa artifacts. Actual public
sum-file digest is `43c41e44c3634724f0bccd0b92ee882f0771138044b5abbbde097890c839503c`;
aggregate digest is `a84811a71b0180de8e3f2c225732c9c47410476d0389c229ef92090bf6314d7c`.
These assets are published and immutable; final postpublication acceptance remains
open. The called downstream job downloaded, verified and installed the public
wheel, then failed shell parsing in an optional setup branch: its nested heredoc
terminator retained indentation. The anonymous job consequently did not run.

Both Sol reviews approve a separate read-only postpublication verification path,
now explicitly governed by CONTRACT-005. Luna repairs the two affected reusable
workflow heredocs and adds actual Bash syntax/optional-branch execution controls.
A second Luna implements the dedicated verification driver with original-run and
trusted-stage pins. All fresh installed/anonymous consumers must pass together;
original qualification receipts are retained and no tag, asset or aggregate is
replaced. The failed publication run is never reported as fully successful.

The verification-only patch is frozen after 95 affected workflow/release tests
pass, full repository Pyright reports zero errors, Ruff/format/YAML/Bash syntax
checks pass, and the generic public-content gate remains current. Actual cached
original run/job/workflow/provenance and all sixteen trusted assets pass the new
provenance helper and existing public-asset planning checker. Sol's broad review
approves the implementation for CI. Reviewed workflow SHA-256 is
`a0093d0857f0f4715ad10f1ce3dea4c67702e1c9f6c1671aa1bc27c9a54b5958`;
provenance helper is
`abda7116afc5f1c05136eec829dae3a6c98f028ac618a25925b2e57f1feb6d3f`;
fixed reusable workflow is
`ff7442808eda1a79ddc6223b61421fe7a4b7fd14763e9c04096f2378df862eb5`.
These are orchestration checks, not anonymous-download completion.
Independent safe reviews of the actual publication are retained as
[build proof](evidence/arras-0.5.1-recovery-build-review-20261023.json),
[public bundle](evidence/arras-0.5.1-published-bundle-review-20261023.json) and
[Mac payload bridge](evidence/arras-0.5.1-binary-bridge-peer-review-20261023.json).

Final public verification run `39883764998` completed successfully on driver
`4bcccd4be9c437eb9957d74134a84b4421322c65`. The result receipt SHA-256 is
`c02767057805896c24acfa98ed5bd5f0fc1d8aa4b89adcd1a56d02893a742023`;
all five linked receipt hashes match. It binds original publication run
`39879533273`, driver `c02bca2b5417227f8f28d72171be0f7378c9b0bf`, tag object
`11b690b3795518315fa643379acf0f94383f135e`, source 8b, SUMS 43c41 and aggregate a848.
Actual anonymous comparison, distribution parity, doctor 20/eight phases/three
controls, fresh example 4/memory 72 and Linux 205/four route/four negative controls
pass. All three jobs and the final tag-recheck/result step pass. Visual execution
is explicitly excluded on Linux. Independent Sol review is retained in
[the safe final record](evidence/arras-0.5.1-public-verification-review-20261023.json).
Only HELIX closeout prose/evidence changes follow; immutable public assets and
original failed-run receipts remain unchanged. Real PyPI/npm upload is deferred.

The final HELIX-only closeout passes 23 documentation/public-content tests and
the generic content/whitespace gates. Sol approves all five updated documents and
three retained safe verification JSON records; the closure remains limited to the
recorded generic release subset. No package/runtime/testkit/asset or tag changes
are part of this documentation follow-up.

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
- [x] The bounded A2 official admission/core metadata API, provider qualification,
  ordering, module boundaries and required test gates are governed before code.
- [x] Bounded A2 admission/projection, memory metadata integration and both fresh
  installed environments pass on the named unreleased candidate. Trusted extension
  registration and broader semantics remain outside this first profile.
- [ ] A3–A7 prove current-source registration, declared execution, ownership,
  generated reads, selected optional/cross-module behavior and installed public-host
  conformance on their named native cohort. Unsupported cases remain explicit.
- [x] The claimed legacy memory mutation subset refuses affected unsupported
  declarations explicitly; broader official facet/rule execution remains open.
- [x] Current Arras request snapshots are reconciled with HF-01–HF-07 dispositions;
  no stale ask or candidate result is counted as release delivery.
- [x] Canonical contracts/test scenarios, evidence and Sol review agree with the
  delivered subset. Downstream application migration, Ashlar feed and actual Lakebase qualification
  remain outside the scoped P0 release. P0 delivery is closed against actual
  publication and supplemental fresh public-download evidence; remaining A2–A7 semantic work
  stays separately open.

## Later public Truss 0.0.49 adoption — isolated work

The isolated adoption branch began at `df923164840cb225a278d760ba911c106fa3c080`
with package metadata 0.5.1. After the release-owner handoff and PR 8 merge,
it merged released main `8542d477c411c96a553ea84572b86c95c59d7cf2`; current
package metadata is 0.6.0. The published 0.6.0 release retains its original
Truss 0.0.48/Weft 0.4.51 cohort. Earlier adoption receipts remain bound to their
captured 0.5.1 sources; the merge does not retarget them or qualify a new wheel.
Merged-head checks and installed-artifact qualification remain separate gates.
No new version/tag/publication follows from this plan. Runtime campaigns require
separately coordinated resource slots.

| Owner | Bounded deliverable | Gate and retained boundary |
| --- | --- | --- |
| Sol | CONTRACT-004/005 and TP-001 later-tranche amendments; source/evidence review | Preserve frontmatter/history; distinguish forwarding, local qualification and real managed acceptance |
| Luna A | Exact public49 pin/lock/artifact references; factory/backend/lifecycle forwarding and safe named refusal; catalog/signature and pure controls | Empty strict default; no reconnect widening or ACL-policy interpreter; keep 926-line ceiling and error/transaction precedence |
| Luna B | Explicit target/authority/fixture-bound executable Lakebase harness and pure gate controls | Actual public operations after admission; original redacted service evidence; no local fallback, inferred provider trust or fabricated MP pass |

The selected public49 source is
`dd13e95804abc30202d449a756240c6a684ab942`, wheel SHA-256
`7ea14b2787f02cbeec9ad99d835adbcc30c684fd5be8e0765a1d8198b50e7182`.
Native digest is `288801f7177338328441b5d3ce9328af31740ebf513f04ea45e30ae316a9f3a4`;
migration digest is `96addcdb95523f478d8f50b0b47198e47a860680c7400dd359711930e837e535`.
Weft stays 0.4.51, source `557153731e9f5d0583193a1189a07c6ed485d3d3`.
The Truss/public49 and managed-target owner
`01a16383-183c-7680-9518-f69ff40383e5` retains the immutable public49 proof and
Lakebase custody. The independent A2/0.6.0 release owner
`01a16023-fabd-7fa3-9abf-44d42e7fd673` provided the integration handoff after
the published release and PR 8 merge.
The published49 proof labels actual Lakebase `not_run`. The separate
[source review](evidence/truss049-adoption-20261023/source-review.json) binds
the harness and reported 52 pure controls. The
[local qualification](evidence/truss049-adoption-20261023/local-qualification.json)
binds the later source-native 199-case run and coordinator-observed two local
transaction-mode passes. Its editable Arras 0.5.1, runtime, cleanup and artifact
capture limits remain explicit; neither receipt is a managed-service result.

The human authorized the managed-target owner to create a dedicated Lakebase
with the Databricks CLI. That target is now provisioned; its read-only preflight
observes PostgreSQL 18.6 (`180006`), psycopg 3.3.6/libpq `180006`, verified TLS
with a maintained CA bundle, and no `truss` schema. No service mutation is implied
by these observations. An ordinary OAuth identity remains blocked by workspace
service-principal creation permission; the owner awaits the human identity
handoff. Neither a native-password baseline nor a nonhuman OAuth actor may be
reported as human-token acceptance. The secure source, exact authorized roles
and operational controls still require handoff without private coordinates in
these artifacts. MP-01–06 and actual consumer acceptance remain open until
original service evidence and confirmed owned cleanup pass. Official UMF
value/action and Ashlar work remain separate.

### PR 9 release execution continuation — 2026-10-23

The human requested completion of the installed 0.0.49 and actual Lakebase gates,
review, merge and release. The release owner now exclusively owns the adoption
checkout and publication lane; action/constraint work proceeds in a separate
checkout. The original draft/source receipts remain historical. The required
managed schedules now have separate implementation and Sol review lanes, with
the target owner supplying only private factual provider/credential controls.
The TP-001 execution amendment governs mixed identities, original service proof,
pre-cleanup sequencing and reusable setup without repeated admin activation.

The first fresh installed native attempt failed conformance validation and then
exposed a failure-receipt path serialization defect. Its failed logs and capture
limitation are retained privately; it is not a pass. The reviewed Path-only
serialization fix and regression test are committed separately, and the same
candidate wheel is being rerun. Exact wheel/sdist parity, packed imports, doctor
controls and fresh official UMF qualification passed for that candidate. These
results do not qualify a later version bump, final release wheel or Lakebase.
Actual service execution and publication remain pending their original evidence.

The rerun of that original candidate passed 64 native cases with eight unchanged
declared limits and zero failed/harness-error cases. A subsequent 0.6.1 candidate
exposed incomplete version updates: its example host still required 0.6.0, and
the public API catalog and theme fixture retained the previous version. The
failed installed-doctor and extension-consumer attempts are retained; the version
references are corrected together before rebuilding and qualifying a new wheel.
The earlier wheel identities are candidate evidence only.

Databricks bootstrap is now complete for the dedicated target: separately
authenticated ordinary OAuth actors include one human writer and three service
principals, all without elevated database attributes or ownership. Reusable
credential references remain in private Keychain custody. Bootstrap and identity
smoke evidence qualify setup only; the actual twelve-case managed campaign and
independently confirmed owned cleanup are still pending.

The corrected 0.6.1 wheel has SHA-256
`7608193d46257e2666b11fabad2696f35d976f9253b032600868729041c60e02`.
Its twenty installed doctor controls, fresh extension consumer and official UMF
gate pass. Independent installed payload comparison covers 172 Arras and 474
Truss wheel members, with the observed public49 archive/native/migration hashes.
The prior `90e613e2...` candidate's native campaign reached the 35-minute command
deadline without a conformance report. Its original failed receipt has SHA-256
`9da367940231af13a3e136686c644ccd9cd7824377da68aeeb2104618e8eb203`;
the exact owned PostgreSQL process was independently identified and stopped, and
zero owned PID files/processes remained. The private failed state and supplemental
cleanup record are retained. The reviewed optional conformance deadline preserves
the 2,100-second default, bounds explicit overrides to 1–7,200 seconds, records
the selected deadline and changes no acceptance assertion or operation timeout.
The corrected wheel still requires its own installed native proof.

Source checkpoint `9377a902fbc1fd8ab457de0c093329875770fedf` passed Linux
source/build, default Python and UI CI, while the native job passed 201 cases and
failed the new managed API case. The selected49 history emitter preserves typed
UMF string cells; the decoder incorrectly expected bare strings. The reviewed
correction preserves the exact `{kind: "string", text: ...}` cell and extracts
text only for the independent Probe comparison, with closed-shape refusal
controls. The actual local public49 API test then passed in 59.59 seconds,
retaining three original feed pages privately, and no qualification PostgreSQL
process remained. The rebound pure runner suite passed 163 cases with the one
explicit Truss-marked test deselected.

The broad Mac default run recorded 3,209 passes, sandbox-denied loopback server
cases and a 100 ms interpreter-start timing assertion. All thirteen server tests
passed in the targeted permitted environment. The reviewed timeout-test fixture
now uses isolated no-site Python startup while preserving its 100 ms deadline,
production runner, stdout and process-reaping assertions; the isolated test and
combined runner suite pass. Original failures remain retained. Final-source CI,
corrected-wheel native qualification and actual Lakebase remain separate gates.


Source `8e807dbfee8bd5d06877a723ea827ab46186a2e2` passed all four CI jobs
in run `39992131372`. The actual Lakebase execution then stopped twice before
SQL admission: the first attempt encountered an expired human CLI refresh token;
ordinary same-profile SSO repaired that credential without renewed admin setup.
The second attempt exposed a verifier defect that indexed the global `mixed`
authentication profile instead of the actor-specific profile. All twelve cases
remained `not_run`, cleanup was `not_attempted`, and the original failed receipt
and equal before/after installed-artifact binding remain retained privately.

The reviewed correction resolves credential provenance against each authorized
actor label. Pure controls cover the actual human-writer/three-service-principal
arrangement, the allowed native-reader variant, profile/subject/provider mismatch
refusals before connection acquisition, and homogeneous schema1 behavior. The
credential-source repair and verifier correction do not qualify managed cases.
A new source/harness/entry freeze and independently rebound private fixture are
required before a fresh actual campaign. Existing failed attempts stay intact.


The third actual attempt passed credential-source admission, then stopped during
service admission. The original failed installed-execution binding is retained;
no installation, module mutation or provider restart occurred. Read-only diagnosis
confirmed that the fixture and four public harness call sites referenced the
nonexistent psycopg3 `ConnectionInfo.dsn_parameters` property. The selected driver
is psycopg 3.3.6 and exposes `get_parameters()` instead. The corrected observers
retain exact endpoint, verify-full TLS, root-certificate and native role checks;
updated test doubles use the actual driver surface and transport refusals remain
explicit. The private fixture has separate review and 48 passing offline controls.
A subsequent actual read-only smoke observed all five authenticated connections,
expected native identities and TLS facts, with Truss absent. This is admission
readiness evidence only; all twelve managed acceptance cases still require a new
full campaign with refreshed source, fixture and authorization bindings.
