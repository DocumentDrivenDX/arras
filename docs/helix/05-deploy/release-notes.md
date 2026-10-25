---
ddx:
  id: arras.release-notes
  type: release-notes
  activity: deploy
  status: draft
  authoring:
    home: repo
  links:
    - id: arras.release-checklist
      kind: informed_by
    - id: arras.downstream-extensibility
      kind: informed_by
    - id: PLAN-ARRAS-INTEGRATION-20261022
      kind: informed_by
---

# Arras release notes

## 0.6.1 published

This release selects public Truss 0.0.50 and preserves Weft 0.4.51 and official UMF
core 0.10.0. Fresh installation accepts an explicit immutable
`tolerated_grantees` tuple; reconnect verifies stored policy without widening it.
The existing metadata-only profile, runtime support boundaries and historical
0.6.0 release artifacts remain unchanged.

The public Truss 0.0.50 wheel is pinned by SHA-256
`7b0483bb0c624c98515cf38ec30bbbf1ca43c1250e8880e5d00d520b4b7eec00`, from
source `a687d0a226dad5745cbd909377bf99c7c1cddc66`. Its native runtime manifest
remains `truss-catalog-runtime/0.74-candidate` with SHA-256
`288801f7177338328441b5d3ce9328af31740ebf513f04ea45e30ae316a9f3a4`; migration
manifest `4c6baf0282e3d0b5492f070c9c07d89ff0c9a819e748f3820f60b11c1f51c7aa`
retains the prior public 0.0.49 manifest unchanged. The additive
[source-binding record](../04-build/evidence/truss050-adoption-20261024/extension-source-binding.json)
documents wheel/source correspondence and references the source-only Truss 0.0.50
dependency review. That review found no newly introduced extension dependency;
the archive comparison matched 50 native SQL files and five JSON resources. The
source-binding record is not a PostgreSQL observation or managed acceptance;
it reports Lakebase acceptance as `not_run` and is distinct from the exact-tag
Truss release result. Truss v0.0.50 tag run
[`40068606364`](https://github.com/DocumentDrivenDX/truss/actions/runs/40068606364)
passed its Linux release gates, including 107 migration tests, 62 HF cases and
174 managed-grant tests. Its selected small functional workload also passed; it
does not establish a general performance result or Arras Lakebase acceptance.

The exact canonical Arras 0.6.1 wheel SHA-256 is
`259e16c7d4c8f6c56d9930ee5f16e74c4ab6b2c8a3ecffdb7d8b306c77b60f18`.
At source `2d1bc7e34af7499d5f4f582d4ee41e0d772920cc`, CI run
[`40119390075`](https://github.com/DocumentDrivenDX/arras/actions/runs/40119390075)
passed all five jobs. Its [fresh-installed Mac campaign](../04-build/evidence/truss050-adoption-20261024/fresh-macos-40119390075/)
on macOS arm64 / CPython 3.11.9 completed 72 applicable cases: 64 passes and
eight unchanged declared limits, with seven replica-only cases inapplicable.
Exact installed-payload correspondence and cleanup passed. No system-wide
dynamic-link audit or execution of forced process-group cleanup is claimed.

The human authorized resumption of the owned-database recovery qualification
on 2026-10-25. Controller preflight passed 6/6 checks and collector controls
passed 8/8; these are controls, not acceptance evidence. The first post-resume
2d baseline remains a 5/6 journal-binding failure. After the bounded
partition-ancestry repair, the fresh source-20db baseline passed 6/6 with
original cleanup, independent audit (`560f5c20…`), process census
(`8da9…`) and custody handback (`9a599e22…`) also passing. The source-bound records are retained in
[baseline-20db-passed-20261025](../04-build/evidence/truss050-adoption-20261024/baseline-20db-passed-20261025/). CI run `40221099126` source-20db Mac run passed 64 cases, retained eight unchanged
limits and skipped seven inapplicable replica cases; native-wheel hashes,
172-file payload parity and cleanup passed. The full original twelve-case
Lakebase campaign on that wheel passed 12/12 with zero failures or blocked cases;
original cleanup, independent audit, process census and custody handback passed.
Its source-bound records are in [full-managed-20db-passed-20261025](../04-build/evidence/truss050-adoption-20261024/full-managed-20db-passed-20261025/).
The scoped supplemental census records all three known groups absent, zero
owned-script matches and zero denials. The direct supervisor PGID was not
captured; no forced-cleanup claim is made. Historical D11/D12 and the initial
2d failure remain preserved as failed evidence. The final PR 9 source is
`243f1ebaf8b32beb0abc30d0d4fdcd9dd7b5ea92` (tree
`9ee467d942ba7440d6adaa9b891b8f00aa2d8c1c`), published as annotated tag
`v0.6.1` (tag object `99609317f1cfc95a2e8e3768f2481910dcf42e23`). The exact-tag
[release workflow](https://github.com/DocumentDrivenDX/arras/actions/runs/40227314485) passed all ten mandatory jobs, including
release build/assembly, installed downstream and anonymous public-download
qualification. The [GitHub release](https://github.com/DocumentDrivenDX/arras/releases/tag/v0.6.1) carries the exact canonical
wheel; public assets and the completed public repeat are described below.

The historical [full WAN campaign, D11](../04-build/evidence/truss050-adoption-20261024/full-managed-d11-failed/),
finished 10 passed / 2 failed; the separate [D12 baseline diagnostic](../04-build/evidence/truss050-adoption-20261024/baseline-six-diagnostic/)
finished 5 passed / 1 failed and did not run the managed gate. Those failed
results remain historical and do not replace the completed 20db campaign. The already-provisioned
ordinary actor setup is reusable; no VM was created or required for these WAN
runs. Credential renewal remains with the user or designated workspace
credential administrator. Historical 0.0.49 receipts retain their original scope.
Both complete campaigns bind to the same canonical Arras wheel SHA-256
`259e16c7d4c8f6c56d9930ee5f16e74c4ab6b2c8a3ecffdb7d8b306c77b60f18`; any future wheel-byte change requires both campaigns rebound and rerun.

The earlier PR 9 candidate with 0.6.0 package metadata passed fresh installed
native conformance (64 cases and eight unchanged declared limits), artifact
parity, doctor and official UMF checks. Those receipts retain their original wheel
identity and remain historical. The 0.6.1 public bundle has 17 assets (16 listed
in `SHA256SUMS`), release-evidence schema v2 and an exact wheel SHA-256 of
`259e16c7d4c8f6c56d9930ee5f16e74c4ab6b2c8a3ecffdb7d8b306c77b60f18`. The anonymous public-download qualification verified every asset against
the exact assembled release stage and confirmed that the npm tarball matches the
wheel-carried bytes. On the downloaded wheel, the public UMF repeat matched all
139 ordered reference and 139 fresh-empty Registry cases, with six base and ten
extra-enabled controls, zero skips and passing cleanup. The public doctor passed
20 cases; the installed extension consumer passed four tests and 72 memory-corpus
cases. The public Linux theme suite passed all 205 nonvisual checks with no
unexpected skips; visual checks were inapplicable on Linux. All results are
bounded to the named wheel and recorded cohorts. Release run `40227314485` passed
all mandatory jobs. Optional `publish-pypi` and `publish-npm` jobs were skipped as
configured; GitHub assets remain the delivery route. The TP-001 and integration-
plan amendments continue to govern the original managed proof and reusable
least-privilege identity setup. The [retained public-repeat receipts](../04-build/evidence/truss050-adoption-20261024/public-release-qualification-20261025/) bind the downloaded wheel and actual postpublication UMF phase.

## 0.6.0

Arras 0.6.0 adds optional official source admission and bounded core-metadata
projection. Install `arras[umf]` to use `arras.umf_admission`:
`admit_document(document)` returns the immutable admission result, and
`project_document(document)` performs fresh admission before returning a supported
metadata projection or explicit projection issues. Legacy parsing stays the
default. A host opts into `metadata_profile="umf-core-metadata/1"` on
`Arras.start`; only the memory adapter qualifies this profile. It allows schema
registration/dry-run, description, document readback and authorized empty-graph
reads. Writes refuse before effects, and the Truss adapter refuses this profile
before acceptance. This does not qualify value/constraint execution, canonical
actions, native metadata generally, Ashlar or managed deployment. See the [official
admission and metadata contract](../02-design/contracts/CONTRACT-002-type-registry-and-placement.md#official-source-admission-and-core-metadata-profile)
for input, profile and refusal details. Truss 0.0.48, Weft 0.4.51 and official UMF
core 0.10.0 remain the selected dependency versions.

## Recorded candidate qualification

Source commit `8f8097ab0bebb3f8eda6d76568c62ee5e84d33ef` carries the same A2 scope
as merged source `df923164`. PR 7's main CI run `39960762557` passed all four
checks. The immutable tag object is `686886c7ed2425e4e9e496b70fcc39272b8a52d9`.
On macOS, the full default Python suite passed 3,064 tests with 199 Truss tests
deselected; content, Ruff, format and full Pyright checks passed. UI source
lint/type, 1,449 unit tests, audit, build and external checks passed. The exact
candidate wheel SHA-256 is `03959567e77a547ed94014f55bd312630a276827753aafbb5615da0b216366ec`;
the candidate wheel-carried npm SHA-256 is
`cfdd2da7a13f088df2146322e14eba202e78b8def3afc86690e550a44d845749`. These are
named Mac component identities, not public asset hashes unless public byte
identity is verified. The final amended source/sdist comparison passed.

Installed admission compared all 139 ordered reference cases and 139 separate
fresh-empty production Registry cases with zero skips; six base and ten
extra-enabled controls passed and both environments were cleaned up. This proves
admission-result parity, not 139 executable metadata cases. The installed doctor
passed 20 cases, eight SDK phases and three controls using Python 3.13.16. The
fresh example passed four tests and 72 memory cases. The candidate native run
passed 199 tests; a separate fresh-native run passed 64 with eight declared limits
and seven replica-only cases inapplicable. The packed browser run passed 272 cases,
including comparison of 67 canonical baselines. These are named component results;
they do not establish a general support matrix.

### Published 0.6.0 qualification

Arras [v0.6.0](https://github.com/DocumentDrivenDX/arras/releases/tag/v0.6.0)
was published on 2026-10-23 from source commit
`8f8097ab0bebb3f8eda6d76568c62ee5e84d33ef`, identified by immutable tag object
`686886c7ed2425e4e9e496b70fcc39272b8a52d9`. Release run
[`39963352238`](https://github.com/DocumentDrivenDX/arras/actions/runs/39963352238)
completed successfully. The required check, Truss adapter on PostgreSQL 18.6,
build, exact-wheel UMF admission, Linux x86_64 native adapter, UI/packed-theme,
evidence assembly, GitHub release, installed downstream consumer and anonymous
public-bundle jobs all passed. PyPI and npm publication jobs were skipped as
deferred; GitHub release assets are the delivery route.

The public bundle has 17 assets: 16 payloads listed in `SHA256SUMS`, plus that
sum file. It uses release-evidence schema v2 and includes the safe UMF admission
receipt as the 17th asset. Key public asset SHA-256 values are:

| Public asset | SHA-256 |
| --- | --- |
| `arras-0.6.0-py3-none-any.whl` | `c3ace4273f483fbf41af3f70a71a65a6d0f9c963c5b1c71eb79c5bf1bd299a3d` |
| `arras-0.6.0.tar.gz` | `1e533d666b664cc99b1d3b8dedc8120e825988e7d997d69189a3507bc9e53ce2` |
| `documentdrivendx-arras-ui-0.6.0.tgz` | `73819275d2b784295e471c8b81fe251acb127b274cc9567946cdce9824ef9a71` |
| `SHA256SUMS` | `db38b4e67897024cb23542a8d2c265967e88d204623e47faba3ef892d9a45aca` |
| `release-evidence.json` | `659ffd6c08e118e357024491fa48c0605b962e4039282285bd561628606bbef1` |
| `umf-admission-installed.json` | `bfa03144ede16d3a8780c4b272f4b0e6ba5202cc4ea4f95eae58f1b85da67517` |

The anonymous public-download UMF run installed the exact public Arras wheel on
Linux x86_64 / CPython 3.11.17 and matched all 139 ordered reference cases and
139 separate fresh-empty production Registry cases, with zero skips. Six base
and ten extra-enabled controls passed, and both environments were cleaned up.
This establishes admission-result parity and the scoped memory metadata
controls, not executable value/constraint semantics. The release build's UMF
receipt is a separate phase. The public installed doctor passed 20 cases, eight
SDK phases and three controls; the fresh extension example passed four tests and
72 memory cases. The public Linux UI qualification passed all 205 nonvisual
checks with no skips; visual checks were inapplicable on Linux. The public Linux
native adapter job also passed. These results are bounded to the named release
wheel, versions and environments.

The local macOS component wheel/npm hashes above remain component evidence. A
separate independent payload comparison found the 321 files inside the local and
published npm tarballs byte-identical, while their compressed npm archives and
wheel `RECORD` entries differ; the wheel/sdist comparison therefore establishes
packaging payload correspondence, not macOS execution of the Linux release
wheel. Registry publication remains deferred.

The final independent public audit is complete. The raw [independent public-repeat
review](../04-build/evidence/arras-0.6.0-release-20261023/public-repeat-review.json)
has SHA-256 `1d38a416e3b161c2d769ca749267c57b56614f9d97a0cba28ff5a5e8ffef814d`.
The [consolidated closeout manifest](../04-build/evidence/arras-0.6.0-public-verification-review-20261023.json)
indexes the final public proof and related independent reviews.
The reviewed bundle supplement has SHA-256
`30b9e0cde06c0cfc669d4898337dcbc005ec1d1a56276b5ad86574349f3a973d`, and the
public UI execution supplement has SHA-256
`a132d7f57db75731abb033df6868e2e00f8fc69fb018bc66c50fdb260e1493a8`.

## Historical release: 0.5.1

### Release scope and audience

Arras 0.5.1 supplies generic Python/UI interfaces for hosts that wrap or embed
Arras. Host developers consume the wheel, source archive and exact scoped npm
tarball through GitHub Release assets, with checksums and qualification receipts.
Operators use these notes for credential and configuration changes. This artifact
release does not install or migrate a live customer database.

Registry access has not been established. PyPI/npm uploads are deferred under
the release instruction. GitHub assets are the supported
delivery route. The [release checklist](deployment-checklist.md) requires exact-tag
checks before publication and fresh public-download qualification afterward.

### Qualification state

[Arras v0.5.1](https://github.com/DocumentDrivenDX/arras/releases/tag/v0.5.1)
is published with all sixteen assets (fifteen covered by SHA256SUMS). All eight generic downstream
seams are delivered for the named subset. Publication run `39879533273` passed all
prepublication gates; a later shell orchestration failure left its public
consumer checks incomplete. The reviewed read-only
[verification run `39883764998`](https://github.com/DocumentDrivenDX/arras/actions/runs/39883764998)
then passed the fixed reusable consumer and full anonymous public-download
checks, including distribution parity, doctor 20/eight SDK phases/three controls,
fresh example 4/memory 72 and all 205 Linux nonvisual themed cases and controls.
The [final independent review](../04-build/evidence/arras-0.5.1-public-verification-review-20261023.json)
binds both runs and exact published artifacts. Original receipts and the
prepublication aggregate remain unchanged; Mac component/visual evidence is
separate and linked by reviewed payload equivalence.

The immutable v0.5.0 tag failed before publication on a stale assertion. The
initial v0.5.1 tag run failed before publication on UI build ordering. Both are
preserved failure history, not replaced release results. This documentation
closeout postdates the tagged package and its original GitHub notes; no artifact
or tag has been rewritten.

### Highlights

Arras exposes a deliberate public API catalog and generic downstream seams for
presentation, UI themes/assets, current-principal policy, explicit content and
backend composition. A neutral installed example and reusable CI workflow show
how to consume them without copying upstream tests. An offline doctor identifies
incompatible explicit configuration and unavailable capabilities before startup.

Persistent development hosts retain per-person credentials. Starting another
host no longer resets those passwords or unrelated grants. Composed UI hosting
also forwards the host's schema-authorization callback.

### Changes by seam

| Seam | Consumer-visible behavior |
| --- | --- |
| Distribution | Public Python/UI exports, contracts, configuration, CSS roles and tooling are catalogued and checked. The wheel carries the verified page and exact npm tarball. Source/sdist-rebuilt wheels and installed consumers are compared. |
| Naming | Immutable Brand and DistributionConfig compose host presentation; public MCP/development launchers support a thin shim. Explicit environment aliases preserve canonical fallback and refuse credential conflicts before choosing identity. Canonical wire/CSS identities and default instrumentation names remain stable. Typed scoped telemetry projection passes 20 installed doctor cases, eight telemetry phases and three false-pass controls on the qualified component wheel, preserving host separation and provider failure isolation. |
| Theme | A compiled host replaces six design-system slots including Mark with one React. A prebuilt page accepts verified CSS/font/favicon assets at runtime. The packed checker tests tokens, contrast, axe, internal controls and keyboard behavior; macOS visual comparison is separate from Linux checks. |
| Operator and policy | Host callbacks retain operator, role, schema and Operate ownership. PolicyBackend checks immutable resolved requests as the current person; policy refusals use existing error envelopes. Annotation-aware providers must commit annotations with the write or refuse before effects. |
| Content | The downstream owns its modules, seeds and graph files and chooses registration explicitly. Demo modules are not discovered automatically. The view vocabulary remains closed; adding a vocabulary item requires an upstream extension. |
| Backend/deployment | Backend factories and connections remain host-owned. A lazy public Truss conformance harness owns only a throwaway local database. Stable credential storage supports multiple persistent development hosts. |
| Testing | The packaged corpus and public UI checker can be run without the upstream test tree. Reusable CI installs an exact digest-qualified wheel and the consumer's selected test targets. Generic import-origin and fixture-provenance gates protect the public source. Public Node-only `./testkit` and browser-only `./testkit/host` carry the shared 17-spec, 83-resource suite. The current installed ordinary themed comparison passes 272 cases, including 67 unchanged reviewed visual baselines; historical capture approvals remain separate; the Linux profile selects 205 nonvisual cases. |
| Upgrade | The offline doctor checks installed identities, contracts/exports, config/naming, role-token names, manifests and declared document profiles. Reports distinguish incompatibility, malformed requests and unavailable proof. It does not read ambient credentials or contact hosts. |

### Required actions and compatibility

Pin exact artifacts and verify SHA256SUMS before installing. Use the catalogued
public exports, keep your theme/content downstream, and run installed/native/UI
qualification against each new pin. Python imports and CSS token prefixes remain
canonical; supply your own package, command and host presentation through the
public seams. Package, contract and vocabulary versions are separate; breaking
0.x package changes increment the minor version, while patches preserve the
public surface and existing contract deprecation periods.

Before sharing a persistent development database, configure retained per-person
credentials. Previously created roles whose credentials were not retained require
explicit administrator recovery. Normal startup refuses that situation instead of
silently changing passwords. This release does not migrate a live database.

### Qualified scope and known limits

The [compatibility matrix](../02-design/downstream-extensibility.md#compatibility-and-qualification-matrix)
separates actual component cohorts from version declarations. The selected native
versions are public Truss 0.0.48, Weft 0.4.51 and pgserver-pg18 18.6.1. Current source Linux qualification passes all 199 native tests. The historical
Mac 199-test source result is retained by the explicit source-equivalence
attestation. A separate fresh 0.5.1 Darwin
arm64/CPython 3.11 installed-native run records 64
passes, eight exact declared limits and seven replica-only cases inapplicable,
with no failures or harness errors. All seven selected native distributions and
their installed payloads match their verified archives; this is not a system
dynamic-link audit. The fresh installed example passes four tests and all 72 applicable memory corpus cases, with seven
replica-only cases inapplicable.

On Darwin arm64, the frozen wheel passes the 20-case doctor/SDK check on Python
3.13.16/OpenTelemetry 1.45.1. The current packed themed browser ordinary comparison passes
272 cases with no failures/skips; all 67 reviewed canonical baselines and eight
route baseline hashes remain unchanged. Historical capture approvals are retained. It uses React 19.3.0, Vite 8.3.2, Playwright 1.63.0,
axe 4.13.0 and Chromium 153.0.8010.12. These are named component results. The
release workflow separately binds its
exact tagged Linux artifacts and emits fresh public-download results; component
interpreter/platform cohorts must not be merged into an unobserved runtime claim.

The supported document profile is the selected legacy Arras subset. General
official-UMF admission/execution, arbitrary view components, managed deployment,
replica convergence and an absent additional storage adapter are not qualified.
Policy annotation atomicity is proved with an annotation-aware synthetic provider;
the native Truss adapter does not implement that optional protocol and refuses
annotation-bearing writes before effects. Deployment-specific sensitive-record
entitlements still require the host's policy and qualified provider capabilities.
Static doctor checks do not establish rendered accessibility or native writes.
Python classifiers and matching version strings do not qualify untested platforms.

### Hold, rollback and support

Hold an upgrade on any doctor incompatibility, checksum mismatch or failed
consumer/native/theme gate. Retain the previous artifact pin and owned data until
the new pin passes. Published versions must not be replaced with different bytes;
fix forward with a new version. For defects, report the exact artifact digest,
versions and bounded diagnostic codes in the repository's issue tracker, without
credentials or sensitive records. Native recovery follows the provider's own
qualified procedures.

### References

- [Deployment checklist](deployment-checklist.md)
- [Per-seam design and compatibility matrix](../02-design/downstream-extensibility.md)
- [Naming inventory](../02-design/naming-surfaces.md)
- [Changelog](../../../CHANGELOG.md)
- [Minimal downstream skeleton](../../../examples/extension_host/README.md)
- [UI consumption and theme checks](../../../ui/README.md)
