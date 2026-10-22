---
ddx:
  id: proposed-external-interface
  type: design
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: CONTRACT-001
      kind: informed_by
    - id: CONTRACT-003
      kind: informed_by
    - id: CONTRACT-007
      kind: informed_by
---

# Arras: proposed external interface

**Status**: proposal for review by consumers (the embedding host, the product catalog, the use case inventory, Python plug-ins). The normative text is in [CONTRACT-001](contracts/CONTRACT-001-ontology-interface.md) to [CONTRACT-007](contracts/CONTRACT-007-mcp-binding.md); this page is the short version a consumer needs.

Terms used on this page:

- Arras is the interface to an ontology.
- UMF (the metamodel, owned by DocumentDrivenDX) is the format in which a module defines its types and actions.
- A backend is a named store the host configures: a reader (serves graph reads) and/or a provider (applies actions). A module's placement names its record store (the reader that is its system of record and serves `latest`), its replicas (other readers, which serve `bulk` and may lag) and the provider of each action (the record store by default). There can be several of each.
- Truss (DocumentDrivenDX) is the UMF-driven property-graph engine on Lakebase (Databricks managed Postgres); its adapter is a reader and a provider.
- Ashlar (DocumentDrivenDX) is the toolkit for property-graph ontologies on a warehouse, running on Unity Catalog (the Databricks governance layer). Its adapter is a reader: it serves bounded reads over the full ontology and may be older than the record store.
- The embedding host owns deployment and session identity.
- MCP (Model Context Protocol, Anthropic's open protocol for agent tools) is the protocol agents use to call tools. stdio means the server talks over standard input and output.
- Weft (DocumentDrivenDX) owns the SQL language `query` takes; the serving backend compiles and runs the statement.
- ADR is an architecture decision record; ADR-005 gates structure derived from sensitive source records.

## What it is

Arras is one interface to the ontology. A module defines its types and actions in UMF. You read with one `query` and change with named actions. Every read says how fresh it is. Everything runs as you, with your own token.

You reach it two ways, with identical behavior: a Python library (`arras`) or a stdio MCP server (`python -m arras.mcp`) built on the library.

## Five rules

1. Your token, always. Every call carries the signed-in person's token. There is no service identity and no caller-asserted author. What you may read or change is what the backend grants that person; a change is attributed to them.
2. Reads state their freshness. Each answer names the backend that served it and the point in time it reflects. `latest` comes from the module's record store; `bulk` may come from a replica and may be older; a read at a receipt's token (`at_least`) is how a client sees its own change. Arras never serves a different level than you asked for, and never falls back silently.
3. Writes are actions. There is no create/update/delete API. A module declares actions with typed inputs, preconditions and effects; an action applies atomically or not at all.
4. Everything is bounded. Pages are at most 100 rows; batches at most 100 items; no unbounded read.
5. Refusal, outage and empty are different answers, so you can fail closed on each.

## Read

```python
ontology = arras.session(Principal(user="jsmith", token=tok, groups=()))

ontology.describe()            # modules, types, columns, relationships, actions, capabilities, backend status
ontology.query(
    "catalog",
    "SELECT u.code, u.name FROM catalog.UseCase u WHERE u.workArea = :p ORDER BY u.code LIMIT 50",
    {"p": "data"}, limit=50)                          # -> Rows
```

`describe` tells you, per type and backend, which columns and relationships you may select and filter, whether counts are served, and whether the type is mutable.

`query(module, sql, params=None, *, limit=50, consistency="latest", at_least=None)` reads one module, which you name; Arras routes by that module's placement and never reads the statement. It returns `Rows`: `rows` (dicts), `columns`, `truncated` (the `limit` cap, 1 to 100, cut the result), `freshness {backend, as_of {value, at}, consistency}`, and the ontology `revision`.

### Example statements (Weft SQL; what is served is what the backend's declared Weft profiles admit)

| You want | Statement |
|----------|-----------|
| One entity by key | `SELECT u.* FROM catalog.UseCase u WHERE u.code = :k ORDER BY u.code LIMIT 1` (no row if absent, not an error; a bare `SELECT *` is not accepted). `u.*` carries the declared fields and the entity facts the backend appends (`_version`, `_created_by`, `_updated_at`, ...) |
| A list | `SELECT u.code, u.name FROM catalog.UseCase u WHERE u.workArea = :p ORDER BY u.code LIMIT 50` |
| An entity with its relationships | `SELECT u.*, RELATED_KEYS(u.addressedBy, 100) AS addressedBy FROM catalog.UseCase u WHERE u.code = :k ORDER BY u.code LIMIT 1` (the statement bounds the keys) |
| Entities connected to a key | `SELECT s.* FROM catalog.Solution s WHERE HAS_RELATED(s.addresses, KEY(:k)) ORDER BY s.code LIMIT 50` |
| The next page | `SELECT u.code, u.name FROM catalog.UseCase u WHERE u.code > :last ORDER BY u.code LIMIT 50` |
| Counts (depends on Weft) | `SELECT u.workArea, COUNT(*) FROM catalog.UseCase u GROUP BY u.workArea ORDER BY u.workArea LIMIT 50` |

Weft owns the grammar, so joins, ordering, bounds and paging are Weft's: a page is `ORDER BY`, `LIMIT` and a keyset predicate in the statement, and the answer carries no cursor. They are available where a backend declares a profile that admits them. A statement neither Weft nor the backend serves, or one that reads outside the named module, is refused with `Unsupported`, carrying the construct and what is supported.

### Read your own write

An action's receipt carries a `token`. Pass it as `at_least` and the answer is at least that new, whichever backend serves it; otherwise you get `NotYetCurrent`.

## Change

```python
ontology.validate("catalog.CreateCandidateSolution", {"coverageAssertion": "ca-0042", "useCase": "uc-1"})
# -> Validation(ok, violations, failures, effects, replay): a dry run; nothing written

ontology.invoke("catalog.CreateCandidateSolution", {...}, idempotency_key="ui-7f3a")      # -> Receipt
ontology.invoke_batch("catalog.CorrectSolution", items, atomic=False, idempotency_key="fix-1")   # -> BatchReceipt
```

- Declared and discoverable: actions, inputs, preconditions and effects come from `describe`. Effects are a closed list: create, update, delete, link, unlink, and `foreach` over a list input.
- Atomic and checked: inputs and preconditions are validated first and every failure is reported at once; a refused action changes nothing.
- Idempotent: repeat a call with the same key and inputs and you get the original receipt. Same key, different inputs is a `Conflict`.
- Receipt: entities created/changed/deleted with versions, counts, a `token`, and `replayed`.
- Bulk: `foreach` inside an action (one group, up to 1,000 effects); `invoke_batch` for up to 100 invocations, either atomic as one group or each independent with a per-item result and index. Large loads are an administrator's import, not a client call.
- Single backend: an action runs on one module's provider; it never spans backends. Modules with no provider for an action (their record store is read-only and none is placed) have no actions.

## MCP binding

`python -m arras.mcp` speaks MCP over stdio for one person; the embedding host launches one per session with that person's token (file re-read for refresh).

| Tool | Purpose |
|------|---------|
| `describe` | Types, columns, relationships, actions, backend status |
| `query` | The read above |
| `validate_action` | Dry-run any action |
| `<module>_<snake_action>`, one per declared action | Invoke it with `inputs` or a batch `items`, `atomic`, `idempotency_key` |

Each action is its own tool so the host can classify and approve it by name. Answers are compact and bounded; refusals come back as `{code, message, hint}` with what to do next; a backend that is down at start does not stop the server (`describe` says which, and the tool list updates when it recovers). The server cannot migrate, register or import.

## Errors

| Error | Meaning | Retry |
|-------|---------|-------|
| `Invalid` | A parameter, input or bound is wrong; all violations listed | After correcting |
| `PreconditionFailed` | A declared condition does not hold; each listed with its reason | After the state changes |
| `Refused` | No access, or the token is missing or expired | After access or re-authentication |
| `Unavailable` | A needed backend is unreachable (names backend and reason) | Yes |
| `Unsupported` | The query shape or capability is not offered; lists what is | No |
| `NotYetCurrent` | `at_least` not reached in time | Yes, or read `latest` |
| `Conflict` | Idempotency key reused with different inputs | No |

## Out of scope

No generic get/list/traverse/aggregate/changes calls (use `query`); no history or change-feed read; no joins or recursive traversal; no writes outside actions; no caching of data or access decisions; no structure derived from sensitive source records (ADR-005).

## Questions for consumers

1. Is the statement set above enough for your screens and agents, or what is the first missing shape?
2. The embedding host: can a per-session stdio process receive a user token and its refresh (a token file is proposed)?
3. Which actions and counts does your first module need?
4. Is `bulk` freshness acceptable for your reads, and what age would you tolerate?
