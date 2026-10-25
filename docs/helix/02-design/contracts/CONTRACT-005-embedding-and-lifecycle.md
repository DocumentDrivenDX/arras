---
ddx:
  id: CONTRACT-005
  type: contract
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-24
  authoring:
    home: repo
  links:
    - id: FEAT-006
      kind: informed_by
    - id: ADR-006
      kind: informed_by
    - id: ADR-010
      kind: informed_by
    - id: ADR-012
      kind: informed_by
    - id: CONTRACT-001
      kind: informed_by
    - id: CONTRACT-004
      kind: informed_by
    - id: CONTRACT-006
      kind: informed_by
    - id: CONTRACT-008
      kind: informed_by
---

# Contract: Embedding and lifecycle

**Contract ID**: CONTRACT-005
**Type**: library
**Version**: v3
**Status**: draft
**Related**: FEAT-006, ADR-006, ADR-010, ADR-012, CONTRACT-001, CONTRACT-004, CONTRACT-006

## Purpose

Defines how a host Python application starts Arras, registers its backends under names it chooses, says where each module lives (placement), supplies each backend's connections as the person (never a service identity), names the administrative principal that registers and imports, installs or verifies an adapter's store through a separate installing connection, learns whether each backend is available, and mounts the console.

Terms. A backend is a named store with the roles `reader` and `provider` (CONTRACT-004). The Truss adapter is a reader and provider on Lakebase (Databricks managed Postgres); the Ashlar adapter is a reader on Unity Catalog (Databricks' governance layer for tables and access); the memory adapter is an in-memory reader and provider plus an in-memory reader. A host is the embedding application and owns its deployment and connection sources. psycopg 3 is the Python PostgreSQL driver. MCP (Model Context Protocol) is Anthropic's open protocol for agent tools. P1 is the Should Have priority of the product requirements document (`docs/helix/01-frame/prd.md`). An ADR is an architecture decision record.

## Scope and Boundaries

- In scope: starting, the backends and the placement, the connection sources, the administrative principal, the installing connection, install-or-verify, per-backend availability, the public-name boundary, mounting the console.
- Out of scope: the operations (CONTRACT-001 to CONTRACT-003), the backend contract (CONTRACT-004), the console's endpoints (CONTRACT-006), provisioning database resources and Unity Catalog access. Running against a local PostgreSQL for development (EMB-05) and the Truss adapter's install-or-verify on the qualified PostgreSQL 18.6 are verified by the test plan (`docs/helix/03-test/test-plan.md`); they add no contract surface.
- Owning system or team: Arras; each embedding host owns its integration.
- Runtime: Python 3.11 or later. The base install requires no Truss or psycopg. The Truss adapter is an optional extra that requires Arras's selected public driver tuple: `truss-toolkit[native,query]==0.0.50`, `weft-sql==0.4.51`, native runtime `truss-catalog-runtime/0.74-candidate`, manifest SHA-256 `288801f7177338328441b5d3ce9328af31740ebf513f04ea45e30ae316a9f3a4`, psycopg and psycopg-binary 3.3.6 with libpq 18.6, PostgreSQL 18.6, on Linux x86_64 or macOS arm64 (Windows is not supported by the extra). Truss refuses a connection to a different server or driver version when it adopts it. This selected tuple does not qualify a managed deployment. Distribution: neither `truss-toolkit` nor `weft-sql` is on PyPI, so a host that installs the extra vendors the pinned wheels (truss-toolkit, weft-sql, psycopg-binary and their pure-Python closure) into its own build, or passes the same find-links (`tools/find-links/index.html`, which carries the release digests). The extra's metadata is in the published wheel either way.

### Distribution and public API catalog — EX-01

`src/arras/public-api.json` is the single reviewed, inert catalog of the distribution boundary
(schema_version 1). It explicitly lists the root `arras.__all__` surface, selected host-importable
modules and call signatures, the contract-to-runtime-key map, the separately classified MCP and
development configuration/commands, the packed npm runtime/type/style exports and peers, the stable
`.arras-root` CSS namespace and role tokens, telemetry names and privacy boundary, and shipped corpus
and vocabulary versions. It is authored deliberately; source drift tests fail rather than regenerate
or silently widen the catalog. The boundary checker reads the package resource and derives its host
module allowlist from that catalog. It does not add a host API or load host configuration.

CONTRACT-001 through CONTRACT-011 map to the existing nine `CONTRACT_VERSIONS` keys. CONTRACT-002
has `runtime_key: null` and catalog version 2; CONTRACT-008 has `runtime_key: null`
and catalog version 1. No runtime keys are introduced for either. Python distribution
and npm package versions follow `pyproject.toml`; they remain separate from the
manifest schema, contract versions and the `arras.view` vocabulary version. The packagable host
surface includes `arras.telemetry.dropped()` and the scoped naming composition values below,
while emitters, operation/span objects and exporter internals remain private. The conformance selection is `Harness`, `Limit`, `Result`, `Report` and `run_corpus`; corpus
loading helpers are not host API. Development-host and credential helpers are classified as
development tooling, separately from the host import allowlist.

For package compatibility, while the distribution remains 0.x a breaking API change increments the
minor version and a patch preserves the declared public surface; at 1.x and later, a breaking change
increments the major version. Existing one-minor Python name deprecation grace, one-minor HTTP
`Deprecation`/`Sunset` grace, and one-vocabulary-major deprecation grace retain their contract-specific
rules. The wheel, sdist-rebuilt wheel and npm package must agree on package versions and exact carried
npm bytes. Distribution qualification inspects hashes and installs each wheel into a separate clean
consumer environment; a source checkout on `sys.path` is not evidence. Evidence records actual
interpreter/platform separately from declared Python classifiers. No artifact check qualifies an
unrun platform, interpreter, registry, managed host or external runtime.

### Mandatory installed-native release gate

The selected first public distribution requires a dedicated unprivileged Linux
installed-native job before GitHub asset creation. It depends on the tag/version
check and exact-artifact build, uses Python 3.11 and has a 60-minute job bound.
It downloads the same verified wheel selected by the build; the driver does not
`uv sync`, import Arras from the source tree or install native SDKs into the
workflow interpreter. The existing stdlib verifier provisions its own isolated
installed environment.

The reviewed source template path is
`tests/downstream/native-cohorts/linux-x86_64.json`, with companion
`linux-x86_64.find-links.html` in that directory. The index includes the reviewed
GitHub and PyPI anchors for every runtime-native wheel in the selected cohort;
it is not the general development `tools/find-links/index.html`. The template
has exactly `schema_version`, `runtime`, `find_links`, `native_wheels` and `corpus`.
It deliberately omits `arras`. A missing template/index or preexisting `arras`
field refuses the job. No placeholder native versions, hashes, URLs, runtime,
corpus fields or allowlists may be supplied to make preparation look runnable.
Those values remain with the cohort's owning qualification/review lane.

The shared private workflow binder
`.github/scripts/bind_native_cohort.py` reads the selected wheel's actual METADATA
version and actual bytes SHA-256. It requires the version to equal the version
check's output and the digest to equal the build's wheel digest before binding.
It adds only `arras: {version: <actual>, sha256: <actual>}` to an ephemeral copy of
the reviewed template. Every preexisting template field/value remains equal,
including all native wheel identities, runtime, find-links digest, corpus version,
roles and exact documented limits. Duplicate JSON keys, unknown template fields,
metadata identity mismatch, digest/version mismatch and output/input aliasing
refuse rather than normalize or overwrite inputs. The completed manifest must
pass the verifier's existing strict v1 cohort validator before it is written.
The binding step records the exact source template, companion index and bound
manifest identities; it is preparation, not native qualification.

The job calls `tools/verify_native.py --wheel <downloaded-wheel>
--cohort <bound-manifest> --find-links <companion-index>
--output-json <receipt> --python <selected-3.11-interpreter>` and preserves the
verifier's exit status even when stdout/stderr are captured. No memory fallback,
case deletion, limit inference, host-specific pass or optional-job switch is
permitted. GitHub release creation MUST depend on successful installed-native
qualification as well as its existing required gates. The source job may be
implemented before the reviewed cohort files exist; their absence keeps the
release blocked until actual public artifacts and qualification are ready.

Always-run artifact retention includes the selected/bound cohort evidence,
verifier success/failure receipt, stdout/stderr and any retained owned
`arras-native-*` PostgreSQL quarantine paths/logs reported by the verifier. It
must not hide a primary failure or kill an unrelated server. A receipt or helper
existing in source does not establish an actual Linux/native result.

Binding tests execute this same helper with temporary synthetic test inputs;
they do not create a fake source cohort. Positive controls verify actual wheel
metadata/digest binding and exact preservation of every template field. Negative
controls change one expected version/digest, supply duplicate/unknown keys or a
preexisting `arras`, omit the template/index, and attempt an input/output alias.
Workflow tests additionally require the installed-native dependency and
always-run evidence upload. String matching alone does not qualify the binder.

### Exact release evidence assembly and public download qualification

A reviewed release driver on the repository's default branch may recover an
unpublished, immutable existing tag after an orchestration-only failure. A manual
request supplies the exact `vX.Y.Z` tag and expected 40-hex source commit. Validate
the event, default-branch driver, remote tag resolution, expected commit and tagged
project version before running payload code. Record driver commit/workflow/run
identity separately from target tag/commit identity. Every payload checkout,
including a called downstream workflow, MUST use the validated target commit and
verify HEAD; a dispatch ref or driver SHA is never a payload-source substitute.
Recheck that the remote tag still resolves to the same identity before publication.
This recovery changes neither tag nor package/API versions. It runs every mandatory
source/build/SDK/native/UI/consumer/assembly/public-download gate freshly in one
current run; no failed-run receipts are relabelled or joined across runs. All
publication and registry ordering/permission restrictions below remain unchanged.
Record operational provenance as CI evidence, not an extra public release asset.
A changed runtime payload still requires its own affected qualification; a workflow
repair is not authority to replace any published artifact bytes.

A postpublication orchestration failure has a separate, verification-only recovery
path. A reviewed default-branch driver with only `contents: read` and `actions: read`
may verify the existing immutable release. It binds the original publication run,
publication driver, target tag/source, wheel digest, trusted-stage `SHA256SUMS`
digest and aggregate digest explicitly. Validate the original repository/workflow
and successful prepublication jobs; an overall failed run is not a successful
postpublication result. Download that run's original trusted stage and verify its
exact inventory and digests before comparing anonymous public downloads.

The fixed reusable installed-downstream job and the complete anonymous bundle,
distribution, doctor/SDK, fresh example and portable themed UI consumers MUST pass
in one new verification run. Every payload/consumer checkout still uses and checks
the immutable source commit. Record the original publication identity and new
verification driver/run separately, and recheck tag identity. This driver cannot
build replacement release artifacts, assemble or join new public evidence, create
or upload release assets, publish to registries, move a tag or request write
permissions. The original prepublication receipts and aggregate stay unchanged,
including `not_run_at_assembly`; do not relabel them as new-run execution. A
successful supplemental verification completes the postpublication gate, not a
new publication. New publication retains the single-current-run assembly rules
below and all existing mandatory qualification.

Release wiring preserves the existing source, native and UI gates. `build`
transports its verified wheel/sdist/npm and distribution/doctor receipts as
`release-build-inputs`; that early transport is not the final public bundle.
A separate unprivileged `assemble-evidence` job depends on `check`, `build`,
`installed-native` and `ui-qualification`. It downloads only current-run component
artifacts and invokes the reviewed private assembler:

```text
python .github/scripts/assemble_release_evidence.py
  --build-bundle <verified-build-inputs>
  --native-receipt <successful-installed-native-receipt>
  --native-binding <successful-binding-receipt>
  --native-cohort <bound-exact-cohort>
  --native-index <reviewed-companion-index>
  --ui-receipt <successful-full-portable-theme-suite-receipt>
  --consumer-receipt <successful-fresh-extension-consumer-receipt>
  --expected-version <check-version>
  --expected-wheel <build-wheel-filename>
  --expected-wheel-sha256 <build-wheel-digest>
  --output-dir <new-public-stage>
```

The release-evidence schema is versioned independently from the runtime contract.
For package versions through 0.5.x, schema v1 keeps the five exact private build
inputs (wheel, sdist, wheel-carried npm archive, raw distribution-verification
receipt and raw installed doctor receipt) and the sixteen-asset public inventory
described below. For package versions 0.6.0 and later, schema v2 adds a mandatory
UMF qualification receipt bound to the exact final wheel and requires the
seventeen-asset inventory. A v2 release must repeat the UMF gate against the
publicly downloaded wheel; an earlier source or candidate-wheel receipt cannot
substitute. In either schema, validate existing checksums, schemas, identities and
required outcomes before projection. The public bundle preserves the **three binary
artifacts** byte-for-byte; it publishes `distribution-verification.json` and
`doctor-installed.json` as separately versioned, typed, allowlisted public-v1
projections, with schemas `arras.distribution-public-qualification.v1` and
`arras.ui.doctor-public-qualification.v1`, respectively. These public diagnostic
files are not byte copies of their raw producer receipts. Each carries `source_receipt_sha256` binding the unchanged raw
receipt, and the aggregate binds both trusted raw input and emitted public asset
hashes. Original raw receipts remain retained evidence; do not rewrite them or
claim that their public projections are new test executions. A public projection
is never admissible as a raw producer input to the assembler.

Projection retains observed artifact/dependency/runtime identities, case outcomes,
SDK phases and controls within their original capture limits. Omit absolute
checkout, interpreter, import-origin, working-directory, temporary and native
process paths from public diagnostics, including nested consumer package paths.
Record the omission explicitly. Do not replace an omitted path with an invented
fresh-origin or isolation observation, infer a missing Python patch/OS version,
merge component runtimes, or weaken a producer's required checks. For schema v1,
the closed sixteen-file inventory receives a newly computed complete `SHA256SUMS`
and unchanged mandatory workflow gates. Schema v2 adds the safe UMF
qualification projection as the seventeenth asset, bound to the unchanged raw
producer receipt and exact public wheel; the public-download repeat remains a
mandatory gate.

The public comparison helper consumes the aggregate's `version` together with
its canonical `release_artifacts.wheel` filename/digest binding. It refuses absent, malformed
or mismatched identities rather than accepting a legacy top-level wheel key.
Tests must exercise actual assembler output through the public comparison helper,
including wrong version/digest controls, and verify diagnostic omission plus raw/
emitted provenance. Synthetic schemas alone do not establish this agreement.

The owning assembler lane governs its finite safe output inventory and strict
receipt schemas; workflow shell must not fabricate, rename status meanings or
fill absent proof fields to satisfy it. Producer/consumer schema agreement is a
prerequisite to final wiring. The assembler binds the same exact wheel/npm to
all selected component receipts and retains qualified runtime/profile/limit
partitions. Public output includes only the selected artifacts and bounded safe
projections/resources/index/cohort admitted by the reviewed assembler, with a new
exact `SHA256SUMS`. Raw stdout/stderr, PostgreSQL paths/data, credentials and raw
browser reports are retained as CI evidence, never copied into the public stage.
Stage output must be fresh and distinct from its inputs. The job publishes the
stage as current-run `release-assets` and exposes the actual SHA-256 of its
`SHA256SUMS` as a trusted job output. The existing wheel identity remains anchored
to `check`/`build`; assembly cannot select a replacement version or artifact.

`github-release` retains its mandatory source/native/UI/build dependencies and
adds `assemble-evidence`; it uploads only that final safe stage after verifying
its exact checksums. Registry configuration is independent. The assembled
prepublication aggregate explicitly records public-download qualification as not
yet run. It cannot require the later public job, which would create a cycle.

Keep the existing `installed-downstream` reusable-workflow invocation after
GitHub publication: it proves the reusable public consumer job really executes
against the released wheel. Add one distinct, bounded `downloaded-release` job,
with dependencies on `check`, `build`, `assemble-evidence`, `github-release` and
`installed-downstream`, for complete bundle qualification. It downloads the
current run's trusted assembled stage separately from anonymous HTTPS GitHub
Release downloads into a new directory. Download requests use no authorization
header, token, netrc or authenticated `gh` asset command; source checkout access
must not stand in for public asset access. HTTP failures or unavailable assets
fail rather than falling back to Actions artifacts as consumer inputs.

Public `SHA256SUMS` must be byte-identical to the trusted current-run sum file
and match the assembler job's digest before its entries are used. Validate a
bounded strict digest/basename inventory with no duplicate, traversal, alias,
symlink, extra or missing members. The trusted stage itself must pass its sums
and identify the exact expected version/wheel/build digest. Every public asset
must equal the corresponding trusted digest/bytes; do not trust a coherent but
replaced public sums/artifact pair. Independently compare the public npm tarball
to the exact bytes carried by the downloaded wheel. A small private comparison/
download-plan helper is permitted; it has no network, package install, native
runtime or alternate artifact selection. The selected private helper is
`.github/scripts/verify_public_release_assets.py`, with `plan` and `verify` phases
and explicit `--trusted-dir`, `--public-dir`, `--expected-version`,
`--expected-wheel`, `--expected-wheel-sha256`, `--expected-sums-sha256` and
`--output` arguments. `plan` validates the trusted stage plus the anonymously
downloaded sum file and writes only safe newline-separated basenames outside
the public asset directory. `verify` requires the complete exact public inventory,
compares hashes and wheel-carried npm bytes, and writes a bounded identity receipt.
Neither phase may substitute a trusted Actions artifact for missing public bytes.
Network commands use that validated plan with bounded HTTPS-only curl requests
and disabled ambient curl configuration. Reuse existing artifact verifiers rather
than reproducing their wheel/sdist/install/metadata algorithms.

Only after input comparison succeeds, run the existing tools with inputs from
the **public download directory**, never the trusted Actions transport:

```text
python tools/verify_distribution.py --output <post-distribution-receipt> <public-wheel> <public-sdist>
python tools/verify_doctor.py --wheel <public-wheel> --output-json <post-doctor-sdk-receipt>
python tools/verify_extension_host.py --wheel <public-wheel> --output-json <post-consumer-receipt> --fresh-dependencies
npm run qualify:downstream -- <public-wheel>
```

The UI command must include the now-required complete portable themed suite,
in addition to its prebuilt/compiled checker routes. Provision Node/Python,
pinned test peers and Chromium explicitly using the already reviewed bounded
APT/browser setup; no public package tool installs browsers implicitly. Linux
runs all nonvisual projects and reports the visual exclusion. Receipts record
actual interpreters, dependency/tool/browser/platform versions and exact artifact
hashes; workspace-linked dependencies in the distribution verifier are labelled
honestly and do not replace the separate fresh consumer/theme proofs. Native
component success/limits remain linked to the exact prepublication native cohort;
this public job does not claim to rerun a live native deployment.

Retain public input comparison, each generated verifier/consumer/UI receipt,
screenshots and bounded failure logs in an always-run CI artifact under a
separate post-download identity. A final post-download result may say passed
only after all required commands and identity checks succeeded; missing output,
empty tests, a failed command or a skipped required stage fails. This later
receipt remains separate from the immutable prepublication aggregate; do not
rewrite published bundle bytes or invent successful publication/download evidence.
New releases MUST automatically publish the verified Python wheel/sdist to PyPI
and the wheel-carried UI archive to npm after the complete release and anonymous
public-download gates succeed. The publisher MUST bind the original successful
release run, repository, workflow, source, immutable tag, driver and exact asset
digests. A separate registry workflow MUST verify those prerequisites before
requesting publishing authority; it MUST NOT rebuild the payload or execute
untrusted release-source code with publishing credentials.

Publishing uses OpenID Connect (OIDC), constrained to the repository, publishing
workflow and named registry environment. Missing access fails the affected
publication; it MUST NOT silently skip a required publisher or substitute a
long-lived token. Historical registry deferrals retain their original scope.
An existing version is recoverable only when registry-served files match the
qualified bytes. A conflicting version, failed authentication or indeterminate
network response MUST NOT be treated as an absent version.

PyPI eligibility checks MUST reject direct-URL dependencies, including optional
extras, before release publication. Metadata changes require a new qualified
version; a publisher MUST NOT strip dependencies or upload an undisclosed
same-version variant. After upload, verify anonymous registry-served digests and
a fresh isolated registry installation with explicit consumer checks. Record
registry delivery separately from GitHub publication and native qualification.

Plain-index PyPI delivery qualifies the base package. An optional extra whose
upstream dependencies are not on PyPI MUST document its qualified wheelhouse
route and retain the exact upstream digests. Version-only dependency metadata
MUST NOT imply plain-index availability of those extras. Keep their separate
installed-cohort qualification; do not remove supported features or adopt a new
upstream producer solely to make an upload succeed.

Workflow tests check the actual dependency graph and exact tool/input wiring.
Execute the actual extracted comparison/download shell with temporary trusted/
public fixture bytes and a local network-command stub: an honest match succeeds;
a changed asset, replaced sums-plus-assets pair, wrong expected wheel digest,
unsafe/missing/duplicate inventory and wheel/npm mismatch fail before any verifier
runs. A verifier failure must keep the public job failing while retaining evidence.
The assembler owner tests its separate receipt/schema/projection logic; do not
replace those tests with workflow string matching or duplicate their implementation.

### Distribution naming values and host composition — EX-02

`arras.distribution.DistributionConfig` is an immutable value object. It reads no
file, environment, credential, registry or backend. `Brand` remains one class,
with the existing fields, validation, defaults and runtime serialization;
`arras.ui.Brand` MUST remain the same class as any leaf-module reexport.
Extracting that value into a standard-library-only leaf module MUST NOT create a
second brand model or make configuration import a UI host or transport.

| Field | Type / default | Rules |
| --- | --- | --- |
| `brand` | existing `Brand`, default `Brand()` | Existing name/title/wordmark/tagline/logo rules and caps apply. The UI receives this value through its existing escaped runtime meta tag; no frontend rebuild is required. |
| `mcp_server_name` | `str`, default `"arras"` | A nonempty plain-text display name, at most 80 UTF-16 code units after trimming; refuse control characters. It names MCP serverInfo and grants no identity or permission. |
| `mcp_tool_prefix` | `str`, default `""` | Empty preserves existing wire tool names. Otherwise `[a-z][a-z0-9_]{0,15}`; exposure is `<prefix>_<existing-tool-name>` under CONTRACT-007. |
| `env_prefix` | `str`, default `"ARRAS"` | At most 32 ASCII characters, matching `[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*`. This is an explicit launcher bootstrap argument, never inferred from a product name, token or document and never changed by a loaded configuration file. |
| `telemetry` | frozen `TelemetryNames`, default `TelemetryNames()` | Bounded non-secret signal naming values; exact projection/provider requirements below. |

`Config.from_env(env=None, *, distribution=None)` in the existing typed process
configuration boundary accepts this object as its bootstrap defaults and exposes
the effective immutable value as `Config.distribution`. Presentation fields may
be overridden by committed configuration as CONTRACT-007 specifies; `env_prefix`
remains the launcher-selected value. Unknown fields or unusable values refuse
startup by field/key name without echoing the value.

A host MAY pass `distribution=...` to `arras.ui.create_app` and development-host
construction. Its `brand` supplies page title, wordmark and product-bearing UI
labels and development banner. Existing explicit `brand=` remains supported;
when supplied together it overrides `distribution.brand` for that UI instance.
This does not change authorization callbacks, endpoints, resource imports or
backend configuration. The host obtains one effective configuration and passes
its values to its surfaces; surfaces MUST NOT independently read the environment.

`arras.devhost.main(argv=None, *, distribution=None, telemetry_factory=None) -> None` is the explicit
development-only callable launcher. It accepts the existing argv flags and the
same immutable distribution value, forwards it to DevHost construction and the
runtime UI, and uses its Brand for a printable development startup banner and
human help description. The canonical program invocation remains
`python -m arras.devhost`; default behavior and all existing flags are unchanged.
This is a development-tool seam, not an import for a production host. Mocked
uvicorn tests must assert the exact selected value reaches the constructed app
and banner without starting a database or server.

`arras.mcp.launch(argv=None, *, distribution=None, telemetry_factory=None) -> None` is the supported
callable launcher for a thin downstream command. `argv` is a sequence of strings,
or the process arguments when absent. It supports only `-h`/`--help` in this cut;
help exits 0 before configuration/credential reads, unknown options exit 2, and
normal operation preserves CONTRACT-007 framing, lifecycle and person-token
semantics. The human help description and diagnostic/banner label use the explicit
bootstrap `distribution.brand.name` before configuration is loaded, and the
effective `Config.distribution.brand.name` after a successful load. Keep the
canonical `arras.mcp` invocation in `argparse`'s program name and actual package
installation guidance. A downstream shim owns its command's help wrapper.
Default distribution behavior retains existing default labels; custom branding
uses product-neutral key-error wording rather than naming another product.
Diagnostic labels are reduced to one printable line without altering the Brand
value used by UI rendering. Credential values and unknown argument values are
never echoed. Canonical signal definitions retain their identities; the optional
scoped output projection below supplies explicitly selected downstream names.
The launcher uses the same typed reader and implementation as
`python -m arras.mcp`, whose default behavior is unchanged. Launching accepts no
Python module path, plugin path, executable string or caller-supplied principal.

The catalog distinguishes the MCP binding's public exports from the narrower
symbols a host-owned distribution command may import. Its additive
`python.launcher_modules` mapping is exactly `{"arras.mcp": ["launch"]}` for this
cut. Each entry must name an already-declared module and a subset of that module's
catalogued names. The host boundary combines these selected names with its normal
host-module surface; it MUST NOT widen the subset to every export of an MCP
module. Thus `from arras.mcp import launch`, `import arras.mcp` followed by
`arras.mcp.launch`, and `from arras import mcp` followed by `mcp.launch` are accepted
for explicit command composition. `McpServer`, `TokenSource`,
`principal_from_token`, `serve`, and direct imports/attributes of MCP server,
process, identity or backend implementation modules remain outside this host
launcher permission. No executable plugin lookup or caller-role inference is
introduced. The existing MCP-binding export classification is unchanged.

A concrete host-boundary smoke MUST import every newly selected public seam,
construct valid inert Brand/DistributionConfig/doctor/policy values, and exercise
meaningful public pure calls with synthetic inputs. It also imports/constructs the
public TrussHarness without opening it, separately verifying native SDK laziness.
The smoke must fail if a contract-promised selected import is omitted from the
catalog/boundary even when catalog-versus-source self-parity passes. Negative
controls reject widening/removing the launcher subset and private implementation
imports/attributes. Keep the broader existing adapter and protocol qualification
separate from this import/composition proof.

Canonical imports (`arras`), contract/vocabulary IDs, qualified module/action
IDs, graph format, error codes, CSS classes/tokens and tracer instrumentation
scope remain unchanged. CONTRACT-008 keeps canonical event/attribute definitions
and permits only the explicit scoped output projection specified below. The host
owns its telemetry Resource service name and provider. Human-facing configuration errors
may use product-neutral wording. Installation guidance continues to name the
actual Arras distribution and extra rather than invent a renamed package.

Example (all new callable/value names are specified here before implementation):

```python
from arras.distribution import DistributionConfig
from arras.mcp import launch
from arras.ui import Brand

launch(distribution=DistributionConfig(
    brand=Brand(name="Example Distribution"),
    mcp_server_name="Example Distribution",
    mcp_tool_prefix="example",
    env_prefix="EXAMPLE",
))
```

Validation MUST cover the unchanged default path, the shared Brand class,
immutable values without import-time configuration I/O, a thin installed shim,
runtime UI presentation, startup/help/errors, alias credential conflicts and
unchanged canonical styles and default instrumentation, plus scoped projection
qualification below. Add exact public names and signatures
to the reviewed catalog in the same implementation change. These are additive
optional interfaces under lifecycle v2; no existing contract integer is bumped.

### Scoped telemetry naming and caller-owned providers — required EX-02 acceptance

The opt-in projection below is required to fulfill the downstream naming requirement;
this section binds acceptance and does not claim implementation or qualification.
Canonical-only instrumentation is not a substitute for configurable signal names.
The default output remains byte/shape compatible with CONTRACT-008. No sink,
exporter, collector, service identity, credential or telemetry cache is introduced.

`arras.distribution.TelemetryNames` is a frozen, standard-library-only value with
`service_name: str | None = None`, `attribute_namespace: str = "arras"`,
`log_prefix: str = "arras"` and `event_prefix: str = "arras"`.
`DistributionConfig.telemetry` defaults to `TelemetryNames()`. Each prefix is at
most 64 ASCII characters and matches `[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*`;
`service_name`, when supplied, matches `[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}`.
Refuse wrong types, empty values, controls and surrounding whitespace; do not
normalize or echo invalid values. These are explicit non-secret deployment names,
never inferred from a principal, Brand, module, request or document.

`arras.telemetry.TelemetryContext(names=TelemetryNames(), *,
tracer_provider=None)` is the public scoped composition object. It exposes its
immutable `names`, `activate()` (a synchronous context manager) and
`wrap_asgi(app)` (an ASGI callable wrapper with no framework dependency).
The optional caller-owned provider follows the OpenTelemetry `TracerProvider`
API (`get_tracer`). An explicit `service_name` requires an explicit provider
whose public `resource.attributes["service.name"]` equals that name. Missing,
unreadable or mismatched Resource information refuses context construction with
`ValueError` and a safe field/reason only. A span attribute named `service.name`
does not satisfy this check. The host constructs/configures the SDK, Resource,
exporters and shutdown; Arras neither sets a global provider nor shuts it down.
With no explicit service name/provider, retain the previous optional global API
fallback. With an explicit provider, a provider failure must never fall back to a
different global provider or host. Runtime emission failures remain isolated as
CONTRACT-008 requires; construction/configuration errors refuse before work.

`activate()` uses context-local tokens, restores the previous context on normal
exit and every exception, and supports nesting and concurrent async tasks.
Every observed operation snapshots its context at start and uses that same
context when it finishes, even if an inner context changes. No process-global
logger factory/filter, provider setter or mutable namespace is permitted.
`wrap_asgi` activates for the entire awaited ASGI invocation, including streamed
sends and background work awaited by that invocation, and always resets afterward.
Arras-owned executor submissions must carry a fresh copied context into the
worker (`copy_context().run` or equivalent), including principal/operator hooks and
console/operator execution; an ASGI wrapper alone does not propagate ContextVars
through `run_in_executor`. Preserve existing admission, shielding and cancellation
semantics. Tasks or threads outliving the invocation that belong to an external
host must be explicitly activated by that host; automatic propagation to arbitrary
detached work is not promised.

`arras.mcp.launch` and `arras.devhost.main` add the optional keyword
`telemetry_factory: Callable[[TelemetryNames], TelemetryContext] | None = None`.
The factory receives the validated **effective** names exactly once after the
existing configuration/argument validation and before backend construction,
token-source construction, seeding or server startup. No factory runs for help,
invalid arguments or invalid configuration. Even without a factory the launcher
constructs a default context from the selected names, so configured aliases take
effect and a custom service name without a matching provider refuses startup.
A factory exception, wrong return type or unequal returned names refuses startup
with a generic telemetry-configuration diagnostic, never its exception text.
MCP uses the effective `Config.distribution`; devhost uses the explicit selected
distribution. The context encloses startup/build and the complete serve lifetime.

`McpServer`, `arras.ui.create_app`/`UI`, and `DevHost` add optional
`telemetry_context=None`. MCP handles each complete frame in its selected context;
UI and DevHost activate around complete ASGI dispatch, including control routes.
Where a distribution is explicitly supplied its names must equal the context's;
a direct UI host supplying only a context selects that context's names. Absent a
context, derive one from the supplied/default distribution. Existing standalone
console/operator/schema apps remain composable with `context.wrap_asgi(app)`;
no extra binding-specific reader is added. `devhost.build` retains its signature;
a direct caller activates its chosen context around build/library calls. Nested
wrappers must not duplicate events or spans.

The public catalog MUST add exactly `TelemetryNames` to `arras.distribution` and
`TelemetryContext` alongside `dropped` to `arras.telemetry`, their constructors,
`TelemetryContext.activate`/`wrap_asgi` signatures, the new optional launcher/host
parameters and committed naming keys. Existing launcher-only permissions remain
narrow; no emitter, logger proxy, operation object or provider/exporter internals
become host API. Doctor reuses these value validators and reports malformed
names as `distribution_invalid`; its offline check must never construct a
provider, invoke a factory or claim service Resource/receiver qualification.
CONTRACT-008 and TP-001 bind default, SDK receiver, redaction, failure, concurrency
and fresh installed no-fork consumer acceptance. This seam remains unqualified
until that evidence exists, independently of native cohort/release qualification.

### Runtime UI asset bundles and downstream themes — EX-03

The frontend is independently consumable as the public compiled npm artifact and
as an inert, versioned page asset bundle. A repository move or separate Python UI
wheel is not required. The first release keeps UI/Python package versions equal;
a future independent frontend release must declare compatible contract versions
and pass the same consumer gates rather than assume equal versions imply support.

`arras.ui.create_app` accepts optional `asset_manifest: Path | None = None` and
`theme_manifest: Path | None = None`. With no explicit page manifest, use
`static_dir / "asset-manifest.json"`; an explicit page manifest selects its own
parent as the page asset root. A conflicting nondefault `static_dir` refuses.
The source-checkout missing-build page may still return 503 when no page exists;
a page that exists must not be served as a qualified bundle with a missing or
invalid manifest. An explicitly supplied missing/invalid page or theme manifest
refuses construction with `ValueError`, naming the file/key and safe reason only.
The existing `brand`/distribution branding and all authentication callbacks are
unchanged. Module documents never select assets, fonts, stylesheets or widgets.

`arras.ui.assets.load_manifest(path: Path, *, kind: Literal["page", "theme"])
-> AssetManifest` is the explicit host/doctor validation entrypoint. Its return
value is immutable validated metadata; it reads only the named manifest and
listed files under its parent and makes no network request. The deliberate
`arras.ui.assets` host-module surface is exactly `load_manifest` and
`AssetManifest`; record the loader's positional `path` and required keyword-only
`kind` signature in the public callable catalog. The exported result type supports
typing and read-only inspection of loader results, not a promise that direct
construction validates arbitrary supplied mappings. Constants, cohort/byte-serving
helpers and private parser utilities are not promoted by this module export. `AssetManifest`
exposes `kind`, `version`, `package`, `contracts`, `files`, `entry` and
`manifest_sha256` as read-only values. It is not a plugin loader.

The UTF-8 JSON manifest has this exact v1 envelope; unknown keys/versions,
duplicate JSON keys and wrong types refuse:

```json
{
  "format": "arras.ui.assets",
  "version": 1,
  "kind": "page",
  "package": {"name": "@documentdrivendx/arras-ui", "version": "0.5.0"},
  "contracts": {"console": 2, "operate": 2, "schema": 1, "browser": 1},
  "schema_browser": {"name": "<locked schema-browser package>", "version": "<exact locked version>", "integrity": "<lockfile integrity>"},
  "entry": {"html": "embed.html"},
  "files": {
    "embed.html": {"sha256": "<64 lowercase hex characters>", "size": 123, "mime": "text/html"}
  }
}
```

`package.name`/`version` are nonempty strings of at most 128 ASCII characters.
The generated page bundle records the actual compiled UI package version and
exact schema-browser dependency name/version/integrity in an additional required
`schema_browser: {name, version, integrity}` object. Its `contracts` values are
integers the serving runtime supports; an incompatible package/contract cohort
refuses before serving. Page entry is exactly `{html: <listed HTML path>}`.
The manifest itself is not a hashed member of `files`.

A theme bundle uses the same envelope with `kind: "theme"`, its own package
identity, `contracts` matching its supported Arras surfaces, and
`entry: {stylesheet: <listed CSS path>, fonts?: [<listed font paths>],
favicon?: <listed image path>}`. It additionally requires
`ui_versions: [<exact compatible UI versions>]`, a nonempty unique string list;
the active page package version must be listed. A theme has no HTML/JavaScript
entry, executable widget reference or schema_browser field. The stylesheet and
optional font/favicon are trusted host-supplied assets, not module input.

Manifest input is bounded to 1 MiB and 10,000 file entries; each file to 32 MiB
and total listed bytes to 64 MiB. Paths are canonical relative POSIX paths with
no empty/dot/parent segments, backslashes, query/fragment, URL scheme or leading
slash. Resolve each real target under the manifest's real parent; a symlink
escape, nonregular file, duplicate normalized path, missing file, digest/size
mismatch or unsupported MIME refuses. MIME is selected from HTML, JavaScript,
CSS, JSON, SVG/PNG/JPEG/WebP/ICO images and WOFF/WOFF2 fonts; kind/entry extension
and declared MIME must agree. The canonical MIME values are `text/html`,
`text/javascript` (`.js`/`.mjs`), `text/css`, `application/json`,
`image/svg+xml`, `image/png`, `image/jpeg` (`.jpg`/`.jpeg`), `image/webp`,
`image/x-icon`, `font/woff` and `font/woff2`, respectively. Validation precedes hosting, and serving must not
return bytes changed since validation without validating them again.

Serve only declared members. Theme assets use same-origin URLs under
`<base>/theme-assets/<manifest_sha256>/<path>` and never expose arbitrary files
beside a manifest. Add an external stylesheet link after the page's built-in
styles, optional favicon link and allowed font sources; never inject script or
inline style. Preserve the existing escaped Brand meta path. CSP remains
same-origin for scripts/styles/connections/frames; fonts are allowed from self
only when declared. Existing explicitly allowed HTTPS Brand wordmarks remain a
separate rule; theme manifests cannot broaden origins. Digest-addressed assets
may use `public, max-age=31536000, immutable`; other asset URLs revalidate and
HTML uses `no-store`. All paths work under base_path and ASGI root_path.

Two downstream routes are supported:

- A host-built UI imports the public npm components/provider and its own theme
  package, supplies any of the six widgets including Mark, and includes its CSS,
  fonts, light/dark values and favicon. React/ReactDOM remain single host peers;
  downstream private design-system dependencies never enter Arras metadata.
- A prebuilt page uses the theme manifest for CSS tokens/fonts/favicon and the
  existing Brand name/title/wordmark/mark selection. It uses built-in widgets;
  replacing React widgets requires the host-build route, not runtime code loading.

The neutral downstream proof includes an actual consumer-owned theme package,
not only inline widget functions or a stylesheet directory. Its minimal shape is:

```text
theme-package/
  package.json           # own identity, public exports and peers
  src/index.tsx          # six widget overrides/Mark and provider
  src/theme.css          # eighteen canonical role tokens, light/dark
  assets/favicon.svg     # optional owned fonts/images alongside it
  dist/                  # compiled JS, declarations and exported CSS/assets
```

The package root exports compiled widget/provider values plus declarations;
`./styles.css` and any public asset paths are explicit exports. React is one host
peer, and the public Arras UI is a peer where imported by the theme; declare
ReactDOM only if the theme uses it. Do not bundle another React or require an
upstream private design-system dependency. Pack the theme deterministically and
consume that package together with the wheel-carried Arras npm tarball from an
external host directory through bare public imports. The host must not import
theme source paths or define substitute inline widgets to bypass package proof.
No registry publication is required for this neutral qualification fixture.
The runtime-theme manifest builder uses CSS/font/favicon from that same packed
consumer package, records the theme's own package name/version and exact supported
UI versions, and preserves digest/MIME bounds. This links both delivery routes to
one owned appearance package. A separate package-source fixture alone does not
prove its packed exports, peer behavior or declarations.

Arras retains layout, routing, dialogs and focus orchestration. A replacement
widget must honor labels, descriptions, refs, busy/disabled/error state and
keyboard behavior. The host owns appearance; the library installs no theme or
preference on an embedding document. All eighteen role tokens retain canonical
names and defaults.

The reusable synthetic downstream UI/theme consumer must consume the wheel's own
npm bytes/catalog and manifest, with public UI imports and no registry-only
design-system dependency. The standard upstream acceptance backend may use its
private development fixture internally as specified below; that is not public-only
consumer composition evidence or a promoted runtime API. It proves a compiled six-widget/Mark theme and a
runtime CSS/font/favicon theme in a real browser, both light/dark. Test all
applicable color pairs/states at 4.5:1 for normal text and 3:1 for controls/focus,
validate noncolor token CSS values, and run axe plus keyboard/focus assertions.
A root hook probe or static shared chunk is not proof that internal browser and
console widgets consume the replacement. Keep reviewed visual baselines per
theme/platform; macOS baselines run on macOS and Linux CI runs the nonvisual
projects. Incompatible/tampered/missing assets and traversal/symlink negatives
must refuse, including mounted paths. Record the actual browser/package cohort.

### Packed public UI qualification runner — EX-03/EX-07

The existing public npm artifact carries
`support/qualify-downstream-theme.mjs` and `support/QUALIFICATION.md`, with
`bin: {"arras-ui-qualify": "./support/qualify-downstream-theme.mjs"}`. Keep the
existing browser runtime/type/style export subpaths unchanged. This is a Node 24
qualification tool; it is not imported into a browser bundle or run on package
installation. The public catalog records the exact bin map, support paths and
SHA256 digests of the packed support bytes. Packing, manifest parity and exact
wheel/npm artifact verification fail on missing or mismatched support content.

The tool's explicit optional test peers are `@playwright/test` 1.63.0 and
`@axe-core/playwright` 4.13.0; optionality and versions are carried by the catalog
and npm peer metadata. Hosts install those dev tools and Chromium separately.
Missing/incompatible peers or a missing browser produce an actionable tool error.
The runner never installs packages, fetches a registry or downloads a browser;
its browser reaches only the requested target and the target's normal resources.
It adds no private design-system dependency and does not bundle another React.

The strict CLI accepts exactly one HTTP(S) target URL and these flags:
`--host-build`, `--console`, `--output <dir>`, `--baselines <dir>`,
`--update-baselines`, and `-h`/`--help`. Unknown options, malformed/repeated value
options, extra positional values and unusable URLs exit 2 without echoing input
values. Reject URL userinfo; reports do not disclose query-string secrets. Help
exits 0 before importing optional tools, creating output directories or launching
a browser. `--output` defaults to a documented child of the current directory;
it retains a versioned JSON report and screenshots after success or failure.
Exit 0 means requested checks passed; exit 1 means qualification/tool capability
failure. No ambient `ARRAS_DOWNSTREAM_*` options are part of the public tool.

Runtime URL mode qualifies the ordinary themed prebuilt UI and its declared
same-origin CSS/favicon asset route. Host-build mode uses documented probe
contract version 1: one `.arras-root` containing a region labelled
`Downstream widget controls` with all six replacement markers
`data-theme-button`, `data-theme-text-field`, `data-theme-text-area`,
`data-theme-select`, `data-theme-notice`, `data-theme-mark`, and a
`[data-arras-app]` subtree holding the actual public app. The actual app must use
the replacement Mark plus an app-owned replacement Button/TextField: open its
Command palette through the normal shortcut, fill its labelled combobox, close
by Escape and verify focus restoration. Showcase-only markers or a root hook
probe do not qualify internal consumption. The fixture supplies a readable
operator as a person; its administrative principal is not a data-reading user.
`--console` selects the offered Operate route; default targets Explore.

In both light/dark schemes, validate the eighteen role-token values by their CSS
categories, applicable text/control/focus contrast, axe and keyboard behavior.
The report identifies package/tool/browser/platform, route/delivery, performed
checks, limitations and visual state. Public fixture docs distinguish a complete
synthetic theme probe from a generic compatibility result for arbitrary markup.
A report never claims all accessibility behavior from token presence alone.

`--baselines` requests reviewed per-theme/route/scheme/platform visual comparison.
On Darwin compare against existing baselines; missing/different images fail.
`--update-baselines` requires an explicit baseline directory and Darwin, and
records creation/update as baseline generation rather than reviewed comparison.
Never rewrite baselines automatically in CI. On Linux run all nonvisual checks
and explicitly mark visual comparison skipped. Without a baseline directory,
retain screenshots and report visual qualification as not performed, not passed.
The external fixture chooses separate output/baseline directories for each theme,
route and scheme so one run cannot silently overwrite another's evidence.

Installed proof invokes the CLI from the wheel-carried packed npm artifact in an
external host with the packed theme and optional test peers, not from `ui/scripts`
or copied repository tests. Build/typecheck that theme and host against the same
packed public declarations, with no source declaration aliases. The Python page
host runs from a fresh selected-wheel environment outside the checkout; report
workspace-linked JS tool dependencies honestly rather than calling them a fresh
registry install. Actual browser execution and retained artifacts qualify this
runner; file presence or Node syntax checking alone does not.

### Portable canonical UI acceptance testkit — required EX-03/EX-07 acceptance

The narrower `arras-ui-qualify` checker does not waive the original requirement
to run Arras's existing Playwright a11y/end-to-end suite against a downstream
theme without copying tests. The public npm package therefore adds exactly these
opt-in subpaths, keeping existing production runtime/type/style entries unchanged:

| Subpath | Export | Boundary |
| --- | --- | --- |
| `@documentdrivendx/arras-ui/testkit` | `createAcceptanceConfig(options)` plus `AcceptanceConfigOptions` (type) | Node-only Playwright configuration factory; never a production/browser import |
| `@documentdrivendx/arras-ui/testkit/host` | `AcceptanceHost()` | Browser acceptance-fixture component reusing the canonical development-host toolbar/shell; no Node or Playwright in its browser graph |

The factory takes one strict object with required `baseURL: string`,
`schemaBaseURL: string`, `outputDir: string`, and optional `themeId: string =
"default"`, `expectedBrand` (existing Brand shape, default `{name: "Arras"}`),
`expectedSurface: {light: string, dark: string}` and `baselineDir: string`.
Unknown keys, wrong types, empty values and unsafe URLs refuse configuration.
Both URLs are credential/query/fragment-free HTTP(S) root origins with no path
prefix in acceptance profile v1, and must differ because schema-administration
mutates its own isolated fixture. Reject unsupported prefixes rather than silently
throwing them away. This profile limitation does not limit mounted production UI
support. `themeId` is a non-secret label matching
`[A-Za-z0-9][A-Za-z0-9._-]{0,63}` and never selects imports or a filesystem path.
Output/baseline directories are explicit host-owned paths. Color expectations
are opaque `rgb(r, g, b)` strings with integer channels from 0 through 255; normalize
spacing before exact computed-color comparison. Use the existing documented
default surfaces when omitted.
The selected expected Brand and surfaces parameterize the existing exact assertions,
not exemptions from them. Hosts provide expectations matching their selected theme.

The returned config points at the **same canonical** specs/helpers/resources used
by the source suite. It requires all existing nonvisual projects (`chromium`,
`schema-admin`, `browser`) without caller-supplied test filtering, skip lists,
selector scripts or assertion callbacks. On Darwin it also runs the existing
visual project with an explicit per-theme `baselineDir`; absent/missing/different
baselines fail. Other platforms omit only the visual project and report that fact.
No automatic baseline rewrite is enabled. Generating/updating snapshots is an
explicit developer Playwright action in a selected directory and is never an
automatic CI recovery. Retain each test's viewport, contrast, incomplete-review,
iframe, source-asset, keyboard, refusal, request-recording and visual assertions.

`AcceptanceHost()` is for the standard synthetic upstream acceptance fixture,
not application hosting. It reads the existing runtime Brand metadata and reuses
`src/dev/DevHost` so the Person toolbar, role choices and API/header behavior stay
identical. A downstream wraps it in its packed design-system/theme provider and
imports its theme CSS using public exports. This component neither installs a
theme nor bundles React. Theme/provider contexts must be shared with production
entrypoints through the same packed React peer/context chunks. Keep the two
Node/browser subpaths separate so optional test tooling never becomes a required
production import. The host controls document title/Brand metadata through the
existing Python/ASGI composition rather than an executable metadata hook. Build
the external AcceptanceHost/theme to static output, then serve that directory
with the public `arras.devhost.main`/`--ui` on each distinct fixture port. UI and
API then share an origin under existing origin rules; an arbitrary Vite proxy
origin is not implicitly admitted. This is a development acceptance fixture, not
qualification of the production asset-manifest route, which remains separately
covered by the prebuilt-page/runtime-theme checks.

The acceptance backend is the explicitly selected standard upstream sandbox/dev
fixture, with its synthetic catalog, people and `/api/dev/control` contract; it
may use Arras's private development helpers internally. This does not promote
Sandbox or test controls to production API, require consumer data, or replace the
separate public-only module/seed/graph composition proof. The host starts fresh
main/schema acceptance servers and builds its overlay explicitly. The testkit
never starts a source-checkout server, installs dependencies/browsers, resets an
arbitrary application database or discovers plugins by name. A host with a
different application layout runs its own tests in addition to this standard
acceptance profile; token/checker success is not full-suite success.

Pack the canonical specs and the exact bounded resources/helpers they require:
example catalog document/seed, conformance module document, scheme vectors,
shared test narrowing/vocabulary values, and schema-browser release/asset facts.
Resolve resources relative to shipped package bytes or the exact declared
schema-browser dependency, not `../..` checkout paths, fixed ports or a source
`ui/dist`. Canonical tests resolve selected origins, fixture paths, expected
Brand/surfaces and outputs through shared typed helpers. The source
`playwright.config.ts` calls the same factory and may add its own explicit source
web-server setup; no second rewritten acceptance suite is allowed. Build-stage
copies into the npm artifact are packaging of that canonical source, not a
consumer-maintained test copy. Preserve licenses and provenance of all resources.

The public catalog records both subpaths, runtime/declaration exports, option
surface, optional Playwright/axe peers, canonical spec inventory and shipped
resource/support digests. Packing/exact-artifact verification must fail closed
on missing, tampered, extra or aliased listed resources and source/packed spec
drift. Production entry imports must still work without optional test peers.
The public manifest must not turn all development components/helpers into exports.

Acceptance executes the packed testkit outside the checkout against a host build
from the wheel-carried npm package plus packed neutral theme. Use independently
started standard/schema fixtures, real Chromium, all canonical nonvisual tests
and, on Darwin, reviewed per-theme existing visual baselines. Record actual test
counts per project, zero unexpected skips, exact wheel/npm/theme/testkit/resource
hashes and Node/Playwright/axe/browser/platform versions. Compare packed inventory
and discovered tests to canonical source expectations; an empty or selected subset
must not pass as full-suite qualification. Negative controls execute missing/
changed fixture resources, invalid origin/options and a controlled failing
assertion/fixture; each must fail rather than silently skip. This is a required
release gate in addition to the narrower checker, pending implementation and
actual qualified evidence. Source inspection or a default-theme source run cannot
substitute for the packed themed run.

## Normative Surface

| Element | Type / Shape | Required | Rules | Notes |
|---------|---------------|----------|-------|-------|
| `ConnectionSource` | `Callable[[Principal], ContextManager[psycopg.Connection]]` | for the Truss adapter | Each call MUST yield a connection to the adapter's database authenticated as that principal, with the principal's own token (ADR-017), closed or returned on exit. The host owns pooling and credential refresh, supplying the person's current credential for each newly acquired connection (ADR-017). Arras MUST NOT read ambient connection variables, create connections itself, or reuse a connection across principals. Connections MUST arrive idle, with autocommit off (psycopg's default), no open transaction, and the session role unset (`SET ROLE` is `none`), and the session authorization unchanged: a source MUST NOT run `SET SESSION AUTHORIZATION`, which only a superuser login may and which the adapter does not check for (it reads `current_setting('role')` only, so a service login switched to a person's authorization would pass), because Postgres gives no portable way to compare the session user with the login identity. A host that connects as a superuser is outside the model: the database's own grants are what bound a person, and a superuser has them all. The adapter sets the isolation level and access mode it needs on each transaction (`SET TRANSACTION`, its first statement, in the transaction the driver opens with it), sets `statement_timeout` with `SET LOCAL` (1 to 60,000 ms, as Truss requires before it adopts the connection; the host sets it with `statement_timeout_ms` on `create_backend`, default 10,000, and an import needs it at or above about 5,000 ms for each 32-record chunk, because Truss's deferred constraint check runs as a single statement at the commit and the adapter does not validate that floor), and MUST commit or roll back every transaction it opens and MUST NOT leave session state: it uses no session-level `SET`, no `conn.read_only` and no `SET ROLE`. When Truss reports a connection quarantined (its `detach()` returns false, or a call reports the transaction unusable), Arras closes that connection and the host's pool MUST discard a closed connection and never return it to service, because Truss keeps the quarantine on the connection object. Arras MUST work whether or not the connection prepares statements; a host behind a transaction-mode pooler MAY disable preparing (`prepare_threshold=None`). | What a person may read or write is what Postgres grants that person's role: membership in a module's reader and writer roles, and registrar membership to register, each granted by the database administrator with `WITH SET FALSE`. Arras holds no mapping from people to roles. |
| Installing connection | `Callable[[], ContextManager[psycopg.Connection]]`, a trusted connection that is not a person's | for the Truss adapter, to install or verify | Used only by install-or-verify, module-access configuration and the install-state read behind `status()`, never to serve a read, an action, a registration or an import. Its role needs `CREATEROLE` and `CREATE` on the database with grant option (or ownership of it), and need not be a superuser. Truss refuses business calls from an elevated installer and from members of its owner role, so it MUST NOT also be a person's connection or the registrar. Install reports the owner and registrar role names, which are generated and not guessable, in `migrate()`'s result (below); the adapter's `install_roles()` reads them again on this connection, through Truss's administrator-only install recovery, for a host that did not keep them. Module access (a module's reader and writer role names and, optionally, its auditor role, which the host supplies and which must already exist as distinct non-login roles with no privilege on Truss) is configured on this connection once the module is registered, because Truss refuses the grant for a module it has not accepted: a refused batch is Truss's typed `ModuleAccessBatchRefused` with the codes of what it refused (`unknown_module`, `unknown_role`, `unsafe_role`, `duplicate_selection`) and changes nothing, never read as a grant. The auditor role is Truss's separate audit grant (`ModuleAuditGrant`): it lets a person read the module's `changes` and `loads` without reading or writing its data, and is given in the same transaction as the module's access, which is rolled back whole when either is refused. `migrate()` does not grant module access; the adapter's `configure_access(modules=None, *, timeout=None)` does, one module per locked transaction in the order given, after registration, stopping at the first refusal (`migration_failed`, the detail naming that module; earlier modules stay configured). Grants persist in Truss, so the call is a configuration step needed only when a module is new or its roles change, not a start step. Until then no person can read or write the module. | The host supplies the role names; Arras holds no role map beyond handing the host's names to Truss. |
| `WarehouseSource` | `Callable[[Principal], ContextManager[WarehouseConnection]]` | for the Ashlar adapter | A Databricks SQL warehouse connection acting with the principal's own token. Arras MUST NOT use a service identity for a user's read. | |
| Administrative principal | `Principal` with `admin=True`, supplied to `start` as `admin=`; once named, only that principal (by user and token) is the administrator and the flag on any other is ignored, and it is refused for every read and action, flag or not | for `register`, `attach`, `bind_handler`, `import_records` (a person with the `schema` grant may also register and validate, as themselves, through `session.schema()`; ADR-026) | The only principal that Arras connects with for attachment, handler binding and imports, and the one that registers at startup; a person registers as themselves under the backend's `schema` grant (ADR-026). It is explicit and the host chooses it (a deploy identity or an operator's own token). It never installs the store (that is the installing connection's). On the Truss adapter it is an ordinary person role holding registrar membership and the writer role of the modules it imports into, and it is never an elevated installer. It is never used to serve a read or an action. `Ontology.registry()` is called only by this principal, at startup (CONTRACT-002). | |
| `Arras.start(backends, *, placement=None, default_placement=None, expected=(), wait_bound=0.0, admin=None, metadata_profile="legacy-arras/1")` over adapters, which the host registers under names it chooses (`{"<name>": backend}`, each matching `[a-z][a-z0-9_]{0,40}`; Arras defines none). The Truss adapter's factory, `arras.adapters.truss.create_backend(name, source, installing=None, *, module_access=None)`, takes the name it will be registered under (the adapter reports it in `BackendInfo.name`, `Revision` and `Freshness`; a name that does not match is a `ValueError`), the per-person `ConnectionSource`, the installing connection and, per module, the host's `ModuleAccess(document_id, reader_role, writer_role, auditor_role=None)`; it never connects, imports Truss or reads the environment | `-> Arras` | yes | `placement={"<module>": Placement(record, replicas, providers)}` and `default_placement` are the host's statement of where each module lives (CONTRACT-002); a module with neither is refused as `invalid_placement` at `register` or `attach`. `expected` is the set of configured backend names; a name that is in `expected` and has no backend is `not_configured`. MUST NOT raise for any availability failure; it returns an instance whose `status()` reports each backend. A host that wants an install at start calls `migrate()` itself, and the only bound on install is `migrate(*, timeout: float | None = None)`, in seconds: Arras sets `lock_timeout` and `statement_timeout` on the installing connection from it and reports `migration_failed` with detail `timeout` when it elapses; with `None` it waits. `start` itself does not install and needs no budget; a host that wants a bound passes `timeout`. Module reader and writer role names are the host's, supplied as `module_access` to the factory. A backend whose source is `None` is `not_configured`. | |
| `Arras.status()` | `-> Status` | yes | `Status` maps each backend name to `BackendStatus` (CONTRACT-004): `available`, `reason` (`not_configured`, `unreachable`, `access_denied`, `migration_failed`, `unsupported_version`) or `None`, `detail`, and for a replica its position and lag. `reason` is `None` iff `available`. | `detail` MUST NOT contain credentials. |
| `Arras.refresh()` | `-> Status` | yes | Probes each backend. Nothing is cached: `status()` is as live as `refresh()`, and an unavailable backend is probed again by the next operation and reported available once it is usable. An adapter that pools connections MAY throttle its own probe to once every 5 seconds. | A transient fault at start does not disable a backend until restart. |
| `Arras.migrate(*, timeout: float | None = None)` | `-> MigrationResult` | yes | Install-or-verify of each adapter that has a store to install (the Truss adapter), on the installing connection and with no person. It takes `pg_advisory_xact_lock` inside its own transaction, then reads Truss's install status: an absent Truss is installed; a present Truss of the pinned release is verified and left alone; a present Truss of another release is `unsupported_version`. The decision comes from the status read, never from parsing an install error. `MigrationResult` has `ran: bool` (true only when this call installed), `revision: str` (Truss's release id), and `owner_role: str | None` and `registrar_role: str | None`, set only when `ran` is true: Truss reports them once, from the installation result, and a later status read does not repeat them. The host SHOULD persist them, because granting registrar membership to the administrative principal and to people needs the registrar name; if it did not, `TrussBackend.install_roles()` recovers both names on the installing connection (a refusal is `Unavailable` with the reason of Truss's typed refusal). An install Truss refuses before it begins (`InstallRefused`) is mapped by its code and installs nothing: `busy` is `Unavailable(busy)`, `incompatible` and `unsupported_postgres` are `unsupported_version`, `unauthorized` and `read_only` are `access_denied`, `already_installed` means another installer finished first (verified, `ran=False`), and `invalid_roles` and `role_exists` are `migration_failed`. If another instance is installing, this call waits for the lock, finds Truss present and returns `ran=False`. A failure sets the backend to `migration_failed` and raises `Unavailable`; the adapter remembers it, so `status()` reports `migration_failed` while Truss is still absent, until a `migrate` succeeds or Truss is seen installed. An installer role without the privileges above is `access_denied`, not a failed install: a missing database privilege is Truss's `42501`, and a missing `CREATEROLE`, which Truss refuses with its one opaque code, is named from the role's attributes the adapter reads first. A COMMIT of unknown outcome is settled by a status read on a new connection: `ran=True` with the names it holds is returned only when the installed installation id is the one this call's install produced; another id means another instance installed (`ran=False`, no names); absent or unreadable is `migration_failed`, detail `outcome unknown`. A refused or lock-timed-out operation maps `55P03` to `the catalog is busy` for `migrate` and `configure_access` (a concurrent registration). With several backends that migrate, `Arras.migrate` returns the result of the backend that ran (the first, when several did) and a host that needs every role pair calls each adapter's own `migrate`; a backend with no `migrate` is skipped. | Safe to call from every instance at start. Arras performs install-or-verify and does not invoke Truss's forward-migration API or recreate a database. A different installed release returns `unsupported_version`. A database administrator may use the selected Truss 0.0.50 tool's separately documented forward-migration procedure only when the source is eligible; Arras then verifies the pinned release. Arras makes no blanket migration promise. |
| Install lock | Postgres advisory lock in the Truss adapter's database | yes | Concurrent installs MUST be serialized by a transaction-scoped advisory lock (`pg_advisory_xact_lock`) taken inside the install transaction before the status read, so it holds behind a transaction-mode pooler; Truss does not serialize installs itself, and without the lock a losing installer fails. Install and status run as the installing connection. Arras keeps no migration history, schema or version table of its own: the store's layout, its release and its upgrades are Truss's. | A person's connection cannot read Truss's install status (an ordinary member gets a permission error); it can read only Truss's minimal person status (`person_runtime_status_in_transaction`: the installation absent, compatible or incompatible, and the catalog empty, accepted or unknown, for any enrolled reader, writer or auditor), which the adapter asks to tell an empty install from another release. `status()` has no person, so it reads install state on the installing connection only and never probes as a person. |
| Operations when a backend is unavailable | | yes | Every operation that needs an unavailable backend MUST raise `Unavailable(backend, reason, detail)` promptly, with no retry loop, and an operation that does not need it MUST still work. | CONTRACT-001 states which backend each level needs. |
| `Arras.session(principal)` | `-> Ontology` | yes | CONTRACT-001. | |
| `Arras.close()` | `-> None` | yes | Releases anything Arras holds. It does not close the host's pool or connections. | |
| Public names | `arras.__all__` and the deliberate host/launcher module names in the carried public catalog | yes | The host MUST import only its selected catalogued names, including the narrow launcher subset above. Arras MUST NOT import any module of the host. A build check fails on a violation in either direction. | CI check in each repository; concrete promised-seam import/composition smoke. |
| `arras.testing.InMemory()`, `example_module()` | the memory adapter's two backends, `memory` (reader and provider) and `memory_replica` (reader), the people they know, and a `Arras` over them | no (host tests) | The only public way to get in-memory backends; `arras.fakes` is internal. It follows the backend contract and passes its conformance corpus: refusals, freshness, outages and attribution behave as on the other adapters. The replica copies `memory` only on `sync()`. `person(user, module, *modes)` grants access, `register`, `import_records` and `start(backends=...)` act as the administrator, and `set_available(backend, up)` takes a backend down. Access is a grant table, not Postgres roles or Unity Catalog. It places its modules itself (record store `memory`, replica `memory_replica`). | A host's own tests use it; it measures neither latency, migration nor connection sources. |
| `arras.console.create_app(arras, *, principal_for_request, base_path="")` | `-> ASGIApp` | yes (P1) | See CONTRACT-006. | |
| `python -m arras.mcp` | stdio MCP server | no | The only code that reads the environment, in one module (`arras.mcp.config`): it builds a `Arras` from its own configuration and one `Principal` from the user's token. See CONTRACT-007. | A host that embeds the library never goes through it. |

The constructor and `Arras.start` also accept the programmatic keyword
`metadata_profile="legacy-arras/1"`. CONTRACT-002 governs its explicit
`umf-core-metadata/1` opt-in, constructor refusal for unknown values and provider
qualification before acceptance. Construction imports no optional engine and
performs no I/O. This adds no TOML, environment, CLI or automatic profile selection.

### Composed UI schema authorization — EX-04

`arras.ui.create_app(..., authorize_schema=None)` and its `UI` construction path
accept the optional `Callable[[Principal, str], bool]` already supported by
`arras.operate.create_schema_app`. Forward the same callback unchanged to the
mounted schema app. Its second argument is the parsed module name; its principal
is the viewer's authenticated principal, not the installer or administrative
principal. `None` preserves existing behavior and the callback can only narrow
backend authorization. No new policy port, grant model or role cache is added.

Keep CONTRACT-011's order: existing route/origin rules, authentication and
operator refusal precede schema execution; a missing principal is 401 and a
nonoperator is 403 before body/schema-hook evaluation. For an admitted operator,
a malformed document is 400 before the schema hook; false is 403 before calling
the library; an exception is the existing scrubbed 500 with no library call or
state change. A true result still requires the backend's current schema grant.
Pass the callback for both validate and register, including nonempty `base_path`
and ASGI `root_path` hosting. With `authorize_operator=None`, `/api/schema` remains
unmounted even when `authorize_schema` is supplied. Existing public version-route
exceptions and the action callback are unchanged.

### Offline compatibility doctor and per-seam upgrade record — EX-08

The public `arras.doctor` module exposes `DoctorRequest`, `Diagnostic`,
`DoctorReport` and `check(request: DoctorRequest | None = None) -> DoctorReport`.
The executable is `python -m arras.doctor --request <path>`; omitting the request
checks the local carried public catalog and its observable package cohort only.
`--help` exits before reading any request or package configuration. A thin host
shim may construct the typed request and call `check` directly. No plugin loader,
arbitrary Python import, native probe or background service is added.

`DoctorRequest` is an immutable value with these optional fields; collections
are copied and frozen. The CLI accepts an inert UTF-8 JSON object with
`schema_version: 1` plus the same field names. Unknown fields, duplicate keys,
wrong types and unsupported request versions are rejected. Paths are explicit
host-selected local files, never discovered from ambient environment or a
referenced credential value. No request field accepts a credential value.
The request JSON and each committed config file are bounded to 1 MiB before
allocation; each module document to 16 MiB, at most 32 documents/config files
combined and at most 64 MiB of their combined bytes. Use regular-file checks and
bounded reads, including changed-file paths; never truncate a file into a
seemingly valid request. Asset files retain EX-03's own bounds. Exact version
pins are supported; ranges or requested native/write-proof profiles produce
`capability_unsupported` rather than guessing compatibility.

| Field | Type / default | Check |
|---|---|---|
| `expected_packages` | `Mapping[str, str]`, empty | Exact pins for `arras` and the wheel-carried `@documentdrivendx/arras-ui`; unknown package names are unsupported, not dynamically imported |
| `expected_contracts` | `Mapping[str, int]`, empty | Existing runtime contract keys and exact versions, plus catalog contract IDs only where explicitly declared; do not invent runtime keys |
| `required_python_exports` | `Mapping[str, tuple[str, ...]]`, empty | Selected public module and declared symbol names from the carried catalog |
| `required_npm_exports` | `Mapping[str, tuple[str, ...]]`, empty | Carried package export paths and declared symbols, preserving runtime versus type-only classification |
| `required_role_tokens` | `tuple[str, ...]`, empty | Canonical CSS role-token names in the carried catalog |
| `distribution` | `DistributionConfig | None`, `None` | Existing naming/prefix/Brand validation; JSON form uses the same constructor fields and existing Brand fields |
| `env_names` | `tuple[str, ...]`, empty | Explicit environment key names against the canonical and selected alias namespaces; no values are accepted or read |
| `config_files` | `tuple[Path, ...]`, empty | Explicit ordered committed-presentation/development TOML files using ADR-019's existing schema/merge rules, without loading ops configuration or following references |
| `asset_manifest` | `Path | None`, `None` | Existing page manifest validation and supported package/contract cohort |
| `theme_manifest` | `Path | None`, `None` | Existing theme validation, requiring an explicit page manifest to establish the exact UI cohort |
| `module_documents` | `tuple[Path, ...]`, empty | Explicit document bytes through the selected existing validator/profile; no registration, handler execution or placement inference |
| `module_profile` | `str | None`, `None` | Explicit `legacy-arras` or `official-umf` selection for requested document checks |

The selected callable inventory includes `arras.doctor.check(request=None)`,
`arras.policy.PolicyBackend(backend, policy)` and
`arras.policy.PolicyRefused(backend, operation, policy_code)`, alongside the
already-public `arras.conformance.run_corpus(make_harness, *, only=None)` from
CONTRACT-004. These entries record the signatures of already-selected exports;
they add no runtime API or additional dataclass/protocol field mirror. The native
`arras.conformance.truss.TrussHarness()` constructor is likewise catalogued as
accepting no arguments. Private native/checker/value helpers remain nonpublic.

The doctor consumes the carried EX-01 catalog and existing DistributionConfig,
ADR-019 committed-config validators/merger and EX-03 asset validators/cohort
checks. Shared internal validation helpers may be extracted without changing
those contracts. Give the doctor its own checked module-boundary group: permit
foundation/domain read-only values and the exact existing config/asset validator
edges it needs, with negative controls against core mutations, adapters,
connection factories, fakes, host applications and transport/process entrypoints.
Do not weaken every tooling module's import rules to accommodate this one port.
The private implementation split is `arras._doctor_types` for immutable request/
report values and `arras.doctor` for bounded orchestration/CLI. The public names
and signatures stay at `arras.doctor`; the private value helper is not a new
supported import surface. The shared pure committed-document parser is
`arras.mcp.config._parse_committed_document(raw: bytes)`, keeping `tomllib` and
the existing configuration grammar in one owner. The doctor reads only its
explicit bounded regular files before passing bytes to that parser. Exact
module groups, allowed edges and negative controls are specified in Architecture's
"Offline qualification and validation modules" section; the 926-line ceiling,
cycle checks and validator-to-transport prohibitions remain enforced.
Do not implement a second configuration or module grammar in
the doctor, and do not call the process-oriented `Config.from_env` path, which
can select ops/credential files. An ops key in a committed file is diagnosed by
key and rule only; neither the key's value nor a referenced path is followed.
Explicit `env_names` checks validate key spelling/namespace and report possible
source ambiguity. They cannot establish token equality, blankness, expiry,
identity or actual token-versus-file precedence without values; they must not
claim to do so. No `os.environ` scan or token-file read is allowed.

A `legacy-arras` document check runs only the existing Arras reader and reports
its exact core/vocabulary versions and supported subset. This is not official
UMF validity, meaning-preservation or execution qualification. `official-umf`
requires an actual supported official validator API in the installed cohort.
If absent, return a typed unsupported diagnostic; never silently substitute the
legacy reader or equate matching version strings with semantic conformance.
Documents without an explicit profile produce an unsupported-profile diagnostic.
Even a successful offline document check proves no registration, backend grant,
handler execution, source entitlement, native action semantics or rendered-view
support. Other agents may supply the official profile later through its owning
contract; this doctor does not define it by inference.

`DoctorReport` is immutable and serializes through `to_dict()` to
`{schema_version: 1, ok: bool, complete: bool, observed: object,
diagnostics: [...]}`. `Diagnostic` contains `code`, `severity`
(`error`, `unsupported`, `warning`, `info`), `surface`, `path`, and an actionable
safe `message`. Paths identify a request field or caller-selected file, not
input content. `observed` is restricted to safe package/contract/catalog/
profile versions, declared names and execution provenance. Report an installed
package version only when metadata and the loaded package/resource origin agree;
an editable/source checkout is labelled as such and cannot qualify an installed
pin merely by finding unrelated installed metadata. Static catalog declarations
are labelled declared; do not call them executed export, browser or native proof.

Stable diagnostic codes for this request/report version include
`request_invalid`, `catalog_invalid`, `package_missing`, `package_mismatch`,
`contract_mismatch`, `python_export_missing`, `npm_export_missing`,
`role_token_missing`, `distribution_invalid`, `env_name_unknown`,
`credential_sources_possible`, `config_invalid`, `asset_invalid`,
`theme_incompatible`, `module_invalid`, `module_profile_unsupported` and
`capability_unsupported`. Additional codes are additive within report version 1;
existing code meanings and field shapes do not change without a version change.
For these stable codes, `request_invalid` identifies malformed request structure
or CLI syntax: unknown fields, wrong field types, duplicate JSON keys, unsupported
request versions and unsafe request-file reads; its CLI status is 2. This includes
malformed distribution/Brand object shapes. A structurally valid distribution
whose existing Brand, display-name or prefix value constraints fail produces
`distribution_invalid` with severity `error` and CLI status 1. The same code
applies when supported committed `[distribution]` or `[distribution.brand]`
values fail those semantic validators. Unreadable/invalid TOML, unknown or
wrongly typed committed keys and other configuration failures remain
`config_invalid` with status 1. Reuse the existing constructors/validators;
do not duplicate their value grammar. Direct Python construction of an invalid
`Brand`, `DistributionConfig` or `DoctorRequest` continues to raise its constructor
error before `check`; it does not fabricate a report from an invalid typed value.
All returned messages identify the rule/field without echoing the rejected value.

A missing native/official capability is unsupported, not a pass. Never include
exception text, file contents, environment values, credentials or source records
in a diagnostic. Invalid input is actionable by field/rule without echoing it.

The CLI emits exactly one JSON report to stdout and exits 0 when all requested
checks complete without errors/unsupported diagnostics; 1 for incompatibility or
invalid checked artifacts; 2 for malformed CLI/request input; 3 when a requested
capability cannot be qualified. Error 1 takes precedence over unsupported 3 for
mixed checked results. Unknown CLI arguments are rejected without echoing their
values. Reports with any unsupported diagnostics have `complete: false`; `ok`
is true only when all requested checks complete and none is an error. Warnings
alone need not fail a report. No network, subprocess, database connection,
registration, installation, migration, credential refresh or grant mutation is
performed by any doctor path, including error and help paths.

Qualification must run the public function and CLI from a clean installed wheel
outside the source checkout with no source import path. Positive controls pin
the actual installed Python and wheel-carried npm versions, names, contracts,
role tokens, naming configuration and compatible manifests. Negative controls
change one requested export/pin/contract/token/name/theme cohort/config key or
module profile at a time and assert its diagnostic code and CLI status. Spy
controls prove no ambient-secret reads, referenced token-file reads, network,
backend/registration calls or arbitrary imports; fixtures use secret sentinels
and assert report/stdout/stderr redaction. Source-only checks and fake manifests
are useful negative controls but cannot replace actual installed positive proof.

The release changelog has one explicit compatibility entry for each seam:
Python/import exports, contract/wire versions, configuration/env aliases,
Brand/process naming, theme/assets/React peers, UMF/profile support, backend/
credential lifecycle, and external runners/doctor reports. State old/new versions,
unchanged versus breaking behavior, required downstream action, deprecations and
actual observed qualification limits. The final release version is selected by
the release owner; a candidate number is not evidence of publication. A successful
doctor is a static compatibility result, never a substitute for the selected
browser/native/release artifact gates.

### Generic write policy at the backend boundary — EX-04

A host may wrap a backend explicitly with
`arras.policy.PolicyBackend(backend: Backend, policy: WritePolicy)` before passing
it to `Arras.start`. The wrapper is opt-in; omitting it preserves all existing
behavior. It does not load a policy by string, import a host module, inspect
ambient configuration, change placement, or create a principal. The public
`arras.policy` surface is `PolicyBackend`, `PolicyRequest`, `PolicyDecision`,
`PolicyOperation`, `WritePolicy`, `PolicyAnnotationCapabilities` and
`PolicyAnnotationProvider` and `PolicyRefused`. Add these deliberately to the public catalog
and boundary; this section does not promote unrelated implementation helpers.

`WritePolicy` is a callable protocol:
`__call__(request: PolicyRequest) -> PolicyDecision`. Both request and decision
are frozen values. Their nested collections are immutable snapshots, not merely
a frozen dataclass containing mutable dictionaries or lists. The callback is a
trusted host component and receives the exact `Principal` that the backend call
received, including that person's credential; credentials and request payloads
must never appear in representations, diagnostics, logs or telemetry by default.
The wrapper must not substitute an administrator, installer or service identity.

`PolicyRequest` exposes the following typed fields. A field not applicable to an
operation is its stated empty value; there is no executable or importable field.

| Field | Type / empty value | Meaning |
|---|---|---|
| `principal` | `Principal` | The exact caller object; no identity reconstructed from user text |
| `operation` | `PolicyOperation` | One of `apply`, `apply_batch`, `import_records`, `register`, `validate_register`, `attach` |
| `modules` | `tuple[str, ...]` | Distinct canonical module names in first-seen order |
| `dry_run` | `bool` | True for `apply(dry_run=True)` and `validate_register`; false otherwise |
| `plans` | `tuple[Plan, ...]`, `()` | The actual already-resolved action plans, preserving action, preconditions, ordered effects and input digest |
| `records` | `tuple[Mapping[str, object], ...]`, `()` | Exact import records as immutable snapshots |
| `document` | `bytes | None`, `None` | Exact registration document bytes, without reserialization |
| `module` | `ModuleInfo | None`, `None` | The supplied registration/attachment module, deeply immutable |
| `options` | `Mapping[str, object]`, empty | Exact operation options: `idempotency_key`, `atomic`, `stop_on_error`, `load_id`, `initiated_by`, `unknown_endpoint`, `expected_revision`, only where applicable |

`Plan` and `ModuleInfo` retain the semantic shapes already used by the provider
protocol. The callback observes resolved effects, not promised original caller
inputs or source-reference fields that are absent from that protocol. A host may
perform additional source checks through its own person-authorized API. Arras
neither infers those entitlements nor caches that answer. Snapshotting preserves
native scalar values, ordered effects, document bytes and revision semantics;
it must not coerce through JSON or silently drop values. The payload delegated
to the provider must preserve the exact approved snapshot's values and native
container semantics, so mutation of the original caller-owned nested containers
cannot change the approved write. An isolated native-shape copy reconstructed
solely from that snapshot is allowed; object identity is not required. Freezing
must not turn a valid many-valued property into an invalid provider tuple, or
change an original tuple into a list indiscriminately. Callback-visible values
remain immutable, including deletion of fields.
Existing operation bounds still apply; no new workload, source model or durable
state is introduced by this port.

`PolicyDecision(allowed: bool, *, code: str = "policy",
annotations: Mapping[str, str] = {})` is immutable. `allowed` must be a bool;
`code` is a safe stable identifier matching `[a-z][a-z0-9_]{0,63}`, not free-form
exception or source text. Annotation keys follow that identifier rule, with at
most 32 pairs, values at most 1,024 UTF-8 bytes, and at most 16 KiB of combined
UTF-8 key/value bytes. The mapping is copied and frozen. Malformed requests or
decisions, an exception from the callback, or a nondecision return fail closed
before any provider mutation, without including callback text or payload values
in the error. Denial raises `PolicyRefused(backend: str, operation: str,
policy_code: str)`, a subtype of the existing `Refused`. It retains canonical
`reason="no_access"`; `policy_code` uses the same safe identifier grammar as the
decision code and is available to direct Python callers. Define the class in the
leaf errors module and reexport the same class from `arras.policy`; foundation
serializers must not import a backend-heavy policy module. A malformed or throwing
callback uses the constant safe code `policy_error`, never exception text.

Only this validated typed policy refusal adds `policy_code` to existing refused
HTTP/MCP error payloads and GraphQL extensions where interface errors are already
serialized. HTTP `error.type` remains `Refused` (also batch-item refusals), MCP's
canonical result code remains `refused`, GraphQL's `extensions.code` remains
`REFUSED`, and the canonical refusal reason remains `no_access`. Existing messages,
status selection, authentication/operator ordering and backend authority remain
unchanged. This optional field is additive policy metadata, not another public
wire error type. Ordinary native Refused errors have no policy_code. Never add
policy input, annotations, token, callback text or arbitrary exception attributes
to the error body. The port exposes a safe refusal reason without disclosing the
policy's evidence.

The wrapper intercepts every mutating method of the existing Backend/Provider
protocol: `apply` (including dry run), `apply_batch`, `import_records`, `register`,
`validate_register` and catalog `attach`. A batch is evaluated as one request
containing all ordered plans, before delegation of any item; a denied request
commits no item even for a non-atomic batch. A dry run evaluates policy but never
commits. A subsequent apply, retry or idempotent replay evaluates policy again;
a successful earlier validation or decision is not authority for a later call.
A denied current decision also denies access to a stored replay receipt.

An allowed decision with empty annotations delegates once with the same
principal and exact options, and returns the provider's result unchanged. The
provider still enforces its current grants, token expiry, preconditions,
transactional checks, revision and idempotency rules. Policy can narrow access;
it cannot grant it. Read methods forward unchanged. Availability and reader
versus provider roles remain the wrapped backend's; optional lifecycle methods
such as `migrate` are exposed only when the underlying backend supports them.
The wrapper owns no connection, pool or credentials. A direct reference to the
unwrapped backend is outside this wrapper's enforcement: the host must register
only the wrapped instance wherever it requires this policy.

**Optional atomic annotation provider capability.** Empty annotations keep the
ordinary Provider call path unchanged. A denied decision raises `Refused` without
any mutation, whether or not it contains annotation values. An allowed decision
with nonempty annotations requires explicit support for that exact operation;
otherwise raise the existing `Unsupported` before any provider mutation or
ordinary-method delegation, including for dry runs. Never discard annotations
and retry the ordinary method.

`PolicyAnnotationCapabilities(version: int = 1,
operations: frozenset[PolicyOperation] = frozenset())` is a frozen public value.
`version` is exactly integer 1, not bool; operations are a copied frozen set of
known PolicyOperation values. An empty set advertises no support. The optional
public `PolicyAnnotationProvider` protocol consists of the read-only metadata
attribute `policy_annotation_capabilities: PolicyAnnotationCapabilities` and
`apply_with_policy_annotations(request: PolicyRequest, *,
annotations: Mapping[str, str]) -> Receipt | Validation | BatchReceipt |
ImportResult | RegistryResult | RegistrationCheck`. This one explicit native
entrypoint dispatches only the six operations in PolicyOperation, using the
already-approved immutable request; it accepts no principal override, arbitrary
method name or executable callback. Metadata is inert, not a probing operation.
The wrapper checks the descriptor type/version/advertised operation and that the
entrypoint is callable before calling it once instead of the ordinary method.
Malformed, absent or incompatible capability metadata refuses as `Unsupported`.
The returned result must match the ordinary operation's result type/shape; this
port does not change receipts, tokens, revisions, wire codes or operation bounds.

For each committed write group, the provider persists exactly those annotation
pairs atomically with that group's effects and native audit attribution to the
request principal. An annotation failure commits neither effects nor annotations
for that group. Registration/import/attachment annotations bind to that
operation's own native durable unit, not an unrelated action or guessed receipt.
A dry run validates the same capability and rules but persists neither business
state nor annotations. An atomic batch commits all effects and corresponding
annotation records together or nothing. A non-atomic batch may retain earlier
successful groups as its ordinary contract permits; each successful group must
have its own committed annotations and a failed group has neither. It must not
report partial annotation success as a successful group.

A current policy decision is still required before an annotated idempotent
replay. The replay returns the original committed result/annotations without
adding another audit record or relabelling the original write. A different set
of annotations on the same provider-declared idempotency key refuses as the
existing conflict class rather than rewriting history; use a new operation key
for a new write. Import `load_id` remains provenance, not an invented idempotency
key: existing record-identity skip rules and native invocation-audit behavior stay
unchanged. A skipped record's committed annotations are not rewritten; a new
native load/invocation audit unit may carry the current decision's annotations.
Native current-person grants, expiry, revision, preconditions and idempotency
checks remain authoritative. No provider may use an installer/service token or a
cache of policy decisions to implement this capability.

Optional capability forwarding must not bypass another policy wrapper.
`PolicyBackend` does not advertise or blindly forward the underlying annotation
entrypoint/descriptor through `__getattr__`. Annotation-required nested wrappers
are `Unsupported` until an explicitly qualified composition exists; empty-
annotation nesting retains each wrapper's ordinary policy checks. The optional
lifecycle forwarding rule above does not override this requirement.

Qualification must include a neutral synthetic transactional provider supporting
all six operations, actual persisted per-group annotation records, all-or-nothing
rollback injection, current refusal after dry run, idempotent replay and changed-
annotation conflict, exact principal attribution, and concurrent calls whose
annotation sets cannot cross groups. Its capabilities are reported as synthetic,
not as Truss or production durability. Real native adapters advertise only
operations independently qualified against their own native write/audit unit;
Truss remains unsupported for this capability until that evidence exists.
Do not send annotations to a side log, logger, trace, receipt attribute or second
transaction and call that atomic audit support. Safe unsupported controls and
the qualified synthetic capability are distinct acceptance results, both retained.

Qualification uses neutral synthetic records and policy decisions. Cover all
six intercepted methods, direct provider and direct Python calls, HTTP/MCP action
paths, the schema registration path, exact principal identity, reader forwarding,
no-wrapper compatibility, malformed/throwing callbacks, deeply nested mutation
attempts, no partial batch, current denial after successful validation, refusal
of a replay after policy revocation, native grant refusal after policy allow,
and unsupported nonempty annotations with an ordinary-provider-call counter
still zero. Include the optional annotation capability controls above. Extend the
installed consumer/public-catalog gates with actual wrapper use; source imports
alone do not qualify the public port. Native adapter annotation persistence and
source entitlement enforcement receive no success claim from synthetic tests.

ADR-005 still gates any actual durable structure derived from sensitive source
records on a written workload, entitlement enforcement point and governed-write
owner (P1/P2/P3). This generic callback/refusal boundary chooses none of those,
does not authorize a deployment, and builds no speculative derived artifact.

### Compiled UI design-system exports — EX-03

The packed `@documentdrivendx/arras-ui` root export deliberately exposes the
existing design-system seam from ADR-029, without a new package/subpath:

- Values: `DesignSystemProvider`, `useDesignSystem`, `defaultDesignSystem`,
  `ROLE_TOKENS`.
- Types: `DesignSystem`, `ButtonProps`, `ButtonVariant`, `FieldChrome`,
  `TextFieldProps`, `TextAreaProps`, `SelectProps`, `SelectOption`, `NoticeProps`,
  `NoticeTone`, `MarkProps`, `RoleToken`.

Use explicit root reexports of the existing definitions. Do not duplicate the
context, provider, props or token list; change no widget semantics, theme, layout,
CSS namespace, Brand, runtime asset manifest or visual baseline. The existing
provider accepts a partial design system, fills missing widgets from the outer
provider/default and shares that context with exported UI components across
entrypoints. Keep React/ReactDOM external peers supplied once by the host.
Generated root declarations and the actual packed manifest must resolve every
advertised export; source-only relative imports do not qualify this boundary.

### Persistent local development identities — EX-06

This surface governs `arras.adapters.truss.local.LocalTruss` and the development
host's explicit composition. It does not provide production identity management,
change Truss 0.0.45, or permit reads/actions as an installing identity.

| Surface | Rules |
| --- | --- |
| `LocalTruss(name="primary", *, directory=None, url=None, reset=False, credential_source=None)` | The optional host-owned source implements `__call__(role: str, *, create: bool) -> str`, receiving the full PostgreSQL role name and returning that person's stable nonempty password. Persistent attachment (`url` supplied) MUST have this source before creating/reusing a person. No source or a missing/invalid credential is a scrubbed `ValueError`; no person-role DDL follows. A throwaway retains random per-run credentials without a source. Never derive person passwords from the installer secret. |
| Source creation intent | Determine role existence under the database lock first. For an existing role call `create=False`: lookup only, no credential generation or store mutation when missing. For an absent role call `create=True`: atomic get-or-create is allowed. Both forms return an existing stable credential when present. Source exceptions are scrubbed; they cannot authorize alternate credentials or role takeover. |
| `LocalTruss.person(user)` | Resolve the prefixed role and serialize existence check/creation in a transaction using a role-scoped advisory transaction lock. Create an absent role with `CREATE ROLE ... LOGIN PASSWORD ...`. A concurrent duplicate-role outcome MUST roll back and perform a bounded reread/lookup/authentication check, never `ALTER ROLE` recovery. PostgreSQL roles are cluster-wide: the database-local advisory lock alone cannot serialize a creator in another database. |
| Existing persistent role | Verify the installing role administers it, then authenticate a fresh connection with the supplied person credential and verify the expected session identity before returning/caching the principal. Wrong/missing/expired credentials, `NOLOGIN`, or an unmanaged role refuse without password, login, expiry, attribute or membership changes. No automatic rotation, expiry reset, generated-password retry or fallback to installer/service identity. Existing scrubbed auth/connection error mapping applies; an outage is not proof of stale credentials. |
| `LocalTruss.created_roles` | A read-only `frozenset[str]` of full managed role names actually created by this instance during its current open lifecycle, including helper-created person and module roles. Existing roles, including a concurrent creator's role, are absent. This supports bootstrap decisions; it grants no authority and is not persisted identity state. |
| `TrussBox(..., credential_source=None)` | Forward the source. Assign each initial registrar/module membership only when the person role or that membership's target managed role was newly created by this instance. Startup, restart and repeated `load()` of an existing module MUST NOT regrant revoked access, reset expiry or remove independent memberships. Existing modules attach without default-grant reconciliation; empty-state seeding is separate from identity bootstrap. |
| Explicit sandbox selection, `TrussBox.person(name, role)` | Reconcile only the installing role's direct grants of known managed reader/writer/auditor roles and the current installation's registrar role, across hosts rather than only this process's `minted` map. Preserve independent grantors' rows, unrelated memberships, inherited rights and role attributes. A selected sandbox label does not promise exclusive effective privileges: PostgreSQL's full current authorization remains authoritative. Ordinary startup and principal reads MUST NOT invoke reconciliation implicitly. Existing explicit grant/revoke/expiry development controls remain explicit; no broad grantor/inheritance revocation is added. |
| Persistent `set_password` / `use_token` | Refuse credential replacement; these development helpers remain usable on throwaways. Coordinated persistent rotation is outside EX-06. Never change a shared database password behind the source or another host's principal. |
| Devhost composition | `devhost.build(..., credential_source=None)` forwards an explicitly supplied source; persistent programmatic construction without it refuses rather than reading or creating files implicitly. CLI composition alone constructs the file source below: `--truss-credentials PATH`, then `ARRAS_TRUSS_DEV_CREDENTIALS`, then the default. Core/adapter do not read ambient environment or credential files. An explicit path option without persistent Truss is a startup argument error. |
| Shared credential file | Default `~/.arras/truss-dev-credentials/<scope>.json`; `scope` is a stable hash of credential-free host/port and installer role, excluding database because roles span databases. Aliased endpoints are not automatically equated: sharing hosts must select the same file. Version 1 contains a role-to-password map. The host-owned source atomically gets/creates independent random per-role passwords only when `create=True`; `create=False` never creates a missing file/entry. |
| File integrity/concurrency | Hold an exclusive stable sidecar process lock across read/validate/get-or-create and atomic same-directory replacement; locking a replaced data inode is insufficient. Use current-user ownership, private parent directory and 0600 regular data/lock files; refuse symlinks, unsafe existing permissions, malformed/unknown-version/duplicate-key data and oversized input without clobbering. Check existing ancestors before making missing directories, then validate the resulting parent; an unsafe ancestor must not create children behind its link. Open paths so nonregular FIFO/device entries cannot block validation. Bound reads to 64 KiB, flush writes before publishing, and release locks on failure. Never log contents, passwords, source exception text or credential-bearing URLs. |

Existing development roles whose old generated passwords were not retained need
an explicit administrator-owned recovery/rotation step or an explicitly selected
isolated reset. Ordinary startup fails safely. Reset remains an explicit
destructive development operation; EX-06 does not broaden its ownership/deletion
rules. A database reset does not implicitly reset the shared credential file.

## Precedence and Compatibility

- Versioning: v3. Version in `arras.CONTRACT_VERSIONS["lifecycle"]`.
- Telemetry: the library emits events and spans to the host's logger and tracer provider and owns no sink (CONTRACT-008).
- Ordering or precedence: `start` connects each backend and reports status; `migrate()` is the host's call. Host-supplied values win; the library has no environment fallbacks (only the MCP binding reads configuration).
- Backward-compatibility rules: adding an optional parameter or a new `reason` value is compatible for callers that handle unknown reasons as unavailable. Removing or renaming a name is breaking.
- Deprecation rules: as CONTRACT-001.

## Error Semantics

| Condition | Error / Outcome | Retry | Recovery Expectation |
|-----------|------------------|-------|----------------------|
| A source is `None` | that backend `not_configured` | no | Host supplies the source |
| Connect fails at serve time | that backend `unreachable` | host decides (restart or a new `start`) | Restore the backend |
| The `migrate` timeout elapses | that backend `migration_failed`, detail `timeout` | after the cause is fixed | Raise the timeout or fix the lock holder |
| A backend refuses the identity, or the installing role lacks install privileges | that backend `access_denied` | no | Platform owner grants access |
| No installing connection is given | that backend reports `not_configured` until a per-person call has been made, because the adapter cannot read the store's release and never probes as a service; after a call it reports what that call showed (available when it reached Truss, unavailable with the reason when it could not), so a host with only the person's token (the MCP process) reports the database it is serving. Reads and writes are not gated on the report: they are served and refused by the database as the person. Consumers of the status (the console's all-down answer, search) treat the backend as down while it is `not_configured` | no | Host supplies the installing connection when it wants the status |
| Install fails | that backend `migration_failed`, detail `truss <code>` (no server or Truss text) | after the cause is fixed | Fix and restart |
| The database holds a Truss release other than the pinned one | that backend `unsupported_version` | no | Do not recreate automatically. Arras does not invoke an upgrade. If the source is eligible, the database administrator may use the selected Truss 0.0.50 tool's separately documented forward-migration procedure, then run Arras install-or-verify; otherwise retain the database and resolve compatibility with the operator |
| Truss quarantines a connection | Arras closes it; the call raises `Unavailable(unreachable)`, detail `the connection was quarantined`. Truss 0.0.45 has no deterministic trigger that quarantines a live connection, so the tests set the flag that the `transaction_unusable` and `commit_unknown` outcomes set | yes, on a new connection | The host's pool discards it |
| A source yields a connection with autocommit on, an open transaction or a session role | the call raises `Unavailable(access_denied)` before any Truss call; a connection with a session role is also closed, because the role is session state, and the host's pool MUST discard it | no | Fix the host's source |
| Truss or its toolkit is not installed (`ImportError` in a call), or Truss raises an exception that is not a programming error (`ValueError`, `RuntimeError`, `OSError`) | `Unavailable(not_configured)`, detail `the truss extra is not installed`, or `Unavailable(unreachable)`, detail `truss error`; neither carries the exception's text; `AssertionError`, `TypeError`, `AttributeError`, `NameError`, `LookupError` and `NotImplementedError` propagate unchanged | no | Install the extra, or fix the cause |
| A write's transaction is aborted when the block ends (a statement failed and the body swallowed it) | Arras rolls back and raises `Unavailable(unreachable)`, detail `the transaction was aborted`; it never commits an aborted transaction, because `COMMIT` would report success for a rollback, and Truss answers that state `invalid_transaction` without quarantining, so this check is the only guard | yes | None |
| Truss refuses the adoption: `Connection already attached or quarantined` | Arras closes the connection and raises `Unavailable(unreachable)`, detail `the connection is quarantined` | yes, on a new connection | The host's pool discards it |
| Truss refuses the adoption: `Live non-pipeline connection required` | `Unavailable(access_denied)`, detail `the connection is in pipeline mode` | no | Fix the host's source |
| Truss refuses the adoption for any other `ValueError` (a driver, libpq or server outside the selected tuple) | `Unavailable(unsupported_version)`; the message is never repeated | no | Run the pinned driver and server |
| Truss refuses the adoption step (`adopt_transaction`) because the transaction profile differs (`invalid_transaction` from adoption; the mapping is by origin, not by message) | `Unavailable(access_denied)`, detail `the transaction profile differs` | no | Fix the host's source |
| A Truss operation outcome is `invalid_transaction` (Truss 0.0.45 gives one message, `Original transaction/profile admission refused`, for every `ValueError` inside an operation) | `Unavailable(unreachable)`, detail `truss invalid_transaction` | at the caller's discretion | Retry the call on a new connection |
| A source yields a connection that is closed or broken before adoption | `Unavailable(unreachable)`, detail `connection lost`, before any statement | yes, on a new connection | The host's pool discards it |
| A statement inside the call raises a psycopg `OperationalError` that carries a SQLSTATE | `57014` is `Unavailable(unreachable)`, detail `statement timeout`; class 08 and `57P01` to `57P03` are classified as connect failures; any other state is detail `database error`. An error with no SQLSTATE is a connect failure classified by message | depends | None |
| A person's token is wrong or expired at connect | the call raises `Refused(token_expired)` (the server does not tell the two apart) | after sign-in | Sign in again |
| Truss's deferred checks, run by the layer with `SET CONSTRAINTS ALL IMMEDIATE` before every write or dry run settles, fail with a server SQLSTATE (the connection is idle again after the rollback) | the transaction rolled back and nothing committed: `Unavailable(unreachable)`, detail `a deferred check of the write failed`; the connection stays open and idle and no server text is repeated | no: the write failed; the caller decides whether to send it again | None |
| That statement raises a timeout (`57014`), a connect-class error (no SQLSTATE, class 08, `57P01` to `57P03`), a non-psycopg error, or leaves the connection closed or broken or its rollback failing | as the statement rows above say: `statement timeout` (the connection stays open if idle), the connect classification, `database error`; a lost, broken or non-server error closes the connection | depends | None |
| A write's `COMMIT` is refused: the server reported the error with a SQLSTATE outside class 08 and `57P01` to `57P03` and the connection is back to idle (ReadyForQuery arrived, Truss's own rule) | the transaction rolled back and nothing committed: `Unavailable(unreachable)`, detail `the commit was refused`; the connection stays open (it is idle) and no server text is repeated | no: the write failed; the caller decides whether to send it again | None |
| A write's `COMMIT` has an unknown outcome: no SQLSTATE, class 08, `57P01` to `57P03`, an error that is not a psycopg error, or the connection is not idle, broken or closed after the error (a PANIC or a FATAL), whatever the SQLSTATE | Arras closes the connection and raises `Unavailable(unreachable)`, detail `outcome unknown` | replay the same request | The receipt replay (CONTRACT-004) |
| A Truss operation outcome is `retry` (a serialization failure or deadlock, `40001` or `40P01`) | `Unavailable(unreachable)`, detail `retry the call` | yes, the whole call on a new transaction | None |
| A Truss operation outcome is `cancelled` (a statement timeout `57014`, an expired operation deadline or a refused cancellation admission) | `Unavailable(unreachable)`, detail `timed out or cancelled` | depends | None |
| A psycopg error that is not an `OperationalError` escapes the call (a statement of the layer's own or of the body: an `InterfaceError`, a `ProgrammingError`) | `Unavailable(unreachable)`, detail `database error`; the server's text is never repeated | depends | None |
| Two instances install together | one installs, the other waits and returns `ran=False` | n/a | None |
| A backend lost after start | operations needing it raise `Unavailable("unreachable")`; `status()` updates on the next failed operation | host decides | None automatic |

## Examples

```python
from arras import Arras, Principal

arras = Arras.start({"memory": memory, "memory_replica": replica}, admin=deploy_principal,
                   placement={"catalog": Placement(record="memory", replicas=["memory_replica"])},
                   expected=("memory", "memory_replica"))
arras.status()          # Status({"memory": BackendStatus(available=False, reason="unreachable", detail="timeout after 10 s"),
                     #         "memory_replica": BackendStatus(available=True, ...)})

ontology = arras.session(Principal(user="jsmith", groups=(), token=tok))
ontology.query("catalog", "SELECT s.* FROM catalog.Solution s WHERE s.code = :k ORDER BY s.code LIMIT 1", {"k": "sol-pipeline-01"})   # raises Unavailable(backend="memory", reason="unreachable") without hanging
ontology.query("catalog", "SELECT u.workArea, COUNT(*) FROM catalog.UseCase u GROUP BY u.workArea ORDER BY u.workArea LIMIT 50", consistency="bulk")   # still answers, from the replica
```

## Non-Normative Notes

The embedding host supplies a current person credential for each new connection through its own pool; a per-principal connection source keeps Arras out of credential handling and keeps every backend call attributable to the person (ADR-017). Whether the host installs at startup or as a deploy step is the host's choice: it calls `migrate()` at start or runs it as a deploy step. The adapter needs no executable on `PATH`: Truss prepares a module in an embedded V8 and spawns no process, so registration, a write, an import and a key lookup all work with no Bun, no Node and an empty `PATH`. The module role names are the host's `module_access`, and whoever holds the installing connection calls `configure_access` after a runtime registration of a new module (the host's decision, which Arras does not take). Warehouse credential delivery and refresh belong to the embedding host under ADR-017. CONTRACT-007 defines the stdio token-file reread and claim-selection mechanisms; the host owns their deployment wiring.

## Later public 0.0.49 managed-host handoff

This later-tranche amendment leaves the published 0.6.0 release and its
receipts unchanged. The host may supply `tolerated_grantees=()` through the
explicit Truss factory/backend constructor (CONTRACT-004). Construction performs
no connection, environment lookup or SDK import; fresh install alone forwards
the tuple. Reconnect verifies upstream stored policy without replacing it.
The setting is not a policy-change, migration or role-management API.

Managed execution requires the exact human-authorized provider target, secure
credential source and disposable resource scope. The designated Truss owner alone
provisions the Lakebase target; Arras must not create a competing instance.
Public Truss installs the fixed `truss` namespace and creates installation roles.
Authorization for an unrelated disposable schema is insufficient. Dedicated
database or explicit fixed-namespace/created-role custody must be established
before effects, with unrelated installations and resources left untouched.

The installer and each person use their own authorized connection sources.
TLS verification, provider identity, token expiry/refresh, actual role privileges,
server/driver/native tuple and resource custody require original observations.
No service-identity fallback, trigger disabling, inferred superuser/extension
trust, automatic role widening or compatibility retry is permitted. Missing
target/source/privilege/control requirements block dependent cases; local or
synthetic evidence cannot satisfy actual Lakebase acceptance.

## Current public 0.0.50 source selection — final release gates open

The current Arras 0.6.1 candidate selects public Truss 0.0.50, wheel SHA-256 `7b0483bb0c624c98515cf38ec30bbbf1ca43c1250e8880e5d00d520b4b7eec00`, from source `a687d0a226dad5745cbd909377bf99c7c1cddc66`. The native runtime manifest remains `truss-catalog-runtime/0.74-candidate`, SHA-256 `288801f7177338328441b5d3ce9328af31740ebf513f04ea45e30ae316a9f3a4`; the distinct active migration manifest is SHA-256 `4c6baf0282e3d0b5492f070c9c07d89ff0c9a819e748f3820f60b11c1f51c7aa` and retains the prior 0.0.49 manifest. The additive [source-binding record](../../04-build/evidence/truss050-adoption-20261024/extension-source-binding.json) documents the unchanged inventory of 50 native SQL files and five JSON resources and references a source-only dependency review; it is not a database observation or managed acceptance.

This current selection supersedes the earlier 0.0.49 pin for the candidate. The 0.0.49 amendments and receipts above remain historical at their original scope. The exact Arras 0.6.1 wheel passed fresh-installed Mac arm64 / CPython 3.11.9 qualification (64 passed, eight declared limits, seven replica-only cases inapplicable), with seven native archive hashes, 172 installed Arras payload hashes and cleanup verified. The repaired fresh Lakebase baseline passed 6/6. The separately bound original twelve-case Lakebase campaign passed 12/12 with zero failures or blocked cases, and original cleanup, independent audit, process census and custody handback passed. Source-bound safe records are retained under `docs/helix/04-build/evidence/truss050-adoption-20261024/`. The scoped supplement did not capture the direct supervisor PGID; no forced-cleanup claim is made. These execution facts do not change this contract or declare final release acceptance; final review, exact-commit CI, merge/tag and publication remain open. The reusable ordinary actor setup is already provisioned; no new VM or repeated administrator provisioning is required.
