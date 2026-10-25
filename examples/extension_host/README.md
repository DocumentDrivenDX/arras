# Neutral extension host

This small downstream package demonstrates an explicit host-owned module, seed,
and graph resource through Arras's public Python API. It has no implicit catalog
or other Arras demo data. The graph envelope is private to this example; it is
not an Arras graph-file format. The document uses the currently supported
Arras legacy action subset and does not claim complete UMF execution support.

Build/install Arras and this example into an isolated environment, then run:

```sh
python -m extension_host --resource seed.json
python -m extension_host --resource graph.json
```

The module document bytes are passed unchanged to registration. The chosen
resource is loaded explicitly, imported with the host principal as actor, and
read through the public Arras session API. `--resource` accepts only the two
named packaged resources; documents do not select Python modules or code.

The installed package also carries an inert ADR-019 configuration resource at
`extension_host/config/default.toml`. A host may select its directory explicitly
with `ARRAS_CONFIG_DIR` when invoking Arras's public launcher. It contains only
Brand, process-name, and telemetry-name defaults; it has no endpoint, token, or
sandbox setting. The environment prefix is a launcher/bootstrap choice supplied
separately because it is needed before typed TOML configuration is loaded. The
example's data-loading path remains an explicit Python choice and does not
implicitly read this configuration.

After building Arras, verify the installed consumer and fixed memory corpus with
the repository's artifact probe:

```sh
python tools/verify_extension_host.py --wheel /path/to/arras-0.6.2-py3-none-any.whl \
    --output-json /tmp/extension-host-receipt.json --fresh-dependencies
```

The probe builds this example with its declared backend and installs both wheels
in a fresh temporary environment, resolving dependencies from public PyPI. It
records actual artifact digests, installed imports and dependency versions. Without
`--fresh-dependencies`, the development convenience mode explicitly reuses the
invoking environment's dependency directory; its receipt is not fresh-install
evidence. Neither mode establishes native backend qualification.

## Installed corpus and custom factories

Run both built-in memory profiles from the installed package, outside this
checkout:

```sh
python -I -m arras.conformance --backend memory-store
python -I -m arras.conformance --backend memory-replica
```

The JSON report names actual roles, corpus version, skipped cases and separate
`passed`, `failed`, `harness_error`, `limit` and `host_specific` outcomes. A
successful exit can include a documented limit; inspect its exact case/step and
refusal before claiming support. Reader-only skips are distinct from passing
provider cases. These commands do not qualify a native adapter.

A downstream adapter can supply an explicitly imported callable to the public
runner without copying Arras's tests:

```python
from arras.conformance import run_corpus

# make_harness is your own callable implementing the public Harness protocol.
report = run_corpus(make_harness)
for result in report.results:
    print(result.case, result.status, result.message)
print("roles:", report.roles, "skipped:", report.skipped)
if report.newer_corpus or not report.results or not report.passed:
    raise SystemExit("the selected corpus did not pass")
```

The factory supplies a fresh isolated resource for each case and a metadata
probe. It may provide `close()`; the runner invokes it once for every acquired
probe/case, including failures. Cleanup failures are failing `harness_error`
results and preserve any primary failure. Documents and configuration never
select Python imports or callable names.

## Owned native test resources

The packaged `arras.conformance.truss.TrussHarness` creates fresh temporary local
PostgreSQL/Truss resources. It accepts no personal endpoint, directory or
credential source. Importing it does not provision or import the native runtime:

```python
from arras.conformance import run_corpus
from arras.conformance.truss import TrussHarness

report = run_corpus(TrussHarness)
for result in report.results:
    print(result.case, result.status, result.message)
if report.newer_corpus or not report.results or not report.passed:
    raise SystemExit("native conformance failed")
```

The command equivalent is `python -I -m arras.conformance --backend truss`.
Missing native prerequisites produce an error; there is no memory fallback.
Every native case owns its server; a foreign-position control obtains a real
receipt from a second owned server. Do not use this helper as application
provisioning or persistent attachment.

