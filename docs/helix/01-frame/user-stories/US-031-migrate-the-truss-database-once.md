---
ddx:
  id: US-031
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-05
  authoring:
    home: repo
  links:
    - id: FEAT-006
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-031: Migrate the Truss database once, on the installing connection

**Feature**: FEAT-006 — Embedding and Lifecycle
**Feature Requirements**: EMB-02
**PRD Requirements**: FR-32
**Priority**: P0
**Status**: Draft

## Story

**As a** Platform owner
**I want** Arras to install Truss when it is absent and verify it when it is present, on a trusted installing connection, once however many instances start
**So that** concurrent starts never collide and the database always holds the release Arras expects

## Context

Truss owns its own installation. `migrate()` asks Truss to install itself on the installing connection the host supplies (a trusted connection that never serves a read or an action), under a Postgres advisory lock taken before Truss adopts the transaction, or verifies the release already there and installs nothing. It grants no module access: `configure_access` does, one registered module at a time. Moving to another release is the separate, explicit `upgrade()`.

## Walkthrough

1. Two instances start together.
2. The system installs Truss in one instance. The other waits on the lock, finds Truss installed and reports that it did not run.
3. The host registers a module and configures access to it.

## Acceptance Criteria

- [ ] **US-031-AC1** — Given two concurrent starts, when each migrates, then one migration run occurs and the other returns `ran=False`.
- [ ] **US-031-AC2** — Given a database where Truss is installed at the supported release, when `migrate` runs, then it verifies the release, installs nothing and returns `ran=False`.
- [ ] **US-031-AC3** — Given a database where Truss is absent, when `migrate` runs, then it takes the advisory lock first, installs Truss, and returns `ran=True` with the owner and registrar role names Truss generated (returned once, only to the call that installed).
- [ ] **US-031-AC4** — Given a database with another Truss release, when Arras starts, then the backend is unavailable with `unsupported_version` and nothing is installed.
- [ ] **US-031-AC5** — Given no installing connection, when Arras starts, then no migration is attempted and the backend is `not_configured` until a call as a person has been made, and afterwards reports what that call showed.
- [ ] **US-031-AC6** — Given an install that fails or a lock wait that runs out, when `migrate` runs, then it fails as `migration_failed` with the detail and `status` reports it.
- [ ] **US-031-AC7** — Given `migrate` has installed Truss, when it returns, then no module has been granted to any role; `configure_access` grants each registered module, and fails at the first unregistered one with the module named.

## Edge Cases

- **A commit of unknown outcome**: settled by reading Truss's installation id back; the names are returned only when the installed id is this call's.
- **Truss installs only the current release** into an empty database and upgrades nothing, so a database of another release is `unsupported_version` and is recreated.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Once | US-031-AC1 | Two instances start together | Migrate | One run; the other `ran=False` |
| Verify | US-031-AC2 | Truss installed at the supported release | Migrate | `ran=False`; nothing installed |
| Install | US-031-AC3 | Empty database | Migrate | Lock taken, Truss installed, `ran=True` with the role names |
| Version | US-031-AC4 | Database at another release | Start | Unavailable, `unsupported_version` |
| No installer | US-031-AC5 | No installing connection | Start | No migration attempted |
| Failure | US-031-AC6 | The install fails, or the lock wait runs out | Migrate | `migration_failed`, with the detail |
| No grants | US-031-AC7 | A fresh install and an unregistered module | Migrate, then `configure_access` | Migrate grants nothing; the grant fails naming the module |

## Dependencies

- **Stories**: US-030
- **Feature Spec**: FEAT-006
- **Feature Requirements**: EMB-02
- **PRD Requirements**: FR-32
- **External**: [CONTRACT-005](../../02-design/contracts/CONTRACT-005-embedding-and-lifecycle.md), Migration.

## Out of Scope

- Connecting the backends at start (US-030).
- Changing Ashlar. Changes never go to Ashlar directly (ADR-013).
