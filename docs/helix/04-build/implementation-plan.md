---
ddx:
  id: implementation-plan
  type: implementation-plan
  activity: build
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-010
      kind: informed_by
    - id: ADR-021
      kind: informed_by
    - id: CONTRACT-009
      kind: informed_by
---

# Build Plan: Operator Console, slice 1

## Scope

Implement FEAT-010 slice 1 (schema, data and actions, OPR-01 to OPR-04, OPR-07, OPR-08) and the library half of the audit reads, so the contracts and the console agree. Slice 2's UI (the Audit area) is built against the fake backend only; no Truss journal read exists to implement it against (this repository has fakes, not a Truss adapter).

**Governing Artifacts**:
- [FEAT-010](../01-frame/features/FEAT-010-operator-console.md), US-060 to US-064
- [ADR-021](../02-design/adr/ADR-021-operator-console-as-a-react-package-in-the-arras-repository.md), [ADR-015](../02-design/adr/ADR-015-writes-are-umf-actions-applied-by-providers.md), [ADR-017](../02-design/adr/ADR-017-backends-are-reached-with-the-users-own-token.md), [ADR-020](../02-design/adr/ADR-020-contract-rules-are-checked-against-an-executable-model.md)
- [CONTRACT-001](../02-design/contracts/CONTRACT-001-ontology-interface.md) (audit reads, `Refused.reason`), [CONTRACT-003](../02-design/contracts/CONTRACT-003-actions.md) (`group`, `expected_revision`), [CONTRACT-004](../02-design/contracts/CONTRACT-004-backend-contract.md), [CONTRACT-006](../02-design/contracts/CONTRACT-006-console-graphql-surface.md), [CONTRACT-009](../02-design/contracts/CONTRACT-009-operator-action-and-audit-surface.md)
- Module boundaries: `tests/modules_check.py`, architecture.md Module Boundaries

## Shared Constraints

- Python 3.11 with `uv`; no `requirements.txt` (ADR-010). Every Python change keeps `uv run pytest`, `ruff` and `pyright` clean.
- The module boundary check (`tests/modules_check.py`) governs new modules. `arras.operate` is a new group that may import `foundation`, `domain` and `core`; it MUST NOT import `console`, `mcp` or `devhost`. Only `devhost` composes them.
- `tests/test_modules.py` caps a module at 960 lines and the fakes are near it; new code goes in new modules.
- No write other than invoking a declared action; no table of Arras's own; no credential in the browser; no input value in a URL, a log or an error `message`, `detail` or `notes` that Arras controls (CONTRACT-009). A refusal's reason text may name a key the caller sent; the console shows it and does not log it.
- Existing behavior stays compatible: new parameters are optional and new fields are additions (CONTRACT-003, CONTRACT-006 compatibility rules).
- `ui/` is a separate npm package: it imports nothing from Python and Python imports nothing from it; the Python wheel carries no UI assets (ADR-021).
- Truss, Ashlar and UMF documents never name Arras.

## Implementation Slices

Each slice is a commit that leaves the tree green; the failing test comes first.