`arras[truss]` supplies the adapter's selected native/query toolkit dependencies;
it does **not** supply the local server runtime. The source-checkpoint cohort is
`truss-toolkit==0.0.48`, `weft-sql==0.4.51`, with the toolkit's `local` extra and
its selected `pgserver-pg18` wheel. This public source tuple passed all 199 native tests on Linux x86_64 and macOS
arm64. A separate fresh installed-wheel run on Darwin arm64/CPython 3.11 passes
64 corpus cases, observes eight exact declared limits and identifies seven
replica-only cases as inapplicable, with zero failures or harness errors. Earlier source-checkpoint
smoke evidence used `truss-toolkit==0.0.45` and `weft-sql==0.4.49`; that evidence
is historical and does not qualify the current tuple. The repository's
`truss-test` dependency group is not a published Arras extra. An installed
consumer must provision the matching public, digest-verified toolkit/local-server
cohort explicitly, using its published platform wheels; a source checkout's
virtual environment is not that proof. Record the Python/OS/architecture/PostgreSQL
and all installed versions with the corpus result. The separate installed receipt verifies all seven selected distributions and
their declared native payloads. It does not qualify other platform/interpreter
cohorts or perform a system dynamic-link audit.

## Production backend factory

For a host-owned database, use the public factory with your own connection/pool
sources rather than the throwaway harness:

```python
from arras.adapters.truss import create_backend


def backend_for_host(person_source, installing_source, module_access):
    return create_backend(
        "primary",
        person_source,
        installing_source,
        module_access=module_access,
    )
```

`person_source(principal)` yields a context-managed connection authenticated as
that person; `installing_source()` yields the separate trusted installing
connection. Both arrive idle, autocommit off and with no selected session role.
The host owns credentials, pools, module access and provisioning; the adapter
does not read environment configuration or share an installer identity with
people. `module_access` maps module names to public `ModuleAccess` values. See
[connection lifecycle](../../docs/helix/02-design/contracts/CONTRACT-005-embedding-and-lifecycle.md)
for the governing ownership rules. This factory does not load demo resources:
register your own module bytes and select your own seed/graph imports explicitly,
as this example does.

## Reusable consumer job

A caller may invoke `.github/workflows/downstream.yml` at a reviewed immutable
Arras commit. Supply the verified public wheel's HTTPS URL and exact SHA-256,
your project directory and one explicit pytest file. For example, replace all
placeholders with your selected artifact and commit:

```yaml
jobs:
  arras-consumer:
    uses: DocumentDrivenDX/arras/.github/workflows/downstream.yml@<reviewed-commit>
    with:
      wheel_url: <public-https-wheel-url>
      wheel_sha256: <64-hex-sha256>
      consumer_project_path: .
      consumer_test_path: tests/test_arras_consumer.py
      consumer_setup_path: ci/setup_consumer.py
```

The optional `consumer_setup_path` runs as a trusted caller-owned Python script
before consumer installation with `--no-deps`; provision your public dependency
cohort there. Optional `native_test_path` requires `native_setup_path` to install
its matching public native prerequisites. Native tests set
`ARRAS_REQUIRE_TRUSS=1`. Optional `theme_test_path` can use `theme_setup_path` for
Node/browser or other prerequisites. No inline shell/eval input is accepted;
setup/test paths stay under the caller workspace, and setup digests plus actual
installed distribution versions are recorded. Setup scripts must preserve the
selected Arras artifact; the job checks its payload again before qualification.

Every selected pytest target must execute at least one test, exit successfully
and emit JUnit with zero errors, failures or skips. Missing optional stages are
`not_run`. The native output means only that explicit consumer target passed;
it does not certify every adapter case/cohort. A theme pytest result alone is
not rendered-theme, browser or accessibility evidence. Those claims require
actual renderer/browser checks and their receipts. Local source validation of
the workflow also does not establish that a hosted workflow has run.
