---
ddx:
  id: ADR-030
  type: adr
  activity: design
  status: accepted
  owner: Erik LaBianca
  updated: 2026-10-12
  authoring:
    home: repo
  links:
    - id: ADR-015
      kind: informed_by
    - id: ADR-025
      kind: informed_by
    - id: ADR-029
      kind: informed_by
    - id: SD-013
      kind: informed_by
    - id: SD-011
      kind: informed_by
---

# ADR-030: The action kit is a neutral layer under both modes, with an import allow-list

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-12 | Accepted | Erik LaBianca (architecture lead) | [ADR-015](ADR-015-writes-are-umf-actions-applied-by-providers.md), [ADR-025](ADR-025-one-shell-two-modes-and-operate-is-offered-by-the-host.md), [ADR-029](ADR-029-the-ui-draws-through-a-pluggable-design-system-seam-with-a-built-in-default.md), [SD-013](../solution-designs/SD-013-instance-work-in-explore-and-the-shared-action-kit.md), [SD-011](../solution-designs/SD-011-graph-browser.md) | High |

## Context

| Aspect | Description |
|--------|-------------|
| Problem | Explore (`ui/src/browser/`) and Operate (`ui/src/areas/`, `ui/src/console/`) both change data by invoking declared actions as the viewer. Each needs the same form model (typed values, built inputs, errors by field, validation, confirmation, a receipt, one idempotency key per input signature, one revision-conflict rule) and the same derivations from a module's declared actions. The two modes must not import each other (SD-011), and the console's own hook reads the console's meta, its cache keys, its refusals and its impact view. |
| Current State | The console's form model is `areas/useActionForm.ts`, an adapter over the kit's `kit/useActionForm.ts`; Explore's one-shot edits are `browser/useAction.ts`, a wrapper over the kit's `kit/actionCore.ts`. |
| Requirements | One implementation of input coding, validation, idempotency, revision conflicts and receipts; each mode keeps its chrome, caches and routes; the rule that separates the modes stays enforceable by a test. |

## Decision

1. **The kit.** `ui/src/kit/` is the neutral layer both modes import. It is internal (not an npm subpath) and imports neither mode.
2. **Its allow-list** is exactly what `KIT_MAY` in `ui/src/test/boundaries.test.ts` enforces: its own modules, `api/`, `ds/` (the design-system seam, ADR-029), `lib/inputs`, `lib/format`, `lib/formFocus` and `lib/template`, besides third-party packages (`react`, `@tanstack/react-query`). It imports nothing from `areas/`, `browser/`, `console/`, `shell/`, `route`, `lib/graph`, `lib/impact` or `components/ui`, and nothing in `lib/` imports `kit/`. `browser/` and `areas/` may import `kit/`. The rule is enforced twice and the two agree: Biome overrides in `ui/biome.jsonc` (for `src/kit/**` an allow-list of the paths up the tree; for `src/browser/**` a forbid-list that includes `console/`), and `boundaries.test.ts`, which resolves relative, aliased (`@/`, `~/`, `src/`), absolute and package-style (`arras-ui/...`) imports to the files they name, so none is a way around it.
3. **The injected interface.** The form model (`kit/useActionForm.ts`) takes `{module, action, prefill?, onApplied(receipt), reloadModule(), client}` and returns a neutral state of at least `info`, `specs`, `revision`, `values`, `touched`, `built`, `violations`, `failures`, `checked`, `fresh`, `stale`, `validating`, `submitting`, `receipt`, `error`, `refusal`, `conflict`, `epoch`, `locked`, `canConfirm`, `effects`, `status`, `valid`, and the transitions `validate`, `confirm`, `onChange`, `onBlur`, `reset`, `editAgain`. It reads no cache, route, console meta or impact view: a surface invalidates its own reads in `onApplied`, reloads the registry in `reloadModule` after a revision conflict, and adapts the result to its own view. A refusal is returned, and the kit neither holds nor acts on it for the surface.
4. **One write core.** The validate-then-invoke of a one-shot change is `useActionCore` (`kit/actionCore.ts`), used by Explore's property edits, link changes and dialogs; the form model is the same two calls with a review between them. `validate` and `invoke` are called from those two modules only (and `batch` from the console's `BatchForm`, outside `browser/` and `kit/`); a boundary test scans `browser/` and `kit/` for any other call and for browser storage.
5. **Headless first.** The model and the derivations carry no markup. Pieces that draw anything use the design-system widgets from `ds/` (ADR-029) and render no `Scope`, dialog or panel. Hosts keep their chrome: the console its `ActionForm`, Explore its `gb-dialog` dialogs.
6. **The cross-mode link vocabulary lives in the kit.** `kit/links.ts` holds `LinkTarget` (an entity, a type, a module or a change group, with qualified type names), `LinkArea`, `CrossLink` (`{href?, go()}`) and `LinkTo`, the function the shell hands each mode; `CrossAnchor` draws a `CrossLink` as an anchor where there is an `href` and as a button where only `go` exists. Both modes import them from the kit, so neither imports the other's, and the shell alone converts a target to either mode's address grammar (SD-013 Rule 7).
7. **One invalidation scheme.** After an apply, either mode's `onApplied` calls `invalidateAfterApply` (`kit/invalidate.ts`), which makes the reads of both modes and every search stale under the shell's shared `QueryClient`. The form model still reads and writes no cache.

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| Explore imports the console's action code | No new layer | Couples the modes to the console's styling, route, meta read and graph code; the browser stops being embeddable alone | Rejected |
| Rebuild the forms in `browser/` | Independent | Two implementations of coding, validation, idempotency and conflicts; every fix twice | Rejected |
| A separate npm package for the kit | Hard boundary | A second release artifact (ADR-027) for two consumers in one repository | Rejected |

## Consequences

| Type | Impact |
|------|--------|
| Positive | One form model and codec; the rule that separates the modes and the rule that keeps writes in one place are tests. |
| Negative | A third place a boundary must be kept (the allow-list); the console's hook is an adapter. |
| Neutral | The npm exports are unchanged; `ActionForm`'s props and exports are unchanged. |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| The allow-list grows to admit a surface's code | M | M | The allow-list is one constant in `boundaries.test.ts`; a change to it changes this record |
| The model's returned shape leaks a surface's needs | L | M | The injected interface is the only input; a surface adapts the output |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| `boundaries.test.ts` fails a kit import outside the allow-list, a `validate`, `invoke` or `batch` call outside the kit's model and core, and browser storage in `browser/` or `kit/`; `kit-form.test.tsx` covers the model with a fake client | A third consumer of the kit; a need for a kit import outside the allow-list |

## Concern Impact

- **Concerns used**: `frontend-framework` (React with TypeScript in `ui/`), `admin-console`.
- **Departures**: none.