| Slice | Story / Area | Governing Artifacts | Depends On | Validation Gate | Notes |
|-------|---------------|---------------------|------------|-----------------|-------|
| B-000 | Test plan and traceability: rows for US-060 to US-064, CONTRACT-009 and the new rules | docs/helix/03-test | None | Docs only | HELIX order: tests before code |
| B-001 | Boundaries and guards: groups `operate` (foundation, domain, core, shared HTTP types) and `devhost` (console, operate, doubles); `arras.boundary.PUBLIC_MODULE_NAMES` gains `arras.operate`; telemetry `EVENTS` gains `arras.changes` and `arras.loads`; a wheel-contents test asserts no `ui/` files | ADR-020, architecture.md | B-000 | `uv run pytest tests/test_modules.py tests/test_boundary.py tests/test_telemetry.py`; the checker rejects `operate` importing `console`, `mcp` or `devhost` | Foundation first |
| B-002 | Shared code and room: move `CONTRACT_VERSIONS` to a foundation `arras.versions` (root re-exports); move `Request` and the ASGI aliases to a foundation `arras.http` (console re-exports); move `to_python`, `convert_inputs` and the converter-fault merge from `mcp` to a `domain` module; split `fakes.py` so the journal code lives in `fakes_journal.py` (same `doubles` group) and stays under `MAX_MODULE_LINES` | CONTRACT-006, CONTRACT-007 | B-001 | MCP, console and public-API tests unchanged and green | No behavior change |
| B-003 | Action additions: `Receipt.group` (field after `replayed`, one group per atomic batch and per non-atomic item, kept on replay); `expected_revision` checked in core against the record store's catalog revision (a race with `register` is an accepted risk until a Truss adapter exists), JSON `{"memory": 3}` read as a `Revision`, every backend it names checked; `Conflict(revision)`; MCP receipts gain `group` (CONTRACT-007 note); conformance `has_group` and `one_group` checks, corpus `version` 2 | CONTRACT-003, CONTRACT-007 | B-002 | Failing tests first; corpus green on both fakes; the executable model in `tests/test_properties.py` gains: replay returns the same group, atomic batch is one group, a stale `expected_revision` applies nothing, each with a mutant that makes the model fail | US-062 |
| B-004 | `Refused.reason` (`no_access` default, `token_expired`), set in core `require_token` and the fakes' gate; `error_body` carries it; CONTRACT-006 extensions carry it; corpus cases | CONTRACT-001, CONTRACT-006 | B-002 | test_errors, test_devhost_server, test_mcp, test_console green plus new cases | Needed for 401 vs 403 |
| B-005 | Audit reads: `Ontology.changes` and `loads`; `Change`, `Load`, `ChangesPage`, `LoadsPage` exported (sorted `__all__`); `Provider.changes` and `loads`; the fake keeps a separate audit journal written only in `_commit`, capturing entity and link ops and the load; a new `journal` grant mode through `FakeAccess`, the conformance harness, the corpus and the sandbox people; core routes `group` lookups across providers and `changes`/`loads` take an optional `provider` (the record store by default; a name outside the placement is `Invalid`); `Unsupported` for a module whose provider keeps none | CONTRACT-001, CONTRACT-004 | B-003, B-004 | Tests: person, action, ops and group appear; refused, validate-only and failed groups add nothing; no inputs; a reader without the journal grant is `Refused`; bounds on `limit`; the executable model gains "each applied invocation adds exactly one change; replays, validates and refusals add none" with a mutant | US-063 |
| B-006 | Console schema additions: `Entity` attribution fields and `ActionInfo.inputSpecs`; the console also refuses cross-origin POST (same-origin only) and CONTRACT-006 says so | CONTRACT-006 | B-001 | SDL tests; attribution null for a foreign `Ref.target`; existing console tests green | US-060, US-061 |
| B-007a | `arras.operate`, action half: `/version`, `/openapi.json`, validate, invoke, batch; an explicit wire encoder for `Validation`, `Effect`, `Freshness`, `Receipt`, `BatchReceipt` (the shapes in CONTRACT-009); an `Invalid`-code-to-status table (`unknown_action`, `unknown_type` to 404, others to 400); origin and preflight rules; `authorize_action`; per-principal bound; `message` rebuilt from type and reason only; `CONTRACT_VERSIONS["operate"]`; checked-in `ui/openapi.json` snapshot with a Python drift test | CONTRACT-009 | B-002 to B-004 | Contract tests derived from CONTRACT-009's tables; a mutant fake that echoes an input in `detail` and in a failure reason; no path writes except the three action endpoints | US-062, US-064 |
| B-007b | `operate` audit half: `/audit/changes`, `/audit/loads` | CONTRACT-009 | B-005, B-007a | Contract tests; 401 on expiry, 403 without the grant, 501 for a module whose provider keeps no journal | Cuttable separately |
| B-012a | Dev host (`arras.devhost`): console, operate and the built `ui/dist` at one origin, sandbox `principal_for_request`, served with uvicorn (an optional `devhost` extra, not a runtime dependency; the release workflow copies runtime dependencies only); a lock around the fakes so parallel requests cannot lose updates | ADR-021 | B-006, B-007a | `uv run python -m arras.devhost` serves `/`, `/graphql`, `/actions/...`; a concurrency test on the fakes | Before the UI slices that test against it |
| B-008 | `ui/` scaffold on praxis's stack (React 19, TypeScript, Vite, Tailwind 4, TanStack Query), versions pinned from praxis's `package.json` with a recorded fallback if unreachable; typed client from the checked-in `openapi.json` and the meta schema; `/version` check at load | ADR-021 | B-007a | `npm ci`, `npm run build`, `npm run typecheck`, `npm test` (Vitest) green | `ui/` builds without Python |
| B-009 | `ui/` Schema and Data areas: module list and detail, table with filters, one page per request marked when truncated, consistency toggle, freshness, entity panel with attribution and `Ref.target` follow | US-060, US-061 | B-006, B-008, B-012a | Component tests with a mocked server; a browser run against the dev host | The relationship diagram is the first cut |
| B-010 | `ui/` Actions area: form from `inputSpecs` (a raw-JSON field for `record` inputs), client-side type checks, validate on blur and before confirm, effects preview, confirm, invoke with a generated key and `expected_revision`, receipt, conflict rebuild; batch last | US-062 | B-007a, B-009 | Component tests per US-062 criterion; whole-stack run | The primary operator workflow |
| B-011 | `ui/` Audit area, hidden unless the backend serves it | US-063 | B-007b, B-009 | Component tests; whole-stack run shows the change attributed | Cut first |
| B-011b | Audit by provider: `provider` on `/audit/changes` and `/audit/loads` (OpenAPI and `ui/openapi.json` regenerated), and a provider selector in the console's audit view for a module with more than one journal-bearing provider | US-063, CONTRACT-009 | B-007b, B-011 | `test_operator_library` (`test_changes_can_name_the_provider_whose_journal_is_read`, `test_loads_can_name_the_provider`, `test_a_provider_outside_the_placement_is_refused`, `test_a_provider_without_a_module_is_refused`), `test_operate_audit::test_audit_routes_accept_a_provider`, ui `audit.test.tsx` | A merged feed across providers is not built (CONTRACT-001, Open Questions) |
| B-014 | Layered MCP configuration: `arras.mcp.config` reads `config/default.toml`, `config/<env>.toml` (`ARRAS_ENV`, `ARRAS_CONFIG_DIR`) and the ops layer (environment and `ARRAS_OPS_FILE`); placement from the files only; one owner per key; startup line on stderr; SIGTERM/SIGINT exit 0 | ADR-019, CONTRACT-007, US-058 | none | `tests/test_config.py` (layers, ops values, one-owner and unknown-key refusals, missing environment file, default file equals the schema) and `tests/test_mcp_process.py::test_sigterm_ends_the_process_cleanly` | `.env.example` lists environment keys only |
| B-012b | Whole-stack test of the primary workflow through the UI against the dev host (Playwright, local run; CI if time allows) | US-064, ADR-021 | B-010 | Find a type, run a declared correction, see `updatedBy` on the entity | Selects the e2e tool for the `admin-console` concern |
| B-013 | Tooling and docs: CI runs `ruff format --check`, `uv build` with a wheel import smoke test, `uv sync --locked`, the 3.11 to 3.13 matrix, and a `ui/` job; the sdist excludes `ui/`; README and the contracts, FEAT-010 and PRD sketches match what was built; ADR-021 stays Proposed | ADR-021 | all | CI green locally by direct commands (no new task runner) | |

