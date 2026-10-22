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

First public Arras Python/UI artifact release from the reviewed integration
cohort. The working package version is `0.5.1`; version selection is not a tag or
publication claim. A 2026-10-22 GitHub preflight found no existing Arras tags or
releases. The [integration plan](../04-build/arras-integration-plan-20261022.md)
tracks all eight required seams and named implementation/review owners.

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

## Rollout Stages

| Stage | Action | Exit condition |
| --- | --- | --- |
| Local qualification | Complete all seam implementations and Sol reviews; collect final exact-cohort receipts. | No unimplemented required row or blocking review finding. |
| Public source | Commit the coordinated frozen source and push the authorized release candidate. | Exact commit CI passes, including all required native/UI/downstream jobs. |
| Tagged build | Create and push the version-matching tag; observe mandatory release jobs. | Exact bundle built and all prepublication checks pass. |
| GitHub release | Workflow attaches verified artifacts and receipt. | Fresh public download/installed-consumer checks pass. |
| Registry delivery | Use existing PyPI/npm access if available; otherwise record the explicit deferral. | Successful registry installs are qualified separately, or notes clearly name GitHub assets as the delivery route. |

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
