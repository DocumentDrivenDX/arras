---
ddx:
  id: arras.release-repair-072
  type: deployment-checklist
  activity: deploy
  authoring:
    home: repo
  links:
    - id: arras.release-checklist
      kind: informed_by
    - id: CONTRACT-005
      kind: informed_by
    - id: ADR-027
      kind: informed_by
    - id: TP-001
      kind: informed_by
---

# Arras successor release repair

## Release

**Decision:** prepare NEW0.7.2 source, fully qualify its exact versioned artifacts
and release consumers BEFORE tagging, then normal reviewed merge, immutable
v0.7.2 tag, mandatory tag/public-download gates and trusted PyPI/npm publication.
Recheck collisions immediately before version freeze and tag; choose the next
free patch if another owner publishes/reserves0.7.2. Never move/delete v0.7.1,
change its source, replace its selected checksum or relabel failed receipts.

E owns implementation in `/private/tmp/arras-final-candidate-isolated`; only this
new uniquely named planning document is written by Sol. Existing dirty files,
producer packets, checklist, runtime/workflows/tests/pins and primary checkout
are untouched. Human authorization already includes repair/merge/tag/publish;
there is no additional approval or permission gap. Sol reviews the concrete
repair/provenance packet via coordinator before E merges/tags.

Authority read: .helix.yml, HELIX README, project principles,
[deployment checklist](deployment-checklist.md), CONTRACT-005, ADR-027,
release/registry/public-verification workflows, tools/verify_distribution.py,
tools/verify_doctor.py, tools/verify_extension_host.py, current version selectors
and `/private/tmp/arras-embedder-release-execution-checklist.md`.

### Actual remote state — read 2026-11-03 around02:18 UTC

