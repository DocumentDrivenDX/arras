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
that assertion and CI dependency parity. Exact-tag GitHub assets and fresh public
download gates remain open in the
[release checklist](05-deploy/deployment-checklist.md). Real registry uploads may
be explicitly deferred; no downstream migration or general official-UMF execution
is implied by this release work.

Raw incoming material goes in `docs/intake/`, outside HELIX. Author artifacts
through the HELIX skill (`/helix`).

- [EX-05/EX-07 external overlay execution plan](04-build/ex05-ex07-external-overlay-20261022.md)
