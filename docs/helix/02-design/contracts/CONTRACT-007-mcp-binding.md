---
ddx:
  id: CONTRACT-007
  type: contract
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-009
      kind: informed_by
    - id: ADR-016
      kind: informed_by
    - id: ADR-017
      kind: informed_by
    - id: CONTRACT-001
      kind: informed_by
    - id: CONTRACT-003
      kind: informed_by
    - id: CONTRACT-005
      kind: informed_by
    - id: ADR-019
      kind: informed_by
    - id: CONTRACT-008
      kind: informed_by
---

# Contract: MCP binding

**Contract ID**: CONTRACT-007
**Type**: MCP server (stdio)
**Version**: v2
**Status**: draft
**Related**: FEAT-009, ADR-016, ADR-017, ADR-019, CONTRACT-001, CONTRACT-003, CONTRACT-005, CONTRACT-008

## Purpose

Defines the stdio MCP (Model Context Protocol, Anthropic's open protocol for agent tools) server that exposes the ontology interface to an agent host, so an MCP client can read and change the ontology through its local stdio adapter with no Python import. It is a binding of the library (CONTRACT-001, CONTRACT-003): it adds no operation, no access decision and no state.

Terms. stdio is the standard input and output streams of a process, which carry the MCP frames. An ADR is an architecture decision record; ADR-016 defines this binding and ADR-017 governs person-token backend access. A backend is a named store with the roles reader and provider (CONTRACT-004). UMF is the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions. JSON Schema is the JSON vocabulary for describing the shape of JSON data.

## Scope and Boundaries

- In scope: launch and configuration, identity, the tool set, tool input and output shapes, annotations, errors, degraded start.
- Out of scope: the operations' meaning (CONTRACT-001, CONTRACT-003), the host's tool catalog and approval policy (the host's), prompts and resources.
- Owning system or team: Arras.

## Normative Surface

**Launch.** `python -m arras.mcp` speaks MCP over stdio. It is the only Arras code that reads the environment (CONTRACT-005). One process serves one `Principal`: the user whose token it was launched with. The host starts one process per signed-in session.

| Element | Rules |
|---------|-------|
| Identity | The user's token comes from `ARRAS_TOKEN_FILE` (a file re-read when the token nears expiry, so the host can refresh it without restarting the process) or `ARRAS_TOKEN`; the claims that name the user are `user_claims` (default `preferred_username`, then `email`, then `sub`; `ARRAS_USER_CLAIM` overrides). `ARRAS_DEV_SANDBOX=1` serves the in-memory fakes for trying a client and is not a deployment mode. The user name and groups are read from the token's claims. With no usable token the server starts and every tool but `describe` returns `Refused`. Tools take no principal argument; a caller cannot name another user. |
| Configuration | One typed object, built once at start by `arras.mcp.config`, the only module that reads files or the environment. Three layers by owner, highest precedence first: (1) ops-injected, never committed: environment variables and one optional ops file named by `ARRAS_OPS_FILE`; (2) the committed per-environment file `<config_dir>/<env>.toml`; (3) the committed defaults `<config_dir>/default.toml`. `env` is `ARRAS_ENV` (no default: unset reads only `default.toml`) and `config_dir` is `ARRAS_CONFIG_DIR` (default `config`). Layer 2 overrides layer 3 key by key and tables merge. Each key has one owner (table below). Errors name the file (or environment variable) and the key, never a value; a key that cannot be used, an ops key in a committed file, an unknown key in a file, a named `<env>.toml` that does not exist, a file that is not valid TOML (named with its line) or an unknown `ARRAS_` environment key ends the process with status 2 and each problem on stderr. A missing `default.toml` is fine. `.env.example` lists the environment keys, `config/default.toml` the defaults and `config/example.toml` every table (read only when `ARRAS_ENV=example`); a test keeps them equal to the schema. |
| Lifecycle | The process is disposable. At start it logs one line to stderr naming the environment and the files read, never values. On SIGTERM or SIGINT it finishes the frame in flight, stops reading, flushes and exits with status 0. |
| Backends | A backend's handle is in the configuration; every connection is made with the user's token (ADR-017). A handle that is a PostgreSQL URI without a credential (`postgresql://host:5432/db`, or `postgresql:///db?host=/socket/dir`) is a Truss backend: the person's role is the user claim of the token (`user_claims`, so on a host whose roles are emails the claim is `email`) and the token is that role's password, on a new connection per call. A remote host defaults to `sslmode=verify-full`, so the server's certificate chain and host name are checked before the token is sent as the password; there is no way to ask a remote host for `require`, `prefer`, `allow`, `disable` or `verify-ca`. The trust roots are `sslrootcert` (an absolute path to a PEM file, or `system` for the operating system's store) or, when the handle names none, the operating system's store. A local socket or loopback host defaults to `sslmode=prefer` and may be given any mode. An `Endpoint` built in code holds the same rules (it defaults to `verify-full`, refuses a remote host's weaker mode, a relative `sslrootcert`, a comma-separated host list, an empty host and an empty database). The adapter needs libpq 16 or later: every connection sets `require_auth=scram-sha-256,password` and `sslcertmode=disable`, so a server whose `pg_hba` trusts the connection, or accepts a peer or certificate identity, is refused rather than connected to without checking the token. Under an older libpq those keywords do not exist and the check could not be made, so building an `Endpoint` (and so parsing a handle) is a `ValueError`, which stops the process at start like any other refused handle; the `truss` extra's psycopg binary carries libpq 16 or later. A handle carrying a user, a password, a service or any parameter other than `host`, `port`, `dbname`, `sslmode`, `sslrootcert`, `connect_timeout` and `application_name`, a remote host with any `sslmode` but `verify-full`, an `sslrootcert` that is neither an absolute path nor `system`, or no database, stops the process at start naming `ARRAS_BACKEND_<NAME>_ENDPOINT`, never its value. A handle no adapter reads, or whose extra is not installed (`arras[truss]`), is reported on stderr with the reason and the backend starts `not_configured`. The process clears every libpq variable (`PG*`) from its environment before its first connection, so none of them reaches a person's connection (US-030-AC2). `ARRAS_ADMIN_*` is never read: the server cannot migrate, register or import, and holds no installing connection, so it cannot read a Truss backend's install state: the status in `describe` is `not_configured` ("no installing connection") until a call as a person has been made and is then what that call showed (available when it reached the database, unavailable with the reason when it could not). The process makes no probe of its own and holds no service identity. Reads and writes are served and refused by the database as the person whatever the status says. |
| Streams | stdout carries only MCP frames. Logs and telemetry go to stderr and never contain tokens or record contents (CONTRACT-008). A `tools/call` with `_meta.traceparent` continues the caller's trace. |
| Degraded start | A backend that is unavailable at start does not stop the server. `describe` reports each backend's status; tools that need an unavailable backend return `Unavailable`; the server sends `tools/list_changed` when the registry or a status changes. |