**Cut order** (cut the first line first if time runs out): B-011; the `/audit` endpoints shipped as 501 `Unsupported`; batch UI; the relationship diagram; Playwright in CI; the generated client (hand-written types). Never cut B-001 to B-004, B-006, B-007a, B-012a, B-008 or the single-invoke form.

## Execution Contract

The user authorizes implementation separately from plan readiness; this plan is authorized by the request to implement it. Execute the ordered slices through their validation gates. Write the failing test first in each slice. A slice is a reviewable commit. Stay within Scope; stop for authority conflicts, a needed decision, or a blocker. Ordinary debugging remains in scope.

## Continuation Evidence

On interruption, record the completed slice IDs with the test evidence, the remaining slices and the next action, beside this plan. On resume, reconcile the record with the diff and `uv run pytest` before continuing.

Deferred: `expected_revision` atomicity inside `Provider.apply`; a module whose record store is not a provider in the dev sandbox so the 501 audit state runs end to end; per-person journal grant policy (PRD open question); publishing `arras-ui` (registry and name undecided). The two mutant tests in `tests/test_properties.py` that failed about one run in seven are deterministic.

## Optional Tracking

None selected. This plan is the one tracked goal.

## Validation Plan

- [ ] Failing tests exist before each slice's implementation
- [ ] `uv run pytest`, `ruff check`, `pyright` and the module boundary check pass
- [ ] `ui/` build, typecheck and tests pass; the whole-stack test passes
- [ ] Behavior changes update the contracts, FEAT-010 and the PRD acceptance sketches

## Risks and Rollbacks

| Risk | Impact | Response | Rollback |
|------|--------|----------|----------|
| The change set is large for one pull request | M | Land it as one slice per commit so a reviewer can read it in order | Revert a commit; each slice leaves the tree green |
| The UI work outgrows the session | H | Cut order: B-011 and B-012's polish go last; B-008 to B-010 are the minimum for a working vertical slice | Ship `operate` and the library additions with a smaller `ui/` |
| The fakes are not thread-safe and the operate surface runs requests in parallel | M | A lock in the fakes (B-012a) and a concurrency test | Serialize requests in the dev host |
| Truss has no journal read, so `changes` exists only on the memory adapter | M | State it in the PR; the audit area stays hidden unless the backend serves it | `changes` raises `Unsupported` for any backend that lacks it |
| `arras.operate` mis-handles an origin rule or leaks an input | H | Contract tests for each rule in CONTRACT-009; the review covers it | Do not mount the app; it is opt-in |
| New dependencies on the Node side | M | Lockfile, audit in CI, versions matched to praxis | Remove `ui/`; the Python package is unaffected |

## Exit Criteria

Execution is complete only when:

- [ ] An operator can, through the UI against the dev host, browse a module, read a type's table, follow a relationship, run a declared action with validate and confirm, and see the attributed change on the entity (`updatedBy`, `updatedAt`); the Audit area is a bonus if not cut.
- [ ] Every slice's validation gate and the final integration gate pass.
- [ ] Acceptance evidence is recorded in the pull request; no required step or material blocker remains.
- [ ] The contracts, FEAT-010 and the PRD match what was built.
