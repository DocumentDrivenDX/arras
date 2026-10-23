# Official UMF core reference corpus

`current-conformance.json` is copied byte-for-byte from the public
`DocumentDrivenDX/umf` repository at tag `umf-v0.5.4`, commit
`53de049136c7e41b482d1a73665d031cd5fbaec6`. Its source path is
`fixtures/metamodel/current-conformance.json`; the source Git blob is
`ac7a5c5947f85d5f31004a4b14b4003fd4a068d2`, and its SHA-256 is
`bb008a98b8448050748e65f867e7863475ccad9501a5b9229ae9e6d336691544`.
The file contains 139 cases for `umf.current-conformance/1` at core version
`0.10.0`.

The corpus derives from upstream `cases.json`, `ts-results.json` and `receipt.json`
at `docs/helix/04-build/evidence/metamodel-authority/baseline-current/`, from
source head `19fe5f1bc98840e3177e0d05584321c1e274bfdd`. Upstream correction C002
removes the blanket `EXPERIMENTAL_CORE_SEMANTIC_TYPES` expected diagnostic and
recomputes completeness from remaining diagnostics; scoped
`SEMANTIC_TYPE_EXTERNAL` diagnostics remain. Tests use upstream's callback
registry only to verify these reference vectors. Arras runtime admission uses a
fresh empty registry and does not load these callbacks.

The source is licensed `MIT OR Apache-2.0`. The upstream `LICENSE.md`,
`LICENSE-MIT` and `LICENSE-APACHE` notices are preserved in this directory.
This attribution describes the copied corpus only and does not claim that all
upstream UMF materials share the same license scope.
