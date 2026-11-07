---
ddx:
  id: CONTRACT-012
  type: contract
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-11-06
  authoring:
    home: repo
  links:
    - id: FEAT-011
      kind: informed_by
    - id: ADR-031
      kind: informed_by
    - id: CONTRACT-003
      kind: informed_by
    - id: CONTRACT-006
      kind: informed_by
    - id: CONTRACT-010
      kind: informed_by
    - id: SPIKE-006
      kind: informed_by
---

# Contract: The static read-only profile

**Contract ID**: CONTRACT-012
**Type**: library and file formats
**Version**: v1
**Status**: draft
**Related**: FEAT-011, ADR-031, CONTRACT-003, CONTRACT-006, CONTRACT-010, SPIKE-006

## Purpose

The Graph Browser (FEAT-011) reads through the `ArrasClient` interface. This contract states a profile of that interface that needs no server: an `ArrasClient` that answers from one UMF module document and one `arras.graph` file held in memory, in the browser, with no write path. It says what the profile serves, what it refuses, how its answers are held to the Python library's, and what is claimed about it and on what evidence. It does not change CONTRACT-006 or CONTRACT-010; it is a profile of them, and where they and this contract differ for the profile, this contract names the difference.

## Scope and Boundaries

In scope: the two input files; the profile's identity; the client surface; the GraphQL surface and its differences; values; search; refusals; conformance; hosting; support claims.

Out of scope: a writer, a journal, SQL, schema administration, the Operator Console, authentication and per-person access (the graph is public and everyone sees all of it), and the Markdown content format (a gap, below).

## Normative Surface

### A. The inputs

1. **The module document** is a UMF document read as `arras.umf.parse_module` reads it (CONTRACT-002): the same core version (`0.10.0`), the same refusals with the same `(code, path)` for the types, properties, keys, relationships and the `arras.view` vocabulary (CONTRACT-010 A). The shared cases in `view_cases.json` hold the two readers to the same refusals. Not carried: view and graph vocabulary aliases (a closed alias list), the refusal of a duplicate JSON key, and `check_action` (an action is read for its name, description and input specs; its guards and effects are neither checked nor served).
2. **The graph file** is the `arras.graph` file of CONTRACT-003 (Export), version 1, read as `arras.graphfile.loads` reads it: a number is an integer (a decimal is a string) and a fraction or an exponent is refused with its path; integers keep every digit (`losslessJson`). A file that does not say `complete: true` is loaded as it is and the profile states nothing about what is missing.
3. **Load.** Every entity record and then every relationship record is applied as `import_records` applies it, and any record `import_records` would reject fails the whole load, naming each such record: an unknown type or a key outside `[A-Za-z0-9._:-]{1,128}`; a required property missing or an undeclared one present; a value not of its property's type (a string, an integer, a boolean, a finite decimal, an RFC 3339 timestamp with an offset, base64 text, or a list of one); a decimal outside its field's precision and scale; an integer outside its field's width; a relationship name that is neither a relationship nor an inverse; an endpoint missing or of the wrong type; an `original_at` that is not a timestamp. A record of an entity already held is skipped. Nothing is retried and nothing is partly loaded.
4. **The page's configuration**, `arras-static.json`, names `module` and `graph`: paths relative to the page, with no scheme, no leading `/` or `//`, no `..`, no query and no fragment. Anything else is refused before a request is made.

### B. Identity and position

| | Value |
|---|---|
| Backend name | `static`; it is the module's `record` and its only reader; `replicas` is `[]`; `providers` is `{}` |
| Status | one entry, `static`, `available: true`, `reason: null`, `position` the `asOf` below, `lag: null` |
| Module revision | `{"static": 1}` |
| Freshness | `backend: "static"`; `asOf`: `static:` and the first 16 hex digits of the SHA-256 of the graph file's text (the first 64 bits of an FNV-1a digest where `crypto.subtle` is absent); `at`: the time the page loaded it; `consistency`: the one the request asked for (`latest` and `bulk` are served alike) |
| Capabilities of a type | `read`, `count` and `search: "substring"` true; `mutable: false`; `latency_class: "batch"`; `columns`, `relationships` and `searchable` as the memory adapter declares them |
| Viewer | `{user: "public", modes: ["user"]}`: Explore only |

### C. The client surface

