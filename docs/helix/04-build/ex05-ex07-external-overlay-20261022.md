---
ddx:
  id: PLAN-ARRAS-EX05-EX07-20261022
  type: implementation-plan
  activity: build
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-22
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: architecture
      kind: informed_by
    - id: arras.downstream-extensibility
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

# Explicit downstream resources and installed conformance

## Scope

Deliver EX-05's neutral Python overlay and EX-07's installed public-runner,
reusable-job and repository-provenance cut. Governed by the
[downstream design](../02-design/downstream-extensibility.md),
[registry contract](../02-design/contracts/CONTRACT-002-type-registry-and-placement.md),
[action/import contract](../02-design/contracts/CONTRACT-003-actions.md),
[backend contract](../02-design/contracts/CONTRACT-004-backend-contract.md) and
[project test plan](../03-test/test-plan.md).

The overlay uses declared public Python APIs to compose an empty in-memory host,
register one host-owned module and import only explicitly selected seed/graph
resources. Its graph envelope belongs to the example; it is not a new public UMF
or Arras graph-file format. It demonstrates the named legacy executable subset,
not complete official UMF support. Branding, process configuration, UI assets,
public manifests and compatibility tooling remain with their coordinated owners.

The public `run_corpus(factory)` already accepts a host-provided `Harness`
factory, but `tests/truss_harness.py` is repository-only. Deliver a small installed
native harness over the production `LocalTruss` lifecycle rather than copying
that repository fixture. Source/helper delivery and installed native qualification
are separate gates. Native/browser jobs stay qualified separately; memory
evidence cannot close them.

## Shared Constraints

- No automatic default module, seed, graph or arbitrary import discovery. Read
  resource bytes explicitly; never load Python named by documents/configuration.
- Consumer shims re-export named public APIs and use the existing typed
  distribution configuration. They do not rewrite canonical package identities.
- Preserve source bytes, actor attribution and registration/import refusals.
  Unsupported declared semantics remain refused by the selected backend profile.
- Reuse the packaged corpus and its runner. No copied repository tests or
  weakened expectations/limits. Record reader/store roles, skipped cases,
  documented limits and host-specific outcomes separately.
- Workflow wheel URL/digest use environment values, not interpolated shell.
  Require 64 hexadecimal digest characters, HTTPS without userinfo and an
  expected wheel basename before downloading/installing. Bound caller project/
  test paths to the workspace; no eval or free-text shell command input.
- A declared optional downstream design-system peer is not a required upstream
  dependency. Required/private dependency checks must preserve that distinction.
- Public-origin policy is declaration/integrity evidence, not proof that a remote
  repository/package is publicly accessible. No customer-name allow/deny-list or
  automatic text scrubber. Review changed prose for meaning and provenance.
- Preserve artifact IDs/frontmatter/links and historical source evidence. Active
  product requirements become generic host requirements; original downstream
  decisions do not become fabricated upstream authority.

## Implementation Slices

