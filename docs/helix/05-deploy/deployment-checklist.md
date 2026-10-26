---
ddx:
  id: arras.release-checklist
  type: deployment-checklist
  activity: deploy
  status: draft
  authoring:
    home: repo
  links:
    - id: PLAN-ARRAS-INTEGRATION-20261022
      kind: informed_by
    - id: arras.downstream-extensibility
      kind: informed_by
    - id: CONTRACT-005
      kind: informed_by
    - id: TP-001
      kind: informed_by
---

# Arras artifact release checklist

## Release

The immutable 0.5.1 release history below remains complete. Arras 0.6.0 adds
bounded official-UMF admission and opt-in read-only memory metadata projection.
Local candidate evidence and completed public acceptance are recorded below and
in the [integration plan](../04-build/arras-integration-plan-20261022.md).

GitHub Release assets and automatic PyPI/npm delivery are required for new
registry-enabled releases. Publishers consume the exact qualified assets after
the complete release/public-download gates, using configured OIDC trust. Missing
access fails the affected publisher; it does not silently defer publication.
Earlier explicitly deferred releases retain their historical delivery scope.
Do not advertise a registry install until its download and clean consumer checks
pass.

## Before Deploy

- Sol reviews Luna's final feature and release changes; blocking findings are
  resolved. All owners acknowledge a source freeze before the release commit.
- Adopt Truss/Weft only after their owner supplies the exact public artifacts,
  digests, compatible source identities and Linux qualification. Keep candidate
  replay evidence separate. Update the pin, lock, find-links, reported version
  and compatibility record together; never skip failing native tests.
- Version, deliberate public catalog, contract mappings, page/theme manifests and
  wheel-carried npm metadata agree. No secret, downstream import, private theme
  dependency or customer-specific fixture enters the public source/artifacts.
- Standard GitHub authentication and push access are verified. Configure PyPI
  and npm trusted publishers for `DocumentDrivenDX/arras`, workflow
  `publish-registries.yml`, with environments `pypi` and `npm`. Each environment
  permits only the `main` publishing driver and requires no per-release reviewer.
  Do not record credentials. First npm publication requires scope-owner bootstrap
  authentication before its package can acquire a trusted publisher.
- Validate explicit consumer configuration and identity-conflict controls. The
  offline doctor reads only declared inputs, never ambient tokens or live hosts.
- Check wheel and sdist dependency metadata for every direct-reference scheme,
  including optional extras. Plain PyPI install qualification covers the base
  package. Extras with off-index upstream dependencies retain explicit verified
  wheelhouse instructions and separate installed-cohort evidence; do not claim
  that plain `pip install arras[umf]` or `arras[truss]` resolves from PyPI.

## Validation Gates

| Gate | Required evidence before publication |
| --- | --- |
| Source quality | Full Ruff/format, strict Pyright with the selected interpreter, default Python suite, module/import boundaries and public catalog checks pass on the final source. |
| Native behavior | Full native Arras suite and installed public conformance helper pass against the exact released Truss/Weft/PostgreSQL cohort; GitHub Linux tag gates pass. |
| UI | Lint/format/type/unit/integration/browser gates pass; both installed prebuilt/runtime-theme and packed host-build routes pass internal widget/Mark, token/contrast, axe and keyboard checks. macOS theme baselines are distinct from Linux nonvisual checks. |
| Portable UI suite | Publish the canonical existing Playwright accessibility/UI suite and standard acceptance resources through a Node-only testkit plus browser acceptance host. Source and installed consumers share assertions; the actual packed themed run passes, with explicit host URLs and separate macOS theme baselines. The narrower theme checker alone is insufficient. |
| External consumer | Generic package shim/config/module/seed/graph and reusable CI jobs run from installed artifacts without copying repository tests. Doctor positive and breaking controls pass. |
| Telemetry naming | Typed per-host service/attribute/event/log names work through effective configuration, preserve canonical defaults, never mutate the global provider, and pass actual SDK receiver, redaction, failure-isolation and concurrent-host controls. Existing host formatting alone does not close this explicit requirement. |
| Policy | Current-principal allow/refusal/revocation checks pass. An annotation-aware synthetic provider proves same-group commit/rollback; unsupported native providers refuse before writing. No speculative sensitive workload is introduced. |
| Exact artifacts | Build wheel/sdist/npm from final source. Rebuild the wheel from that exact sdist, compare complete payloads/metadata, run fresh installed consumers and retain a separate verification receipt. Rebuild again after any packaged source/test/tool change. |
| Tag and assets | Mandatory exact-tag source/native/UI/downstream/build gates precede GitHub publication. Attach wheel, sdist, wheel-carried npm tarball, receipt and `SHA256SUMS`; registry publishers use those same verified bytes. |
| Downloaded release | Download the public release assets into a new directory, verify digests and repeat installed consumer/skeleton/doctor checks. A local build alone does not pass this gate. |
| Official UMF qualification (0.6.0+) | The exact final wheel passes the installed admission/metadata gate with pinned official UMF 0.10.0: all 139 ordered reference and separate fresh-empty production Registry comparisons, six base and ten extra-enabled controls, zero skips, and verified cleanup. Repeat against the exact public-download wheel in a fresh environment; retain distinct receipts. The 0.5.1 candidate receipt is historical and cannot close this gate. |
| Public assembly (0.6.0+) | Use release-evidence schema v2: include the mandatory safe UMF receipt projection as asset 17, bind it to the exact wheel, and repeat UMF qualification after public download. Keep v1/sixteen-asset evidence for historical releases unchanged. |
| Truss 0.0.50 adoption / PR 9 | Before merge or tagging, retain and independently review the fresh-installed exact-cohort proof and full actual Lakebase receipt: LB-ADMISSION, LB-INSTALL, LB-PERSON, LB-CUSTODY, LB-SETTLEMENT, LB-ACL and MP-01–06 all pass, with independent owned-cleanup confirmation. Bind the managed receipt to the executed harness/fixture hashes, actual installed Truss archive/manifests and exact final Arras wheel, which must also pass the complete fresh-installed macOS campaign. Require the tagged-build and public wheel SHA-256 to match both original campaign bindings; any byte change requires both campaigns rebound and rerun. Document exact source correspondence to the release artifact; source-local checks, bootstrap evidence, partial schedules and earlier candidate artifacts cannot close this gate. |