**Configuration keys.** Each key has exactly one owner.

| Key | Owner | Where | Default |
|-----|-------|-------|---------|
| Backend endpoint | Ops | `ARRAS_BACKEND_<NAME>_ENDPOINT` (the name upper-cased in the key, lower-case in Arras), or `[backends.<name>] endpoint` in the ops file; the environment wins | none |
| Token | Ops | `ARRAS_TOKEN_FILE` or `ARRAS_TOKEN` (not both) | none |
| `ARRAS_ENV`, `ARRAS_CONFIG_DIR`, `ARRAS_OPS_FILE` | Ops | environment | unset, `config`, unset |
| `placement` table (the default placement) and `modules.<module>` tables: `record`, `replicas`, and a `providers` table of action to provider backend (CONTRACT-002) | Dev | the committed files only; there are no `ARRAS_PLACEMENT*` keys | no default placement |
| `log_level` | Dev | the files; `ARRAS_LOG_LEVEL` overrides at deploy time | `INFO` |
| `user_claims` | Dev | the files; `ARRAS_USER_CLAIM` overrides at deploy time | `preferred_username`, `email`, `sub` |
| `dev_sandbox`, `dev_user` | Dev | the files; `ARRAS_DEV_SANDBOX`, `ARRAS_DEV_USER` override | off |

