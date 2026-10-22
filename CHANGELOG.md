# Changelog

## Unreleased — first public distribution candidate

These changes are in the reviewed release candidate. Publication and final
cohort qualification are tracked by the
[release checklist](docs/helix/05-deploy/deployment-checklist.md).

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
source-entitlement guarantees are not supplied by this release candidate.

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

The final release record must state its exact Python, UI, UMF-profile,
Truss/Weft/PostgreSQL, Node/browser and platform evidence. Source classifiers and
matching version strings do not qualify unrun platforms. Registry availability
must be reported separately from GitHub artifact delivery.
