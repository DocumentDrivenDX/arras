---
ddx:
  id: CONTRACT-010
  type: contract
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-12
  authoring:
    home: repo
  links:
    - id: FEAT-011
      kind: informed_by
    - id: ADR-022
      kind: informed_by
    - id: ADR-023
      kind: informed_by
    - id: ADR-024
      kind: informed_by
    - id: ADR-025
      kind: informed_by
    - id: CONTRACT-001
      kind: informed_by
    - id: CONTRACT-002
      kind: informed_by
    - id: CONTRACT-004
      kind: informed_by
    - id: CONTRACT-006
      kind: informed_by
    - id: CONTRACT-009
      kind: informed_by
---

# Contract: Graph Browser view vocabulary, search read, location and modes

**Contract ID**: CONTRACT-010
**Type**: schema, HTTP API and library
**Version**: v1
**Status**: draft
**Related**: FEAT-011, ADR-022, ADR-023, ADR-024, ADR-025, CONTRACT-001, CONTRACT-002, CONTRACT-004, CONTRACT-006, CONTRACT-009

## Purpose

Defines what the Graph Browser (FEAT-011) needs beyond the reads that CONTRACT-006 already gives: the `arras.view` vocabulary in which a module declares how its types are presented (ADR-022), the resolved view that the meta schema returns, the search read (ADR-023), the location a node page carries (ADR-024), the viewer's modes (ADR-025), the interface's brand (FR-73) and the writes Explore offers by declared action (SD-013). It extends CONTRACT-006 v2 and CONTRACT-009 v2 additively: no existing field changes meaning, and a client that does not use the additions is unaffected.

Terms. UMF is the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions; a vocabulary is a named set of extension terms a UMF document declares. A *record* is a UMF entity type. A *template* is the text grammar defined below. A *tone* is one of eight palette slots a host maps to its own colours. The *resolved view* is the declared view merged with the derived defaults. A *hit* is an entity that matched a search. The URL fragment is the part of an address after `#`, which a browser does not send in a request. An *operator* is a viewer whom the host has said may use Operate (a builder or an administrator).

## Scope and Boundaries

- In scope: the vocabulary and its checks at registration; the resolved `view` on the meta schema; the search read and the backend capability it needs; the location grammar and the browser's props; the viewer's modes, the state they share and the operator refusal; the brand; the browser's writes, each a declared action invoked as the viewer (edits, links, New, Retire, the Actions menu) and the History read.
- Out of scope: how a page is drawn (DESIGN-GB, `graph-browser-visual-design.md`); the technical decomposition (SD-011); any write that is not a declared action invoked as the viewer; the Operator Console's own areas (CONTRACT-009).
- Owning system or team: Arras.

## Normative Surface

### A. The `arras.view` vocabulary, version 0.1.0

A document MUST declare it as `vocabularies["arras.view"] = {"version": "0.1.0"}` to use it. Terms appear in `extensions["arras.view"]` of the module, a record, a field or a relationship; a term at any other place MUST be refused. Every term not listed here MUST be refused (the vocabulary is closed). The vocabulary is presentation only: it MUST NOT change the types, properties, relationships, actions, access or what a read returns.

**Module** (`modules[0].extensions["arras.view"]`)

| Term | Type | Required | Rules |
|------|------|----------|-------|
| `title` | string | no | Plain text, 1 to 80 characters. Default: the module name. |
| `description` | string | no | Plain text, at most 280 characters. |

**Record** (`elements[<record>].extensions["arras.view"]`)

| Term | Type | Required | Rules |
|------|------|----------|-------|
| `label` | string | no | Plain text, 1 to 60. The type's display name; default the type name split into words (`UseCase` becomes `Use case`). |
| `pluralLabel` | string | no | Plain text, 1 to 60. The type's name where it names a collection (a breadcrumb to the type's list, the list's heading, a type chip or card). Default: `label` pluralised by English rules on its last word only, keeping its capitalisation: ends in a consonant and `y`, `y` becomes `ies`; ends in `s`, `x`, `z`, `ch` or `sh`, add `es`; otherwise add `s` (`Use case` becomes `Use cases`, `Category` `Categories`, `Address` `Addresses`, `Coverage` `Coverages`). Declare it where the rule is wrong (an uncountable `Coverage`, an irregular plural). |
| `icon` | string | no | One of the icon set below. Default `circle`. |
| `tone` | string | no | One of the tone set below. Default: by the record's position in the module's declaration order, `slate`, `blue`, `teal`, `green`, `amber`, `red`, `violet`, `rose`, repeating. |
| `title` | template | no | The page and link title; at most 200 characters; every placeholder MUST name a property of the record. Default: the first of `name`, `title`, `label` that the record has and is not the key, else the first single-valued string property that is not the key, else `{<key>}`. |
| `summary` | template | no | One line under the title; same rules. Default: the first of `summary`, `description`, `statement`, `problem`, `notes` that the record has and the effective title (declared or default) does not use; else none. |
| `sections` | list of section | no | At most 8. A *section* is `{label: string 1..60, properties: [property names, 1..24], collapsed: boolean = false}`. A property MUST appear in at most one section. Properties in no declared section, except the key and the properties the title and summary templates use, are listed in a final section `More` (omitted when empty). Default: one section `Details` with every property except the key and the properties the title and summary templates use, in declared order (omitted when empty). The resolved view lists every such property in its section; the browser leaves a property out of its section when it draws that property as a header badge (DESIGN-GB, Node page), and draws no section left with no rows. |
| `search` | list of property names | no | At most 8, each a string-typed property of the record, each once. The order is the rank order: a match in a property listed first outranks the same kind of match in a property listed later. Default: the string properties the effective title names, in order, then the key, then those the effective summary names, then `description`, `statement`, `problem`, `notes` where the record has them, none listed twice and at most 8. `[]` makes the type not searchable. |

