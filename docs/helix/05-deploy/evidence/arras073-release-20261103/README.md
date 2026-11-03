# Arras 0.7.3 public release closure

[GitHub](https://github.com/DocumentDrivenDX/arras/releases/tag/v0.7.3),
[PyPI](https://pypi.org/project/arras/0.7.3/) and
[npm](https://www.npmjs.com/package/@documentdrivendx/arras-ui/v/0.7.3)
contain the same qualified 0.7.3 bytes. GitHub release 432275707 is public and
immutable with 18 assets. Source is
`dc2dc6f9b9d823e3ce5ffbc4e86f49fd92646f2b`; annotated tag object is
`984c13739be80b682752e6405399e61f7b029ba0`. The [closure receipt](release-closure.json)
records the named scopes and actual postpublication results.

| Artifact | Public SHA-256 |
| --- | --- |
| arras-0.7.3-py3-none-any.whl | `2d48d87f872ec9145a9f6d2f2b7adcae9ebe3154f9b47f7aa8aa2b411200c0dd` |
| arras-0.7.3.tar.gz | `2d9b434dcba20d026bad58ff108361ca9db40152167ed2448cc22202968e4ba1` |
| documentdrivendx-arras-ui-0.7.3.tgz | `10150ef0e4ad5bad8242ff8186ec6199d79839088729325c8afd0e7f22932695` |

## Source, package and publication gates

[PR60](https://github.com/DocumentDrivenDX/arras/pull/60) exact head
`0cd71cfd9bf487346dad98f708a743eeadadb8c2` received Sol source and bounded
runtime/native/UI evidence-reuse approval. The [repair packet](../arras073-repair-20261103/README.md)
retains complete source/wheel/npm/RECORD correspondence. All 115 runtime Python
and 376 UI source/build files and dependency closure remain unchanged apart from
root version metadata; versioned artifacts receive their own qualification.

[PR pre-tag run 41573076848](https://github.com/DocumentDrivenDX/arras/actions/runs/41573076848)
and [final merged run 41573945577](https://github.com/DocumentDrivenDX/arras/actions/runs/41573945577)
passed the SAME required source/workflow suite, quality/vector gates, two clean
byte-identical wheel/sdist/npm builds, full fresh distribution/sdist rebuild,
doctor, normal resolver-built extension host, SDK and installed CLI/page checks.
Each full source run passed 3,885 tests and skipped two installed-wheel cases;
both installed cases then passed explicitly. Final merged source and all three
complete archive bytes match the reviewed candidate
([correspondence](final-merged-correspondence.json)).

[Mandatory exact-tag run 41575055410](https://github.com/DocumentDrivenDX/arras/actions/runs/41575055410)
passed source 3,885, native 203 with zero skips, exact qualified-wheel guard,
installed native conformance, UMF admission/generated actions, UI and packed host,
evidence assembly, installed downstream and anonymous public-download gates.
UI reports 1,481 unit passes plus two browser-availability skips before Chromium
installation; those two unchanged controls separately passed with cached
Chromium ([log](browser-requirements-controls.log)). Integration passed 206;
source and packed portable browser suites each passed 218. No observed failure
was changed to a skip. [Public-download receipt](public-download-qualification.json)
records the later mandatory repeated qualification of actual anonymous downloads;
the immutable assembly evidence correctly retains its earlier
`not_run_at_assembly` marker.

[Publisher 41578947721](https://github.com/DocumentDrivenDX/arras/actions/runs/41578947721)
completed successfully on attempt two. Attempt one uploaded both PyPI files
(HTTP 200) and npm successfully, then failed fresh-install resolution while
indexes still exposed the older versions. Actual registry bytes already matched.
After public index visibility was confirmed, only failed publisher verification
and dependent checks were requested again. The existing immutable-byte guards
reported matching and BOTH upload steps were skipped. No file/tag was replaced;
passing source/native/UI qualification was not restarted.

## Actual public bytes and fresh consumers

[Independent byte proof](independent-public-bytes.json) anonymously downloads all
18 GitHub assets, validates the complete 17-entry checksum inventory and exact
published evidence/component map, verifies tag/source and prequalified archive
digests, then compares actual PyPI wheel/sdist and npm HTTP bytes to GitHub.
The npm archive also equals the wheel-carried file; SHA-512 integrity and SHA-1
metadata match. Version strings alone do not close this check.

Fresh public-PyPI-only Python 3.11 extras environments passed on
[Linux x86_64](public-pypi-extras-linux.json) and
[macOS arm64](public-pypi-extras-macos.json): no direct-URL closure, qualified SDK
archive digests, pip check, imports, offline doctor and complete UMF document
smoke. The SDK cohort stays UMF 0.10.5, Truss 0.0.50 and Weft 0.4.51; no newer
standalone SDK release was adopted. An additional independent macOS Python
3.11.17 environment installed `arras[devhost,truss,umf]==0.7.3` from public PyPI
with empty cache/config and normal dependency resolution
([report](independent-pypi-extras-qualification.json)).

| Released issue | Actual delivered behavior / consumer proof |
| --- | --- |
| [#49](https://github.com/DocumentDrivenDX/arras/issues/49) | Effective configured operator groups appear in installed dev-host help. |
| [#50](https://github.com/DocumentDrivenDX/arras/issues/50) | Distribution theme reaches the stock installed UI; real Chromium observes the expected stylesheet values. |
| [#51](https://github.com/DocumentDrivenDX/arras/issues/51) | Light/dark/omitted theme declarations work; invalid appearance has no output effect; tampered/missing stylesheet controls refuse or lose the proof marker. |
| [#52](https://github.com/DocumentDrivenDX/arras/issues/52) | Genuine package-owned operate/mcp modules win in both fresh-process import orders and host attributes remain available; reviewed closed-entrypoint semantics are preserved. |
| [#53](https://github.com/DocumentDrivenDX/arras/issues/53) | Canonical reviewed host-appearance acceptance testkit is carried unchanged in the byte-verified public npm payload; complete portable/packed suites pass, with public stock-theme OS/storage preservation and missing-stylesheet control. |
| [#36](https://github.com/DocumentDrivenDX/arras/issues/36) | Explicit view/graph aliases work; raw UTF-8 custody, default-reader refusal after alias use, immutable policy, ambiguity refusal and canonical graph output pass. The selected nine-case Linux native gate and tag native suite qualify the declared native scope. |

The [ten installed feature controls](independent-feature-consumer.json) and
[stock UI Chromium 153.0.8010.12 proof](independent-stock-theme-browser.json)
run from public installs outside the checkout. All
[323 installed npm files](independent-npm-install-verification.json) equal the
public archive, and all ten dependency origins are the public npm registry.
The public stock page declares light appearance against dark OS settings,
computes `--surface: #123456`, preserves host storage/declaration across OS
changes, and fails the stylesheet proof when the stylesheet is removed.

## Scope and cleanup

Native evidence applies to Linux x86_64/PostgreSQL 18.6 and the published
cohort's declared component profiles and limits. The public native receipt
retains eight existing limits; this release does not claim a new unrestricted
native, managed alias or macOS database campaign, or qualify the independent
full temporal work. Prior managed/UI observations keep their original identities
under Sol's bounded correspondence approval.

The [selected native cleanup](selected-native-cleanup.json) records nine cases,
zero skips/failures/errors, zero matching PostgreSQL processes after teardown,
and removal of the job-owned temporary roots. Its actual synthetic PR source
is preserved; [tree correspondence](selected-native-source-correspondence.json)
proves equality to the reviewed and released source trees. No unrelated service
ownership or process termination is inferred.

The [owned-host cleanup](independent-consumer-cleanup.json) records normal process
reaping and a closed port, no forced kill and no local database startup. The
clean, owned forensic worktree was removed; its commits, failed tag receipts and
independent source artifacts remain retained. Primary Arras and other workers'
checkouts were not modified. Immutable unpublished tags v0.7.1 and v0.7.2 and
all original failed receipts remain intact.

## Reproduction and receipt integrity

[Consumer probes](consumer/) contain the exact public-only installer, byte and
file verifiers, feature inputs, stock host/browser probe and release identity.
Copy that folder to a new temporary directory; create its own Python 3.11 venv,
then run its installer and probes there. Supply the original tag's qualified
index/doctor/reference fixtures to the unchanged public-extras verifier. Do not
replace public installs with local wheels or carry over a site-packages tree.

[Proof file hashes](proof-file-sha256.json) bind every included receipt/probe.
The [pre-tag summary](pretag-summary.json) is a historical checkpoint before
publication; this closure and public receipts record the completed later gates.
