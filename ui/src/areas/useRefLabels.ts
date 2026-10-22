// SPDX-License-Identifier: MIT OR Apache-2.0
import { useQueries } from "@tanstack/react-query";
import { useClient } from "../api/context";
import type { ModuleInfo, Ref } from "../api/types";
import { planRefLabels, readRefLabels } from "../lib/relLabels";

/**
 * Readable names for relationship targets, by `type:key`. Each bounded request is its own query, so
 * a request that fails or has not answered leaves its chips showing keys, never an error.
 */
export function useRefLabels(m: ModuleInfo | undefined, refs: Ref[]): Record<string, string> {
  const client = useClient();
  const plans = m ? planRefLabels(m, refs) : [];
  const revision = JSON.stringify(m?.revision);
  return useQueries({
    queries: plans.map((plan) => ({
      // under "entity", so an applied action reads the names again
      queryKey: ["entity", "labels", m?.name, revision, plan.query, JSON.stringify(plan.variables)],
      staleTime: 30_000,
      retry: false,
      queryFn: async () => {
        const r = await client.moduleQuery<Record<string, Record<string, unknown> | null>>(
          m?.name ?? "",
          plan.query,
          plan.variables,
        );
        return readRefLabels(plan, r.data);
      },
    })),
    combine: (results) => Object.assign({}, ...results.map((r) => r.data ?? {})),
  });
}
