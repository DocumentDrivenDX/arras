---
ddx:
  id: ADR-028
  type: adr
  activity: design
  status: proposed
  owner: Erik LaBianca
  updated: 2026-10-12
  authoring:
    home: repo
  links:
    - id: ADR-015
      kind: informed_by
    - id: ADR-021
      kind: informed_by
    - id: ADR-025
      kind: informed_by
    - id: SD-012
      kind: informed_by
    - id: CONTRACT-003
      kind: informs
    - id: CONTRACT-004
      kind: informs
    - id: CONTRACT-009
      kind: informs
---

# ADR-028: The graph is exported as the records the import takes, in a file that version control can keep

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-12 | Proposed | Erik LaBianca (architecture lead) | [ADR-015](ADR-015-writes-are-umf-actions-applied-by-providers.md), [ADR-021](ADR-021-operator-console-as-a-react-package-in-the-arras-repository.md), [ADR-025](ADR-025-one-shell-two-modes-and-operate-is-offered-by-the-host.md), [SD-012](../solution-designs/SD-012-graph-browser-editing-and-export.md), [CONTRACT-003](../contracts/CONTRACT-003-actions.md), [CONTRACT-004](../contracts/CONTRACT-004-backend-contract.md), [CONTRACT-009](../contracts/CONTRACT-009-operator-action-and-audit-surface.md) | Medium |

Proposed records the direction under review; it does not claim implementation is complete.

## Context

| Aspect | Description |
|--------|-------------|
| Problem | A graph changed in the interface has nowhere to go. The dev host keeps it in memory, so every edit is lost on restart, and there is no file that records what the graph should be. |
| Current State | Data enters by actions and by `import_records`; the dev host seeds from a list of action steps (`--seed`). The journal records effect-level changes, not the inputs of the actions that made them, so the steps cannot be recovered from it. Only the schema (UMF documents) can be exported. |
| Requirements | Until a database holds the graph, git is its persistence: a developer loads a graph, edits it in the interface, exports it, commits the file and loads it again. The same file ships as a known-good fixture. Long term the database is the record, so the format must be what a database loads. |
| Decision Drivers | A file that loads back unchanged; the same bytes for the same graph (a diff shows only what changed); nothing in the file that varies between runs; reads as the viewer and adds no write path (ADR-015). |

## Decision

1. **The export is a read of records of the shapes `import_records` takes** (CONTRACT-003, Import): an entity record (`type`, `key`, `properties`) for every entity of the module, then a relationship record (`relationship`, `source`, `target`) for every link between them. A property that is not set is absent, and `original_author` and `original_at` are written only where the record already has them, so an export never invents a provenance. The library's `export_records` is a read on the module's record store as the person; a backend that cannot serve it answers `Unsupported`, and a type the person could not be given is named in the page's `omitted`.
2. **The file is canonical.** `arras.graphfile` writes `{format, version, module, complete, records}` with keys sorted, two-space indent and a final newline, records in type declaration order then key, links by relationship then source then target, and no time, person or revision. The interface's Export control writes the same bytes (shared golden vectors check both). A number in the file is an integer: a decimal is a string (as the import takes it), so the same value is the same bytes in both languages, which write a float differently (`1.0` and `1`). The readers, `loads` and the interface's, refuse a number with a fraction or an exponent (and `NaN` or `Infinity`) and name its path, and the writers, `dumps` and the interface's `graphText`, refuse to write one with the same message, so a file the readers would refuse is never produced. A file is `complete: false`, with `omitted`, when the person could not read every type, and such a file is not a whole graph.
3. **The interface offers it to operators.** `POST /export` on the operate surface (a read, so a `POST` only to keep the module and cursor out of a URL) returns pages of up to 500 records; the Export control pages through them and saves `<module>.graph.json`. It is offered where the host offers edits (`canEdit`).
4. **The dev host loads it.** `--records <file>` imports a graph file as the administrator after the module is registered and any seed steps have run; a file for another module, or one the graph rejects, stops the start with the reason. Loading never replaces: an import creates what is missing and skips what exists.
5. **The database takes the same file.** The records are the import's own, so a backend that holds the graph loads a graph file with `import_records`, and the file stays the fixture format after git stops being the store.

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| Export the action steps (`seed.json` format) | Matches the seed file's format | The journal does not hold the inputs; deriving steps means choosing a create action and link actions per type, which a module need not declare | Rejected; `seed.json` stays the way to author a graph from scratch |
| Compose the file in the browser from list reads | No server change | A relationship field returns at most 100 keys, so a hub's links vanish silently; many requests against the entity budget | Rejected |
| Export the browser's own invocations as steps | Cheap | Covers only that session's browser edits, not the graph | Rejected as the export |
| Add a header with time, viewer and revision | Self-describing | Every export differs, so git shows noise and a fixture cannot be compared | Rejected; the file says what it is and what it lacks, nothing more |

## Consequences

| Type | Impact |
|------|--------|
| Positive | A graph edited in the interface can be kept in git and loaded again; fixtures are files that load; a diff of the file is a diff of the graph; the format is the import's, so it outlives git as the store. |
| Negative | A new backend operation (`export_records`) on the contract; a reload recreates the graph and does not replay its journal; created-by and updated-by are not in the file (git records who changed the file). |
| Neutral | Import stays administrative and library-only; loading a file into a Truss module is an administrator's act and is not offered in the interface. |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| A partial file mistaken for the graph | M | H | `complete` and `omitted` in the file; the Export control says so; a partial file is for the operator to judge |
| A backend cannot list relationship instances | M | M | `Unsupported`, named in the page's `omitted`; the conformance corpus to cover it |
| A graph file carries data its holder should not keep | L | H | Read as the viewer; offered to operators; a `POST`; the file is the operator's to protect, as the schema export is |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| Exporting a graph and loading the file into a fresh one gives a graph that exports the same bytes (`tests/test_graphfile.py`); the UI's file and the library's are the same bytes (`tests/vectors/graphfile.json`, the integration test) | A backend that cannot serve `export_records`; a type whose properties do not survive the round trip; the database becoming the record |

## Concern Impact

- **Concerns used**: `admin-console` (changes only through declared actions; an export is a read), the Python 3.11 library with `uv`.
- **Departures**: none.
