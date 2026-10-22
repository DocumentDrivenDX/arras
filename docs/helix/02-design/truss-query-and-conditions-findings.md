# Truss 0.0.45 and Weft 0.4.49: query refusals, nameless documents and condition precedence

Measured with `truss-toolkit` 0.0.45 (the corpus cases) and 0.0.41 (the timings below, not repeated) and `weft-sql` 0.4.49 on PostgreSQL 18.6 (a throwaway `pgserver` for the corpus runs and a persistent Homebrew PostgreSQL 18 for the dev host). The captures in sections 1 and 2 are the calls the host's adapter made; the host's corpus cases that pin them (`read.relationship-columns-follow-ends`, `read.relationship-columns-are-capped`, `action.applies-atomically-and-reads-back`, `action.conflict-rolls-back-the-unit`) end at the same step with the same refusal on 0.0.41, and a document with every `name` removed registers on 0.0.41 (a pizza document, measured). Where something was not run it is marked unverified.

## 1. Query refusals

### 1.1 `WFT-OUTPUT-NAME` on a whole-entity read with an explicit relationship alias

Call (as made, `QueryRows` options shown):

```
query_in_transaction(
  tx,
  sql='SELECT x.*, RELATED_KEYS(x."addressedBy", 100) AS "addressedBy", RELATED_KEYS(x."coveredBy", 100) AS "coveredBy", RELATED_KEYS(x."evidence", 100) AS "evidence", RELATED_KEYS(x."adjacentEvidence", 100) AS "adjacentEvidence" FROM "catalog"."UseCase" x ORDER BY x."code" LIMIT 51',
  document_ids=('praxis-catalog',),
  parameters=None,
  maximum_rows=10000,
  read_profile='complete-entity')
```

Module `catalog`, type `UseCase` (document id `praxis-catalog`; four relationships: `addressedBy`, `coveredBy`, `evidence`, `adjacentEvidence`). No bind parameters.

Result, in full:

```
QueryRefused(code='invalid_query',
             diagnostics=(QueryDiagnostic(code='WFT-OUTPUT-NAME', message='Repeated output name'),),
             outcome='refused')
```

The same shape on a second module (`pizza`, type `Pizza`, relationships `hasTopping`, `hasBase`, `countryOfOrigin`, document `pizza-example`) gives the identical refusal. Under `complete-entity` the result already carries one column per relationship named as the relationship (R17.2a), so the explicit `AS "<relationship>"` repeats the output name. This is the behaviour already recorded as R17.2c; it is now the failure of the list read of every sample module with a relationship.

Under `complete-entity` the same module's `SELECT x.* FROM "pizza"."Pizza" x ...` returns the columns `code, name, description, price, vegetarian`, the eight facts, then `hasTopping, hasBase, countryOfOrigin` with their keys. The host names its own keys column `_hasTopping` (and so on): that statement is accepted and returns both columns, the same keys twice.

### 1.2 `WFT-NAME-MISSING` on a module whose record and field elements carry no `name`