The set of configured backend names (`expected`) is the names that have an endpoint. A placement that names a backend with no endpoint is a problem naming the file and table key (the sandbox excepted). The ops file may carry only `[backends.<name>] endpoint`; a committed file may carry none of the ops keys.

**Tools.** The list is generated from the registry at the current revision.

| Tool | Input | Result |
|------|-------|--------|
| `describe` | `{module?: string}` | Modules, their types with columns, relationships and capabilities, actions, per-backend `status` (`available`, `reason`, `detail`; a replica adds `position` and `lag`) and revision (`Ontology.describe`). |
| `query` | `{module: string, sql: string, params?: object, limit?: int 1..100, consistency?: "latest"\|"bulk", at_least?: string}`; `module` and `sql` are required | `{rows, truncated, freshness}` (CONTRACT-001). |
| `validate_action` | `{action: string, inputs: object}` | The `Validation` of CONTRACT-003: violations, failed preconditions and resolved effects, nothing written. |
| `<module>_<snake_action>`, one per declared action | `{inputs: object, idempotency_key?: string}` or, for a batch, `{items: object[], atomic?: bool, stop_on_error?: bool, idempotency_key?: string}` | A `Receipt` or a `BatchReceipt` (CONTRACT-003); a receipt carries its `group`, the id of the atomic group the change committed in. |

- Every declared action has its own tool, named from its module-qualified name in snake case (`catalog_set_coverage` for `catalog.SetCoverage`). A name that collides is disambiguated by suffix and `describe` lists the mapping; a call is routed by the mapping the last `tools/list` gave out, so a name never comes to mean another action between listing and call, and a status or revision change sends `tools/list_changed` (checked after a call or a `ping`, at most every few seconds). Without a usable token a call to any tool but `describe` is `refused`, whatever its name. No generic `invoke` tool exists, so the host can classify and approve each tool by name under its own operator policy.
- An action tool's input schema is JSON Schema derived from the action's UMF input types: a string, a boolean, an integer (as a JSON integer when it fits 53 bits, otherwise a decimal string), a decimal (a decimal string), a timestamp (RFC 3339 text), binary (base64 text), a list as an array. The converter (`arras.inputs.convert_inputs`, shared with CONTRACT-009) takes exactly these text forms: an integer as ASCII digits with an optional sign; a decimal as digits with an optional sign, point and exponent, never `NaN` or `Infinity`; a timestamp as an RFC 3339 date-time with a calendar date, in-range hour, minute and second, and a required offset, accepting `t`, `z`, a space for `T` and omitted seconds; binary as padded base64. Anything else is a `type` violation at the input's path. Required inputs are `required`. Enumerations and bounds are carried when UMF declares them. The `batch` form (`items`, 1 to 100) is declared in the same schema as an alternative to `inputs`.
- `query` says in its description that the statement is Weft SQL and carries one worked example drawn from the registry.

**Annotations.** Arras sets `readOnlyHint` on `describe`, `query` and `validate_action`. For an action tool it sets `destructiveHint` (and only ever to true) when any effect is `delete` or `unlink`, or the action has a handler, `idempotentHint` always (an action is idempotent under a key) and `openWorldHint` false. The host's operator catalog decides tool class and reversibility; these protocol annotations can only tighten that classification.

**Answers.** An answer is compact JSON: rows as objects, no echo of the request, relationship columns as arrays of keys, `freshness` as `{backend, as_of: {value, at}, consistency}`, the library's `Freshness` and `Position` (CONTRACT-001), so an MCP result equals the library's. A result whose body is larger than 50 KB is cut at a row boundary and returned `truncated`; the caller continues with a keyset predicate in its own statement (`WHERE x.key > :last`). A single row beyond that is returned whole. The structured copy of the body is not counted. Integers beyond 53 bits and binary values go out as they come in: decimal text and base64. Nothing is returned that the user's token could not read.