- PR56 merged at9e9beeaa9841be29b81bdac40e7b18e5c31fbfb3. [PR57](https://github.com/DocumentDrivenDX/arras/pull/57)
  is merged; remote main is0f7817eb15ee73d1d62eb75c7fe87caa3aa1aa65.
- v0.7.1 annotated tag object60021573c9b62c362c3ddb5686ab30647c597d7e
  peels to that exact main commit. Preserve it even though unpublished.
- GitHub releases/tags/v0.7.1 returns404: NO GitHub Release/assets for0.7.1.
  Latest published GitHub release is immutable v0.7.0 with18 assets. PyPI arras
  and scoped npm @documentdrivendx/arras-ui both latest0.7.0; neither registry has
  0.7.1 or0.7.2. Git ref v0.7.2 also returns404. Thus0.7.2 is available NOW.
- [Tag run41561152998](https://github.com/DocumentDrivenDX/arras/actions/runs/41561152998)
  failed its build job125674826451 at **Require the exact wheel selected for this
  release cohort**. Native job125671857973 succeeded; downstream release/UI/
  installed/public jobs skipped. Registry run41562876034 skipped. Do not describe
  this as a successful released0.7.1 or as a tag-run doctor failure.
- [Producer diagnostic41563181620](https://github.com/DocumentDrivenDX/arras/actions/runs/41563181620)
  succeeded. Artifact13197137663 digest
  e6007327567e4e46811cc1de2762b5a2bb75980fd6e7368f5d9fa8228d5ebe93.
  Its later diagnostic [41563653335](https://github.com/DocumentDrivenDX/arras/actions/runs/41563653335)
  failed job125679871874 at actual-Linux-wheel fresh installed qualification.
  The local source-bound packet records the additional genuine conflict:
  tagged example-extension-host requires arras==0.7.0 alongside candidate0.7.1.
- Diagnostic PR58 remains OPEN/unmerged, latest observed head
  557ae66240860c5c5bb759fce466f9f29bea2190. It is evidence-producing, not a
  reviewed repair or release. PR59 was absent at observation. Recheck live state;
  local already-dirty0.7.2 edits are work in progress, not remotely merged.

GitHub connector returned404 for0.7.1 Release; read-only authorized GitHub API
confirmed tag refs/jobs/assets, and public PyPI/npm metadata supplied registry
state. Sandbox network failure was not treated as an upstream authority outage.

### Two distinct defects

1. Exact-wheel guard correctly rejected Linux wheel
   c999729cd1ae96df5e5fd40b608faeefeb89d58f4f8f3eb4ac55e7120586ce09 against
   selected Mac wheel1ef8396a487cf737b81918df6f792d57474dadaa397ae9c7729a847defa5100f.
   [Producer correspondence](evidence/arras071-aborted-20261103/producer-correspondence.json)
   proves188 wheel members with only carried gzip npm archive/RECORD differences;
   decompressed npm tar bytes, order/metadata and323 members match exactly.
   Both tested Node24/26 producers reproduced the Linux bytes. Do NOT claim Node
   major version alone explains or fixes this platform/archive-byte difference.
2. Tagged extension-host dependency and doctor expectations remained0.7.0. The
   candidate resolver/doctor/fresh downstream gate is required to catch this.
   Fix ACTIVE source/version coupling, not dependency checks. Driver-only recovery
   of the immutable0.7.1 source is not selected because the delivered source
   consumer declaration itself must change. New source receives a new patch tag.

## Before deploy — repair closure

E completes a narrowly reviewed release repair. Existing work-in-progress edits
are evaluated by these criteria, not accepted wholesale. Preserve immutable old
pins/history; no global string replacement of0.7.0/0.7.1.

| Active path / surface | Required repair / invariant |
| --- | --- |
| pyproject.toml and uv.lock | Root project0.7.2 and root editable lock entry agree; dependency closure stays explicitly qualified UMF0.10.5/Truss0.0.50/Weft0.4.51. Review every actual lock delta; no incidental upstream adoption. |
| examples/extension_host/pyproject.toml | Exact arras==0.7.2, required normal resolver installation alongside the exact candidate wheel. Example's OWN0.1.0 version is independent and need not change. |
| examples/extension_host/doctor-request.json | Arras and scoped carried UI expected packages0.7.2. Preserve every contract/export/provider/resource/negative expectation and no-secret/offline rule. |
| src/arras/public-api.json and established derived catalogs | Distribution version/package metadata matches0.7.2; export/resource/contract inventories retain reviewed behavior. Regenerate through existing ownership path and review diff; no arbitrary hash refresh. |
| ui/scripts/pack-wheel.ts, pack-manifest.ts, runtime/page asset builder and actual outputs | Derive published scoped npm version from root pyproject as designed, create exactly documentdrivendx-arras-ui-0.7.2.tgz and matching runtime/page/package manifests. Source ui/package.json is PRIVATE arras-ui0.1.0, intentionally independent; do not blindly bump it or its lockfile/transitive version strings. Rebuild actual generated assets, do not rename0.7.1 outputs. |
| .github/workflows/release.yml and tests/test_release_workflow_binding.py | Add explicit0.7.2 exact-wheel digest only AFTER actual canonical Linux artifact qualification. Retain historical checksum entries, matching/missing/changed byte refusals and unknown-version failure. Test the new selector case, not just old versions. |
| .github/scripts/verify_pypi_extras.py and tests/test_pypi_extras.py | Add deliberate0.7.2 qualified cohort entry, preserve historical mappings; positive platform closures and cross-cohort/wrong-hash refusals. Next unqualified version0.7.3 still refuses. Historical0.7.0 fixture constants stay historical. |
| tools/verify_doctor.py, tools/verify_extension_host.py, .github/workflows/downstream.yml, verify-published-release.yml and publish-registries.yml | Audit ALL actual source/example/request/input paths used by built, fresh-dependency, public-download and registry runs. Every ACTIVE selected input resolves candidate identity; do not alter historical closed recovery origins. No --no-deps, ignore-installed, constraint suppression, weakened doctor, source-example substitution or assertion deletion. |
| .github/workflows/candidate-package.yml (current new dirty file) | Make complete PRE-TAG consumer/coupling gate, triggered by all relevant version/catalog/build/consumer/selector/tool changes or explicitly dispatched on exact candidate. Current narrow path list alone misses selectors, catalog and UI producer changes. It is not a substitute for mandatory tag gates. |
| CHANGELOG.md / new successor release evidence | Explain unpublished0.7.1 failure and bounded repair; preserve all old source, checksums, diagnostics and receipts. No success backfill into historical evidence. |

Audit active exact-version consumers by parsed metadata plus scoped search over
pyproject/locks, examples, tools, src catalogs, workflow inputs and release
selectors. Classify every retained old match as deliberate historical fixture,
closed recovery origin or unrelated package version. Keep this classification
reviewable; an rg search with zero old strings is not the acceptance criterion.

## Validation gates

| Gate | Must pass before | Concrete acceptance / negative controls |
| --- | --- | --- |
| AR-01 active coupling | Candidate build/merge | One root version drives Python metadata, active example Requires-Dist, doctor Arras/UI expectations, derived catalog, staged scoped npm/runtime/page manifests, artifact names and selected cohort/hash case. Deliberately revert JUST example pin or either doctor package expectation: pre-tag gate fails. Preserve unrelated expectations. |
| AR-02 canonical producer | Digest selection | Canonical hosted Linux producer records exact OS/arch/Python/uv/Node/npm/build inputs. Build0.7.2 wheel/sdist/carried npm twice from clean exact source using the SAME selected producer; source/sdist rebuild and full archive/payload/metadata comparison pass. Freeze actual0.7.2 wheel and npm digests; neither0.7.1 Mac nor Linux digest is a successor pin. Missing/changed bytes refuse. |
| AR-03 full PRE-TAG release consumer | Merge/tag | Run the commands below on actual0.7.2 artifacts, fresh resolver-built extension host and installed doctor positive/negative controls. Installed origins outside checkout, pip check, selected candidate remains installed, independent rebuilt wheel comparison, public catalog, installed CLI/devhost page and carried npm consumers all pass. No native/scale campaign is needed for this bounded packaging gate. |
| AR-04 source/payload impact | Reuse approval | Sol independently reviews complete delta and member correspondence; only proven unchanged runtime/native/UI semantic inputs reuse prior narrowly scoped observations. Versioned metadata/archive differences are recorded; no receipt's original version/hash is rewritten. Any changed runtime/native/consumer semantics gets affected tests. |
| AR-05 reviewed merge + exact tag | GitHub publication | Required repair PR checks and exact-head Sol PASS; normal merge; final merged tree/candidate archive equality; live tag/PyPI/npm collision recheck; immutable v0.7.2 tag on exact matching source. Run ALL mandatory tag source/native/UI/installed SDK/actions/downstream/build/asset/provenance jobs through existing workflow. No skip-through diagnostic driver. |
| AR-06 public bundle | Registry upload | Anonymous GitHub download of exact wheel/sdist/npm/evidence/SHA256SUMS, strict complete asset inventory/provenance and actual installed doctor/fresh extension-host/SDK/UI/downstream repeats. Failed mandatory public gate holds both registries. |
| AR-07 registries/consumers | Delivery close | Trusted publishers upload those EXACT verified bytes, no rebuild. Independently fetch PyPI wheel/sdist and npm tarball; compare archive hashes/integrity/provenance and complete payload. Public-only fresh Python3.11 Linux x86_64 AND macOS arm64 extras installs, pip check, origins/no direct URLs, doctor, UMF smoke and actual embedder/alias features; fresh scoped npm install/inventory/export consumer. Cleanup receipts required. |

### AR-03 command and coupling contract

Use existing build path `npm ci && npm run build:wheel` in ui, then `uv build
--wheel --sdist`. On frozen candidate run existing tools, with actual artifact
paths and fresh output directories:

```text
python tools/verify_distribution.py --output <distribution-receipt> <wheel> <sdist>
uv run --no-sync python tools/verify_doctor.py --wheel <wheel> --output-json <doctor-receipt>
python tools/verify_extension_host.py --wheel <wheel> --output-json <fresh-host-receipt> --fresh-dependencies
uv run --no-sync python tools/verify_umf_admission.py --wheel <wheel> --output-json <sdk-receipt>
```

Also run focused public catalog/content/cohort/release-binding tests and the two
existing ARRAS_WHEEL installed CLI/devhost tests. The fresh extension host must
be built from the ACTIVE example with normal declared dependencies and installed
alongside exact candidate0.7.2. Before publication, candidate wheel is an explicit
local input; all other dependencies retain declared public/qualified origins.
Do not pretend prepublication pip install arras==0.7.2 from PyPI can succeed.
After publication use public PyPI ONLY, empty cache/config and no local wheelhouse.

Extend pre-tag gate with controlled mismatches of root version, example exact
pin, each doctor expected package, catalog/staged npm version, lock root version,
missing/changed selected wheel, unknown selector version and cross-release SDK
pin. Each must fail for its specific mismatch, not missing tool/network error.
No blanket version wildcard in place of explicit qualified cohort. All doctor
contract/export/resource/security negatives stay active. Record actual case IDs,
inputs, resolved versions and failure classifications, not a syntax-only pass.

Run AR-01/03 on the FINAL merged/source tree before creating a tag. A late change
to examples, workflow/tooling, lock, catalog or packaged bytes invalidates affected
pre-tag proof. If only a nonpackaged hash guard is added after candidate build,
prove COMPLETE payload equality and repeat selector/coupling controls on that
exact head. Rebuild sdist and run its required consumer checks because tooling/
examples/tests may be inside it even if wheel bytes remain unchanged.

### Efficient evidence reuse and review packet

Prior source3832/3840, native focused9, tag-native203 and UI1483/206/browser
observations remain bound to their actual source/artifacts/platforms. No new Mac
native or Lakebase/full-scale matrix is selected merely because the patch version
changes. Mandatory exact-tag jobs still execute; do not repeat those same broad
campaigns separately pre-tag without a material source/closure change.

For each reused observation, E supplies original receipt/run/hash, original and
new source closure, all relevant runtime/native/UI files and dependency hashes,
full wheel member map, decompressed npm tar/member order/metadata comparison and
an explicit allowlist of version-only field deltas. Compare exact bytes FIRST;
classify differences SECOND. Do not normalize away unexpected JS/CSS, export,
asset content, behavior, contract or dependency changes. New0.7.2 npm package.json,
page/runtime version fields, archive name and metadata legitimately change and
need fresh build/consumer proof. Prior1ef… or c999… qualification is supporting
unchanged-behavior evidence, never exact0.7.2 installed/public-byte evidence.

Sol reviews AR-01–04 packet and concrete repair diff; candidate-package workflow
must actually finish the previously missed doctor/fresh-host checks. Source-only
CI, successful build portion of a failed diagnostic job, or a renamed receipt
cannot authorize tagging. Existing source-bound aborted evidence is preserved
unchanged and cited separately. Diagnostic PR58 does not merge wholesale; only
explicitly reviewed reusable tooling may enter the repair.

## Rollout stages

1. E finishes bounded source/tool/selector repairs in its current isolated
   checkout; no other worker/primary writes. Select canonical Linux producer,
   collect actual0.7.2 artifacts, complete AR-01–04 and independent Sol review.
2. Merge reviewed repair normally; confirm final tree/source/artifact and
   pre-tag gates, recheck live version availability. Tag next free patch exactly.
3. Complete mandatory exact-tag workflow and anonymous public bundle verification.
   Publish same assets through existing trusted registry workflows; no newly
   inferred registry authority, recovery-origin widening or manual credential path.
4. Finish AR-07 independent fresh public consumers, feature proofs and confirmed
   cleanup, then record successor release closure with actual versions/digests.

## Rollback and stop conditions

A failed gate holds publication; the public working release remains0.7.0 until a
successor completes. Preserve v0.7.1 and all existing published assets/checksums.
Never retag, delete/re-upload or bless a mismatched hash. If0.7.2 becomes occupied,
select the next free patch and rerun affected version-coupled gates BEFORE tag.
If a registry upload partially succeeds, preserve its immutable bytes and reconcile
only against matching expected assets using existing publisher controls; do not
rebuild, replace or claim both registries complete prematurely.

Unknown source/payload differences, changed dependency closure, failed resolver/
doctor/fresh host, missing mandatory exact-tag/public job or uncertain cleanup is
a stop for the affected gate. Ordinary correction remains already authorized;
no human approval is needed merely to perform this plan. Genuine external OIDC/
registry permission failure must be reported with the actual failed operation;
current read access is working and does not establish a publisher failure.

## Planning closeout

Only this deployment-plan artifact was authored. No tests/builds/merges/tags/
publications were executed; no implementation file, existing release document or
E evidence packet was edited. Current0.7.2 dirty source is not reviewed by writing
this plan. Full release remains open until AR-01–07 and exact final public source/
artifact/consumer/cleanup evidence pass.
