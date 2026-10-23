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

GitHub Release assets are mandatory. Publish to real PyPI/npm only through
existing configured access; the human explicitly permits deferring those uploads
if access cannot be found. Do not advertise an unavailable registry install.

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
- Standard GitHub authentication and push access are verified. Repository release
  permissions are sufficient; optional registry variables remain off unless the
  matching publisher is configured. Local npm authentication returned `E401`;
  no local PyPI configuration was found. Organization-secret inspection is not
  permitted by the current account scope. No credential values are recorded.
- Validate explicit consumer configuration and identity-conflict controls. The
  offline doctor reads only declared inputs, never ambient tokens or live hosts.

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
| Tag and assets | Mandatory exact-tag source/native/UI/downstream/build gates precede GitHub publication. Attach wheel, sdist, wheel-carried npm tarball, receipt and `SHA256SUMS`; optional publishers use those same verified bytes. |
| Downloaded release | Download the public release assets into a new directory, verify digests and repeat installed consumer/skeleton/doctor checks. A local build alone does not pass this gate. |
| Official UMF qualification (0.6.0+) | The exact final wheel passes the installed admission/metadata gate with pinned official UMF 0.10.0: all 139 ordered reference and separate fresh-empty production Registry comparisons, six base and ten extra-enabled controls, zero skips, and verified cleanup. Repeat against the exact public-download wheel in a fresh environment; retain distinct receipts. The 0.5.1 candidate receipt is historical and cannot close this gate. |
| Public assembly (0.6.0+) | Use release-evidence schema v2: include the mandatory safe UMF receipt projection as asset 17, bind it to the exact wheel, and repeat UMF qualification after public download. Keep v1/sixteen-asset evidence for historical releases unchanged. |
| Truss 0.0.49 adoption / PR 9 | Before merge or tagging, retain and independently review the original fresh-installed exact-cohort proof and full actual Lakebase receipt: LB-ADMISSION, LB-INSTALL, LB-PERSON, LB-CUSTODY, LB-SETTLEMENT, LB-ACL and MP-01–06 all pass, with independent owned-cleanup confirmation. Bind the managed receipt to the executed harness/fixture hashes, actual installed Truss archive/manifests and qualified Arras wheel. Document exact source correspondence to the release artifact; source-local checks, bootstrap evidence, partial schedules and earlier candidate artifacts cannot close this gate. |

## PR 9 / 0.6.1 execution

- [ ] Corrected final-version artifacts pass fresh installation, native, doctor,
  distribution, official UMF and downstream UI gates on their recorded cohorts.
- [ ] All twelve actual Lakebase cases and independent owned cleanup pass; the
  original safe receipt, fixture/harness identities, review and support limits
  are linked from the integration plan and release notes.
- [ ] Reusable ordinary identity setup and private credential-reference custody
  are documented separately from disposable database cleanup, so routine future
  campaigns use that setup without repeating admin provisioning.
- [ ] Final source/control/service-evidence review and exact-commit CI pass;
  PR 9 is merged and the version-matching immutable release workflow passes.
- [ ] Public anonymous download and installed-consumer repeats pass on the
  published bytes; registry delivery or the authorized deferral is recorded.

## Rollout Stages

| Stage | Action | Exit condition |
| --- | --- | --- |
| Local qualification | Complete all seam implementations and Sol reviews; collect final exact-cohort receipts. | No unimplemented required row or blocking review finding. |
| Public source | Commit the coordinated frozen source and push the authorized release candidate. | Exact commit CI passes, including all required native/UI/downstream jobs. |
| Tagged build | Create and push the version-matching tag; observe mandatory release jobs. | Exact bundle built and all prepublication checks pass. |
| GitHub release | Workflow attaches verified artifacts and receipt. | Fresh public download/installed-consumer checks pass. |
| Registry delivery | Use existing PyPI/npm access if available; otherwise record the explicit deferral. | Successful registry installs are qualified separately, or notes clearly name GitHub assets as the delivery route. |

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
