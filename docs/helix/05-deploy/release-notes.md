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

# Arras 0.5.0 release notes — candidate

## Release scope and audience

This draft describes the first public Python/UI distribution candidate for hosts
that wrap or embed Arras. It is not a publication claim. Final source identity,
artifact digests, native cohort and public download results remain pending the
[release checklist](deployment-checklist.md). There is no live deployment or
customer-data migration in this artifact release.

Host developers receive the release through the public GitHub repository and
Release assets; operators use these notes for credential/configuration changes.
Real PyPI/npm uploads will use existing access if available. Registry access has
not been established, and the human permits deferring those uploads. GitHub
wheel, sdist, scoped npm tarball, checksums and verification receipts are required.

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
| Naming | Immutable Brand and DistributionConfig compose host presentation; public MCP/development launchers support a thin shim. Explicit environment aliases preserve canonical fallback and refuse credential conflicts before choosing identity. Canonical wire/CSS identities and default instrumentation names remain stable. Typed scoped telemetry projection is implemented and source-reviewed. A corrected temporary installed consumer passes 20 doctor cases and eight telemetry phases, with independent no-op/snapshot controls; the frozen release wheel must repeat that qualification. |
| Theme | A compiled host replaces six design-system slots including Mark with one React. A prebuilt page accepts verified CSS/font/favicon assets at runtime. The packed checker tests tokens, contrast, axe, internal controls and keyboard behavior; macOS visual comparison is separate from Linux checks. |
| Operator and policy | Host callbacks retain operator, role, schema and Operate ownership. PolicyBackend checks immutable resolved requests as the current person; policy refusals use existing error envelopes. Annotation-aware providers must commit annotations with the write or refuse before effects. |
| Content | The downstream owns its modules, seeds and graph files and chooses registration explicitly. Demo modules are not discovered automatically. The view vocabulary remains closed; adding a vocabulary item requires an upstream extension. |
| Backend/deployment | Backend factories and connections remain host-owned. A lazy public Truss conformance harness owns only a throwaway local database. Stable credential storage supports multiple persistent development hosts. |
| Testing | The packaged corpus and public UI checker can be run without the upstream test tree. Reusable CI installs an exact digest-qualified wheel and the consumer's selected test targets. Generic import-origin and fixture-provenance gates protect the public source. Delivery and packed-theme execution of the existing full Playwright suite remains an open release blocker; the narrower checker is not that evidence. |
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

The expanded source checkpoint passed 2,797 default Python tests and strict type/lint/format
checks on the existing Truss 0.0.45/Weft 0.4.49 pins. Its 199 native deselections do
not qualify native execution. The full product UI source checks passed unit,
integration and 272 browser tests on macOS; packed consumer evidence separately
covers runtime and compiled themes. These are pre-freeze checkpoints, not final
release-artifact evidence. The exact final compatibility matrix and downloaded
artifact identities must be recorded here before the candidate is marked shipped.

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
