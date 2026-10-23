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
---

# Arras artifact release checklist

## Release

The immutable 0.5.1 release history below remains complete. The current candidate
package version is `0.6.0`; version selection is not a tag or publication claim.
Its selected change is bounded official-UMF admission and read-only memory
metadata projection. The [integration plan](../04-build/arras-integration-plan-20261022.md)
tracks the candidate scope and its remaining release gates.

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

## 0.6.0 candidate gates

- [ ] Exact final wheel passes the official UMF installed qualification and zero-skip controls.
- [ ] Public download of that exact wheel passes the same gate in a new environment.
- [ ] Schema-v2 release evidence contains the mandatory UMF projection in the 17-asset inventory and binds the raw receipt and wheel.
- [ ] No value/constraint execution, canonical action, native metadata, UI or Ashlar support is claimed from this admission/metadata profile.

The completed 0.5.1 candidate receipt is historical evidence only. It does not
qualify the 0.6.0 wheel or public download.

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
Closure requires the new verification result and independent public-bundle review.
