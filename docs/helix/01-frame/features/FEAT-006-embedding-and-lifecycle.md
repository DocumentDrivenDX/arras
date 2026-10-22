---
ddx:
  id: FEAT-006
  type: feature-specification
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: concerns
      kind: informed_by
---

# Feature Specification: FEAT-006 — Embedding and Lifecycle

**Feature ID**: FEAT-006
**Status**: Draft
**Priority**: P0
**Owner**: Erik LaBianca
**Covered PRD Subsystem(s)**: Embedding and Lifecycle
**Covered PRD Requirements**: FR-31 to FR-35, FR-48 to FR-50
**Cross-Subsystem Rationale**: None; single subsystem.

## Overview

Embedding and Lifecycle implements PRD FR-31 to FR-35 and FR-48 to FR-50. A host Python application starts Arras as a library. The host registers its backends under names it chooses, states each module's placement, supplies for each backend a connection source that yields a connection for a given person, names an administrative principal for registration, attachment and imports, and for the Truss adapter supplies an installing connection. Arras installs or verifies the adapters' stores through their own installers and reports whether each backend is available.

The host is the application that embeds Arras. Truss is the hot mutable store on Lakebase (Databricks managed Postgres). Ashlar is the warehouse store on Unity Catalog (Databricks' data catalog and access-control layer). MCP (Model Context Protocol, Anthropic's open protocol for agent tools) is the protocol of the stdio binding specified in FEAT-009.

## Ideal Future State

The embedding application adds Arras as a library, builds a Truss adapter from a per-principal connection source and an Ashlar adapter from a warehouse source, registers them under names it chooses with each module's placement, names an administrative principal and an installing connection and starts. A backend that is down is reported with its reason while the host keeps serving. The install runs once however many instances call `migrate`; `start` installs nothing. The stdio MCP binding is the only code that reads the environment or configuration files.

## Problem Statement

- **Current situation**: No store is embedded in the embedding host. A host could keep a database inside its own project for the catalog.
- **Pain points**: A slow or failing backend must not break a shared app's startup, and installs must not collide.
- **Desired outcome**: A library the host controls, with bounded startup and per-backend status.

## Functional Areas

| Area | User question or job | Feature responsibility |
|------|----------------------|------------------------|
| Connections | What does the host supply? | A source per backend, called with the principal, an administrative principal, and for the Truss adapter an installing connection |
| Migrations | Who prepares the Truss adapter's database? | Truss's own installer, on the host's installing connection: install-or-verify under an advisory lock, once across concurrent calls; no upgrade (a database of another release is recreated); module access by `configure_access` |
| Availability | Is it up? | Per-backend status; the host keeps starting |
| Boundary | Who imports what? | Public names only, checked in the build; no environment reads outside the MCP binding |
| Development | How is it tested? | A local PostgreSQL 18.6 |
| Structure | Do the modules keep their rules? | A dependency map, checked in the build |
| Observability | What did it do, and how did it end? | Events and spans to the host's tooling, with no content |
| Configuration | What does the MCP process need? | One schema, one reader, a named failure |

## Requirements

### Functional Requirements by Area

#### Connections

EMB-01. Arras runs inside a host Python application as a library. The host supplies, for each backend, a source that yields a connection for a given principal. Arras reads no ambient connection variables, creates no connection itself and reuses none across people. Only the MCP binding reads the environment or configuration files (FR-31).

#### Migrations

EMB-02. Arras installs or verifies the Truss adapter's store through Truss's installer, on the installing connection the host supplies and under a transaction-scoped advisory lock, on request and once under concurrent calls; it keeps no migration history of its own (FR-32).

#### Availability

EMB-03. If a backend is unconfigured, unreachable, denies access or fails to migrate, Arras reports it unavailable with a reason and the host continues to start (FR-33).

#### Boundary

EMB-04. Arras imports nothing from the host, and the host imports only Arras's public interface. A check fails the build on a violation (FR-34).

#### Development

EMB-05. A developer can run Arras and its tests against a local PostgreSQL with no external database (FR-35, P1).

#### Structure

EMB-06. The library's modules follow the dependency rules of the architecture's Module Boundaries, with no cycle and no module above the length ceiling. A check fails the build on a violation (FR-48, P1).

#### Observability

EMB-07. Arras emits the events of CONTRACT-008 to the host's logger and, with OpenTelemetry installed, spans on the host's tracer provider. Attributes are default-deny, the caller's trace continues across MCP, nothing is written to stdout, and telemetry never fails an operation (FR-49, P1).

#### Configuration

EMB-08. The MCP process builds one typed configuration from a published schema at start, in three layers by owner (ops-injected environment and ops file, a committed per-environment file, committed defaults), each key with one owner. It is the only code that reads files or the environment, and it stops naming the file and key it cannot use and never its value (FR-50, P1). It is disposable: SIGTERM or SIGINT finishes the frame in flight and exits 0.

### Non-Functional Requirements

- **Reliability**: a budget bounds connection and install attempts. An unavailable backend re-probes at most every 5 seconds.
- **Concurrency**: a transaction-scoped advisory lock serializes installs, and the lock holds behind a transaction-mode pooler.
- **Portability**: the Truss-marked suite passes on PostgreSQL 18.6, the engine Truss runs on and the engine Lakebase provides.

## User Stories

- [US-030: Embed Arras with host-supplied, per-person connections](../user-stories/US-030-embed-arras-with-host-settings.md)
- [US-031: Migrate the Truss database once, on the installing connection](../user-stories/US-031-migrate-the-truss-database-once.md)
- [US-032: Keep the host starting when a backend is unusable](../user-stories/US-032-keep-the-host-starting-when-a-backend-is-unusable.md)
- [US-033: Fail the build on a boundary violation](../user-stories/US-033-fail-the-build-on-a-boundary-violation.md)
- [US-034: Run Arras and its tests on a local PostgreSQL 18.6](../user-stories/US-034-run-tests-on-embedded-postgres.md)
- [US-056: Keep the library's modules to their dependency rules](../user-stories/US-056-keep-the-librarys-modules-to-their-dependency-rules.md)
- [US-057: Observe operations without leaking content](../user-stories/US-057-observe-operations-without-leaking-content.md)
- [US-058: Configure the MCP process from one schema](../user-stories/US-058-configure-the-mcp-process-from-one-schema.md)

## Edge Cases and Error Handling

- When two instances start together, one install runs.
- When a database is lost after start, operations that need it raise unavailable and other operations work.
- When the Truss adapter's layout major version differs, the backend is unavailable with that reason.
- A pooler that does not support prepared statements works, at a small cost.

## Success Metrics

- The embedding host starts and serves with either backend unavailable.
- One install under two concurrent starts.

## Constraints and Assumptions

- Python 3.11, psycopg 3 (the Postgres driver) and Truss, both in the optional `truss` extra, per ADR-006 and ADR-010.
- The host supplies the Databricks SQL warehouse access for Ashlar, acting with the person's token.
- The administrative principal is explicit and never serves a read or an action.

## Dependencies

- **Other features**: FEAT-004 (the backends started), FEAT-005 (the person's own token), FEAT-009 (the MCP binding).
- **External services**: Lakebase, Databricks SQL, Unity Catalog; the exact surface lives in CONTRACT-005 (embedding and lifecycle).
- **PRD requirements**: FR-31 to FR-35 (P0 item 6; P1 item 2).

## Out of Scope

- A standalone process.
- The host's own API and screens.