Document: `pizza-example` as the host generated it before the fix: record and field elements had `id`, `kind`, `members`/`scalarType`, `nullability`, `cardinality` and `extensions`, and no `name` member (the catalog example's elements have `"name"`).

Truss accepted and registered the document. Two queries then failed:

```
query_in_transaction(tx, sql='SELECT x.code FROM pizza.Pizza x LIMIT 1',
  document_ids=('pizza-example',), parameters=None, maximum_rows=10000, read_profile=None)
-> QueryRefused(code='invalid_query',
     diagnostics=(QueryDiagnostic(code='WFT-NAME-MISSING', message='Selected member name missing or ambiguous'),),
     outcome='refused')

query_in_transaction(tx, sql='SELECT x.* FROM "pizza"."Pizza" x ORDER BY x."code" LIMIT 51',
  document_ids=('pizza-example',), parameters=None, maximum_rows=10000, read_profile='complete-entity')
-> QueryRefused(code='invalid_query',
     diagnostics=(QueryDiagnostic(code='WFT-NAME-MISSING', message='Property not found among record members'),),
     outcome='refused')
```

The same two statements on `praxis-catalog` (elements with `name`) return `QueryRows`. Every statement over the nameless module failed the same way, including `SELECT x.name` and `SELECT x.price`.

## 2. A first write refused as input on the same nameless module

Group sent for the first seed step `pizza.AddCountry {code: italy, name: Italy}` against the nameless `pizza-example`:

- `GroupSemanticInput`, layout profile `truss-layout` 1.0, mutation profile `truss-owned-scalar-graph` 0.1, value profile `truss-scalar-string-values` 0.6, `catalog=CurrentCatalog(selection='current')`, `interface_version='truss-group-input/0.1.0'`.
- one operation: `CreateObject(type_definition_pin='aa03bfba...6e00', values=(AuthoredValue('code', TextValue('string','italy')), AuthoredValue('name', TextValue('string','Italy'))), ownership=RootlessOwnership, alias='e1')`.
- `asserted_origin`: map `{x-action: 'pizza.AddCountry'}`.
- one precondition: `KeyAbsent(id='fresh', reason='a country with that code exists', key_id='identity', values=(TextValue('string','italy'),))`.
- request: `RequestPresent`, `request_id='91668fa7-a034-442b-8299-6538be8845a3'`, `input_profile='truss-group-input/0.1.0'`, scope a `truss-person:` identity.
- documents: the one `pizza-example` document, revision `accepted`.

Result: `Ok(GroupFailed(failure=InvalidGroupInput(diagnostic_profile=truss-native-create-diagnostic 0.1, code='invalid')))`, whose artifact decodes to `{"code": "invalid_input", "outcome": "failed", "nativeState": "22023", "operationIndex": "0"}` (22023 is PostgreSQL's invalid_parameter_value).

The identical group against the same document with `name` added to every record and field element returns `AppliedPending` (receipt `created=1`). Nothing else differed, so the missing `name` is the whole cause. Unverified: a reproduction against the public toolkit alone (install, register a nameless document, create one object) was not built; the evidence above is through the host's adapter, whose request is the one printed.

Ask of Truss (this strengthens R16.4): register should refuse a record or field element with no `name`. A nameless document is accepted today and then every read fails as `WFT-NAME-MISSING` and every write as `invalid_input` with a native `22023` and no message, which reads as the caller's mistake.

## 3. Failed condition plus failed operation

A declared condition outranks a failed operation (R18.18 of `truss-requirements.md`). The six corpus cases (`action.failed-precondition-changes-nothing`, `action.dry-run-writes-nothing-and-keeps-the-key`, `action.atomic-batch-is-all-or-nothing`, `action.independent-batch-reports-each-item`, `action.same-key-from-another-person-replays`, `journal.changes-are-committed-groups-newest-first`) pass on 0.0.41 through the adapter with no judgement of its own: Truss answers `GroupFailed/PreconditionFailed` with the declared condition's id, reason and rule. A run of independent creates is still inserted as one statement and a `key_conflict` still carries the index of the run's first create whichever create collided (a batch of `zz-a`, `zz-b`, `zz-c` with `zz-b` held names the create at index 0 without the adapter's attribution and index 1 with it), so the adapter reads the run again to name the create that collided.

## 4. Diagnosis

| Symptom | Whose | Evidence |
|---|---|---|
| `WFT-OUTPUT-NAME` on a list read with an explicit relationship alias | Both: Truss's documented behaviour (R17.2), and a statement that carries an alias the host is documented to leave off | the corpus limit cases end at that refusal on 0.0.45 (Truss's guide names an unused explicit alias after `x.*` as the way, and the 100-key cap of the complete relationship columns stays) |
| `WFT-NAME-MISSING` and `invalid_input` on a nameless document | The host's generator (it writes `name` on every record and field element); Truss's registration check (R16.4, met) | the nameless pizza is refused at registration with a `TRUSS-NAME-MISSING` diagnostic for each element (0.0.45), which the host lists as one `Invalid` |
| A UMF 0.10 record or field that carries an extension is `WFT-TYPE` ("outside the raw scalar profile") to `compile_json` | Weft's parser, for a model with Arras's `umf.ddd` or `arras.view` extensions; the host's Weft parse check shows it a model without them | 107 of the statements fail until the extensions are removed from the model shown |

## 5. The cost of a whole entity

Met (R17.8 of `truss-requirements.md`): 50 entities with the facts take 0.55 s (measured on 0.0.41) against 0.27 s for the same rows as a projection.
