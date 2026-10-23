# HELIX artifacts

Scope root for the `arras` instance of the `helix` flow declared in
[`.helix.yml`](../../.helix.yml). HELIX is the documentation-driven workflow that
organizes this repository's governed artifacts (PRDs, ADRs, designs, test plans) by
activity. Arras is an open-source interface to an ontology: UMF-defined types and
actions, reads that state their freshness, and a backend contract over named backends (implemented Truss and in-memory
adapters, with an additional storage adapter still planned). Each activity has one directory:

| Directory | Activity | Owns |
| --- | --- | --- |
| `00-discover/` | Discover | product vision, business case, research |
| `01-frame/` | Frame | PRD, feature specs, user stories, concerns, principles |
| `02-design/` | Design | architecture, ADRs, contracts, spikes, solution designs |
| `03-test/` | Test | test plans |
| `04-build/` | Build | implementation plans |
| `05-deploy/` | Deploy | deployment checklists, runbooks |
| `06-iterate/` | Iterate | roadmap, iteration plans, backfill reports |

[`glossary.md`](glossary.md) defines the external systems and Arras terms the artifacts use.

The [Arras integration build plan](04-build/arras-integration-plan-20261022.md)
coordinates official UMF adoption, generated-client transport and the existing
Truss follow-up work. It records the current cohort, owners, first bounded change
and remaining native qualification; planned integration is not delivered support.
Its separate EX queue tracks the generic
[downstream extensibility design](02-design/downstream-extensibility.md). The
implemented candidate includes credential/grant safety, schema authorization,
public distribution/catalog, typed naming and policy, explicit consumer content,
external theme assets and the portable canonical testkit. The fresh 0.5.1 wheel
passes installed SDK/doctor, fresh example and selected installed-native proofs.
Its ordinary themed comparison passes all 272 cases, with all 67 canonical and
eight narrow reviewed baseline hashes unchanged. Historical capture/source
receipts remain bound to their original artifacts; the explicit source-delta
attestation qualifies retention of the Mac source-native evidence. Final source
archive parity and independent component reviews pass. The immutable 0.5.0 tag
failed before artifact publication on a stale refusal assertion; 0.5.1 fixes
that assertion and CI dependency parity. P0 is closed: immutable GitHub v0.5.1
publication `39879533273` and supplemental fresh public verification `39883764998`
pass the [release checklist](05-deploy/deployment-checklist.md). The publication's
post-download failure remains historical; the separate verification run supplies
the passing current receipts. Linux qualifies 205 nonvisual UI cases; its visual
stage is explicitly not run. The Mac comparison and payload bridge retain their
separate artifact scope. PyPI/npm uploads remain explicitly deferred. No downstream
migration or general official-UMF execution is implied. The bounded A2
admission/metadata profile now passes source and fresh installed-wheel checks;
the [execution checkpoint](04-build/arras-integration-plan-20261022.md#bounded-a2-execution-checkpoint)
records the exact unreleased candidate and safe receipt. It uses the released
official core with fresh empty registries and an explicit memory-only metadata
profile. The candidate retains package version 0.5.1 and is distinct from the
immutable public 0.5.1 assets. Official value/constraint execution, canonical
actions, broader ownership/registration and the Ashlar adapter remain open.

Raw incoming material goes in `docs/intake/`, outside HELIX. Author artifacts
through the HELIX skill (`/helix`).

- [EX-05/EX-07 external overlay execution plan](04-build/ex05-ex07-external-overlay-20261022.md)
