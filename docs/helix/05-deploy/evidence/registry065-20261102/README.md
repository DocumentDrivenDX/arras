# Arras 0.6.5 npm delivery

The exact immutable UI archive is published as
`@documentdrivendx/arras-ui@0.6.5`. [Publisher run 41493303642](https://github.com/DocumentDrivenDX/arras/actions/runs/41493303642)
passed all local-origin qualification gates, npm OIDC upload, anonymous registry
byte comparison and a fresh public-registry install/import check. Its driver is
`ae8d81c0865b84d31038f68d8463582ac1aee037`, attempt 1. The original GitHub
publication remains local; this run does not invent an original hosted Release
producer or replace any public asset.

| Identity | SHA-256 or source |
| --- | --- |
| Release/source | `v0.6.5` / `ad597d248847da47523155842524bb451a97f8d8` |
| Annotated tag object | `85beae38114650caa7ff25d9dde090e20071c4e4` |
| UI archive | `26abe759e7bb918bf30c5144a34cff8deb7ecb4dd2ef531d41ec3ceab2155e0f` |
| Wheel | `beed68b94567699313a44c5f8865ecfb6e1f34842d7c5ba5055ac866a664a98b` |
| SHA256SUMS | `dbe547fe5f05386759f6fed80fc85991b676e8ca6eeb67788b2b84dbba1919f8` |

[The hosted receipt](hosted-local-origin-qualification.json) binds every selected
source/native/UMF/UI/consumer receipt to the immutable archives. [The summary](qualification-summary.safe.json)
records 3,452 general source passes with two retained skips, 202 Truss passes
with zero skips, 64 native passes with eight explicit limits, 139 reference and
139 fresh-empty Registry comparisons, six base and ten extra controls, and all
205 Linux UI cases with zero skips. The complete UI validator checked 17
canonical specs, original sidecars, pinned npm resources and both delivery
routes across browser and console surfaces. Native qualification is Linux
x86_64 / Python 3.11 with Truss 0.0.50 and Weft 0.4.51; UMF admission uses
official core 0.10.0. This does not qualify a newer UMF cohort.

The [npm receipt](npm-publication-receipt.json) and [postflight](npm-postflight.json)
separately establish registry bytes and installation. The final wheel's
distribution check rebuilt its sdist only as a verification operation and
matched the original wheel digest; rebuilt outputs were never delivery inputs.
PyPI was not republished and this run does not claim a new public-PyPI extras
campaign. Original macOS visual/native/managed observations retain their
historical identities and correspondence limits in the pinned local proof;
Linux visual execution was explicitly not run.

An [independent public install](independent-public-install.json), outside the
publisher, separately fetched npm metadata and the public tarball, checked
SHA-256 plus registry SHA-512/SHA-1 integrity, compared the GitHub archive,
installed from the public registry with a fresh separate cache, and matched all
323 installed files byte-for-byte with exact inventory and no extras. All 33
root exports loaded on Node 26.12.1 / Darwin arm64, with lifecycle scripts
disabled. [Registry metadata](npm-metadata.json) and the original
[verifier](verify-installed.mjs) are retained. Its initial subprocess-buffer
failure and corrected 32 MiB buffer are [recorded separately](independent-attempts.safe.json);
the smoke makes no additional browser/native support claim.

[The first attempt](first-attempt.safe.json), run `41491255649`, remains failed.
Its source job inherited the unsupported test-only Truss flag into strict MCP
subprocesses; publication was correctly skipped. [PR 41](https://github.com/DocumentDrivenDX/arras/pull/41)
scoped that flag to the native test command. A dry-run against its actual passing
UI receipt also caught the aggregate's two-record expectation; [PR 42](https://github.com/DocumentDrivenDX/arras/pull/42)
requires all four route/surface records and reuses the complete existing UI
validator. No failed receipt was relabeled and no successful source evidence
was substituted. [PR 40](https://github.com/DocumentDrivenDX/arras/pull/40)
introduced the independently reviewed local-origin path.
