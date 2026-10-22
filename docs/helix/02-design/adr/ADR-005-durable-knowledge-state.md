---
ddx:
  id: ADR-005
  type: adr
  status: proposed
  authoring:
    home: repo
  links:
---

# ADR-005: Durable structure derived from sensitive source records is gated on a workload, an entitlement rule and a governed write path

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-09-11 (opened) | **Proposed** (the gate is proposed; the artifact is undecided) | Erik LaBianca (architecture lead) with the data governance owner | [ADR-013](ADR-013-arras-is-an-ontology-interface-over-named-backends.md), [ADR-017](ADR-017-backends-are-reached-with-the-users-own-token.md) | Low |

Terms. ADR: architecture decision record. Sensitive source records: records held in a source system under access rules that the source enforces (for example per-case or per-customer entitlements). Derived structure: relationships, categories or graphs computed from those records and stored apart from them.

> **Settled: nothing durable is built speculatively, and placement is an architecture decision.** Arras is the interface to an ontology. This ADR does not choose what a derived knowledge layer over sensitive source records would be. It records what must be true before anything is built.
>
> **Open: what the artifact is.** An ontology, a relationship graph, a categorization scheme and a retrieval index are four artifacts with four different costs. Nothing in the evidence selects among them, and this ADR stays Proposed until a workload does.

## Context

| Aspect | Description |
|--------|-------------|
| Problem | Organizations that hold sensitive records want durable, queryable structure over them: links between records, categories, remembered judgements. Such a layer is attractive to build early and expensive to govern late. The records carry access rules in their source system, and a derived structure whose value is connecting records can erase the boundaries those rules draw. |
| Current State | Retrieval over source records already answers a large class of questions without any durable derived state. Arras holds no structure derived from sensitive source records. The catalog and inventory modules hold records about software and infrastructure, not about the content of sensitive source systems. |
| Requirements | Durable, queryable structure over sensitive source records, where one is needed. Governed writes with proportionate validation, approval and reversibility. Enforcement of the source system's entitlements on the derived structure. A representation consumers can read behind a stable contract. |
| Primary criterion | A named workload whose requirements cannot be met by retrieval alone. Until one is registered, building durable state adds a governance surface for no established requirement. |
| Decision Drivers | Durable state that is built speculatively invents its own requirements. Governed writes and entitlement enforcement over derived structure have no incumbent owner unless someone is named. A derived layer can be created by default inside a source-system project, unowned and unreviewed, if placement is not decided first. |

## Decision

Two limbs are settled and one is deferred.

**1. Durable structure derived from sensitive source records is not built until a named workload requires it.** Three preconditions must be answered in writing before any build begins:

| # | Precondition | Why it gates |
|---|---|---|
| P1 | A named workload whose requirements cannot be met by retrieval alone | Without it the build has no requirement to meet and invents its own |
| P2 | Where the source system's entitlement is enforced on the derived structure | A structure whose value is connecting records cannot be built before the rule that limits who may see those connections is satisfied. A filter on search results does not answer what a derived graph may contain |
| P3 | Who owns governed writes: validation, approval, reversibility | Without an owner, governed writes get implemented implicitly by whoever builds first |

**2. When it is built, its placement is an architecture decision.** It is placed on the platform of record, reading the source system as a source. A project that modernizes the source system does not create it as a by-product. If such a project intends to build structure over the records, it is building this component and this ADR applies to it.

**3. The artifact's shape is not yet chosen.** The Alternatives table lists the candidates, and Validation names the evidence that decides.

**Key Points**: The deferral is a decision, and it stops a drawn box from becoming a build | Retrieval is the null hypothesis and may remain sufficient indefinitely | P2 is the hard one, and it is an authorization question before it is a modelling one

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| **A. Build the ontology now over the source records** | Starts compounding the asset. The records are real and deep | No workload requires it, so the requirements would be invented. Creates a governance surface (governed writes, entitlement over derived structure) that has no owner. Entitlement is unanswered, and this is the artifact the rule governs most | **Rejected**: speculative construction |
| **B. Defer behind the three preconditions; claim placement now** | Keeps the goal live without building on invented requirements. Claims the placement decision while it is still open. Costs nothing and prevents the by-default outcome | Reads as inaction to anyone who wants the layer built. Leaves the goal without a mechanism for now | **Selected** |
| **C. Let a source-system modernization project build it** | Whatever project already modernizes the source systems may have the capacity. Closest to the records | Places the derived knowledge outside the platform of record. Unowned by this architecture, unreviewed against P2 and P3. It is the default outcome if nothing is decided | **Disfavored, and the live risk**: it happens when no option is chosen |
| **D. Never build it; retrieval is sufficient** | Cheapest and safest. Retrieval already answers a large class of questions with no durable state, no governed writes and no new entitlement surface | If the value requires remembering judgements as well as finding records, this forecloses it. It would need stating as a position and not reached by drift | **Carried, open**: this is the null hypothesis P1 must beat |

B is the decision. D is where B ends up if P1 is never satisfied, which is a legitimate outcome. C is what happens if nobody decides.

## Consequences

| Type | Impact |
|------|--------|
| Positive | Stops a drawn box from turning into a build with invented requirements. Claims placement before a source-system project settles it by default. Names the three questions that gate the piece, so the deferral is auditable. Keeps retrieval as the null hypothesis, which is the cheap answer if it holds |
| Negative | The goal of remembered judgements has no mechanism for now, and this ADR supplies none. P3 has no named owner, so the gate contains a precondition nobody is yet accountable for answering |
| Neutral | Does not change the source records or the retrieval layer. Changes only what may be built on them, and where |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| A source-system project builds the layer anyway, inside the source system, unreviewed | M | H | Ask the project's owner what it will build. This is the cheapest question in the set |
| P1 is satisfied by a workload assembled to justify the build | M | H | P1 requires the workload's requirements to be unmeetable by retrieval alone, stated in writing. Retrieval is the null hypothesis and the burden sits on the build |
| P3 stays unowned, and governed writes get implemented implicitly by whoever builds first | **H** | M | Name an owner for governed writes independently of this ADR |
| Entitlement is resolved for retrieval but not for derived structure, and the distinction is lost | M | H | P2 is scoped to derived structure. A filter on search results does not answer what a derived graph may contain |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| A workload exists whose written requirements cannot be met by retrieval alone (P1) | Any workload proposal that names durable state, memory or an ontology as a requirement |
| Entitlement on derived structure has a written enforcement point (P2) | The source system's owner names an enforcement mechanism on the derived path |
| Governed writes have a named owner (P3) | A governed-write owner is named, or any workload proposes a durable write |
| Nothing durable is built inside a source system without this ADR being revisited | A source-system project reports what it will build |
| The artifact's shape is chosen from the four candidates | P1 is satisfied: the workload's requirements select the representation, and the representation is not chosen first |

When P1 is satisfied, the workload's requirements select the artifact. That choice is a separate decision, recorded as its own ADR that cites this gate.

## Concern Impact

- **Concern selection**: Governs any design that introduces durable derived state over sensitive source records. A design that creates such state without answering P1, P2 and P3 violates this ADR, including one built inside a source system.
- **Practice override**: None.
- This gate is recorded in [`../../01-frame/concerns.md`](../../01-frame/concerns.md) for any structure derived from sensitive source records. Arras holds no such structure, so P2 does not gate it. The catalog is the named workload for P1. P3 is met for the catalog by actions authorized through database role grants, with no named human owner yet.