| Slice | Area / governing artifact | Depends on | Exact files and acceptance |
| --- | --- | --- | --- |
| E57-0 | Boundary/contract adoption; CONTRACT-002/003/004, TP-001 | Owner acknowledgement | Contracts/test plan first; keep current `tests/test_modules.py` and public-import gates. Parent coordinates manifest/CI ownership. No new internal-import exemption. |
| E57-1 | Own resource/shim proof; EX-05 | E57-0; public configuration owner | `examples/extension_host/pyproject.toml`, `README.md`, `src/extension_host/{__init__.py,__main__.py,app.py,configuration.py,resources/{module.umf.json,seed.json,graph.json}}`, `tests/test_overlay.py`. Build/install outside the Arras source tree; only its own namespace/content exists. Exact source round-trip, seed/graph attribution, a declared action/read and isolation from another host pass. No bundled defaults or private imports. |
| E57-2 | Installed corpus command; EX-07, CONTRACT-004 | E57-0; public command manifest owner | `src/arras/conformance/__main__.py`, `tests/test_conformance_cli.py`. Fixed built-in memory-store/replica choices call existing `run_corpus`; JSON records actual roles, corpus version and every outcome category. Nonempty complete applicable corpus required for success; failed/newer/empty selections exit nonzero. No import-string adapter loader. Public custom factories use the existing Python callable protocol. |
| E57-2N | Optional lifecycle and native harness; EX-07, CONTRACT-004 | E57-0; native owner/exact-cohort coordination | New `src/arras/conformance/truss.py`, `tests/test_conformance_lifecycle.py`, `tests/test_conformance_truss.py`; narrow `src/arras/conformance/__init__.py` optional `close()` handling. No required protocol method. Owned fresh local servers, real principals/foreign receipt, explicit testing-only unsupported-version simulation, cleanup on every path with primary-failure preservation. No personal endpoint or copied repository test implementation. Qualify installed native corpus on the selected released cohort separately. |
| E57-2NV | Strict installed native verifier; CONTRACT-004, TP-001 | E57-2N; explicit reviewed public cohort/index; release owner | `tools/verify_native.py`, private `tools/_native_{artifacts,install,payload,process}.py` helpers and `tests/test_verify_native.py`. Cohort schema v1 names exact Arras/native wheel hashes, index digest, runtime and complete deliberate corpus limit map. Verify selected anchors/downloaded bytes/metadata; install direct native paths with toolkit local/native/query extras and fresh public base dependencies outside checkout. Installed payload/origin/version evidence plus exact installed-derived applicable/skipped IDs/counts and CLI exit determine the result. Empty limits means strict all-pass; no invented prospective-release allowance. Unit/source proof and actual installed native qualification remain distinct. Parent owns release workflow invocation, not this tool. |
| E57-3 | Generic repository gate; EX-07 | E57-0; reviewed provenance inventory | `tools/check_public_content.py`, `tools/public-content-policy.json`, `tests/test_public_content.py`. Check declared dependency/import origins, sensitive credential patterns and fixture/prose provenance with source hashes/classification. Negative controls cover undeclared consumer import, credential-bearing source, untracked fixture and stale digest. Reviewed exceptions name a source and reason, never a customer term. The checker does not claim to infer customer identity or license grants. |
| E57-4 | Reusable installed jobs; EX-07, TP-001 | E57-1/2/3; CI owner acknowledgement | `.github/workflows/downstream.yml` plus narrowly coordinated `.github/workflows/ci.yml` hook. Required wheel URL/digest verified before installation; install into a clean environment, record actual artifact/dependency identities, execute installed corpus and explicit consumer proof. No silent native/theme fallback. Callers pin the workflow revision; remote-host execution remains unqualified until run. |
| E57-5 | Semantic documentation generalization; EX-07 | Reviewed per-file inventory; reserved-owner acknowledgement | Pure prose files named in the coordinated inventory only. Current requirements retain their FR/US/ADR IDs and intended behavior; borrowed downstream decisions are distinguished from Arras authority. Dated evidence remains historical. Neutral renames of two story filenames require index/link coordination. UI fixtures and reserved contracts/ADRs stay with their owners. |

The current module checker is `python -m pytest -q tests/test_modules.py`; the
separate public-boundary test remains in the final selected set. A forbidden
consumer import must fail without changing the import baseline. No pre-commit
hook is asserted. CI adoption is recorded only after its actual workflow hook
exists. E57-2N native delivery and its exact installed cohort must pass before E57-4
claims the native backend job requirement complete.

## Release evidence assembly — E57-2NE

The release owner invokes a private, standard-library-only assembler after the
build, installed-native and exact-wheel UI jobs pass. This is release proof
linkage, not another qualification implementation. Luna owns only
`.github/scripts/assemble_release_evidence.py`, the cohesive private IO/parser/
archive helper `.github/scripts/_release_evidence_inputs.py` and
`tests/test_release_evidence.py`; the release workflow remains with its owner.
The helper has no import back into the assembler and introduces no public API
or source-size ceiling change.

The command takes explicit paths for the verified build bundle, native receipt,
binding receipt, bound cohort, companion index, full UI receipt and fresh
consumer receipt, plus the trusted build's expected version, wheel filename and
SHA-256 and a new output directory. The full portable UI receipt's schema and
success predicate must be agreed with its producer before that interface is
frozen. Historical narrow theme receipts cannot satisfy the full-suite gate.

All selected inputs are bounded regular files: reject duplicate JSON keys,
symlinks, escaping names, input/output aliases, unsupported schemas and missing,
failed, stale or mismatched evidence. Verify the build checksum inventory and
the actual wheel/sdist/npm identities, including the wheel-carried npm bytes.
Bind every qualification to that exact wheel and version; bind UI to the exact
npm artifact as well. Cross-check native manifest/index/binding digests, selected
runtime and wheels, corpus version/roles/IDs/outcomes and the complete deliberate
limit mapping. A manifest is not evidence that its cohort passed.

Preserve the verified distribution artifacts and original build-verification
receipt bytes. Publish only explicitly selected safe evidence fields and public
native manifest/index data, with original input hashes recorded in the aggregate.
Preserve existing build receipts byte-for-byte; diagnostic receipt projections
are separate assets rather than replacements for those original receipts.
Do not copy raw logs, process environments, credentials, PostgreSQL state or
arbitrary artifact-directory contents. The aggregate records successful
prepublication gates and marks the public-download gate
`not_run_at_assembly`, with its purpose. This immutable aggregate is not later
rewritten to claim success; a separate post-download receipt can record that
execution. Its `qualification_scope` describes linked component proofs and their
exact cohorts/runtime limits, not one production-host end-to-end proof. Generate
`SHA256SUMS` over every selected output asset after assembly.

