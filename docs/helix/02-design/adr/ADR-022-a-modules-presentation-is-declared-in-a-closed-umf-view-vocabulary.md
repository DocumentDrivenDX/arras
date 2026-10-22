---
ddx:
  id: ADR-022
  type: adr
  activity: design
  status: proposed
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: FEAT-011
      kind: informed_by
    - id: FEAT-002
      kind: informed_by
    - id: ADR-013
      kind: informed_by
    - id: ADR-021
      kind: informed_by
    - id: ADR-005
      kind: constrained_by
    - id: CONTRACT-002
      kind: informs
    - id: CONTRACT-006
      kind: informs
    - id: CONTRACT-010
      kind: informs
---

# ADR-022: A module's presentation is declared in a closed UMF view vocabulary

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-11 | Proposed | Erik LaBianca (architecture lead) | [FEAT-011](../../01-frame/features/FEAT-011-graph-browser.md), [ADR-013](ADR-013-arras-is-an-ontology-interface-over-named-backends.md), [ADR-021](ADR-021-operator-console-as-a-react-package-in-the-arras-repository.md), [CONTRACT-010](../contracts/CONTRACT-010-graph-browser-view-and-search.md) | Medium |

Proposed records the direction under review; it does not claim implementation is complete.

## Context

| Aspect | Description |
|--------|-------------|
| Problem | The Graph Browser (FEAT-011) shows an entity as a page. A `Solution` and a `Finding` should not look alike: each wants its own title, summary, grouped properties, formats, icon, tone and relationship labels, and its own ordered list of properties worth searching. Where that knowledge lives decides who can change it and what it can break. |
| Current State | The registry holds each type's properties, relationships and actions, read from a UMF document (`arras.umf`). The console picks a label property by a heuristic (`labelProp`: `name`, `title`, `label`, `summary`, `description`, else the first string). Arras's UMF reader accepts only the `umf.ddd` vocabulary and refuses any other extension. A module's UMF document is the one artifact the module owner already authors and registers. |
| Requirements | Declared by the module that owns the type, in the document it already authors (the operator's "customizable via UMF extension"); checked at registration so a bad declaration fails where it is written; unable to run code or alter the host's look, so a module cannot break the browser or its contrast; served with the types so no client needs a second read; versioned with the registry so a page and its types always agree; absent means a sensible default. |
| Decision Drivers | The viewer sees what a module's owner declared, so the declaration is an input from a less-trusted author than the host (any module developer): it must be data, not code (FR-58). A second authoring artifact would drift from the types it describes. Arras keeps no state of its own (ADR-013), so the declaration must live in what is already registered. |

## Decision

We will define an Arras-owned UMF vocabulary, `arras.view`, whose terms are listed in CONTRACT-010. A module carries it in its UMF document: declared in the document's `vocabularies`, and used in `extensions` on the module, on each record (entity type), on each field and on each relationship. It is **presentation only**: it does not add, remove or change any type, property, relationship or action, and the registry's types are identical with or without it.

The vocabulary is **closed and data-only**. Strings are plain text or a template of `{property}` placeholders and literal text. Icons, tones and formats are names from fixed sets that Arras owns (the browser maps each name to its own drawing and its own theme-checked colours). The vocabulary has no markup, no script, no stylesheet, no colour value, no URL that is loaded, and no reference to a component. A term outside it is refused.

Arras **checks it at registration** with the rest of the document, refusing an unknown term, a reference to a property or relationship the type does not have, a format that does not suit the property's type, an unknown icon or tone and a malformed template, each with the path of the fault; the registry is unchanged on refusal.

Arras **resolves it on the server, from the registered document**: it reads the module's registered document (`document`, CONTRACT-001), resolves the view against the module's types, merging the derived defaults for what is not declared, and returns it on the meta schema (`EntityTypeInfo.view`, CONTRACT-010), cached by module and revision. The view is not part of any backend's catalog, `ModuleInfo` or `EntityTypeInfo`, so the backends persist nothing new, the registry's types are equal with and without a view by construction, and every client (the browser, the Operator Console, the MCP binding) shows the same default and none re-implements it.

**Key Points**: Declared in the module's own UMF | closed vocabulary of data, never code | checked at registration, resolved on the server | presentation only: no effect on types or permissions

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| Heuristics only (status quo: `labelProp` and a generic table) | No new surface | Every type looks alike; a module cannot say which property is its title or what a status means; each client re-implements the heuristic | Rejected: does not meet the requirement; kept as the derived default |
| A sidecar view document registered beside the UMF document | Does not depend on UMF accepting another vocabulary; can change without touching the types | A second artifact to author, version and keep in step with the types; drift between them; two registrations | Rejected as the primary carrier; **kept as the fallback** if UMF's validator refuses an additional vocabulary (see Risks). The vocabulary and its checks are the same either way, only the carrier differs |
| Per-client configuration (the host or the UI holds a map of type to look) | Simple for one client | Each client and host repeats it; the module owner does not control how their types appear; changes need a client release | Rejected: the knowledge belongs to the module |
| Component references or HTML templates in the document | Unlimited presentation | A module author could run script in every viewer's session, break the host's theme or contrast, or exfiltrate through an image URL; unreviewable | Rejected: violates the data-only requirement |
| Propose the vocabulary to UMF as `umf.view` now | One vocabulary for all UMF consumers | The vocabulary is Arras's reading of what a browser needs and is untested; it would fix UMF's namespace before we have used it; UMF owns its own roadmap | Deferred: Arras uses its own namespace and offers it upstream once proven; moving to a UMF-owned name later is a version bump of the vocabulary |
| **A closed `arras.view` vocabulary in the module's UMF document, checked at registration, resolved on the server** | Authored where the types are; cannot run code; one default for all clients; versioned with the registry | A new vocabulary to maintain and version; the closed sets limit expression; depends on UMF tolerating it | **Selected: meets every requirement; the limits are the point, and the sidecar is the fallback** |

## Consequences

| Type | Impact |
|------|--------|
| Positive | A module owner makes pages read well by editing one document, with the registration refusing mistakes by path. The same resolved view serves the browser, the console and agents. The closed sets guarantee theme and contrast in light and dark. |
| Negative | A closed vocabulary will be too small for some module; each addition is a vocabulary version and a browser release. A view-only edit changes the registry revision and invalidates cached pages. Arras's UMF reader (`arras.umf`) accepts a second vocabulary and runs a validator for it; today it does not examine the record, field and relationship `extensions` at all, so the closedness of this vocabulary is enforced entirely in that validator. |
| Neutral | `describe` and the meta schema grow one field. A document without the vocabulary is unchanged. Search weights ride in the same vocabulary but are specified by ADR-023. |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| UMF's own validator refuses a vocabulary other than `umf.ddd`, and FR-13 requires Arras to read UMF as the reference does | L | H | UMF's requirements say a model with an unknown vocabulary stays usable and keeps that vocabulary's content (UMF PRD FR-22, FR-41, read 2026-10-11), which supports the decision; only Arras's own reader is strict today. Checked in UMF's reference validator (`src/validation/document.ts`, 2026-10-11): a vocabulary declared in `vocabularies` but not in UMF's registry yields the warning `UNKNOWN_EXTENSION` ("content retained"), its payloads are skipped, and only an extension used without a declaration is an error; so a document with `arras.view` is valid in UMF. Registering the vocabulary with UMF would add structure checks there; that is a feature request, not a prerequisite |
| A view edit is a new revision, as any edit of the document is (CONTRACT-002), so open forms in the Operator Console rebuild (`expected_revision`) and cached pages refresh | M | L | Accepted: Arras does not compose revisions (CONTRACT-002), and a view edit is rare; the browser refreshes without losing its place |
| Modules over-declare and the vocabulary grows into a layout language | M | M | The closed sets are the guard; a request for a term is an ADR-level change to the vocabulary version; a module that needs more builds its own screen (PRD non-goals) |
| A declaration leaks something it should not (a template that renders a restricted property) | L | M | A view reads only properties the viewer's own read returns; a property the backend omits for the viewer is omitted from the page; the view grants nothing (CONTRACT-010) |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| The catalog declares a view for all six types and each page differs from the derived default with no browser code change | A type's wanted presentation cannot be expressed in the vocabulary |
| 100% of invalid declarations in the conformance corpus are refused with the path of the fault | A declaration is accepted that renders badly or breaks contrast |
| The registry's types, relationships and actions are equal with and without a view (property test) | Any difference |
| UMF's reference validator accepts a document carrying the vocabulary, with only the `UNKNOWN_EXTENSION` warning | It refuses it (switch to the sidecar carrier) |

## Concern Impact

- **No concern impact**: the vocabulary is data under the existing modularity and testing practices. It adds a module to the library (`arras.view`, SD-011) that follows the existing module-boundary rules.

## References

- [FEAT-011](../../01-frame/features/FEAT-011-graph-browser.md), [CONTRACT-010](../contracts/CONTRACT-010-graph-browser-view-and-search.md), [SD-011](../solution-designs/SD-011-graph-browser.md)
- [CONTRACT-002](../contracts/CONTRACT-002-type-registry-and-placement.md), [ADR-013](ADR-013-arras-is-an-ontology-interface-over-named-backends.md), [ADR-021](ADR-021-operator-console-as-a-react-package-in-the-arras-repository.md)
- PRD open question: UMF's acceptance of an additional vocabulary
