# Changelog

## Unreleased

- `arras.alias.alias_package(name, *, target="arras", modules=None)` lets a thin package under
  another import name serve `arras` itself: same module objects, canonical `__spec__`, working
  `importlib.resources` and `python -m`, with an optional closed list of modules.

## 0.6.4 — embedding isolation

Adds explicit identity/API session boundaries and optional `pageEffects=false`
for compiled React consumers. Resets cached data, refusals, forms, drafts and
viewer modes across sessions; guards shared-cache ownership and conflicting
nested configuration. Controlled Explore preserves host history and scroll.
Individual areas get a CSS scope, and instance-local labels, SVG resources,
focus requests and edit portals avoid cross-widget collisions. Documents API-only
ASGI hosting and compiled public npm entrypoints. Native/UMF pins and HTTP
contract versions are unchanged. Published as [v0.6.4](https://github.com/DocumentDrivenDX/arras/releases/tag/v0.6.4)
on PyPI and npm. All ten release gates, public-byte checks, fresh installs and
public PyPI extras checks on Linux x86_64/macOS arm64 passed; the
[publication record](docs/helix/05-deploy/evidence/embedding064-20261029/registry-publication.safe.json)
retains exact hashes and npm visibility-retry history.

## 0.6.1 — release candidate

Adopts exact public Truss 0.0.50 while keeping Weft 0.4.51 and official UMF
core 0.10.0 fixed. Hosts may explicitly supply an immutable `tolerated_grantees`
tuple for fresh Truss installation; reconnect preserves stored policy. Typed
third-party grant refusals retain bounded diagnostics and the original rollback,
uncertainty and quarantine behavior.

The Truss native runtime manifest remains `truss-catalog-runtime/0.74-candidate`
with SHA-256 `288801f7177338328441b5d3ce9328af31740ebf513f04ea45e30ae316a9f3a4`.
The active migration manifest is versioned separately and retains the prior
0.0.49 manifest. The 0.0.50 public source binding does not transfer earlier installed-native or
Lakebase receipts. The exact canonical Arras wheel has since passed both complete
0.6.1 campaigns; source-bound receipts are retained in the governed evidence tree.

Adds separately authorized Lakebase qualification with original identity,
transaction, feed, recovery and provider observations. The exact-wheel macOS
campaign passed, and the original twelve-case managed campaign passed 12/12 with
cleanup, audit, census and custody checks. Final review, exact-commit CI, release
artifacts, merge/tag and publication remain open; execution results alone do not
declare final release acceptance.

As of 2026-10-25, source `20db67822b20c822ee91c6823a3fe73ebc3ae932` passed all
five CI jobs in run `40221099126` and remains bound to the canonical wheel SHA-256
`259e16c7d4c8f6c56d9930ee5f16e74c4ab6b2c8a3ecffdb7d8b306c77b60f18`. Fresh Mac
arm64 / CPython 3.11.9 qualification in run `40221099126` passed 64 cases with
eight declared limits and seven replica-only cases inapplicable; native-wheel
hashes, 172-file installed payload parity and cleanup passed. The repaired fresh
Lakebase baseline passed 6/6. The separate original twelve-case Lakebase campaign
passed 12/12 with original cleanup, independent audit, process census and custody
handback passed. Source-bound safe receipts are retained in the governed evidence
tree. The scoped supplemental census did not capture the direct supervisor PGID;
no forced-cleanup claim is made. The initial journal-binding failure and earlier
D11/D12 failures remain historical. Final review, exact-commit CI, release build,
merge/tag and publication gates remain open; this remains a release candidate,
not a published or finally accepted release.

## 0.6.0 — 2026-10-23

Adds optional official UMF source admission through `arras.umf_admission` and an
opt-in `umf-core-metadata/1` profile for bounded memory-backend metadata
registration and readback. Legacy parsing remains the default; writes refuse for
the metadata-only profile, and the Truss adapter refuses it before acceptance.
This does not add value/constraint execution, canonical actions, native metadata
or Ashlar support. The official UMF core 0.10.0, Truss 0.0.48 and Weft 0.4.51
pins remain unchanged.

Source commit `8f8097ab0bebb3f8eda6d76568c62ee5e84d33ef` carries the same A2 scope
as merged source `df923164`; PR 7 main CI run `39960762557` passed all four checks.
Immutable tag object `686886c7ed2425e4e9e496b70fcc39272b8a52d9` was published as
[v0.6.0](https://github.com/DocumentDrivenDX/arras/releases/tag/v0.6.0) on
2026-10-23. Release run
[`39963352238`](https://github.com/DocumentDrivenDX/arras/actions/runs/39963352238)
completed successfully, including the required Linux jobs, exact-wheel UMF proof,
installed consumer and anonymous public-download verification. The public bundle
contains 17 assets: 16 checksum-listed payloads plus `SHA256SUMS`, with the
schema-v2 safe UMF receipt as asset 17. Public asset identities and Linux results
are recorded in the release notes and deployment checklist. The final independent
public review is complete and linked from the release notes.
PyPI/npm registry publication remains deferred.

## 0.5.1 — 2026-10-22

This patch preserves the generic downstream interfaces described below. It
corrects a CLI-refusal test to check the bounded parser diagnostic, exit status,
credential redaction and absence of startup effects. Regular Python CI now uses
the same Truss-extra dependency environment as the release build.

The immutable `v0.5.0` tag failed its build gate before any release assets were
published. Version 0.5.1 is a fresh artifact cohort. Its SDK/doctor, fresh consumer and
ordinary themed checks pass independently on the new wheel; all 75 reviewed
baseline hashes are unchanged. The release requires its own installed-native,
exact-tag and anonymous public-download gates before completion. The release
notes and receipts distinguish component runtimes and delivery results.

## 0.5.0 — failed unpublished tag, 2026-10-22

The following records the qualified candidate feature scope. The tag workflow
stopped before artifact creation or publication; it did not deliver a release.

The first public distribution supplies generic Python/UI seams and installed
consumer qualification. The [release notes](docs/helix/05-deploy/release-notes.md)
record qualified cohorts and limits; the
[release checklist](docs/helix/05-deploy/deployment-checklist.md) governs delivery.

### Distribution and public API

The wheel carries the built page, exact scoped npm tarball and a deliberate,
machine-checked public API catalog. Artifact checks compare source and
sdist-rebuilt wheels, dependency metadata, packaged resources and installed
consumers. GitHub assets provide wheel, sdist, npm tarball, checksums and receipts.
Registry uploads are independent, explicitly configured delivery steps.

Package, contract, vocabulary and catalog versions are separate. A breaking
0.x package change increments its minor version; patches preserve the public
surface. Existing contract-specific deprecation periods remain in force.

### Naming and configuration

`Brand` and `DistributionConfig` supply host presentation without rewriting
upstream imports or wire identities. Public MCP/development launchers support
thin wrapper commands. Opt-in environment aliases take precedence over canonical
fallback, while conflicting credential sources fail before identity selection.
MCP tool aliases reject collisions and stale mappings. Canonical CSS tokens,
protocol names and default instrumentation identifiers remain stable. `TelemetryNames` and
`TelemetryContext` provide typed per-host event/attribute/log projection and
validated host-owned service Resources. Awaited ASGI/MCP/worker operations preserve
the selected context; failures do not mutate global providers or business results.
Focused source tests and Sol review pass. The frozen candidate passes 20
installed doctor cases, eight SDK phases and three false-pass controls; exact-tag
and public-download checks remain separate.

### UI assets and theming

A compiled host replaces the six design-system slots, including Mark, through public
exports, using one React. A prebuilt page accepts a bounded verified runtime
CSS/font/favicon theme manifest. Same-origin digest routes validate exact paths,
MIME, sizes, hashes and UI cohorts. Arbitrary widget replacement uses the compiled
route. The packed `arras-ui-qualify` tool checks an explicit host URL with optional
public test-tool peers, retained reports and separate macOS visual baselines.
It never installs peers or downloads browsers implicitly. Node-only `./testkit`
and browser-only `./testkit/host` share the canonical 17-spec suite and 83 verified
resources. The actual packed themed capture and ordinary comparison each pass
272 cases, with all 67 reviewed baselines unchanged and negative controls intact.

### Operators, policy and audit

Composed UI hosting forwards schema authorization alongside existing operator
and action callbacks. `PolicyBackend` checks current host policy over immutable
resolved requests while preserving the person's token and backend authority.
`PolicyRefused` exposes a bounded policy code through existing refusal envelopes.
An optional provider protocol binds annotations to the write/audit group; a
provider without that capability refuses before writing. The generic transaction
proof is synthetic. Native Truss policy annotations and deployment-specific
source-entitlement guarantees are not supplied by this release.

### Modules and content

A neutral external package selects its own module, seeds and graph resources
through public registration/import calls, without loading demo content by
default. Registration/discovery stays explicit; documents do not import code.
The selected legacy Arras document/action profile is qualified separately from
source admission and native execution. The closed view vocabulary has no
arbitrary document-component escape hatch. General official-UMF adoption is not
claimed.

### Backends and development deployment

Hosts compose backend factories and own connections, roles, credential sources
and deployment timing. Persistent development hosts retain stable per-person
credentials and preserve unrelated memberships and expiry. Missing retained
credentials require explicit administrator recovery; ordinary startup does not
rotate another host's password. A public lazy native conformance helper owns
only its throwaway local database and closes it after each corpus case.

### Downstream testing and repository hygiene

Installed consumers can run the packaged corpus and UI checker without copying
the upstream test tree. A reusable workflow verifies an exact HTTPS wheel digest,
installs a consumer and reports explicitly selected test outcomes. Generic gates
check dependency origins, public import boundaries and fixture provenance. The
upstream source/docs no longer depend on a named downstream as their authority.
Consumers link or extend HELIX decisions and keep their own content downstream.

### Upgrade diagnostics

The offline doctor checks explicit installed pins, public exports, configuration,
naming, role tokens, asset manifests and declared module profiles. Stable reports
separate incompatibility, malformed requests and unavailable capabilities. It
reads no ambient credentials, token file, native host or authorization decision.
Static compatibility does not establish rendered accessibility or native writes.

### Required actions and limits

Pin exact released artifacts and verify their checksums. Use only catalogued
Python/UI exports. Keep theme/content packages in the consumer, and run its
installed, native and rendered qualification profiles against each new pin.
Configure a shared stable credential source before attaching another persistent
development host; recover previously unretained role credentials explicitly.

The release notes and machine-readable evidence separate Python/SDK, UI, native
and installed-consumer cohorts. The selected native tuple is public Truss 0.0.48,
Weft 0.4.51 and pgserver-pg18 18.6.1. Both Linux and Mac source suites pass 199 tests;
the fresh Darwin installed corpus records 64 passes, eight declared limits and
seven replica-only cases inapplicable. Source classifiers do not qualify unrun
platforms. PyPI/npm uploads are deferred while existing publishing access is
unavailable; GitHub artifact delivery remains required.
