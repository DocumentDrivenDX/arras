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
external theme assets and the portable canonical testkit. The final 07b wheel
passes the installed doctor/SDK and fresh example proofs. Its packed themed
capture and ordinary comparison each pass all 272 cases; all 67 canonical images
and eight narrow route images have Sol review. Earlier failures and exact scoped
receipts remain in the build plan. Final Mac native, source/sdist parity, exact-tag
GitHub assets and public-download gates remain open in the
[release checklist](05-deploy/deployment-checklist.md). Real registry uploads may
be explicitly deferred; no downstream migration or general official-UMF execution
is implied by this release work.

Raw incoming material goes in `docs/intake/`, outside HELIX. Author artifacts
through the HELIX skill (`/helix`).

- [EX-05/EX-07 external overlay execution plan](04-build/ex05-ex07-external-overlay-20261022.md)
