# Arras 0.7.0 managed qualification by correspondence

The existing legacy Truss/Lakebase profile carries forward to released Arras
0.7.0. This is an impact-reviewed qualification, using historical managed
execution and existing 0.7.0 regression results. No fresh Lakebase campaign was
needed or executed. The operator explicitly directed reuse of unchanged-behavior
evidence on 2026-11-02 rather than repeating every managed case for a new wheel.

## Evidence and affected boundaries

`correspondence.json`, reproduced by `verify-correspondence.py`, verifies the
published 0.6.4 wheel `29139ac7…` against published 0.7.0 wheel `b20f2b0c…`:

- All 23 shipped adapter files are byte-identical, including the Truss adapter.
- The complete adapter and Lakebase harness source inventories are unchanged
  between release sources `11be778e…` and `f9f04c42…`.
- Truss 0.0.50 is the same archive `7b0483bb…`; Weft 0.4.51, psycopg 3.3.6,
  mini-racer 0.14.1 and the other baseline application runtime versions match.
  Installer/bootstrap versions are not application-runtime changes.
  The retained managed dependency-install report also matches the selected
  archive hashes, including Weft, psycopg-binary and mini-racer; the shorter
  historical installed-wheel summary alone did not contain those digests.
- The [original managed campaign](../embedding064-20261029/full-managed.safe.json)
  passed all twelve cases. Its [independent cleanup](../embedding064-20261029/independent-cleanup.safe.json)
  and [resource cleanup](../embedding064-20261029/provisioning-cleanup.safe.json)
  remain bound to that original execution and its original target.

| Changed boundary | Existing 0.7.0 validation and disposition |
| --- | --- |
| Shared host registration and action dispatch | Full [CI 41510837413](https://github.com/DocumentDrivenDX/arras/actions/runs/41510837413) passed the Truss adapter tests and Python suite. New guards select only the explicit `arras-umf-set/1` profile; legacy Truss routing remains unchanged. |
| Provider descriptors | `BackendInfo.action_profiles` defaults to empty; Truss advertises no new action profile. Registration refuses unsupported profiles before provider acceptance. Existing registration/profile/refusal tests cover the boundary. |
| Telemetry | New translated-refusal handling is limited to `arras.execute`; existing legacy event outcomes and database calls retain their behavior. The Python suite includes the telemetry regression controls. |
| Optional UMF core and new memory actions | Exact-wheel admission/action receipts and fresh public extras checks passed; these qualify the memory profile, not a new Truss execution path. |
| Installed native composition | The exact b20 wheel passed the fresh Mac campaign (64 passes, eight declared limits) in CI 41510837413, and native Linux qualification in [Release 41514683626](https://github.com/DocumentDrivenDX/arras/actions/runs/41514683626). That run's separate final public-codec failure remains recorded. |
| UI, CLI and embedding additions | Existing release/public consumer checks cover these additions; they do not change Lakebase TLS, authentication, SQL, transactions, feed, restart controls or extension requirements. |

Concrete shared-path controls include `tests/test_metadata_profiles.py`,
`test_registry_refuses_unqualified_profile_before_provider_acceptance` in
`tests/test_umf_core_registration.py`, capability and legacy-route refusals in
`tests/test_umf_action_memory.py`, and the legacy refusal/failing-sink controls
in `tests/test_telemetry.py`. These suites passed in the existing full CI run.

LB-ADMISSION, LB-INSTALL, LB-PERSON, LB-CUSTODY, LB-SETTLEMENT, LB-ACL and
MP-01–06 retain their historical execution status. Their applicability to the
unchanged 0.7.0 legacy managed profile is established by this correspondence
review; they are not relabelled as an execution of b20. Existing 0.7.0 tests cover
the changed shared paths, so there is no uncovered managed-behavior delta that
requires a new service campaign.

## Support boundary

This carries forward only the previously qualified PostgreSQL 18.6 / Truss
0.0.50 / Weft 0.4.51 legacy profile and its existing limits. It does not qualify
new UMF actions through Truss or Ashlar, durable memory replay, a different
dependency cohort, or a new provider configuration. An actual deployment still
checks its current target identity, TLS, credentials, grants and ownership;
historical observations do not establish today's target state. Those deployment
admission checks do not require rerunning every semantic test.

Future qualification follows impact: compare relevant source, shipped payloads,
dependency/native manifests and configuration; reuse unaffected evidence; run
only affected, uncovered checks. A full campaign is needed when changes span
its behavior or correspondence cannot establish applicability, not merely when
the overall wheel hash or version changes. Original PR 9 execution requirements
and all original receipts remain unchanged.
