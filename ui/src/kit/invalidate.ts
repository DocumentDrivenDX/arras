// SPDX-License-Identifier: MIT OR Apache-2.0
// One cache-invalidation scheme under the shell's shared QueryClient (SD-013 D6): after an action is
// applied, in either mode, every family of reads that can show the change is stale: Explore's `gb`
// reads (pages, labels, history, search) and the console's list, graph, entity, status and audit
// reads. The form model itself knows no cache; a surface calls this from its `onApplied`. The
// registry (the `meta` key) is not invalidated: a revision conflict reloads it through
// `reloadModule`.
import type { QueryClient } from "@tanstack/react-query";
import { invalidateSearch } from "../api/search";

/** The query-key families an applied action makes stale. */
export const APPLY_KEYS = ["gb", "list", "graph", "entity", "status", "audit"] as const;

/** Mark every read the change can show stale; the promise settles when the active ones are read again. */
export function invalidateAfterApply(qc: QueryClient): Promise<void> {
  return Promise.all([
    ...APPLY_KEYS.map((queryKey) => qc.invalidateQueries({ queryKey: [queryKey] })),
    invalidateSearch(qc),
  ]).then(() => undefined);
}
