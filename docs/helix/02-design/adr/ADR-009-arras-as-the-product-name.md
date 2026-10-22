---
ddx:
  id: ADR-009
  type: adr
  activity: design
  status: accepted
  owner: Erik LaBianca
  updated: 2026-10-18
  authoring:
    home: repo
  links:
    - id: ADR-006
      kind: informs
---

# ADR-009: Arras as the product name

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-18 | Accepted | Erik LaBianca (architecture lead) | [ADR-006](ADR-006-embedded-library-on-psycopg-and-the-truss-toolkit.md) | High |

> The name is recorded as an ADR because ADR-006 and every Arras artifact identifier carry it. The decision is a naming choice and makes no architecture claim.
>
> Terms. ADR: architecture decision record. Arras: the interface to an ontology, a Python library with a React console and Graph Browser, embedded by host apps such as praxis.

## Context

| Aspect | Description |
|--------|-------------|
| Problem | The product is the interface to an ontology: UMF-defined types and actions, reads that state their freshness, and a contract over named backends. It needs a name so that ADRs, specs, identifiers, packages and conversation can refer to it unambiguously. |
| Current State | The sibling projects carry names from craft and structure: Truss (the authoritative store), Ashlar (the replica), Weft (the query language) and UMF (the modelling format). |
| Requirements | A short, pronounceable name that fits that family. Available as a package name on PyPI and npm. |
| Decision Drivers | The name is a label. It should suggest the product's role without claiming a design the product does not have. |

## Decision

We will name the product **Arras**. An arras is a tapestry wall-hanging: a picture woven from many threads. The product gives a woven view onto a graph of linked records, and the name sits naturally beside Truss, Ashlar and Weft.

**Key Points**: A woven picture from threads suits a view onto linked records | Fits the family of craft and structure names | Short, and available as a package name

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| **Arras** | A woven picture; short; fits Truss, Ashlar and Weft | Less familiar as a word than the alternatives, so documents gloss it once | **Selected** |

## Consequences

| Type | Impact |
|------|--------|
| Positive | One stable name across ADRs, specs, code identifiers, packages and conversation. The name fits the project family. |
| Negative | Readers who do not know the word need the one-line gloss the first time it appears. |
| Neutral | Renaming later is possible but costs a coordinated edit across every artifact that carries `arras` in its identifier. This ADR exists so that cost is only paid on new evidence. |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| A product or trademark adopts "Arras" in the same field | L | M | Re-check before any wider announcement; the identifier cost of a change is recorded above |
| The name reads as obscure | M | L | Pair the name with a one-line gloss in introductory material; do not shorten or nickname it |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| The name is used unmodified across ADRs, the concerns document, the spikes, the PRD, the packages and the repository, with no competing label in circulation | A second name for the same product appears in a governed artifact |
| No contributor or user raises a brand-collision objection | An objection is raised |

## Concern Impact

- **Concern selection**: None. This decision selects no technology concern.
- **Practice override**: None.
- **Identifier convention**: Arras artifacts and code use the `arras` slug (`arras_search`, `arras-*`); recorded in [`../../01-frame/concerns.md`](../../01-frame/concerns.md).
