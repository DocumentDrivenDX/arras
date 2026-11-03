# Arras 0.7.2 repair review packet

This is prepublication evidence. It does not declare a release or rewrite any
0.7.1 result. The governing [repair plan](../../arras-072-release-repair-plan.md)
requires final exact-head/merged Linux producer qualification and Sol approval.

## AR-01 active consumer audit

The root version, root editable lock entry, catalog Python/npm distribution,
active example's exact Arras dependency, doctor expected Arras/npm versions and
first changelog heading now agree at 0.7.2. The example's own 0.1.0 and private
UI development package's 0.1.0 are intentionally independent. Public-content
policy changes only the actual modified doctor-request digest.

The wheel builder continues deriving its scoped package version from root
metadata. The new preflight also reads actual generated page/staged/carried npm
manifests and the selected wheel bytes. Lean PR CI and release check run the
source coupling/strict selector guard before the expensive tag qualification.
Candidate qualification checks the generated assets and exact wheel hash too.

Audited active consumers: verify_doctor.py and verify_extension_host.py build
ROOT/examples/extension_host with its normal declared dependencies; neither was
overridden. downstream.yml checks out the explicitly supplied source SHA and
uses explicit wheel/digest/consumer inputs. verify-published-release.yml binds
its driver and immutable selected release through release_target.py.
publish-registries.yml's normal hosted route derives identity from the successful
release; retained local-0.6.5 and hosted-recovered-0.7.0 are deliberately closed
historical recovery routes. verify_pypi_extras.py has a deliberate 0.7.2 cohort;
its 0.7.0 default and old test requests are historical fixtures, while release
callers provide the explicit selected version. Historical release selectors,
registry recovery origins, fixture versions and documentation receipts remain
unchanged. No dependency suppression or untagged source override is introduced.

## AR-02 canonical producer and original failure

[The preserved 0.7.1 packet](../arras071-aborted-20261103/README.md) records full
ZIP/RECORD/tar maps and actual same-input gzip reproduction. The Mac compressor
and hosted Linux bundled zlib encode identical tar bytes differently. Neither
Node major version nor application source explains the observed mismatch.

The canonical producer is Ubuntu 24.04 x86_64, Python 3.11.18, uv 0.13.6,
Node 24.22.1/npm 11.19.1, Hatchling 1.33.0. Hatchling was already the actual
initial candidate wheel generator; root/example build requirements now freeze
that observed producer. Runtime dependency lock closure does not change.
Candidate and tag producer settings agree. Each candidate builds wheel/sdist/npm
twice from separate clean checkouts of the exact same source and requires full
byte equality, retaining full archive/member metadata and actual toolchain/input
hashes. Unexpected producer drift fails before tagging.

## AR-03 actual Linux package evidence

[Initial Linux candidate run 41565639830](https://github.com/DocumentDrivenDX/arras/actions/runs/41565639830)
completed distribution/sdist-rebuild, FULL installed doctor, normal resolver fresh
extension host, installed UMF 139+139+16 and two installed CLI/devhost tests on
source 95cad20ae3b935877637c095bf2ccfee7e7f4a73. Wheel:
`5cc8bd18799590406501c58c34be5cd17e32bb0813daaf512fa7b0f493cc2db1`;
carried npm: `b284c86951e3148e902ca522009988892112d6f3bc14792ced185b5ac06107f0`.
The new selector uses those actual qualified wheel bytes, preserving all old
selectors. Initial sdist was source-bound and is not relabeled as final source.
Final repair-head and final merged-tree producer/consumer receipts remain
required because tooling/build requirements changed after this initial run.

## AR-04 requested evidence reuse

[Complete source/payload correspondence](source-payload-correspondence.json)
compares exact bytes before classifying explicit version-only deltas. It retains
all 188 wheel member hashes, all 323 npm member hashes/order/full metadata,
independently validates both complete RECORD maps, and enumerates unchanged
source closures. All 115 Python runtime and 376 UI source/build files match the
original 0.7.1 source. All locked dependency sources/versions/hashes match;
only the root editable Arras version differs. Existing test files changed only
for release selectors/cohort controls; the runtime/native harness remains intact.

Five wheel payload members change: distribution catalog's two version fields,
page manifest package.version, npm package.json.version inside the carried
archive, wheel METADATA Version, and corresponding RECORD paths/digests. The
explicit dist-info/npm filename renames are recorded. Every other payload is
byte-identical. No JavaScript/CSS/exports/behavior/contract delta is normalized.

Prior source/native/UI receipts retain their original source, platform and hash.
Sol is asked to approve reuse only for the proven unchanged semantic closures.
New versioned package/consumer, final merged producer, ALL mandatory exact-tag
jobs, anonymous GitHub asset gates and public registry/fresh installs remain
separate mandatory gates. No new Mac native/scale campaign is proposed.