The selected output inventory has sixteen files: the five original build assets
(wheel, sdist, npm archive and two build receipts); four safe native/binding/UI/
consumer projections; `release-evidence.json`; the validated bound cohort and
companion index; the three safe canonical UI inventory/resource/summary JSON
sidecars; and regenerated `SHA256SUMS`. Preserve the cohort/index and sidecar
bytes exactly because component digests refer to them. The aggregate links each
published component by filename and digest; original diagnostic input hashes are
separate provenance. The root owner settles the final producer predicates before
implementation review closes.

Synthetic tests prove successful linkage, unchanged artifact bytes and exact
output inventory, plus refusals for missing/failed/stale receipts, mismatched
wheel/npm/cohort/index identity, incomplete full UI evidence, duplicate JSON,
unsafe paths and output aliases. They are not native, browser, publication or
public-download qualification. Final assembly consumes actual passing job
receipts; post-download consumer/config/doctor checks reuse the existing tools
under the release owner's workflow.

## Execution Contract

The human has authorized the eight extensibility requirements. This lane owns
EX-05/EX-07 under the parent coordination boundary: Sol planning/contracts/review,
Luna implementation. Exact implementation paths require parent acknowledgement
before code changes; ordinary implementation/debugging then stays in scope.
No commit, tag, push or publication is authorized here. Token estimate and total
spending ceiling are unknown; no separate numeric budget was supplied or is
claimed enforced. Verification and review are part of each slice.

## Continuation Evidence

The explicit overlay, fixed corpus command, optional harness lifecycle, owned
native helper, generic content gate and reusable workflow are implemented. Sol
review and qualification remain scoped by the evidence below; source delivery is
not hosted-workflow or full installed-native qualification.

| Slice | Current evidence and remaining gate |
| --- | --- |
| E57-0 | CONTRACT-002/003/004 and TP-001 define explicit resource ownership, cleanup, installed checks and truthful optional-stage outcomes. |
| E57-1/2 | Real declared-Hatchling consumer wheel and temporary Arras wheel passed an external fresh-venv/public-index run: isolated imports, own graph/seed/action attribution, 72 memory-store corpus cases and three installed-only consumer pytest tests with zero failures/errors/skips. The earlier shared-dependency run remains separately labeled historical evidence. See [fresh receipt](evidence/ex05-ex07-20261022/fresh-installed-consumer.json) and [profile](evidence/ex05-ex07-20261022/fresh-and-native-profile.json). The final verifier run used explicit public indexes, uv no-config and pip isolated mode. Earlier incorrect importer/admin-read test assumptions were corrected without product changes and retained in the profile history. |
| E57-2N | Owned native helper, lazy foreign provisioning and cleanup/factory-error controls are source-reviewed. First smoke exposed invalid hyphenated backend names; underscore correction and real-factory regression control preceded the passing native smoke (real foreign receipt and admin-without-schema refusal). [Three selected source corpus cases](evidence/ex05-ex07-20261022/native-three-case.json) also passed on Truss 0.0.45/Weft 0.4.49. Full installed native corpus on the selected released cohort remains open; no Linux claim. |
| E57-2NV | Implemented and Sol-reviewed as source/offline preparation. Seventeen offline tests pass, including real POSIX timeout cancellation, executed ELF/foreign-PE probe classification, rewritten-script payload checks, input aliases, generic/CLI/installed-validation failure receipts and exact case/limit accounting. Whole-project Pyright reports zero errors; Ruff/format and actual CLI `--help` pass. The verifier is 922 lines under the unchanged 926 ceiling; four cohesive private helpers retain the direct CLI/import boundary. Failed owned PostgreSQL state is quarantined rather than deleted. No native cohort is prequalified by its manifest: public 0.0.48/0.4.51 adoption, a current wheel and full installed native execution remain pending. No prospective-release limit allowlist or native receipt was invented. |
| E57-2NE | Assembler source is implemented and independently Sol-reviewed: eleven synthetic tests pass; Ruff/format, strict targeted Pyright and actual CLI help pass. The 921-line assembler and private input helper remain below the unchanged source ceiling. Tests cover the exact sixteen-file inventory, unchanged five build assets and raw cohort/index/UI sidecars, emitted component hashes, native/memory corpus applicability parity, full seventeen-spec archive resources, unsafe input/JSON/HTML/FIFO refusals, and trusted doctor source/literal-probe digest linkage. The doctor predicate preserves all twenty named expected outcomes, including negative exit statuses; checks eight routed telemetry phases, three exact false-pass controls and typed tripwire controls; and rejects a receipt when its trusted producer source changes. Logical structured operation records do not establish OpenTelemetry span-event counts. Doctor OS, architecture, release and Python identity are validated and reported separately from the native runtime; exact Windows architecture aliases are metadata controls, not Windows qualification. CLI parsing remains in the private input helper. An early incorrect npm resource prefix was corrected against the actual packer layout (`package/support/`). Historical direct validation accepted the doctor component receipt for temporary wheel `cdc7ec0d…c8261`, source `356fe79e…17c4` and literal probe `2dd054ff…6e0f`. That receipt is now stale after the producer changed OS reporting to `sys.platform`; current source `d17c291c…5e19` requires a new actual receipt. No old receipt was rewritten. Component compatibility and synthetic controls are not full assembly or native/browser/publication/download qualification. Exact final release-cohort workflow execution remains with the release owner. |
| E57-3/4 | Generic origin/import/fixture gate and self-contained reusable workflow are implemented. Negative controls cover missing provenance, stale hashes, undeclared imports, unsafe caller paths and empty/skipped/failing JUnit reports. Optional trusted setup paths are hashed; native setup requires `ARRAS_REQUIRE_TRUSS=1`. Final Sol review found no blocking issue in reference-SHA and installed-payload revalidation after setup; its tamper controls pass in the 12-test source gate. Hosted execution and rendered-theme/browser qualification remain separate. The coordinated CI source change is also Sol-reviewed: approved Ubuntu HTTPS-source helper/self-test, effective APT retry/time bounds, bounded update/dependency/browser installation, locally locked Playwright Chromium launch with a 90-second bound and receipt upload, and the unchanged three Linux test projects. YAML/embedded-code/helper-fixture/pin checks pass; this source evidence is not an actual Linux Chromium or native run. No macOS APT application is claimed. |
| E57-5 | Human semantic review generalized 64 acknowledged prose files, preserved IDs/source history and migrated two neutral story filenames with index/relative-link checks. [Dated provenance](evidence/ex05-ex07-20261022/documentation-generalization.json) records original/current checkpoint hashes. Reserved-owner prose and source/test fixtures are coordinated separately; this inventory is not a text-classification claim. |

