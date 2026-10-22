---
ddx:
  id: ADR-025
  type: adr
  activity: design
  status: accepted
  owner: Erik LaBianca
  updated: 2026-10-12
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: FEAT-011
      kind: informed_by
    - id: FEAT-010
      kind: informed_by
    - id: ADR-005
      kind: constrained_by
    - id: ADR-015
      kind: informed_by
    - id: ADR-017
      kind: informed_by
    - id: ADR-021
      kind: informed_by
    - id: CONTRACT-009
      kind: informs
    - id: CONTRACT-010
      kind: informs
---

# ADR-025: One shell, two modes; Operate is offered by the host

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-11 | Accepted | Erik LaBianca (architecture lead) | [FEAT-011](../../01-frame/features/FEAT-011-graph-browser.md), [FEAT-010](../../01-frame/features/FEAT-010-operator-console.md), [ADR-017](ADR-017-backends-are-reached-with-the-users-own-token.md), [ADR-021](ADR-021-operator-console-as-a-react-package-in-the-arras-repository.md) | Medium |

## Context

| Aspect | Description |
|--------|-------------|
| Problem | Arras has two interfaces: the Operator Console for the people who build and run modules (builders, administrators) and the Graph Browser for everyone who reads. They should be one product with a mode switch, "user" and "admin", and only builders and administrators should see Operate. Arras has no role model of its own, so something else must say who a builder or an administrator is. |
| Current State | The host supplies `principal_for_request` (identity only) and optionally `authorize_action` (per-action approval for invocations). `Principal` carries `user`, `token`, `groups` and `admin` (the host's administrative principal). The operate surface (CONTRACT-009) serves every principal that is accepted; the PRD makes an authorization model for the host organization a non-goal; backends decide what a viewer may read or change by their own grants (ADR-017). The dev host's people: alice and bob (read, write, journal; group `builders`), root (the administrator; group `admins`), carol (read only), dave (no access). |
| Requirements | A switch in the interface between Explore and Operate; Operate absent, not merely disabled, for people who are not operators; a person who is not an operator cannot reach the operator surface by calling it directly; Arras decides nothing about who is an operator; no change to what any viewer may read or change. |
| Decision Drivers | Two shells would split the product, the sign-in and the embedding in the embedding host. A switch that is only hidden in the interface is cosmetic, so the operate surface must also refuse. The host's notion of a builder belongs to the host and the platform (PRD non-goals), not to the library. |

## Decision

We will ship **one shell**, `<ArrasApp>` in `arras-ui`, with two modes: **Explore** (the Graph Browser, the instance tool and the default for everyone) and **Operate** (the Operator Console, the model and platform tool). Their API ids stay `user` and `admin`: `modes` holds `admin` when the host offers Operate. The host decides who is an operator:

- The operate app takes an optional `authorize_operator(principal) -> bool`, beside `authorize_action`, and `arras.operate.operators_in_groups(*groups)` builds one from group names the host configures. The default operator groups are `admins` and `builders` (the host's directory groups, carried on `Principal.groups`, configurable per host); a builder sees the admin console as an administrator does. The default `None` keeps the surface's existing behaviour (every accepted principal is an operator), so nothing changes for a host that does not pass it; a host that serves the browser to people who are not operators MUST pass it.
- A new endpoint `GET /viewer` on the operate surface answers the request's principal with `{user, modes}`, where `modes` contains `admin` exactly when the principal is an operator. The shell asks it once at load.
- Every other operate endpoint refuses a non-operator with HTTP 403 `REFUSED` `not_operator` before any work.
- With no `admin` mode the shell renders Explore only and shows no switch, link or hint to Operate. With it the shell shows a two-option switch in the top bar (`Explore`, `Operate`).
- The host's offer of Operate also decides whether Explore offers writes. Explore's edits, links, New, Retire, Actions menu and History are offered only where `modes` contains `admin`, and each write is the `validate` and `invoke` of a declared action on the operate surface as the viewer. A non-operator who calls the operate surface is refused `not_operator` whatever the interface shows; the offer is a convenience and the server's refusal is the rule.
- The console GraphQL surface (CONTRACT-006) stays open to any viewer the backends let read, because Explore needs it.

Arras never infers "operator" from `Principal.groups` or `Principal.admin` by itself: `admin` there is the host's administrative principal for registry and imports, and the group names are the host's configuration, passed to the helper by name. Operate is **an offer, not a permission**: reading and changing remain what the backends' grants and `authorize_action` allow.

**Key Points**: One shell, two modes, Explore the default | the host decides who is an operator | absent for others, refused on the server | the offer also gates Explore's writes | an offer, not a permission

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| Two separate apps | Simple separation | Two sign-ins and embeddings in the embedding host; the browser and console cannot link to each other | Rejected: one product |
| Hide Operate in the interface only | Trivial | Anyone can call the operate surface directly; the hiding is cosmetic | Rejected |
| Hard-code operator as membership of fixed groups inside Arras | No new hook | Arras would own a role model the PRD excludes, and group names differ by host; the helper takes the names instead | Rejected; the host names its groups (by default `admins` and `builders`) through `operators_in_groups` |
| Operator means "holds a write grant on some module" (ask the backends) | No host code | A reader-turned-editor would see Operate; a builder who only reads would not; it makes a data grant carry an interface meaning | Rejected: wrong coupling; a host may implement exactly this in its hook if it wants |
| **Host hook `authorize_operator`, a viewer endpoint, server-side refusal, one shell** | Arras decides nothing; absent not disabled; enforced on the server; default unchanged | A host that forgets the hook offers Operate to everyone it authenticates | **Selected**; the risk is called out below and in the embedding guide |

## Consequences

| Type | Impact |
|------|--------|
| Positive | One product and one embedding. The interface for readers cannot reach the operator surface. A host's own directory (a builders group) defines operators in one function. |
| Negative | A host that serves the browser to everyone MUST pass `authorize_operator`, and the default is permissive for compatibility. The console's schema and data areas, which read through the open GraphQL surface, remain callable by any reader; they reveal only what the viewer may read. |
| Neutral | CONTRACT-009 has an added endpoint and refusal (additive); the standalone host and the dev host pass a hook; the existing `ArrasConsole` export stays for hosts that embed only the console. |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| A host mounts the shell with the default hook and every reader sees Operate | M | M | The embedding guide and `README` state it first; an embedding host passes `operators_in_groups("admins", "builders")` or its own group names; the dev host does the same over its sandbox people; a startup log line names the default |
| The audit, schema and action endpoints leak to non-operators | L | H | They live on the operate surface and are refused server-side; a conformance test calls each as a non-operator |
| "Operator" is confused with an authorization to change data | M | M | The contract says an offer, not a permission; writes still need the provider's grant and `authorize_action` |
| A mode in the URL fragment of a shared link takes a non-operator to Operate | L | L | The shell reads the fragment and shows Explore's entry when `admin` is absent |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| A whole-stack test as an operator and as a non-operator: the first sees the switch and can open Operate, the second sees no control and gets 403 from each operate endpoint called directly | Any operate endpoint that answers a non-operator |
| The shell renders Explore only, with no Operate code path executed, when `modes` lacks `admin` | Any request to the operate surface other than `/viewer` and `/version` from a non-operator's session |

## Concern Impact

- **Concern selection**: the `admin-console` concern's operator workflow is exercised in Operate as before; this ADR adds no new concern.

## References

- [FEAT-011](../../01-frame/features/FEAT-011-graph-browser.md), [US-072](../../01-frame/user-stories/US-072-switch-between-explore-and-operate.md), [CONTRACT-010](../contracts/CONTRACT-010-graph-browser-view-and-search.md)
- [FEAT-010](../../01-frame/features/FEAT-010-operator-console.md), [CONTRACT-009](../contracts/CONTRACT-009-operator-action-and-audit-surface.md), [ADR-017](ADR-017-backends-are-reached-with-the-users-own-token.md), [ADR-021](ADR-021-operator-console-as-a-react-package-in-the-arras-repository.md)