**Field** (`elements[<field>].extensions["arras.view"]`)

| Term | Type | Required | Rules |
|------|------|----------|-------|
| `label` | string | no | Plain text, 1 to 60. Default the property name split into words. |
| `format` | string | no | One of the format set below, and MUST suit the property's type: `text`, `prose`, `code`, `link` and `badge` suit a string, `tags` a list of strings, `date` and `datetime` a timestamp, `number` an integer or decimal, `boolean` a boolean, `json` a structured value or a list of anything else. Default: see Defaults. |
| `hideWhenEmpty` | boolean | no | Default `false`: an empty value shows a "not set" marker. |
| `tones` | map of string to tone | no | Only where the effective format (declared or default) is `badge`; at most 24 entries; maps a value to a tone; a value not in the map uses `slate`. |

**Relationship** (`relationships[<relationship>].extensions["arras.view"]`)

| Term | Type | Required | Rules |
|------|------|----------|-------|
| `label` | string | no | Plain text, 1 to 60. The group title on the source's page. Default the relationship name split into words. |
| `inverseLabel` | string | no | Plain text, 1 to 60. The group title on the target's page; only where the relationship has an inverse. Default the inverse's name split into words. |
| `hideWhenEmpty` | boolean | no | Default `false`. |
| `order` | integer 0..99 | no | Group order on a page, ascending; ties by label. Default 50. |

**Sets**

| Set | Members |
|-----|---------|
| Icons (24) | `box`, `package`, `puzzle`, `file-text`, `folder`, `user`, `users`, `building`, `tag`, `flag`, `alert`, `check-circle`, `clock`, `calendar`, `link`, `globe`, `wrench`, `scale`, `book`, `chart`, `shield`, `star`, `bolt`, `circle` |
| Tones (8) | `slate`, `blue`, `teal`, `green`, `amber`, `red`, `violet`, `rose` |
| Formats | `text` (string), `prose` (string: line breaks kept, never markup), `code` (string, monospace), `link` (string: an `http`, `https` or `mailto` address shown as a link; any other value is shown as text), `badge` (string), `tags` (list of string), `date` (timestamp: date only), `datetime` (timestamp), `number` (integer, decimal), `boolean` (boolean), `json` (structured value) |

