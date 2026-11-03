# Arras 0.7.2 unpublished tag evidence

Immutable tag `v0.7.2`, object `470a2bfbbcb7cbeb9526a5924bcc0e5c68b9a345`,
points to source `6f3ced65e43bb80ee86221a0b3b5ea7e944f0a21`. It is preserved.
[Release run 41570362942](https://github.com/DocumentDrivenDX/arras/actions/runs/41570362942)
failed build job `125704328456` before building/publishing release artifacts.
No GitHub Release/assets, PyPI or npm 0.7.2 was published.

The source-suite failure is
`tests/test_truss_docs.py::test_release_assets_are_gated_and_registry_publishing_follows_publication_gates`,
line 159: `assert 'python-version: "3.11"' in build`. The reviewed producer
intentionally requires the narrower exact Python `3.11.18`. The old textual
assertion rejects that valid stricter producer. The source result was 3,875
passed, one failed, two installed-wheel tests skipped, 203 native cases
deselected. Ruff/format, strict Pyright and the official UMF-vector check passed.
The separate exact-tag PostgreSQL 18.6 suite passed all 203 cases, zero skips,
in 480.38 seconds. Later release/package/public jobs were skipped, not passed.

The 0.7.3 repair requires the exact `3.11.18` literal rather than broadening or
removing the assertion. Its final pre-tag workflow runs the SAME full default
source/workflow suite with required Weft/UMF/actions flags, in addition to the
existing full fresh package/doctor/extension-host/SDK/installed CLI/page gates.
The test is also in focused release controls and the candidate workflow's path
triggers. Native tests remain separate, required by the immutable tag workflow;
no new local Mac native campaign is selected.

[The 0.7.2 repair packet](../arras072-repair-20261103/README.md) and actual
[final merged-source qualification 41569954622](https://github.com/DocumentDrivenDX/arras/actions/runs/41569954622)
remain historical supporting evidence, not successful publication. Their exact
wheel, sdist and npm bytes remain bound to 0.7.2; no receipt is renamed 0.7.3.
New versioned Linux artifacts, full pre-tag source qualification, independent
review, final merged-source proof, mandatory tag jobs and actual public bytes/
fresh consumers remain necessary for the successor.
