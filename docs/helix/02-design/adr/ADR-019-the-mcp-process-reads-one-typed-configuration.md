---
ddx:
  id: ADR-019
  type: adr
  activity: design
  status: accepted
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: ADR-006
      kind: informed_by
    - id: ADR-016
      kind: informed_by
    - id: ADR-017
      kind: constrained_by
    - id: CONTRACT-005
      kind: informs
    - id: CONTRACT-007
      kind: informs
---

# ADR-019: The MCP process reads one typed configuration

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-11 | Accepted | Erik LaBianca (architecture lead) | [ADR-006](ADR-006-embedded-library-on-psycopg-and-the-truss-toolkit.md), [ADR-016](ADR-016-mcp-stdio-binding-over-the-library.md), [ADR-017](ADR-017-backends-are-reached-with-the-users-own-token.md) | Medium |

## Context

| Aspect | Description |
|--------|-------------|
| Problem | The library takes everything as parameters and reads no environment (CONTRACT-005). The MCP process is the one place configuration arrives from outside. Its keys must not be read where they are used, with no schema, no check that a key is known and no way to see the surface (a misspelled endpoint would be a silent `not_configured`), and a stack of environment variables is a poor place for what developers own: where each module lives, the log level, the user claims. |
| Requirements | One place reads files and the environment. Every key has exactly one owner. A bad configuration stops the process at start, naming the file and key and never a value. The surface is a contract between whoever deploys the process and whoever develops it. The process is disposable (starts fast, stops on a signal). |
| Decision Drivers | Twelve-factor config split by owner, with committed per-environment files for what developers own and the environment for what operations inject; ADR-017 (the token is the person's own, never a backend credential); the host, praxis, supplies the backends. |

## Decision

`arras.mcp.config` holds the schema and builds one immutable `Config` at start. It is the only module that reads files or the environment. Configuration has three layers by owner, highest precedence first:

1. **Ops-injected, never committed.** Environment variables, and one optional ops file named by `ARRAS_OPS_FILE` (a mounted secret or handle file outside the repository). Ops keys: each backend's endpoint (`ARRAS_BACKEND_<NAME>_ENDPOINT`, or `[backends.<name>] endpoint` in the ops file; the environment wins), the token (`ARRAS_TOKEN`, `ARRAS_TOKEN_FILE`, not both), `ARRAS_ENV`, `ARRAS_CONFIG_DIR` and `ARRAS_OPS_FILE`.
2. **Committed per-environment file**, `<config_dir>/<env>.toml`, with `env` from `ARRAS_ENV` (no default: unset reads only the defaults) and `config_dir` from `ARRAS_CONFIG_DIR` (default `config`). Developer-owned and non-secret.
3. **Committed defaults**, `<config_dir>/default.toml`.

Layer 2 overrides layer 3 key by key and tables merge. The format is TOML, read with the standard library.

**Key Points**:
1. **One owner per key.** A committed file that carries an ops key (`endpoint`, `token`, `backends`, any `ARRAS_` name) is refused, naming the file and the key. The ops file may carry only `[backends.<name>] endpoint`. An unknown key in a file is refused by name.
2. **Placement lives in the files.** Where each module lives is `[placement]` (the default) and `[modules.<module>]` with `record`, `replicas` and a `providers` table of action to provider backend (CONTRACT-002). There are no `ARRAS_PLACEMENT*` environment keys. A placement that names a backend with no endpoint is reported against the file and table key (the sandbox excepted).
3. **Dev keys may be overridden at deploy time.** `log_level`, `user_claims`, `dev_sandbox` and `dev_user` are developer-owned in the files and may be overridden by `ARRAS_LOG_LEVEL`, `ARRAS_USER_CLAIM`, `ARRAS_DEV_SANDBOX` and `ARRAS_DEV_USER` as an incident measure.
4. **Fail fast and say which file and key.** Every unusable key is reported together, as the file (or environment variable) and key with a reason. A named `<env>.toml` that does not exist is an error naming the path; a file that is not valid TOML is an error naming the path and line, never content. A missing `default.toml` is fine: the schema supplies defaults. An unknown `ARRAS_` environment key is an error. Values are never echoed, so a token cannot reach a log through a message.
5. **No backend credential.** `Config` holds handles (endpoints), `env`, `config_dir` and `sources` (the files actually read). The person's token is carried only to build the token source and is excluded from the object's representation (ADR-017).
6. **Handles become adapters in one place.** `arras.mcp.backends.build_backends` is the composition root. A handle that is a `postgresql://` URI becomes a Truss backend over the person's own token (`arras.adapters.truss.endpoint`; no new key, so the schema, `.env.example` and the example file are unchanged); a URI that is not a usable endpoint (a credential, an unknown parameter, plaintext to a remote host) is a start error naming the key. A configured handle no adapter reads, or whose extra is missing, is reported as unbuilt with the reason, so the process starts degraded and says why rather than treating a handle as a connection. The process holds no installing connection, so it cannot read the Truss backend's install state: the status is `not_configured` until a call as a person has been made and is then what that call showed (available, or unavailable with the reason); Truss limits its install-state read to the installer and the registrar (R22). Before it connects the process clears the libpq environment (`PG*`): no connection keyword switches the service file off, so scrubbing is the one way that no ambient variable reaches the connection.
7. **The schema is published.** `.env.example` lists every environment key, ops keys blank and dev keys at their defaults; `config/default.toml` holds the defaults; `config/example.toml` shows every table and is read only when `ARRAS_ENV=example`. A test keeps all three equal to the schema.
8. **The process is disposable.** It starts from configuration alone, logs one startup line to stderr naming the environment and the files read (never values), and on SIGTERM or SIGINT finishes the frame in flight, stops reading, flushes and exits with status 0.

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| Read the environment where a key is used | Nothing to build | No schema, silent typos, secrets in scattered code | Rejected |
| Environment variables only, placement included | One mechanism | Placement is structured (tables, lists, action maps) and developer-owned; a stack of variables is hard to review and to diff per environment | Rejected |
| **One schema, one reader, three layers by owner** | Developer-owned values are committed and reviewed; secrets and handles stay out of the repository; fails fast | One more module and a small file format | **Selected** |

## Consequences

| Type | Impact |
|------|--------|
| Positive | The deployment surface is a document, committed files and a test; typos fail at start, naming file and key; placement is reviewed like code. |
| Negative | A deployment with a stray `ARRAS_` variable, or an ops key in a committed file, no longer starts. |
| Neutral | The library's parameters are unchanged. |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| The adapters need keys the schema lacks | H | L | Add them to the schema, `.env.example` and the committed files in the same change; the sync test fails otherwise |
| A secret is committed in a file | L | H | A committed file may not carry an ops key; the loader refuses it |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| One module reads files and the environment | A second one does |
| `.env.example` and the committed default file equal the schema | They differ |
| The real process exits 0 on SIGTERM | It does not |

## References

- [CONTRACT-007](../contracts/CONTRACT-007-mcp-binding.md), [CONTRACT-005](../contracts/CONTRACT-005-embedding-and-lifecycle.md), [CONTRACT-002](../contracts/CONTRACT-002-type-registry-and-placement.md)
