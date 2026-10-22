---
ddx:
  id: SPIKE-002
  type: tech-spike
  activity: design
  status: review
  owner: Erik LaBianca
  updated: 2026-10-05
  authoring:
    home: repo
  links:
    - id: ADR-011
      kind: informs
    - id: ADR-013
      kind: informs
    - id: ADR-015
      kind: informs
---

# Technical Spike: How the field exposes an ontology for writes and projections

**Spike ID**: SPIKE-002 | **Lead**: Erik LaBianca | **Time Budget**: one research session | **Status**: Completed

> Research input to design, not a decision. Palantir pages were reached only through search-engine excerpts and are reported, not verified.

Terms used in this spike:

- Arras is the interface to an ontology: UMF-defined types and actions, reads that state their freshness, and a backend contract with two adapters.
- UMF (the metamodel, owned by DocumentDrivenDX) is the metamodel that defines Arras's types and actions.
- Truss (DocumentDrivenDX) is the UMF-driven property-graph engine that Arras runs on Lakebase as the authoritative store for mutable types.
- Ashlar (DocumentDrivenDX) is the toolkit for property-graph ontologies on a warehouse; its gold Delta tables on Unity Catalog serve bounded reads over the full ontology.
- Lakebase is Databricks' managed Postgres. Unity Catalog is the Databricks governance layer for the warehouse.
- the host is the application that embeds Arras as a library.
- ADR is an architecture decision record. ADR-011 (read-only GraphQL surface generated from the type registry), ADR-013 (Arras as an ontology interface over Truss and Ashlar) and ADR-015 (writes are UMF actions on the authoritative backend) are the decisions this spike tests.
- MCP (Model Context Protocol, Anthropic's open protocol for agent tools) is the transport agents use to call tools.
- CQRS (command query responsibility segregation) is the pattern of one command model for writes with separate read projections.
- RBAC is role-based access control. OSDK is Palantir's Ontology SDK, generated per application.

## Objective

**Technical Question**: What patterns have systems that expose an ontology to agents, humans and applications converged on for writes, for governed reads, and for keeping several surfaces from drifting, and which bear on Arras's interface?

**Goals**:
- [x] Identify the converged pattern for agent and application writes.
- [x] Identify the converged pattern for governed, bounded reads.
- [x] Identify how surfaces are kept from drifting apart.

**Success Criteria**: Evidence-backed findings that either support or challenge the decisions in ADR-011, ADR-013 and ADR-015.

**Out of Scope**: Storage design, entity vocabularies, any evaluation of Palantir as a vendor, and Palantir's internal data structures, which neither research pass could verify.

## Hypothesis

**Primary**: The field's converged patterns support ADR-011, ADR-013 and ADR-015. (Inferred from the success criteria.)

## Approach

**Method**: Literature review and comparative analysis of vendor documentation, engineering retrospectives and standards. The research sandbox blocked palantir.com, arXiv, Neo4j and most secondary sites. Only Datadog's engineering blog, Anthropic's platform docs and the CypherBench repository were read in full. Every other claim comes from a search-engine excerpt and is reported, not verified.

## Findings

**FINDING 1**: For agents the field converged on a curated tool surface for writes and a governed, bounded query surface for reads.
- **Evidence**: Anthropic's tool-definition docs recommend consolidating related operations into fewer tools (one tool with an `action` parameter instead of separate `create_pr`/`review_pr`/`merge_pr`), namespacing tool names by domain, and returning "only high-signal information … semantic, stable identifiers (slugs or UUIDs) rather than opaque internal references" ([Define tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools)). The companion piece frames agents as "non-deterministic users of deterministic tools" and prefers `search_*` over `list_*` ([Writing effective tools for AI agents](https://www.anthropic.com/engineering/writing-tools-for-agents)). Datadog's MCP-server retrospective replaced thin wrappers around existing APIs with purpose-built tools and found that "as the number of tools grows, agents struggle with accurate tool calling". It added a SQL-style query tool because letting the agent write `SELECT service, COUNT(*) … GROUP BY` was "about 40% cheaper because agents used fewer tokens to reach answers" than pulling raw records. It also added token-based pagination, trimmed default fields and actionable errors ("unknown field 'stauts' – did you mean 'status'?") ([Designing MCP tools for agents](https://www.datadoghq.com/blog/engineering/mcp-server-agent-tools/)).
- **Implications**: Use small, namespaced, consolidated tools and a bounded query tool for the long tail. Do not expose one MCP tool per REST endpoint.

**FINDING 2**: The data-analytics vendors reached the same conclusion through semantic layers.
- **Evidence**: Databricks Genie "resolves business terms, metric definitions, and table relationships through Genie Ontology, your governed semantic layer, which produces more accurate answers than an agent writing SQL directly against raw tables". Unity Catalog metric views define measures once, and Genie, dashboards, managed MCP servers and agents all consume them ([Operationalizing Genie Ontology](https://www.databricks.com/blog/operationalizing-genie-ontology-your-data-stack)). Snowflake Cortex Analyst uses a semantic model instead of raw text-to-SQL, with agent queries inside Snowflake's governance perimeter so RBAC applies ([Cortex Analyst](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst)). Databricks positions Lakebase as the Postgres OLTP store that "can store ontology metadata and agent state at low latency" beside the analytical estate.
- **Implications**: Arras's type registry is the semantic layer, and agents query through it.

**FINDING 3**: MCP is the de-facto agent transport, and its safety annotations are advisory.
- **Evidence**: The MCP authorization spec makes the server an OAuth 2.1 resource server, with the client acting "on behalf of a resource owner". The agent acts as the user and not under a service superuser identity ([MCP authorization spec](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)). `readOnlyHint` and `destructiveHint` "are advisory metadata … and don't authorize, restrict, or block any operations". They trigger client-UI confirmation dialogs and enforce nothing server-side ([MCP authorization patterns, AuthZed](https://authzed.com/learn/mcp-authorization-patterns)).
- **Implications**: Enforcement lives in the ontology service, with acting-as-user authentication end to end.

**FINDING 4**: The emerging standard for agent writes is propose, diff, approve, commit, with idempotency and audit.
- **Evidence**: Idempotency keys on every mutation; dry-run and validate endpoints; guardrails as "the critical boundary for writes — do not rely on prompt instructions alone to protect database mutations"; and a log of what the agent proposed, who decided and why, as auditable events ([Reco](https://www.reco.ai/hub/guardrails-for-ai-agents); [Arthur](https://www.arthur.ai/column/human-in-the-loop-governance-for-ai-agents)).
- **Implications**: Provide `validate` and `apply` as separate operations, and have the action log record the principal and the decision.

**FINDING 5**: For other applications, REST with OpenAPI and generated SDKs is the default, and GraphQL's agent-relevant technique is persisted queries as the tool set.
- **Evidence**: The mature pattern is "hybrid by layer: REST and OpenAPI for public and partner APIs, GraphQL for the complex internal/frontend data graph, and increasingly gRPC for service-to-service" ([WunderGraph](https://wundergraph.com/blog/fact-checking-graphql-vs-rest)). Palantir's OSDK is generated per application in TypeScript, Python and Java, plus OpenAPI for any other language, scoped to selected object types, actions and functions ([Ontology SDK overview](https://www.palantir.com/docs/foundry/ontology-sdk/overview)). Apollo's MCP server turns persisted query manifests into the agent tool set: "instead of allowing any arbitrary queries, you can restrict them to a pre-approved set of persisted operations" ([Apollo MCP Server](https://www.apollographql.com/apollo-mcp-server)).
- **Implications**: Expose one graph with curated projections per consumer, generated from the schema.

**FINDING 6**: The field uses one model, one write path and several read and interaction surfaces, and prevents drift by generating the projections from one registry.
- **Evidence**: Cube's 2026 guidance says agents "reach the semantic layer through the same governed interfaces as everything else — SQL, REST, GraphQL, and MCP — but they use them differently … A layer with only one interface may solve one tool's problem, but it will not become the shared path agents and humans both take" ([Cube](https://cube.dev/articles/semantic-layer-for-ai-agents-2026)). CQRS is the general form: one command model with validation, authorization and domain rules, and several read projections. The same source warns that eventual consistency between write and read models affects autonomous agents that read back what they just wrote ([Tacnode](https://tacnode.io/post/cqrs-pattern)). Palantir generates OSDK, OpenAPI, MCP tools and Workshop forms from Ontology Manager metadata. Apollo generates MCP tools from the GraphQL schema plus persisted operations. Databricks generates Genie, MCP and dashboards from Unity Catalog metric views.
- **Implications**: Generating the projections from the registry prevents drift structurally. Agent-facing reads should stay strongly consistent (read-your-writes).

**FINDING 7**: The action layer is a named, parameterized, permission-checked, criteria-validated, side-effecting, logged and partially revertible write.
- **Evidence**: Submission criteria determine whether an action can be submitted, combining user context, parameter values and object and relation state ([Submission criteria](https://www.palantir.com/docs/foundry/action-types/submission-criteria)). Permissions require edit rights on the action type and on every ontology resource type it edits ([Action type permissions](https://www.palantir.com/docs/foundry/action-types/permissions)). REST exposes `validate` (it checks parameters and criteria but "will not consider existing objects or other data … such as the uniqueness of a primary key") and `apply` separately. The action log "models all action submissions as object types … linked to all objects edited by the submitted action" ([Action log](https://www.palantir.com/docs/foundry/action-types/action-log)). Edit-history records "cannot be deleted or modified by end users, even if the corresponding ontology edits are reverted". Revert is limited to "the most recent edit to an object" and does not revert side effects such as notifications or webhooks ([Undo or revert Actions](https://www.palantir.com/docs/foundry/action-types/action-reverts)).
- **Implications**: The design is reproducible on Postgres. The action log as an object type linked to the edited objects is the concrete artifact behind "an agent bounded by the same validation and permissions as a human operator, reviewable in the same log."

**FINDING 8**: Palantir hands agents scoped SQL for reads and named actions for writes.
- **Evidence**: AIP Logic and Agent Studio give the LLM three tool categories: data (object query tools with accessible-property scoping "to make queries more token-efficient"), logic (Foundry and AIP Logic functions), and action (an ontology edit "configured to run automatically or to run after confirmation from the user", filling parameters "within authorized Action Type boundaries") ([Agent Studio, Tools](https://www.palantir.com/docs/foundry/agent-studio/tools)). The security claim is that the LLM "operates within the user's existing permission context … if a user doesn't have access to a specific financial record, the AI assistant won't be able to see or summarize that record" ([AIP Logic core concepts](https://www.palantir.com/docs/foundry/logic/core-concepts)). Ontology MCP (2026) provides a SQL tool that "lets agents read ontology data by issuing SQL queries against the exposed object types". Action types become their own MCP tools, Developer Console OAuth scopes apply, and the documentation warns that returned data "leaves Foundry" ([Ontology MCP overview](https://www.palantir.com/docs/foundry/ontology-mcp/overview)).
- **Implications**: Offer scoped SQL over permission-filtered object types and never over base datasets. Three points are flagged and unconfirmed: whether Ontology MCP supports server-side "require confirmation" as AIP-native agents do; what the action log records when an agent submits instead of a human; and a Palantir community thread titled "is there a residual enforcement gap after Ontology permissions and actions?" (title only).

## Analysis

**Hypothesis**: CONFIRMED
**Rationale**: The findings agree on one shape: a single semantic model and a single write path, with several read and interaction surfaces generated from the same registry. Writes are named, parameterized, permission-checked and logged. Reads are governed and bounded. Agents act as the user.

### Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| Palantir-specific claims rest on search excerpts, not full reads | H | L | No conclusion depends on one Palantir detail; Databricks, Apollo, Cube and the MCP specification evidence the same shape independently |
| Hand-written projections drift from the registry | M | H | Generate projections from the registry; contract tests replay action fixtures through each surface |
| Agent reads are eventually consistent with the agent's own writes | M | M | The interface's receipt and `at_least` mechanism (ADR-014) |

## Conclusions

**Primary Conclusion**: The field's convergence supports ADR-011, ADR-013 and ADR-015 without challenging any of them:

- Writes go only through named actions. Findings 1, 4, 7 and 8 support ADR-015: a curated, discoverable write surface with preconditions, idempotency and an audit record, and no raw write path.
- Every read and action runs as the user, end to end. Findings 3 and 8 support ADR-013's principal: the user's own access applies and the backends enforce it.
- Reads are governed and bounded. Findings 1, 2 and 8 support CONTRACT-001's bounded operations and capability descriptors over any raw or natural-language query path.
- One registry generates the projections. Findings 5 and 6 support generating the console's GraphQL (ADR-011) and any REST or MCP surface the host wants from the type registry, so projections cannot drift. Exposing Arras to agents is the host's decision.
- A dry run is worth having. Finding 4's propose, validate, approve, commit pattern is what CONTRACT-003's `validate` provides: it checks inputs and preconditions and returns the effects without applying them.

**Confidence**: High for the shape, because several independent sources converge. Medium for the Palantir specifics, which come from search excerpts.

**Limitations**: Palantir pages, Cube, Neo4j and arXiv were not read in full. The three thin spots in Finding 8 remain unconfirmed.

## Recommendations

**RECOMMENDATION**: Keep ADR-011, ADR-013 and ADR-015 as decided, and generate every projection from the type registry.
- **Rationale**: Findings 1 to 8 support all three decisions, and the only risk with high probability (Palantir claims from excerpts) does not affect a conclusion.
- **Next Steps**: Add contract tests that replay action fixtures through each surface, as the risk table specifies.
- **Concern Impact**: None. No concern changes and no ADR needs revision.

## Artifacts

- Read in full: Datadog's MCP retrospective, Anthropic's tool-definition docs and engineering post, and the CypherBench repository.
- Reached only through search-engine excerpts: every Palantir page cited, Cube, Neo4j, arXiv and the secondary sources.