**Errors.** A refusal is an MCP tool result with `isError: true` and a structured body, not a protocol error: `{code, message, hint}` where `code` is `invalid`, `refused`, `unavailable`, `unsupported` or `not_yet_current` (CONTRACT-001), or `precondition_failed` or `conflict` (CONTRACT-003) and `hint` says what to do next in a sentence an agent can act on (for example the closest column name when a column is unknown, or "call validate_action first" for a failed precondition). A violation carries its field or precondition and the value that failed. Protocol errors are for malformed MCP requests only.

### Distribution configuration, aliases and exposed tool names — EX-02

The `DistributionConfig` value and callable `arras.mcp.launch` are defined by
CONTRACT-005. Default construction preserves `serverInfo.name = "arras"`, the
existing tool spellings and the canonical `ARRAS_*` environment. The process uses
`Config.distribution.mcp_server_name` for serverInfo. Existing
`serverInfo.version` semantics are unchanged; distribution configuration supplies
no version override. Presentation never determines the token's user, groups, backend credentials or
an action's qualified identity.

Committed developer configuration accepts only these additional tables/keys:

```toml
[distribution]
mcp_server_name = "Example Distribution"
mcp_tool_prefix = "example"

[distribution.brand]
name = "Example Distribution"
title = "Example Workspace"
wordmark = "Example"
tagline = "A generic downstream interface"
logo = "theme"

[distribution.telemetry]
attribute_namespace = "example"
log_prefix = "example"
event_prefix = "example"
# service_name = "example-service"  # requires the explicit host provider factory
```

All fields are optional. Missing fields use the launcher's immutable defaults;
`default.toml` overrides those defaults and `<env>.toml` overrides `default.toml`,
merging distribution/brand/telemetry tables by field. Telemetry values and the
post-validation provider factory obey CONTRACT-005/008 and ADR-018/019. Existing ops ownership and file
precedence remain unchanged. Brand optional fields are omitted rather than written
as TOML null. An unknown distribution/brand/telemetry key, invalid type/value, or a loaded
`distribution.env_prefix` refuses startup. This cut adds no environment key for
presentation fields; the existing reader owns these TOML tables.

**Environment aliases.** For an explicitly selected prefix `P`, each recognized
`ARRAS_<suffix>` key/pattern has the optional spelling `P_<suffix>`. Read alias
and canonical namespaces once, before selecting files or building a token source.
A nonblank alias wins per key over the canonical fallback, except credential
ambiguity MUST refuse as below. Keep original key spellings for diagnostic
provenance; normalize into the existing schema, not a second loader. A misspelled
key in either selected namespace refuses startup. The existing explicitly ignored
admin/test prefixes remain ignored with their corresponding selected-prefix
spellings. Unrelated environment namespaces are not examined. With `P=ARRAS`
there is one namespace, not two copies. An empty/whitespace-only key remains unset
as in the existing loader.

Before alias precedence, examine every nonblank `TOKEN` and `TOKEN_FILE` in both
selected namespaces. Any token plus any token-file selection refuses, even when
one would otherwise be shadowed. Two different normalized token values refuse;
two different normalized token-file path strings refuse. Identical duplicates
of the same credential kind may be accepted. Normalization is the existing
outer-whitespace trim; do not read token files or resolve paths to decide that
conflicting strings are equivalent. Report conflicting key names, never token,
path, source content or callback exception text. No fallback or conflict policy
may join one person's credential to another credential source. Existing token
refresh and claim selection continue after this single check.

**Tool mapping.** Let `n` be the existing fixed/action tool name after the current
action collision-suffix rule. With empty prefix, expose `n`; otherwise expose
`<prefix>_<n>`. This mapping is injective and covers fixed tools, generated action
tools, tool names returned by describe/validation metadata and dispatch lookup.
An exposed name is at most 128 ASCII characters; this is an Arras bound, not a
claim about every MCP implementation. Refuse invalid prefix, an overlong name or
a duplicate exposed mapping before emitting an affected tools list or accepting
its calls; never truncate or silently replace an action. At startup inspect all
actions currently visible to the process's person before serving the first frame.
A degraded start retains its existing availability behavior; it MUST NOT report
unreadable modules as collision-checked or use an installer to enumerate them.
Later registry changes are checked on refresh before their tools become callable.