## PR 9 / 0.6.1 execution

- [x] Historical candidate `c31b56e5...` passed the complete fresh-installed
  macOS native campaign (64 passed, eight unchanged limits, no failures),
  independent cleanup, installed doctor and CI-installed official UMF checks.
  This Truss 0.0.49-bound result is retained historically and does not qualify
  the current Truss 0.0.50 selection.
- [x] The current public Truss 0.0.50 / Arras 0.6.1 binding is recorded at
  source `20db67822b20c822ee91c6823a3fe73ebc3ae932`. Canonical Arras wheel
  `259e16c7d4c8f6c56d9930ee5f16e74c4ab6b2c8a3ecffdb7d8b306c77b60f18`
  passed the complete fresh-installed macOS arm64 / CPython 3.11.9 campaign in
  CI run `40221099126`: 64 passes, eight unchanged declared limits, seven
  replica-only cases inapplicable, and successful cleanup. The [current Mac
  records](../04-build/evidence/truss050-adoption-20261024/fresh-macos-40221099126/)
  retain exact installed-payload and source correspondence. The separate full
  twelve-case managed campaign on the same wheel passed 12/12 with zero failures
  or blocked cases and passing original cleanup, independent audit, census and
  custody handback. The public release built from merge commit
  `243f1ebaf8b32beb0abc30d0d4fdcd9dd7b5ea92` carries the same wheel bytes.
