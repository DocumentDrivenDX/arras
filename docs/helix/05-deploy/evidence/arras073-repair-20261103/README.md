# Arras 0.7.3 bounded repair packet

The [0.7.2 failure](../arras072-aborted-20261103/README.md) is preserved with its
immutable tag. The next patch was free on explicit GitHub tag/release, public
PyPI and scoped npm checks. The existing [successor repair contract](../../arras-072-release-repair-plan.md)
requires the next free patch if the prior identity is occupied; all its exact
artifact, source review, pre-tag, tag and public-consumer gates still apply.
No publication or full-source success is declared by this packet.

## Concrete repair

`tests/test_truss_docs.py` now requires the EXACT qualified Python selector
`3.11.18`, replacing the stale broad literal `3.11`. No assertion is removed or
weakened. The full source run had passed 3,875 tests and failed only that literal;
203 separate native cases passed. The original full-source run is not called
successful. No tagged source, test or receipt is overridden.

The final candidate workflow now includes the SAME tag-required Weft parser
asset/SHA validation, Ruff/format, strict Pyright, official UMF-vector check,
and COMPLETE default source/workflow suite. `ARRAS_REQUIRE_WEFT`,
`ARRAS_REQUIRE_UMF` and `ARRAS_REQUIRE_UMF_ACTIONS` remain 1, and the standard
native marker exclusion is unchanged. A JUnit report retains actual selection,
counts and the ordinary two installed-wheel skips; later explicit installed
CLI/page tests execute both. Full source checks run before UI build and before
the second nested checkout so no copied tests are discovered twice.

The new workflow-contract control fails against the prior short pre-tag workflow
and passes with this complete source gate. The test file and every release-control
file are also candidate workflow triggers. Native tests remain the explicit
separate selected/tag gates; no local Mac native campaign is added.

Active root/lock/catalog/example/doctor consumers use 0.7.3. The qualified SDK
closure is unchanged and deliberately listed for the new version; all prior
pins and closed historical recovery routes remain intact. The next unknown
0.7.4 still refuses. Public policy changes only the actual doctor-request hash.
The private UI package and neutral example own versions remain 0.1.0.

## Actual Linux bytes and remaining gates

[Capture 41572525707](https://github.com/DocumentDrivenDX/arras/actions/runs/41572525707)
on f6e72fe931b8cfba6b7bb6b28b3427202a4aa43a passed both clean byte-identical
builds, 133 focused controls, full fresh distribution/sdist rebuild, installed
doctor, normal resolver-built fresh extension host, UMF admission 139+139+16 and
two installed CLI/page tests. It then correctly refused the still-unselected
0.7.3 wheel at the final strict-pin gate. This is a partial qualification run,
not a green PR or permission to tag. Initial sdist is source-bound, not final.

The actually qualified Linux wheel is
`2d48d87f872ec9145a9f6d2f2b7adcae9ebe3154f9b47f7aa8aa2b411200c0dd`;
carried npm is
`10150ef0e4ad5bad8242ff8186ec6199d79839088729325c8afd0e7f22932695`.
The new exact selector and its matching/missing/changed-byte controls use that
wheel. Final-head FULL source plus all consumer/clean-build gates and Sol review
remain required; final merged-source qualification precedes the next immutable
tag. All mandatory tag, anonymous GitHub, trusted registry and independent fresh
public-consumer gates remain unchanged.

## Bounded impact / requested review

[Complete correspondence](source-payload-correspondence.json) compares exact
0.7.2 and actual Linux 0.7.3 wheel/npm members before classifying explicit
version-only differences, validates both entire RECORD maps, and retains full
member hashes/order/metadata and source closures. All 115 runtime Python files,
376 UI source/build files and the complete dependency lock closure are unchanged
except the root editable Arras version. No runtime/native/UI semantic fix is
introduced. Test changes cover explicit cohort/selector versions and this
workflow assertion/pre-tag coverage. Prior full native/UI observations retain
all original source/platform/hash bindings; Sol is asked to approve only bounded
unchanged-component reuse. New package, full-source, final tag and public
artifacts are independently qualified, never renamed from older receipts.
