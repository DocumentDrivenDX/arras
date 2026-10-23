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

# Arras 0.5.1 release notes

## Release scope and audience

Arras 0.5.1 supplies generic Python/UI interfaces for hosts that wrap or embed
Arras. Host developers consume the wheel, source archive and exact scoped npm
tarball through GitHub Release assets, with checksums and qualification receipts.
Operators use these notes for credential and configuration changes. This artifact
release does not install or migrate a live customer database.

Registry access has not been established. PyPI/npm uploads are deferred under
the release instruction. GitHub assets are the supported
delivery route. The [release checklist](deployment-checklist.md) requires exact-tag
checks before publication and fresh public-download qualification afterward.

## Qualification state

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

## Highlights

Arras exposes a deliberate public API catalog and generic downstream seams for
presentation, UI themes/assets, current-principal policy, explicit content and
backend composition. A neutral installed example and reusable CI workflow show
how to consume them without copying upstream tests. An offline doctor identifies
incompatible explicit configuration and unavailable capabilities before startup.

Persistent development hosts retain per-person credentials. Starting another
host no longer resets those passwords or unrelated grants. Composed UI hosting
also forwards the host's schema-authorization callback.

## Changes by seam

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

## Required actions and compatibility

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

## Qualified scope and known limits

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

## Hold, rollback and support

Hold an upgrade on any doctor incompatibility, checksum mismatch or failed
consumer/native/theme gate. Retain the previous artifact pin and owned data until
the new pin passes. Published versions must not be replaced with different bytes;
fix forward with a new version. For defects, report the exact artifact digest,
versions and bounded diagnostic codes in the repository's issue tracker, without
credentials or sensitive records. Native recovery follows the provider's own
qualified procedures.

## References

- [Deployment checklist](deployment-checklist.md)
- [Per-seam design and compatibility matrix](../02-design/downstream-extensibility.md)
- [Naming inventory](../02-design/naming-surfaces.md)
- [Changelog](../../../CHANGELOG.md)
- [Minimal downstream skeleton](../../../examples/extension_host/README.md)
- [UI consumption and theme checks](../../../ui/README.md)
