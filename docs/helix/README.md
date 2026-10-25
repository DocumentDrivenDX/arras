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
separate artifact scope. PyPI/npm uploads remain explicitly deferred. No downstream migration or general official-UMF execution is implied. Arras 0.6.0
adds bounded official-UMF admission and opt-in read-only memory metadata projection.
The immutable [GitHub release](https://github.com/DocumentDrivenDX/arras/releases/tag/v0.6.0)
was published from source `8f8097ab0bebb3f8eda6d76568c62ee5e84d33ef`; release run
[`39963352238`](https://github.com/DocumentDrivenDX/arras/actions/runs/39963352238)
passed all required jobs. Its 17-asset schema-v2 bundle includes the safe UMF
receipt. The public Linux UMF repeat matched 139 reference and 139 fresh-empty
Registry cases with zero skips; doctor, extension example, 205 nonvisual UI
checks and native adapter qualification passed on their named Linux environment.
The in-memory profile remains bounded to the released official core, fresh empty
registries and memory-only metadata readback. This does not qualify official
value/constraint execution, canonical actions, broader ownership/registration,
general native metadata, or Ashlar support. The final independent public review is
complete and linked in the [release notes](05-deploy/release-notes.md).

Arras 0.6.1 / Truss 0.0.50 is published from merge commit
`243f1ebaf8b32beb0abc30d0d4fdcd9dd7b5ea92` as tag `v0.6.1`. The canonical
wheel `259e16c7d4c8f6c56d9930ee5f16e74c4ab6b2c8a3ecffdb7d8b306c77b60f18` passed the exact-wheel Mac and original twelve-case Lakebase
gates, and the exact-tag release workflow completed all mandatory public asset,
installed-consumer and UI/UMF repeats. The [release notes](05-deploy/release-notes.md),
[deployment checklist](05-deploy/deployment-checklist.md) and
[integration plan](04-build/arras-integration-plan-20261022.md) record the bounded
receipts and explicitly deferred registry jobs.

Raw incoming material goes in `docs/intake/`, outside HELIX. Author artifacts
through the HELIX skill (`/helix`).

- [EX-05/EX-07 external overlay execution plan](04-build/ex05-ex07-external-overlay-20261022.md)


## Arras 0.6.1 published status — 2026-10-25

Arras 0.6.1 pins published Truss 0.0.50 and was merged from source
`243f1ebaf8b32beb0abc30d0d4fdcd9dd7b5ea92` (tree `9ee467d942ba7440d6adaa9b891b8f00aa2d8c1c`) under annotated
tag `v0.6.1` (object `99609317f1cfc95a2e8e3768f2481910dcf42e23`). Its canonical wheel remains
`259e16c7d4c8f6c56d9930ee5f16e74c4ab6b2c8a3ecffdb7d8b306c77b60f18`. Exact-wheel fresh macOS arm64 / CPython 3.11.9 evidence from run
`40221099126` has 64 passes, eight unchanged limits, seven inapplicable replica
cases, seven verified native-wheel hashes, exact 172-file Arras payload parity
and passing cleanup. The repaired fresh Lakebase baseline passed 6/6; the separate
original full twelve-case Lakebase campaign on the same wheel passed 12/12 with
zero failures or blocked cases. Original cleanup, independent audit, process
census and custody handback passed; source-bound safe records are retained under
[`full-managed-20db-passed-20261025`](04-build/evidence/truss050-adoption-20261024/full-managed-20db-passed-20261025/).
The scoped supplemental census did not capture the direct supervisor PGID; no
forced-cleanup claim is made. The initial 2d journal-binding failure and D11/D12
failures remain historical. Exact-tag [release run 40227314485](https://github.com/DocumentDrivenDX/arras/actions/runs/40227314485)
passed all mandatory jobs, including anonymous public asset verification and
installed downstream repeats. The published 17-asset schema-v2 bundle binds the
exact wheel; public UMF matched 139 reference and 139 fresh-empty Registry cases,
with six base and ten extra controls, zero skips and passing cleanup. Registry
publisher jobs were skipped as configured; GitHub Release assets are the delivery
route.