| `ArrasClient` member | Profile |
|---|---|
| `version` | the contract versions this build speaks (`operate: 2`) |
| `viewer` | the public viewer above |
| `meta`, `status` | the two meta reads and the status read, answered by the meta schema over the loaded module (D) |
| `moduleQuery` | one request against the module's schema (D); a request the surface answers with an HTTP status (syntax `400`, unknown module `404`) is an `ApiError` of that status and code |
| `export` | pages of at most 500 records in the canonical order of CONTRACT-003 (entities by type declaration then key, relationships by declaration then source then target), with the cursor of `exportcursor.py`; `omitted` is always empty. Written with `graphText`, the pages are the bytes the library writes for the file that was loaded |
| `schemaCatalog` | the module document as loaded (when the page has its text) |
| `validate`, `invoke`, `batch`, `changes`, `loads`, `query` | `501 Unsupported`, `construct` the thing refused, `supported: ["reads"]`, message "this graph is published read-only: it is read from files, and nothing can be changed in it". The Browser's audit probe reads a `501` as "no journal" and hides history |

### D. The GraphQL surface

The module schema is CONTRACT-006's, field for field: `<type>(key)`, `<type>List(filter, limit, afterKey, consistency)` with a keyset page and `truncated`, the relationship fields (each at most 100 keys), `Ref` with `target`, and `_search`. The meta schema is `modules` and `status`. The profile holds the same request limits and gives the same codes:

| Limit | Value | Code |
|---|---|---|
| Query depth | 6 | `DEPTH_EXCEEDED` |
| Field selections | 50 | `COST_EXCEEDED` |
| Entities resolved in a request | 1,000 (a list reserves its `limit` before it reads) | `COST_EXCEEDED` |
| Relationship targets opened in a request | 100 | `COST_EXCEEDED` |
| Tokens in a query | 5,000 | `BAD_QUERY` (400) |
| List `limit` | 1 to 100 | `LIMIT_EXCEEDED` |
| Search `limit` | 1 to 50 | `LIMIT_EXCEEDED` |

A filter key that is not a property or relationship of the type, or a filter that is not an object, is `BAD_QUERY`; a property filter is an equality on a stored value (never on an absent one) and a relationship filter is `HAS_RELATED` on the other end's key. Lists are in code point order of the key (Python's string order, not UTF-16 order). A hub is read past the 100 keys an entity carries by listing the other type with the relationship as a filter and `afterKey`.

Differences from CONTRACT-006 for this profile, and only these:

1. One module and one backend; a `Ref` into another module has `target: null`, as a module the viewer cannot read has on the server.
2. `version` is `1`. `createdBy` and `updatedBy` are the record's `original_author`, and `createdAt` and `updatedAt` its `original_at`, or null: a file carries no other attribution.
3. An action's `preconditions` and `effects` are `[]`; its name, description and inputs are served.
4. The text of a `BAD_QUERY` raised by GraphQL validation, syntax or variable coercion is graphql-js 16.11.0's; the server's is graphql-core 3.3.0's. Codes and paths are the contract; the text is not.
5. Introspection is answered by graphql-js within the introspection bounds of the console; it is not in the corpus.

### E. Values

Strings and booleans as stored. Integers are exact: held as `bigint` where they pass 2^53 and written through the `BigInt` scalar as text. Decimals are held as text at their field's scale (`7` in a scale-2 field is `"7.00"`, `1e1` is `"10.00"`) and written as Python's `str(Decimal)` writes them; a decimal in a field with no complete domain, or in a list, is written at no scale. A timestamp is written as `datetime.isoformat()` writes it (`Z` is `+00:00`; microseconds only when not zero). Binary is its base64 text. A property that was not set is `null`.

`tests/vectors/domain.json` (41 vectors, from `fakes_domain.stored`) holds the decimals and integer widths in both languages.

### F. Search

`_search` is CONTRACT-010 C. For each type the view declares a search property for, up to 20 types, the backend match is: the first 50 entities in key order in which every word occurs, after lower-casing the value as a whole, in at least one of the declared properties; each is then re-checked and ranked by the library's per-character fold with the tiers, position scaling, excerpt window, ellipses and ties of CONTRACT-010 C. A type with no search property is `not_searched` (`no_searchable_property`, no backend); one whose search properties are not single-valued strings is `not_searched` with backend `static`; a request that exceeds the entity budget names `over_budget`; a search that searched no type is an error (`COST_EXCEEDED` or `UNSUPPORTED`). Whitespace is Python's `str.isspace` set and a word boundary is a Unicode letter or number (`\p{L}`, `\p{N}`).