- [x] Release-built artifacts match that exact wheel and complete their own
  distribution, native, doctor, official UMF and downstream UI release gates;
  mandatory exact-tag jobs passed in [run 40227314485](https://github.com/DocumentDrivenDX/arras/actions/runs/40227314485).
- [x] All twelve actual Lakebase cases and independent owned cleanup pass; the
  original safe receipt, fixture/harness identities, review and support limits
  are linked from the integration plan and release notes.
- [x] Reusable ordinary identity setup and private credential-reference custody
  are documented separately from disposable database cleanup, so routine future
  campaigns use that setup without repeating admin provisioning.
- [x] Final source/control/service-evidence review and exact-commit CI pass;
  PR 9 is merged and the version-matching immutable release workflow passes in
  [run 40227314485](https://github.com/DocumentDrivenDX/arras/actions/runs/40227314485).
- [x] Public anonymous download and installed-consumer repeats pass on the
  published bytes. The release contains 17 assets (16 SHA256SUMS entries), with
  schema-v2 evidence and public UMF 139/139 reference plus 139/139 fresh-Registry
  matches, six base and ten extra controls, zero skips and passing cleanup.
  Optional PyPI/npm publisher jobs were skipped as configured; GitHub assets
  remain the delivery route.

The human authorized resumption of the owned-database recovery qualification
on 2026-10-25. Controller preflight passed 6/6 checks and collector controls
passed 8/8; these controls are not acceptance evidence. The initial post-resume
2d baseline remains a 5 passed / 1 failed journal-binding diagnostic; preserve
it as failed history. After the bounded partition-ancestry repair, a fresh
baseline at source `20db67822b20c822ee91c6823a3fe73ebc3ae932` passed 6/6, with
original cleanup, fresh independent audit (`560f5c20…`), process census
(`8da9…`) and custody handback (`9a599e22…`) passing. These are supplied
receipt prefixes, not full digests; full source-bound records are retained in
[baseline-20db-passed-20261025](../04-build/evidence/truss050-adoption-20261024/baseline-20db-passed-20261025/).
D11 remains 10 passed / 2 failed / 0 blocked; D12 remains a 5 passed / 1 failed
baseline diagnostic / 0 blocked, with its managed gate not run. Original
cleanup, independent audits and custody handbacks passed for both historical
runs, whose [failed-run records](../04-build/evidence/truss050-adoption-20261024/full-managed-d11-failed/)
and [baseline diagnostic records](../04-build/evidence/truss050-adoption-20261024/baseline-six-diagnostic/)
remain historical failed evidence. The separate original full twelve-case
campaign on the same exact wheel passed 12/12 with zero failures or blocked
cases; original cleanup, independent audit, process census and custody handback
passed. See [full-managed-20db-passed-20261025](../04-build/evidence/truss050-adoption-20261024/full-managed-20db-passed-20261025/).
The supplemental scoped process census found all three known groups absent and
no exact owned-script matches or inspection denials. The direct supervisor PGID
was not captured and no forced-cleanup claim is made; see the retained
[projection](../04-build/evidence/truss050-adoption-20261024/full-managed-20db-passed-20261025/root-process-census-supplement.public-projection.json).
The [current Mac records](../04-build/evidence/truss050-adoption-20261024/fresh-macos-40221099126/) retain exact source/cohort/payload bindings. PR 9 merged as `243f1ebaf8b32beb0abc30d0d4fdcd9dd7b5ea92`, and [v0.6.1](https://github.com/DocumentDrivenDX/arras/releases/tag/v0.6.1) plus its mandatory public-download and installed-consumer repeats passed in [release run 40227314485](https://github.com/DocumentDrivenDX/arras/actions/runs/40227314485). The separately authorized PyPI/npm deferral remains in force.

## Rollout Stages

| Stage | Action | Exit condition |
| --- | --- | --- |
| Local qualification | Complete all seam implementations and Sol reviews; collect final exact-cohort receipts. | No unimplemented required row or blocking review finding. |
| Public source | Commit the coordinated frozen source and push the authorized release candidate. | Exact commit CI passes, including all required native/UI/downstream jobs. |
| Tagged build | Create and push the version-matching tag; observe mandatory release jobs. | Exact bundle built and all prepublication checks pass. |
| GitHub release | Workflow attaches verified artifacts and receipt. | Fresh public download/installed-consumer checks pass. |
| Registry delivery | Automatically publish exact qualified assets through registry OIDC trust after all release/public-download gates pass. | Registry bytes match the qualified digests, fresh isolated installs pass, and a separate receipt records each registry outcome. Missing access or conflicting existing bytes fails publication. |

## Recorded 0.5.1 acceptance

- [x] Generic eight-seam implementation, catalog, contracts and Sol reviews.
- [x] Exact source/native/build/SDK/installed-native/UI/assembly gates in publication
  run `39879533273`; sixteen immutable GitHub assets published.
- [x] Original trusted stage/SUMS/aggregate pinned and independently reviewed.
- [x] Fixed reusable installed consumer and complete anonymous asset/distribution/
  doctor/example/themed Linux 205 checks in verification run `39883764998`.
- [x] Final independent receipt/provenance/cohort review and tag recheck.
- [x] Registry deferral recorded under the human's instruction; GitHub assets are
  the supported delivery route, with no PyPI/npm publication claim.

[Final evidence](../04-build/evidence/arras-0.5.1-public-verification-review-20261023.json)
keeps original publication and supplemental verification distinct. All runtime
and platform limits remain in the design matrix; this closeout changes no assets.

## Recorded 0.6.0 candidate acceptance

- [x] Source, UI, installed UMF, doctor, fresh example, native and packed-browser candidate gates pass on their named local cohorts; details and limits are recorded in the integration plan.
- [x] PR 7 main CI run `39960762557` passes all four checks.
- [x] Immutable tag `v0.6.0` was published from source `8f8097ab0bebb3f8eda6d76568c62ee5e84d33ef` (tag object `686886c7ed2425e4e9e496b70fcc39272b8a52d9`); [release run `39963352238`](https://github.com/DocumentDrivenDX/arras/actions/runs/39963352238) passed all required jobs, including Linux native, installed consumer and anonymous verification.
- [x] The public [GitHub release](https://github.com/DocumentDrivenDX/arras/releases/tag/v0.6.0) contains 17 assets: 16 checksum-listed payloads plus `SHA256SUMS`; the public wheel, sdist, npm archive, sum file, aggregate and UMF receipt hashes are recorded in the release notes.
- [x] Exact public-download UMF repeat passed on the published wheel: 139/139 reference cases, 139/139 fresh-empty Registry cases, zero skips, six base and ten extra-enabled controls, with cleanup. Public doctor, fresh example, Linux nonvisual UI and native adapter jobs also passed in the named release environment.
- [x] Final independent public review completed; the raw [public-repeat review](../04-build/evidence/arras-0.6.0-release-20261023/public-repeat-review.json) has SHA-256 `1d38a416e3b161c2d769ca749267c57b56614f9d97a0cba28ff5a5e8ffef814d`. The [consolidated closeout manifest](../04-build/evidence/arras-0.6.0-public-verification-review-20261023.json) indexes the release proof and supporting reviews.
- [x] The release claims no value/constraint execution, canonical action, general native metadata, Ashlar or managed deployment support.

Source commit: `8f8097ab0bebb3f8eda6d76568c62ee5e84d33ef`; immutable tag object:
`686886c7ed2425e4e9e496b70fcc39272b8a52d9`. The published wheel SHA-256 is
`c3ace4273f483fbf41af3f70a71a65a6d0f9c963c5b1c71eb79c5bf1bd299a3d`, the sdist
is `1e533d666b664cc99b1d3b8dedc8120e825988e7d997d69189a3507bc9e53ce2`, and the
npm archive is `73819275d2b784295e471c8b81fe251acb127b274cc9567946cdce9824ef9a71`.
Local Mac component hashes remain scoped component evidence; the independent
payload comparison does not claim macOS execution of the Linux release wheel.
Preserve the completed 0.5.1 receipts and acceptance below unchanged.

## Rollback

This artifact release does not install or migrate a live customer database. A
failed build or gate must not replace an existing release artifact. Stop before
tagging on any source/native/theme/consumer failure. Do not reuse a published
version/tag with different bytes; fix forward with a new version if a released
artifact is defective. Downstreams retain their prior pin and owned data until
the replacement passes their deployment checks. Native database migration and
credential recovery follow the owning provider's separately qualified procedures.

Any checksum mismatch, missing mandatory job, unreviewed source change, policy
bypass or installed-consumer failure blocks publication. Registry access failure
alone may be deferred under the human's instruction, with no claim of registry
delivery. Final support limits and per-seam changes belong in release notes only
after the actual cohort is known.

## Recovering an unpublished tag

An orchestration-only failure may use the reviewed default-branch release driver
with an explicit immutable target tag and expected source commit. Verify driver
CI/review and target identity, then run every mandatory gate freshly in the new
current run. All payload and downstream checkouts use the validated source commit;
record the separate driver identity. Recheck the remote tag before publication.
Never move the tag, reuse failed-run receipts or overwrite published bytes.

## Recovering postpublication verification

If immutable assets are already published and a consumer orchestration step fails,
use the reviewed read-only verification driver. Pin the original publication run
and driver, source/tag, wheel, trusted-stage sum file and aggregate. Validate its
successful prepublication jobs and trusted stage, then run the fixed installed
consumer and complete anonymous public-download consumers in one new verification
run. Record both runs and tag rechecks. Preserve every public asset and original
receipt; no build/reassembly/publication/registry step is part of this recovery.

This recovery path currently supports only an original `workflow_dispatch`
publication dispatched from the default branch whose original run concluded
with failure, as enforced by `verify_publication_provenance.py`. The normal
tag-push publication and anonymous verification flow is unaffected. If recovery
is needed for a push-triggered publication, first review and adapt the
default-branch verification driver to accept that original event identity; the
existing helper fails closed for it.
Closure requires the new verification result and independent public-bundle review.


### 0.6.2 qualified wheel — 2026-10-26

The selected wheel is `82cd5ef7e7284ded7bb7af98934fe0c3f6840450948205e3430d99ff0478f176`.
CI `40244842788` passed all five required jobs. The fresh Mac and actual full12
WAN gates, original cleanup, independent audit, archive retention, actual
process/group absence and custody handback passed on those exact bytes. The
[retained qualification index](evidence/registry-publication-20261025/qualification-062-index.json)
records the qualified versions, unchanged declared limits and failed no-effect
history. Official UMF installed admission and Twine metadata checks also passed.
The release workflow's strict wheel guard binds these bytes; any rebuild
mismatch blocks publication. Exact-tag Release/public-download and registry
OIDC/byte/install receipts remain distinct required controls, recorded with the
[versioned release](https://github.com/DocumentDrivenDX/arras/releases/tag/v0.6.2).
