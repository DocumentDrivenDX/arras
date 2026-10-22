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
---

# Arras integration build plan

## Scope

Adopt official UMF semantics and the generated client's public transport in
Arras, the current name of Hohfeld. Arras owns the application interface to the
universal graph: registration, authenticated sessions, placement, execution
coordination and results. UMF owns the metamodel, constraints, action declarations,
generation and reusable conformance vectors. Truss owns native graph transactions;
Weft owns query compilation. Each change must preserve those boundaries.

Active Arras work targets `/Users/erik/Projects/arras`. Historical Hohfeld artifact
IDs, source paths and digests remain historical evidence. This plan sequences
Arras work alongside existing owners; it does not reopen or duplicate their queues.
Praxis is an optional acceptance-fixture source, not an implementation target.
No Praxis code, dependencies, transport glue, deployment or UI changes are in scope.

Governing local artifacts: [PRD](../01-frame/prd.md) FR-9/13/14,
[principles](../01-frame/principles.md) 1–6,
[architecture](../02-design/architecture.md#module-boundaries),
[CONTRACT-002](../02-design/contracts/CONTRACT-002-type-registry-and-placement.md),
[CONTRACT-003](../02-design/contracts/CONTRACT-003-actions.md),
[CONTRACT-004](../02-design/contracts/CONTRACT-004-backend-contract.md), and
[TP-001](../03-test/test-plan.md). The installed HELIX 0.18.0 `workflows/`
catalog supplies the plan shape and `artifact-signal` voice; it is not copied here.

Upstream coordination sources:

- Truss's [HF-01–HF-07 follow-up plan](../../../../truss/docs/helix/04-build/hohfeld-followup-plan-20261021.md)
  and [semantic pushbacks](../../../../truss/docs/helix/04-build/hohfeld-pushbacks-20261021.md).
- UMF's [general UMF–Arras plan](/Users/erik/.codex/worktrees/1243/umf/docs/helix/04-build/umf-arras-integration-plan.md),
  retaining artifact ID `umf.praxis-hohfeld-adoption-plan`. H1–H7 and HA-0–HA-7
  below refer to that plan and its governing CONTRACT-079/900.
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
| H1–H7 / HA-0–HA-7 | Evaluate Hohfeld requirements ask, `01a16384-78eb-7b30-82e1-c1f1feacc383` | UMF owns shared semantics, wire/generator changes and vectors; this chat coordinates Arras host/runtime implementation. Preserve the renamed plan's original ID. |

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

## Continuation Evidence

2026-10-22 baseline reported by the coordinating chat: Arras source identifies
itself as 0.5.0 and pins Truss 0.0.45 with Weft 0.4.49. The ordinary suite returned
2,551 passes and 187 deselections, with one failure and eleven setup errors from
denied local socket binding in `tests/test_devhost_server.py`. The complete HTTP
file separately passed all 13 tests with socket permission. These are baseline
suite results, not native Truss or official-UMF conformance. The Arras checkout
has no committed HEAD; preserve the existing working files and exact tested bytes.

Source inspection finds only the Truss adapter and memory doubles. A search of
visible repository source excluding dependency/Git directories found no Hohfeld
references. Current-source probes reported by the coordinating chat show:

- The official action fixture is refused by the legacy reader. This does not
  qualify current action support or justify weakening UMF's fixture.
- Declared DDD version `999` is accepted and executable; A0 addresses this gap.
- A declared Unicode-scalar length maximum of three accepts/stores a longer name
  in memory. `PropertyInfo` does not retain facets. This is an execution-fidelity
  defect, not evidence against the native Truss facet controls or a reason to copy
  an evaluator. A0 does not close it.

Luna is assigned A0's declared-version guard and parser/zero-state-mutation tests.
Sol owns this plan and review. No A0 completion is asserted here. The existing
Truss owner is qualifying its following-release cohort; its plan still separates
candidate evidence from public release adoption. The UMF owner has been asked to
implement UMF-only work against the renamed integration plan.

The four current Arras request files were hashed directly on 2026-10-22:

| Current file under `docs/helix/02-design/` | SHA-256 | Historical Truss snapshot |
| --- | --- | --- |
| `truss-requirements.md` | `0a7be408d15947382f0ab3a5af05a3ff0978c85e597db31ff6acb50caeabed60` | Different |
| `truss-statement-overhead-spec.md` | `caeb0276935514aa05735772fd3653dd9fb6cefaf7145d8f3263d60b6ba4ff15` | Different |
| `truss-registration-evidence-spec.md` | `1a60da1464be4d1b03b0877e27b497551b86782ef55c1776eeaa4c72a3742abf` | Same |
| `truss-query-and-conditions-findings.md` | `d31e36a1fdfa47fb35a0999f22317b410ad22455fb343d80f3362aad3228e777` | Different |

Keep the historical hashes in Truss's source-custody section unchanged. Reconcile
the three changed files against those inputs and dispositions before claiming the
current Arras request queue closed. Renaming alone cannot prove equal requests.
Next action: verify/review A0, then run A1 and record exact artifacts, commands,
results and missing semantic registrations alongside this plan.

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

- [ ] A0 passes its guard, unchanged-state, boundary, quality and review gates.
- [ ] A1 identifies a usable official artifact cohort or records the precise missing
  API/semantic registration; A2 settles the contract before dependent implementation.
- [ ] A3–A7 prove current-source registration, declared execution, ownership,
  generated reads, selected optional/cross-module behavior and installed public-host
  conformance on their named native cohort. Unsupported cases remain explicit.
- [ ] Memory facet loss is resolved through the authoritative boundary or explicit
  affected-operation refusal; no silent meaning loss remains in the claimed subset.
- [ ] Current Arras request snapshots are reconciled with HF-01–HF-07 dispositions;
  no stale ask or candidate result is counted as release delivery.
- [ ] Canonical contracts/test scenarios, evidence and Sol review agree with the
  delivered subset. Praxis migration, Ashlar feed, actual Lakebase qualification,
  merge and publication remain outside this plan's completion claims.
