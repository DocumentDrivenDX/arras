---
ddx:
  id: US-058
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-006
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-058: Configure the MCP process from one schema

**Feature**: FEAT-006 — Embedding and Lifecycle
**Feature Requirements**: EMB-08
**PRD Requirements**: FR-50
**Priority**: P1
**Status**: Draft

## Story

**As a** Platform owner
**I want** the MCP process to read its configuration once, from a published schema, and to stop at start naming any key it cannot use
**So that** a misspelled endpoint, a secret in a committed file or a bad value is a clear failure at deploy time, naming the file and key, and not a silent degraded start

## Context

The schema is `arras.mcp.config` (ADR-019). Configuration has three layers by owner: ops-injected (environment variables and an optional ops file named by `ARRAS_OPS_FILE`), the committed `config/<env>.toml` (`env` from `ARRAS_ENV`) and the committed `config/default.toml`. Ops keys (a backend's endpoint, the token file or token) are never committed and have no default; dev keys (placement, log level, user claims) live in the committed files, and the process stops at once naming the file and key when one is wrong. `.env.example` lists the environment keys. The library reads no environment and no file.

## Walkthrough

1. The operator deploys the process with a misspelled endpoint key.
2. The process exits with status 2 naming the key (and the file, when it is in one).
3. The operator corrects it and the process starts.

## Acceptance Criteria

- [ ] **US-058-AC1** — Given no keys, when the process starts, then defaults apply and no backend is configured.
- [ ] **US-058-AC2** — Given an unusable or unknown key, when the process starts, then it exits with status 2 and each key named on stderr, and no value is shown.
- [ ] **US-058-AC3** — Given both a token and a token file, when the process starts, then it is refused.
- [ ] **US-058-AC4** — Given the schema, when `.env.example` is read, then it lists exactly the schema's keys, ops keys blank.
- [ ] **US-058-AC5** — Given the library, when its source is read, then the only reader of the environment and of configuration files is the config module.
- [ ] **US-058-AC6** — Given a handle with no adapter built, when the process starts, then it starts degraded and says so on stderr.
- [ ] **US-058-AC7** — Given `config/default.toml` and a `config/<env>.toml` named by `ARRAS_ENV`, when the process starts, then the environment file overrides the defaults key by key, and ops values (environment, then the ops file) override both.
- [ ] **US-058-AC8** — Given a committed file that carries an ops key (an endpoint, a token), an unknown key, a named environment file that does not exist, or text that is not TOML, when the process starts, then it exits with status 2 naming the file and key (or path and line) and no value.
- [ ] **US-058-AC9** — Given the module placements, when the configuration is read, then they come only from the files (`[placement]`, `[modules.<module>]` with `record`, `replicas` and `providers`); no `ARRAS_PLACEMENT*` environment key exists.
- [ ] **US-058-AC10** — Given the ops file, when it carries anything but `[backends.<name>] endpoint`, then it is refused; given an endpoint in both the environment and the ops file, then the environment wins.
- [ ] **US-058-AC11** — Given a running process, when it receives SIGTERM, then it finishes the frame in flight and exits with status 0.
- [ ] **US-058-AC12** — Given the schema, when `config/default.toml` is read, then it carries exactly the schema's defaults.

## Edge Cases

- **A token in an error**: never: values are not echoed
- **A variable that is not `ARRAS_`**: ignored
- **No `ARRAS_ENV`**: only `default.toml` is read; a missing `default.toml` is fine (schema defaults)
- **A secret in a committed file**: refused, naming the file and key, never the value
- **`ARRAS_ADMIN_*`** and **`ARRAS_REQUIRE_WEFT`**: belong to the administrator's process and to the test suite; present, never read, never an error (CONTRACT-007)
- **A user claim list that is empty or padded**: trimmed, and an empty list is the default

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Defaults | US-058-AC1 | empty environment | Build the config | Defaults, no endpoints |
| Bad keys | US-058-AC2 | a typo, a bad level | Build the config | Every key named, no value shown |
| Two token sources | US-058-AC3 | a token and a token file | Build the config | Refused, naming the key |
| Process exit | US-058-AC2 | a bad level and a token | Run the process | Status 2, stdout empty |
| Example file | US-058-AC4 | `.env.example` and the schema | Compare | Equal |
| One reader | US-058-AC5 | the package source | Scan for environment reads | Only the config module |
| Unbuilt handle | US-058-AC6 | a configured backend endpoint (`ARRAS_BACKEND_<NAME>_ENDPOINT`) | Build backends | None built, the backend's name given |
| Layers | US-058-AC7 | a default file, an environment file and an endpoint in the environment | Build the config | The environment file wins over the default key by key; ops values win over both |
| One owner | US-058-AC8 | an endpoint in a committed file, an unknown key, a missing named file, invalid TOML | Build the config | Each refused, naming file and key (or path and line), no value |
| Placement in files | US-058-AC9 | a `[modules.catalog]` table | Build the config | The placement is in `Config`; no placement environment key is read |
| Ops file | US-058-AC10 | a mounted ops file with an endpoint and one with another key | Build the config | Endpoints read, environment wins; the other refused |
| Disposable | US-058-AC11 | the real process with a frame in flight | Send SIGTERM | Clean exit, status 0 |
| Default file | US-058-AC12 | `config/default.toml` and the schema | Compare | Equal |