The temporary installed proof does not qualify every later source edit or a final
released artifact. Source-helper smoke does not establish full native corpus
support. Optional caller pytest targets do not establish a renderer/a11y or
managed-platform certification.

Fixture provenance is recorded from actual sources: the catalog states its data
is invented; pizza states invented instances over the Protégé tutorial structure;
Northwind is an abridged Microsoft sample. Preserve those distinctions and any
unknown redistribution terms rather than invent a license. The new neutral
extension fixture is authored for this example and declared under the repository
license. A manifest entry proves recorded origin/integrity, not source access or
permission from a third party.

## Validation Plan

- Run focused new behavioral/negative controls, existing testing/conformance,
  public import/boundary/module tests, Ruff and the selected interpreter's Pyright.
- Build the wheel through the existing artifact pipeline, install it and the
  example into a clean external directory, and run with Python isolated mode.
  Record no Arras checkout/test import path and no copied tests. Preserve the
  root artifact verifier's distinct qualification.
- Exercise the reusable job's exact local command path; record remote workflow
  execution separately. Optional native/browser/theme work must identify its
  artifact/platform/profile and explicitly fail or remain unqualified if absent.
- Review every generalized document diff for changed requirements, false source
  claims, broken links and preserved frontmatter/IDs. Search alone is not review.

## Risks and Rollbacks

| Risk | Response | Rollback |
| --- | --- | --- |
| Host data/defaults leak into a generic consumer | Own namespace/resources and module enumeration assertions; no example_module default | Remove the example/loader without changing product defaults |
| Corpus success misstates coverage | Report roles/skips/limits and require nonempty applicable results; negative failing harness control | Remove the command; keep existing Python runner |
| Policy becomes a name scrubber or fabricated license proof | Generic declarations/provenance and semantic review; explicit third-party unknowns | Revert the disputed prose/policy entry, preserving original evidence |
| Native facade accidentally becomes production provisioning | Separate owned testing resources from host credentials and qualify only an explicit native cohort | Keep native job unavailable; retain memory proof and existing public factory protocol |

## Exit Criteria

- [x] A clean installed generic overlay loads only its own module/seed/graph through public APIs (dated temporary-artifact scope above).
- [ ] Installed corpus/job reports distinguish declared roles, skips, limits and actual qualification.
- [x] Generic content/dependency/provenance gate and negative controls are wired locally/CI (source/local checks; hosted workflow execution is separate).
- [x] The semantic hygiene inventory is dispositioned with reserved owners and source history preserved.
- [ ] Optional native/theme requirements are delivered with evidence or explicitly remain open; memory success cannot close them.
- [ ] Required focused/integration checks and Sol review pass; canonical docs and evidence match the delivered scope.