**Defaults for `format`.** String: `link` when the property name ends in `Url`, `Uri` or `Link` (case-insensitive); else `prose` when the name is one of `summary`, `description`, `statement`, `problem`, `notes`, `prompt`, `workflow`, `caveat`, `rationale`; else `badge` when it is one of `status`, `state`, `kind`, `level`; else `text`. List of strings: `tags`; any other list, and a structured value: `json`. Timestamp: `datetime`. Integer and decimal: `number` (the integer part grouped by the viewer's locale, the stored digits otherwise unchanged). Boolean: `boolean`. Binary: `binary`, which no declared format suits and a client does not show.

**Template grammar.** A template is plain text with: `{name}` (the property's value as text), `[` … `]` (an optional group, shown only if every placeholder inside it is non-empty), and `\{`, `\}`, `\[`, `\]`, `\\` for a literal character. Nothing else is interpreted; a `{`, `}`, `[` or `]` that is not escaped and not part of those forms makes the template malformed. A placeholder that names a missing property, or an optional group that is empty, produces no text. A title that evaluates to empty is replaced by the entity's key. A template is a string, never markup: its output is shown as text.

**Size.** The `arras.view` terms of one record with its fields, and of each relationship, MUST NOT exceed 16 KiB serialized each; a document's all views MUST NOT exceed 128 KiB. A text term over its length is `view_too_large`, except a template, which is `view_bad_template`.

**Checks at registration.** Registration MUST run the checks below over the document, as a `Violation(path, code, message)` list in the rest of registration's style (CONTRACT-002), the path being the document path of the fault (`modules[0].elements[3].extensions.arras.view.sections[0].properties[2]`), and the registry MUST be unchanged on any fault. The record, field and relationship `extensions` of a document that does not declare this vocabulary are not examined. A record that is a structured value, an action, and the document root have no view: a term there is `view_unknown_term`.

| Code | Fault |
|------|-------|
| `view_unknown_term` | A term outside the tables above, at any level, including anything resembling markup, script, a URL to load, a colour value or a component reference; a view on something that has none |
| `view_unknown_property` | A property named in a template, section or `search` that the record does not have |
| `view_unknown_relationship` | `inverseLabel` or `order` (terms only a relationship has) on something that is not a relationship, or `inverseLabel` with no inverse |
| `view_format_mismatch` | A `format` that is not one of the set or does not suit the property's type, or `tones` where the effective format is not `badge` |
| `view_unknown_icon`, `view_unknown_tone` | A name outside its set |
| `view_bad_template` | A malformed template or one over its length; a non-string property in `search`; a term whose value is not of its type or range (text, boolean, `order`, list) |
| `view_duplicate` | A property in two sections or twice in `search` |
| `view_too_large` | A size limit exceeded: a text term, the number of sections, properties, search properties or tones, or the bytes of a view |
| `view_unsupported_version` | A `vocabularies["arras.view"].version` this release does not support; the only fault then, at `vocabularies.arras.view.version` |

**Where the view lives.** The view is not part of any backend's catalog and not of `ModuleInfo` or `EntityTypeInfo`: it is read from the module's registered document (`document`, CONTRACT-001 and CONTRACT-004) and resolved against the module's types when asked for, and the resolution is cached by module and revision. A change to a view is a change to the document, and therefore a new revision as any change of the document is (CONTRACT-002); there is no separate view revision. The registry's types, relationships and actions are equal with and without a view by construction.

### B. The resolved view

CONTRACT-006's meta schema carries these fields; nothing else in it changes.

```graphql
type Module { # existing fields unchanged, plus:
  view: ModuleView!
}
type ModuleView { title: String!  description: String }

type EntityTypeInfo { # existing fields unchanged, plus:
  view: View!
}
type View {
  declared: Boolean!            # true if the document declared any arras.view term for the record
  label: String!
  pluralLabel: String!          # declared, else label pluralised (section A)
  icon: String!   tone: String!
  title: String!  summary: String          # templates
  sections: [ViewSection!]!                # the declared sections, then More; by default one Details. A property appears once
  search: [String!]!                       # the effective search properties, in rank order
  fields: [FieldView!]!                    # one per property, including the key
  relationships: [RelationshipView!]!      # one per relationship field the type has
}
type ViewSection { label: String!  properties: [String!]!  collapsed: Boolean! }
type FieldView { property: String!  label: String!  format: String!  hideWhenEmpty: Boolean!  tones: JSON }
type RelationshipView { field: String!  label: String!  hideWhenEmpty: Boolean!  order: Int! }
```

| Element | Rules |
|---------|-------|
| Resolution | The server MUST return the resolved view: the declaration merged with the defaults above, so a client never derives a default. `declared` states whether any term was declared for the record or one of its fields. `RelationshipView.field` is the relationship field's name on the type, as in the generated schema (CONTRACT-006). |
| Access | The view carries no entity data and grants nothing. A page built from it MUST show only what the viewer's own reads return; a property the backend omits for the viewer is omitted from the page, and a template over it drops that placeholder. |
| `capabilities` | `EntityTypeInfo.capabilities` (JSON, a map by backend name, CONTRACT-006) carries `search` and `searchable` inside each backend's entry: `search` is `"none"` or `"substring"`, and `searchable` lists the string properties the backend can match, per CONTRACT-004. |

### C. The search read

The additions live on a module's own endpoint, so their names begin with an underscore, which CONTRACT-002 forbids in a declared name; they cannot collide with a module's types or fields.

```graphql
type Query { # on a module's endpoint
  _search(text: String!, types: [String!], limit: Int = 20,
          consistency: Consistency = LATEST, atLeast: String): _SearchPage!
}
type _SearchPage {
  text: String!                      # the text as searched, folded
  hits: [_SearchHit!]!
  counts: [_TypeCount!]!             # one per searched type
  notSearched: [_NotSearched!]!      # every requested type that was not searched, and why
  truncated: Boolean!
  freshness: [Freshness!]!           # one per backend that answered
}
type _SearchHit { type: String!  key: String!  score: Int!  label: String!
                  excerpt: [_Segment!]  matched: [String!]!  entity: Entity! }
type _Segment { text: String!  mark: Boolean! }   # an excerpt as consecutive segments; mark is true for matched text
type _TypeCount { type: String!  count: Int!  atLeast: Boolean! }
type _NotSearched { type: String!  reason: String!  backend: String }
```

| Element | Rules |
|---------|-------|
| `text` | Trimmed with whitespace runs collapsed to one space, then folded (Unicode simple lowercase applied one character at a time, so that a word-final Greek capital sigma folds to σ in the query, the ranking and the excerpt alike; the backend's `lower` is not relied on, as the library re-checks every candidate; no compatibility normalisation and no case folding beyond it). MUST be 2 to 200 characters afterwards and at most 6 words (split on a space); otherwise `BAD_QUERY`. |
| `types` | Entity types of this module. Default: every type the viewer can read that has a searchable property. A name that is not a type of the module returns `BAD_QUERY`. |
| Match | A hit MUST match **every** word (split on a space, kept as typed, none removed as a repeat), each in at least one of the type's searchable properties, case-insensitively, as a substring. A type's searchable properties are its effective `search` list that the serving backend's `searchable` also names. `%`, `_` and `\` in the text match literally. The library MUST re-check every candidate with the same fold before ranking, so a backend's differing case handling cannot show a non-match. |
| Execution | For each searched type whose serving backend declares `substring`, one ordinary `query` of the module as the viewer, `SELECT x.*, RELATED_KEYS(x.r, 100) AS "_r" … FROM module.Type x ORDER BY x.<key> LIMIT 51` (one `RELATED_KEYS` per relationship, its output name never the relationship's own: CONTRACT-006) with `limit=50` and a text match (below), run through the interface's backend choice and consistency rules. A type that has no searchable property, whose backend declares `none`, whose backend is unavailable, or that would exceed the budget MUST appear in `notSearched` with `reason` one of `no_searchable_property`, `no_capability`, `unavailable`, `over_budget`, and MUST NOT be counted as having no hits. A type the viewer may not read is absent from `notSearched` and from everything else. The per-type reads run one after another or on a bounded pool, and the whole search MUST run under one registry revision: a backend that answers under another is `REVISION_CHANGED` as in CONTRACT-006. |
| Rank | For each word the best `tier × (n − i)` over the type's searchable properties (a property at position *i* of *n*), summed over the words. Tier, on the folded value: 4 when the whole value equals the word, 3 when it starts with it, 2 when it occurs at the start of a word within it (after a character that is not a letter or digit), 1 when it occurs anywhere else. `score` is the integer sum. Order by `score` descending, then the module's type declaration order, then key. |
| `limit` | 1 to 50, else `LIMIT_EXCEEDED`. At most `limit` hits are returned. |
| `counts` | For each searched type, in the module's declaration order, the number of candidates that matched after the library's re-check (at most 50); `atLeast` is true when the cap was reached (50 rows returned, or the answer is `truncated`). |
| `truncated` | True if any searched type reached its candidate cap, or hits were cut to `limit`. There is no cursor: a viewer who gets `truncated` chooses one type (the browser's type chips) and lists that type (CONTRACT-006 list reads). |
| `type` of a hit | The module's local type name (`Solution`), as `_TypeCount.type` and `_NotSearched.type`. |
| `label`, `excerpt`, `matched` | `label` is the type's `title` template evaluated; `excerpt` is up to 160 characters around the first match in the first matched property that the type's `title` template does not use (so the title is not shown twice), or `null` when the title uses every matched property, as consecutive segments (at least one segment with `mark` true when a match is in the excerpt), cut at a word boundary where one is near and ending with a segment that includes any ellipsis; `matched` names the properties in which a word matched, in the type's order. A client MUST render each segment as text. |
| `entity` | The matched entity, the same object as `Query.<t>`, from the same row; selecting its fields costs no further read. |
| Cost | The candidates count against the request's 1,000-entity budget (CONTRACT-006), 50 reserved before each query and settled to what it returned; at most 20 types are searched in one request, the rest are `over_budget`. |
| Freshness | `freshness` has one entry per backend that answered, stating consistency and how current as in CONTRACT-006. |
| Principal | Every query runs as the viewer's principal; a hit is only what the viewer may read, and counts are of what the viewer may read. |
| Telemetry | The text and the words MUST NOT be an attribute of any span, metric or log of Arras (CONTRACT-008). |

**Text match** (CONTRACT-001, CONTRACT-004). `query` takes an optional keyword-only `text`, a `TextMatch(words, properties)` that `search` makes; it travels to the backend beside the statement (`Backend.query(principal, module, statement, *, limit, text=None)`). A backend that serves it narrows the statement's rows to the entities for which every word occurs, after the fold, in at least one of the named properties; the statement keeps its own order and bounds. `text` is never carried in SQL, and Arras reads neither it nor the statement. `Capabilities` has `search` (`"none"` or `"substring"`, with `word` and `ranked` reserved) and `searchable` (the string properties, optional ones included, that the backend can match for the type). A backend that declares `substring` MUST treat `%`, `_` and `\` in a word as literal characters, and accepts the cost of a scan on the type. A backend that does not declare `substring` for the type, or a property not in its `searchable`, answers `Unsupported`. The conformance corpus covers it (CONTRACT-004, corpus version 6).

`Ontology.search(module, text, types=None, limit=20, consistency="latest", at_least=None, *, budget=None, revision=None)` is the library operation under `_search`. It returns the page above as plain data (CONTRACT-001); it is a composed read, not a new backend operation. It does not raise for a type it did not search: `_search` turns a page in which no type was searched into the error below, by what stopped it (`UNAVAILABLE` if any type was unavailable, else `COST_EXCEEDED` if any was over budget, else `UNSUPPORTED`). A type that the viewer's backend refuses to read (`no_access`) is left out of everything, as an unreadable type is.

### D. The location

| Element | Type / Shape | Required | Rules |
|---------|---------------|----------|-------|
| Fragment, Explore | `#/explore/<module>/<type>/<key>` | yes | Each segment percent-encoded UTF-8; the whole location is in the fragment and MUST NOT appear in the path or the query string. `#/explore/<module>` opens the module's entry; `#/explore/<module>/<type>` (no key) opens the entry with that type's list, so the list has a location of its own and a breadcrumb can link to it, and `#/explore/<module>/<type>?after=<key>` is that list positioned after the given key (a key, never search text; the only query Explore's grammar allows, and only on a bare type list); `#/explore/<module>/<type>/<key>/history` is the entity's page with its History panel open (a key named `history` is still a key, so its History address ends `/history/history`); `#/explore` opens the module chooser (or the only module). A fragment that does not parse (another query, an extra segment), or names an unreadable or absent entity, shows the "not available" page, which leads to the module's entry when the location names a module the viewer can read and to the start otherwise; its document title is the brand alone and never carries a key. |
| Fragment, Operate | `#/operate/<module>/<area>/<third>` | yes | The Operator Console's own route (FEAT-010), `<area>` is `model`, `graph`, `entities`, `actions`, `changes` or `query`; the area aliases `schema`, `data` and `audit` are accepted for `model`, `entities` and `changes` and the address is rewritten to the area id once, in place. `model[/<type>][?view=umf]` is the model with a type selected, or its UMF source; `entities/<type>[/<key>]` is a type's table with the entity open (the first type is written explicitly), with `?f.<column>=<key>` for the table's filter, written only for a key column (its value is a key; a filter on any other column is typed text and is never written to the fragment, which the table's writer ensures), `after=<key>` for the key its page starts after and `sort=<column>:<asc|desc>`; `graph/<type>/<key>` the selected entity; `changes[/<type>/<key>]` a module's changes or that entity's History, with `?group=<id>` for the receipt of one change group (an opaque id), `action=<name>`, `since=<instant>` and `until=<instant>` (ISO 8601) for the filters, and `view=loads` for the import loads instead of the changes; `actions/<action>[?in.<input>=<key>&…]` an action with ref inputs prefilled from entity keys: an entry whose input is not a ref input of the action, or whose value is not a key, is left out, so a link never fills a typed field. A query string carries only keys, group ids, column ids, sort directions, instants, action names and the view names `umf` and `loads`: never a person, search text, a query's statement or any other typed value. Every segment and value is percent-encoded, a value that does not fit its field is left out, and a fragment that does not fit falls back to the module's area. An address that parses but names nothing the viewer can open (a type or action the module does not declare, an entity that cannot be read, a group with no changes) shows one not-found page, the same for every cause, that links to the module's Model. Each navigation adds a history entry and Back and Forward restore the console. With no prefix, a fragment is read as an Operate route for an operator and opens Explore's entry for anyone else. |
| Fragment, mode aliases | `#/browse/...`, `#/admin/...` | yes | `browse` and `admin` are alias ids, accepted as the first segment for `explore` and `operate` and mean the same; the shell rewrites the address to the mode id once, in place (replace, not push), keeping the rest of the fragment (an Operate address also has its area ids rewritten). |
| History state | `history.state` | yes | Carries the search text, the chosen types, the picture's hops, the scroll position and, on an entity's History entry opened from the entity, the mark that closing it goes back (the browser's own session history, not storage written by Arras), and nothing of them in any part of the URL. |
| `<GraphBrowser>` props | `location?: {module?: string, type?: string, key?: string, history?: boolean, after?: string}`, `onLocation?: (l: {module?, type?, key?, history?, after?}, opts?: {replace?: boolean}) => void`, `links?: {toOperate}` (E), `canEdit?: boolean` (F) | no | When a host passes `location` the browser MUST NOT read or write the URL and MUST call `onLocation` on each navigation, with `{replace: true}` where the entry is rewritten rather than added (Show next, Retire); a host-owned location carries the same fields as the fragment. Without them the browser uses the fragment. |
| Request hygiene | | yes | A request MUST NOT carry the key, the search text or a person in a path, query string or `Referer`; search and reads are `POST` bodies (CONTRACT-006). |

### E. Modes

The shell (`<ArrasApp>` in `arras-ui`) offers two modes: **Explore** (id `user`), the Graph Browser, the instance tool, and **Operate** (id `admin`), the Operator Console, the model and platform tool (FEAT-010). The host protocol keeps the ids `user` and `admin` (`GET /viewer`'s `modes`, `defaultMode`, `Mode`) where the labels are Explore and Operate: `admin` is a protocol value and never appears as a label, and the route ids are `explore` and `operate`. Explore is the default for everyone; Operate is offered only to operators, and the same offer decides whether Explore offers writes (F).

| Element | Type / Shape | Required | Rules |
|---------|---------------|----------|-------|
| `authorize_operator` | `Callable[[Principal], bool] \| None` on `arras.operate.create_app` | no | The host's decision that a principal is an operator (a builder or an administrator). `arras.operate.operators_in_groups(*groups)` builds one from group names the host configures (the embedding host: `admins` and `builders` by default, read from `Principal.groups`). Arras keeps no role model (PRD non-goals) and never infers operator from `Principal.groups` or `Principal.admin` by itself; the host decides. The hook runs on the operate pool and within the per-person and global in-flight caps of CONTRACT-009 (over a cap the request is 429 as any other), so a viewer who is not an operator cannot make the host's hook run without limit. Default `None`: every principal that `principal_for_request` accepts is an operator, which is CONTRACT-009's own default; a host that serves the Graph Browser to people who are not operators MUST pass it. |
| `GET {operate_base}/viewer` | JSON `{user: string, modes: ["user"] \| ["user", "admin"]}` | yes | Answers for the request's principal: `admin` is present exactly when `authorize_operator` is `None` or returns true; a hook that raises is false. 401 as the rest of the surface when there is no principal. It answers a non-operator, as `GET /version` and `GET /openapi.json` do. |
| Operator refusal | HTTP 403, `{error: "REFUSED", reason: "not_operator"}` (`error` is the plain string here, not the object of the other errors) | yes | Every other operate endpoint (CONTRACT-009: catalog, validate, invoke, batch, changes, loads) MUST refuse a principal for whom `authorize_operator` returns false, before the body is read and before any other work (an origin refusal of a `POST` comes first, and a missing principal is 401), with this answer. `GET /version` and `GET /openapi.json` (a static document) answer anyone. The console GraphQL surface (CONTRACT-006) is unchanged: it serves any viewer the backends let read, which is what Explore uses. |
| Offer, not permission | | yes | Operate is a convenience of the interface, not an authorization: what a person may read or change is decided by the backends' grants (ADR-017) and, for the operate surface, by `authorize_operator` and `authorize_action`. |
| `<ArrasApp>` | Props as `ArrasConsole` and `GraphBrowser`, plus `defaultMode?: "user" \| "admin"` and `brand?: Brand` (Brand) | yes | Asks `/viewer` once at load. With `admin` absent it renders Explore only and MUST show no control, link or hint to Operate. With it present it shows a mode switch in the top bar (two options, `Explore` and `Operate`, the chosen one `aria-pressed="true"`), remembers the choice for the session in `history.state` and in the fragment prefix, and opens in Explore unless `defaultMode` or the fragment says otherwise. Switching carries what is open both ways: Operate opens Entities on the node's module and type with its entity open, and Explore opens the node page for the entity open in the console, else its type's list, else the module's entry; each switch is a history entry. A fragment naming Operate, opened by a non-operator, shows Explore's entry. |
| Shared state | | yes | The shell holds what a mode switch must keep: one `QueryClient` (so one invalidation scheme reaches every read of both modes), one meta read (the client's `meta()`), the edit-mode lock, the single-key shortcut switch, the command palette with its shortcut help, and the Query area's session (its draft, consistency and history). All of it is in memory and lives as long as the page; none of it is in browser storage, a URL or a log. A mode given no cross-mode link primitive by the shell shows no cross-mode link, so a standalone `<GraphBrowser>` or `<ArrasConsole>` shows none. |
| Cross-mode links | | yes | The shell gives each mode a function from a target (`{entity \| type \| module \| group, area?}`) to `{href?, go()}`, offered only where `admin` is present: an anchor where an `href` exists, and `go()` where the host owns the location. A target's type names are qualified; the shell is the only place that converts them to either mode's address (`ui/src/shell/links.ts`), and it hands Explore `links: {toOperate}` and Operate `links: {toExplore}`. **Open in Operate** (Entities, History, Actions) on a node page and **Model** on a type's list are Explore's; **View in Explore** is Operate's. |

### F. Edits and instance work

Explore changes data only where the module already declares how. The browser adds no write path of its own: each of its writes (an edit, a link, a new entity, a retirement, another entity action) is the `validate` and then the `invoke` of a declared action (CONTRACT-003), run on the operate surface as the viewer (CONTRACT-009). Plans are derived from declarations only, never from names (SD-013 Rules 1 to 4).

| Element | Type / Shape | Required | Rules |
|---------|---------------|----------|-------|
| `canEdit` | `<GraphBrowser>` prop, boolean, default `false`; widens to New, Retire, Actions and History | no | The host's offer of writes to this viewer: edits, links, New, Retire, the Actions menu and History. `<ArrasApp>` sets it to whether `GET /viewer` lists `admin` (E), so a non-operator is offered none; a host that mounts `<GraphBrowser>` alone sets it from its own decision. It is an offer, not a permission: the action's `authorize_action`, `authorize_operator` and the backends' grants decide what is applied. |
| Meta read | | yes | The browser and the console make one meta read (the client's `meta()`, the query key `["meta"]`): each module's `view`, types, relationships, `actions` (`name`, `description`, `inputSpecs`, `preconditions` and `effects`, which Explore's read carries for the plans below) and status, then each type's resolved view, merged by the client. An entity's name in either mode is the type's `title` template evaluated over its placeholders. |
| Editable property | | yes | A property of the node's type is editable when it is not the key, is a scalar of type `string`, `integer`, `decimal`, `boolean` or `timestamp` with cardinality one or optional, and some action of the module has exactly one effect, an `update` of this type, whose key is a `ref` input of cardinality one and whose `properties` set this property from a scalar input. Two shapes qualify. *Alone*: every other input of the action is optional, so the property can change by itself. *Together*: every input of the action other than the key is a scalar value for a property of the update, some of them required, so the properties can only change together. An action with any other input (a record, a list, a second reference) qualifies for neither. Where several actions qualify, one that changes the property alone wins over one that changes it together, then the one that updates the fewest properties, then the first by name. A property no action qualifies for has no edit. |
| Edit mode | | yes | The edit controls show only in edit mode, which the reader turns on and off with a lock at the top right of the node card (closed while off, open while on); the lock is shown only where `canEdit` is set and the page has an editable property. The mode is the reader's choice for the session and holds while moving between nodes. |
| Form | | yes | A property that changes *together* opens a popup form (`role="dialog"`, `aria-modal`) with one input for each property the action sets, started from the node's current values, saved with one `validate` and `invoke`. A required input left empty is refused in the browser; an empty optional input is left out of `inputs`, so that property is kept as it is. Escape and Cancel close it without a write, and focus stays inside it while it is open. |
| Change | | yes | The editor sends `validate` and, if it is `ok`, `invoke` with `inputs` of the key input and the value input only (for a form, the key input and one value input for each property it asks for), `expected_revision` of the module's revision the page was read at, and an `idempotency_key` kept for the same inputs. The value is encoded as the action's input type is (CONTRACT-009); an empty value is refused in the browser, since the actions give no way to clear a value. A refusal (a violation, a precondition, `no_access`, a revision conflict) is shown at the property in words and nothing is applied; the editor stays open. After an apply the page, its labels and any search are read again. |
| Request hygiene | | yes | As D: the key is in the `inputs` of a `POST` body, never in a path or query string. |
| Link plan | | yes | A relationship group of a page, whichever end the page is, can have a link added where the module declares an action with exactly one effect, a `link` whose `type` is the relationship's name and whose `source` and `target` are `{name}` expressions for two `ref` inputs of cardinality one, typed as the page's type and one of the other end's types, every other input of the action being optional; and a link removed where such an action's effect is an `unlink`. The group named by the relationship is the page as source, the group named by its inverse the page as target, and the page's key fills the input of its end. Where several fit, the ranking is SD-013 Rule 1a. A relationship the module declares no such action for has no control. |
| Link controls | | yes | In edit mode a group with an add plan offers **Add** (even when empty and `hideWhenEmpty`), and each member of a group with a remove plan offers a remove control. Add opens a popup (`role="dialog"`, `aria-modal`) that lists the entities of the types the other end may be at once, in key order, up to the list read's page of 100 for each type (CONTRACT-006), grouped with their type where more than one is allowed; the reader narrows the list by typing, locally when the list is complete and, when a type has more than the list holds (the popup says so), by the search read (CONTRACT-010 C) restricted to those types once the text is long enough to search. A linked end is shown disabled as "Already linked". Saving sends one `validate` then `invoke` with only the two keys. Where the list cannot be read the reader types the key and the action says whether it names something. Remove asks once, then `validate` and `invoke`. A refusal is shown where it was asked, nothing is applied, and the member or dialog stays. After a change the page, its labels and any search are read again. |
| New | | yes | Where `canEdit` is set and edit mode is on (the lock, drawn beside the list's heading), a type's list offers **New <type>** for a `createPlan`: an action whose effects are exactly one `create` of the type and any number of `link` effects of which one end is the created alias and the other a `ref` input or another alias. The form asks for every input of the action (a `ref` input through the picker, a list input one value per line, a record input as JSON, the key as an ordinary field unless generated). **Validate** shows the effects as text and any refusal in the dialog, violations that name an input at that field; **Create** is offered once the validation has passed and invokes. The browser then opens the created entity from the validated `create` effect's key, confirmed by the receipt's ref of the created type (a receipt that does not carry that key names the entity only when it holds exactly one ref of the type; otherwise the receipt is shown). The new page is read like any other, at the default consistency `latest`, which only the module's record store serves; the browser passes no `at_least`. The picker is also the `ref` field of the Actions menu's dialogs and of Retire's optional inputs, and lists up to a page of the referenced type's entities, narrowed by the text typed above it or searched where the type has more; where the type cannot be read it is the key field. Several create actions for a type are offered in a `Select`, the one with the fewest inputs first. A type with no create plan has no New. |
| Retire | | yes | In edit mode a node page offers **Retire**, an item of the header's entity menu (`role="menu"`), for a `retirePlan`: an action whose one effect is a `delete` of the type, keyed by a `ref` input, every other input optional. The confirmation names the entity's links from the page's own read, says the key cannot be used again and that there is no undo, then validates and invokes; the browser then opens the type's list, replacing the entity's history entry. What a delete does to links is unspecified (CONTRACT-003, 004). A type with no retire plan has no Retire. |
| Actions menu | | yes | In edit mode the header's entity menu lists, after Retire, every other declared action with a `ref` input typed as the page's type that no inline plan (edit, link, retire, create) claims, by its label with its description as secondary text, whose inputs and effects the generic form can ask for and summarise. An item opens a dialog with the form, the entity prefilled, then `validate`, a text summary of the effects, `invoke` and a receipt with links to the entities it touched. Batch is not offered. A refusal is shown where it was asked and nothing is applied. |
| History | | yes | An operator's node page offers **History**, the entity's changes by the operate surface's `changes` read (CONTRACT-009) by qualified type and key, the module inferred from the type, newest first, 20 a page. A change names who, when, its action and what it touched (each entity named in its `ops`, either end of a link counting); a touched entity resolves through the normal read and one the viewer cannot read shows as "not available" with no key. The panel's address is D's `/history`. A refusal for lack of the journal grant (403) and a backend that keeps no journal (501) are each one sentence, not an error panel; the journal grant, not the edit offer, decides what shows. A change's group links to Operate's receipt view where Operate is offered. |
| Export | | yes | Where `canEdit` is set, the module's entry page offers **Export graph**: it reads the module through `POST /export` (CONTRACT-009) a page at a time and saves one file, `<module>.graph.json`, in the graph file format of CONTRACT-003 (Export), the same bytes the library writes. It says how many records were saved and, when the file is `complete: false`, which types could not be read. It is a read and needs no edit mode. |

### Brand

The interface's name is configuration, not code (FR-73, SD-013 D11).

| Element | Type / Shape | Required | Rules |
|---------|---------------|----------|-------|
| `brand` | `{name: string, wordmark?: string, title?: string, tagline?: string, logo?: "theme"}` | no | The application name (at most 80 characters, not blank), an optional wordmark (an `https://` image URL, shown as an image in the top bar with the name as its text alternative, or any other text, shown in place of the name), an optional page title (else the name), an optional line under the name and `logo: "theme"`, which shows the design system's mark (`Mark`, labelled by the name) before the name in the top bar; a wordmark takes precedence over it, and any other `logo` value is ignored. Defaults to `{name: "Arras"}`; the default is the only place the product's name is a user-visible literal. A field over its cap (wordmark 2048, title 120, tagline 200) is cut; a field that is not text is ignored. |
| `useBrand()` | React context | yes | `<ArrasApp>` provides the brand, and `<GraphBrowser>` and `<ArrasConsole>` provide it for themselves when used alone (`lib/brand.tsx`). A host passes `brand` to any of the three. |
| Meta tag | `<meta name="arras-brand" content="…">` | yes | The served page carries the brand as HTML-escaped JSON of the fields that are set, and its `<title>` is `brand.title` or `brand.name`; the page's strict policy forbids inline scripts, so the app reads the tag at start. A missing or malformed tag, or one with no name, gives the default brand. `arras.ui.create_app(brand=Brand(...))` renders both; a wordmark that is a URL of any scheme but `https`, or a `logo` other than `theme`, is a `ValueError`. Each field has a cap the page and the library share (name 80, title 120, wordmark 2048, tagline 200 characters, counted as the browser counts after trimming; `tests/vectors/brand.json` is checked by both): the page cuts a longer field to its cap and `Brand` refuses one, so a field is never shown cut short. An image wordmark is the literal `https://` form: an `https://` value with whitespace, `;`, `,`, a quote, userinfo or no host is a `ValueError` too. The served page's policy is `img-src 'self'` (the theme's mark is the page's own asset) plus the image wordmark's origin and nothing else (`Brand.csp()`). |
| Where the name appears | | yes | Only in: the document title (`<entity> · <area> · <module> · <title or name>`, empty parts dropped), the page's `<title>`, the GraphiQL page's title (`<name> console`) and the OpenAPI `info.title` (`<name> operator surface`), the top bar's wordmark in both modes, labels of landmarks and dialogs that name the product, the shortcut help's heading and the "not built" placeholder page. No other user-visible string names the product; `brand-strings.test.ts` fails a literal product name in any JSX text, string or template outside `lib/brand.tsx` (comments, identifiers, package names and developer-facing errors are allowed). |

## Precedence and Compatibility

- Versioning: v1; versions in `arras.CONTRACT_VERSIONS["browser"]` (this contract) and `["operate"]` (unchanged, because the additions are additive). The vocabulary has its own version (0.1.0).
- Ordering or precedence: a view is read from the document at the request's revision; a declared term overrides its default; a record's `search` overrides the derived search list; an explicit `[]` disables search for the type.
- Backward-compatibility rules: a document without `arras.view` registers unchanged and resolves to the defaults. The vocabulary is closed: a release refuses a document using a term or version it does not know; a newer term is added by a vocabulary minor version and read only by releases that list it. An operate app built without `authorize_operator` treats every accepted principal as an operator.
- Deprecation rules: a term is deprecated for a vocabulary major version before removal; a deprecated term still validates and still resolves.

## Error Semantics

| Condition | Error / Outcome | Retry | Recovery Expectation |
|-----------|------------------|-------|----------------------|
| Declaration fault | Registration refused with a `Violation` list; registry unchanged | No | Fix the document and register again |
| Text too short, too long, more than 6 words, an unknown type | `BAD_QUERY` on `_search` | No | Correct the request |
| `limit` outside 1 to 50 | `LIMIT_EXCEEDED` | No | Use 1 to 50 |
| Budget exceeded | The type is `notSearched` with `over_budget`; other types answer. If no type could be searched the field returns `COST_EXCEEDED` | Narrow `types` | Narrow by type |
| A backend unavailable | The type is `notSearched` with `unavailable` and the backend; other types answer. If every requested type is unavailable `UNAVAILABLE` | Yes | Retry later |
| A backend declares no search | The type is `notSearched` with `no_capability`; if no requested type is searchable `UNSUPPORTED` | No | List by type |
| A search spans two revisions | `REVISION_CHANGED` | Yes | Retry |
| Viewer lacks access to the module | 404, as CONTRACT-006 | No | None |
| Token expired | 401 `REFUSED` `token_expired`, as CONTRACT-006 | After sign-in | Sign in again |
| A non-operator calls an operate endpoint | 403 `REFUSED` `not_operator` | No | Use Explore |
| History read refused for lack of the journal grant | HTTP 403 | No | The panel says so in a sentence |
| History read on a backend with no journal | HTTP 501 | No | The panel says so in a sentence |
| Location unreadable or entity unavailable | The "not available" page (the same for every cause) | No | None |

## Examples

A `Solution` view in the catalog's UMF document:

```json
{
  "vocabularies": { "umf.ddd": { "version": "0.1.0" }, "arras.view": { "version": "0.1.0" } },
  "modules": [{
    "id": "catalog",
    "extensions": { "arras.view": { "title": "Product catalog", "description": "Use cases, Solutions, products and findings" } },
    "elements": [
      { "id": "Solution", "kind": "record",
        "extensions": { "arras.view": {
          "label": "Solution", "icon": "puzzle", "tone": "blue",
          "title": "{name}[ ({code})]", "summary": "{summary}",
          "sections": [
            { "label": "Delivery", "properties": ["deliveryMode", "audience", "launchUrl"] },
            { "label": "How it works", "properties": ["workflow", "prompt"], "collapsed": true }
          ],
          "search": ["name", "code", "summary"]
        } } },
      { "id": "Solution.deliveryMode", "kind": "field",
        "extensions": { "arras.view": { "label": "Delivery", "format": "badge", "tones": { "Embedded": "teal", "Standalone": "blue" } } } },
      { "id": "Solution.launchUrl", "kind": "field",
        "extensions": { "arras.view": { "label": "Launch", "format": "link", "hideWhenEmpty": true } } }
    ],
    "relationships": [
      { "id": "solution-providedby", "name": "providedBy", "inverse": "provides",
        "extensions": { "arras.view": { "label": "Provided by", "inverseLabel": "Provides", "order": 10 } } }
    ]
  }]
}
```

A refused declaration (a misspelled property):

```text
Violation(path="modules[0].elements[0].extensions.arras.view.sections[0].properties[2]",
          code="view_unknown_property",
          message="Solution has no property 'sumary'")
```

A search request and answer (a module endpoint, `POST /graphql/catalog`):

```text
{"query": "query($t:String!){ _search(text:$t, limit:5){ hits{ type key label score excerpt{ text mark } } counts{ type count atLeast } notSearched{ type reason backend } truncated freshness{ backend asOf at consistency } } }",
 "variables": {"t": "lumen alert"}}

200
{"data": {"_search": {
  "hits": [
    {"type": "Solution", "key": "sol-lumen-correlate", "label": "Lumen alert correlation (sol-lumen-correlate)", "score": 17,
     "excerpt": [{"text": "…uses ", "mark": false}, {"text": "Lumen", "mark": true}, {"text": " for ", "mark": false}, {"text": "alert", "mark": true}, {"text": " correlation…", "mark": false}]},
    {"type": "Product", "key": "lumen", "label": "Lumen", "score": 14,
     "excerpt": [{"text": "Lumen", "mark": true}, {"text": ": log search for ", "mark": false}, {"text": "alert", "mark": true}, {"text": " work", "mark": false}]}
  ],
  "counts": [{"type": "Solution", "count": 3, "atLeast": false}, {"type": "Product", "count": 1, "atLeast": false}, {"type": "Finding", "count": 0, "atLeast": false}],
  "notSearched": [{"type": "UseCase", "reason": "unavailable", "backend": "ashlar"}],
  "truncated": false,
  "freshness": [{"backend": "truss", "asOf": "lsn 0/1A2B3C", "at": "2026-10-11T09:30:00Z", "consistency": "LATEST"}]
}}}
```

The viewer's modes:

```text
GET /api/operate/viewer   (as alice, a builder) -> 200 {"user": "alice", "modes": ["user", "admin"]}
GET /api/operate/viewer   (as carol, a reader)   -> 200 {"user": "carol", "modes": ["user"]}
POST /api/operate/validate (as carol)            -> 403 {"error": "REFUSED", "reason": "not_operator"}
```

A location:

```text
https://host.example/catalog#/explore/catalog/Solution/sol-lumen-correlate   (host path, no key outside the fragment)
```

## Non-Normative Notes

- The tone and icon names are deliberately semantic-free beyond the hue and glyph, so a module does not encode meaning in a colour; a tone always accompanies an icon or a label in the browser (DESIGN-GB).
- Rank scales by position rather than a numeric weight: three words in a three-property list cannot be tied by a weight a module author guessed, and the order is something an author already thinks in.
- The vocabulary omits: paging a multi-type search (narrow by type and list), a two-hop picture, decimals, per-row `hit` badges and a numeric weight. Each is an additive vocabulary or contract minor version.
- A title, summary or section can name only the entity's own properties: a template cannot reference a related entity, so a type that is mostly a relationship (a coverage assertion between a product and a use case) cannot be titled by the entities it joins. Its key or code carries the names, and this is the known limit for relationship-like entities.
- The sidecar carrier (ADR-022's fallback) would hold the same terms in a companion document registered with the module; sections A and B would be unchanged.