### G. Conformance

The profile is conformant when all of these pass, on the stated environment:

| Data | Reference | Run by |
|---|---|---|
| `src/arras/conformance/view_cases.json` (28 cases) | `arras.umf.parse_module`, `arras.view` | `tests/test_view_conformance.py`; `ui/src/test/static-view-cases.test.ts` |
| `tests/vectors/template.json` (58 vectors) | `arras.view.evaluate` | `tests/test_template_vectors.py`; `static-backend.test.ts` |
| `tests/vectors/domain.json` (41 vectors) | `arras.fakes_domain.stored` | `tests/test_static_reads.py`; `static-backend.test.ts` |
| `src/arras/conformance/read_cases.json` (253 requests, three fixtures) | the console surface over the in-memory adapter (`create_app`, one record store named `memory`) | `tests/test_static_reads.py` (the file is what the reference answers now); `ui/src/test/static-read-corpus.test.ts` (the TypeScript answer equals it) |

A run compares **status, data, and each error's code and path** after one reduction, written in `tools/gen_static_reads.py` (`normalise`) and `ui/src/static/corpus.ts`, which must agree: drop `freshness`, `createdBy`, `createdAt`, `updatedBy`, `updatedAt`, `position`, `revision`, `mutable`, `latency_class` and `locations`; read the backend name `memory` as `static`; and, for an error that is not `BAD_QUERY`, compare its message and its extensions other than `violations`. The Backend corpus of CONTRACT-004 (`corpus.json`) is Weft SQL over writes, principals and the journal and is not run against this profile, which has no SQL surface and no writer.

### H. Hosting

A static file host that serves the page, `arras-static.json`, the module document and the graph file with their media types (`text/html`, `text/javascript`, `text/css`, `application/json`) and answers `GET` and `HEAD`. The page loads nothing from another origin and sends no cookie (`credentials: "omit"`); its `Content-Security-Policy` meta tag allows `connect-src 'self'` and `script-src 'self'` (and `style-src 'self' 'unsafe-inline'`, because the interface sets style attributes; no inline script, no `eval`). Nothing of a viewer, a search or a node is sent anywhere: the Browser keeps its address in the URL fragment. For a weekly republish, serve `arras-static.json` and the data files with `Cache-Control: no-cache` (or name them by content), so a visitor reads the new graph at the next load; the built page's own assets are content-hashed and may be cached for as long as the host likes.

## Support claims

| Claim | Engine and version | Evidence |
|---|---|---|
| The Graph Browser runs from static files over `examples/catalog` and `examples/pizza` and a synthetic 1,024-node graph with a 1,000-edge hub | Chromium 153.0.8010.12 (Playwright 1.63.0, headless), macOS arm64, served by a Node static file server | `ui/e2e-static/*.spec.ts`: 15 passed, 8 of them axe-core WCAG 2.1 A and AA scans, light and dark, no violations and no unreviewed results |
| The read corpus, `arras.view` cases and vectors hold for the TypeScript backend | Node 26.12.1 and vitest 5.0.3 (jsdom for the UI suite, node for these); graphql-js 16.11.0 | `ui/src/test/static-*.test.ts` |
| The reference side of the corpus | CPython 3.11.17, graphql-core 3.3.0 | `tests/test_static_reads.py` |
| Read-only: nothing written, no request but `GET` of the page's own origin | the same Chromium run | `browse.spec.ts` "reads the module and its graph as GETs of its own files, and nothing else" and "offers no way to change anything" |
| Not claimed | Firefox, WebKit, Safari, Chrome on Android and iOS, any OS but macOS, any Node line but 26, a graph past 1,024 nodes or 7.9 MB | not run |

## Known gaps

1. **Markdown.** The `arras.view` `prose` format forbids markup (CONTRACT-010 A, US-070-AC5). A graph whose text is Markdown is shown as text. A sanitized `markdown` format is a separate upstream proposal (ADR-031 decision 8).
2. The behaviours "not carried" in A and D.
3. Other browsers and larger graphs (Support claims, last row).
4. The profile is read at load, not refreshed: a visitor with the page open sees the old graph until a reload.

## Versioning

v1 follows CONTRACT-006 v2 and CONTRACT-010 v1. A change to either that alters a read in the profile regenerates `read_cases.json` and, if it is not a corpus-only change, bumps this contract.