When configured with a nonempty prefix, only the exposed names dispatch; bare
fixed/action names and unknown prefixed names do not obtain an alias fallback.
`validate_action` still takes the canonical qualified `action` argument, and
receipts, error codes and audit attribution keep that qualified identity. Prefix
selection changes no schema, inputs, access, action collision ordering or
idempotency scope. A protocol-invalid unknown tool has no write effects.

Validation MUST demonstrate prefixed initialize/list/describe/query/validate and
actual action invocation, all returned tool references, changed-registry names,
collisions/bounds, tokenless/degraded behavior and refusal of bare names. Cover
alias/fallback file selection and endpoints, unknown keys in both namespaces,
blank handling and every TOKEN/TOKEN_FILE conflict combination with zero token
reads/backend effects and scrubbed errors. Default tests remain positive controls.
Opt-in exposure/alias configuration is additive under MCP v2; removing default
names or changing canonical action identity remains breaking.

## Precedence and Compatibility

- Versioning: v2, the tools and shapes this contract states; `arras.CONTRACT_VERSIONS["mcp"]`. The tool list is part of the contract for the fixed tools; action tools follow the modules' own revisions.
- Ordering or precedence: the library's rules (CONTRACT-001 to CONTRACT-005) decide every outcome; the binding translates and adds none.
- Backward compatibility: adding an optional field or tool is compatible. Renaming a fixed tool, changing a result shape or renaming the `<module>_<snake_action>` rule is breaking.
- Deprecation: as CONTRACT-001.

## Error Semantics

A typed `arras.policy.PolicyRefused` (CONTRACT-005) is still a `refused` tool
result with the existing hint/message and canonical native `no_access` meaning.
It additionally carries `policy_code`, the validated stable identifier chosen by
the host policy (or constant `policy_error` for a malformed/throwing callback).
Ordinary backend refusals do not acquire this field. No policy evidence, inputs,
annotations, credential values or exception text is serialized. This optional
field is additive; it does not create a protocol error or rename an error code.
Tests must pass an actual policy-wrapped backend through MCP, preserve the caller
identity, and prove denial applies nothing while the safe code reaches the
structured result. A policy allow cannot bypass a native grant refusal.

| Condition | Outcome | Retry | Recovery |
|-----------|---------|-------|----------|
| No, expired or malformed token | `refused`, hint to re-authenticate | after the host refreshes the token | Host refreshes the token file |
| A backend is unavailable | `unavailable` with backend and reason | yes | See CONTRACT-005 |
| Inputs fail the action's schema | `invalid`, per-field violations | after correcting | Correct inputs |
| A precondition fails | `precondition_failed` with every failed precondition and its reason | after the state changes | Call `validate_action` |
| An effect collides with existing state, or an idempotency key is reused with different inputs | `conflict` with the reason (CONTRACT-003) | after reading, or no for a reused key | Read the state, or use a new key |
| A query uses a shape the backend lacks | `unsupported` with the nearest supported shape | no | Rewrite the statement |
| A tool is called that the registry no longer declares | MCP invalid-params protocol error (-32602) | no | Re-list tools |

## Examples

```json
{"name": "query", "arguments": {"module": "catalog", "sql": "SELECT u.code, u.name FROM catalog.UseCase u WHERE u.workArea = :p ORDER BY u.code LIMIT 50", "params": {"p": "Finance"}, "limit": 20}}
{"name": "catalog_set_coverage", "arguments": {"items": [{"solution": "sol-pipeline-01", "level": "full"}, {"solution": "sol-pipeline-02", "level": "partial"}], "atomic": true, "idempotency_key": "cov-2026-10-05"}}
```

## Non-Normative Notes

The host consumes this binding through a local stdio adapter and classifies tool use and reversibility by tool name under its own fail-closed operator policy; each action is therefore exposed as its own tool. A per-session process carries one person's token without sharing multi-user state (ADR-016/017). The token-file reread and user-claim selection rules above define supported refresh mechanisms; the embedding host owns credential delivery and deployment wiring.
