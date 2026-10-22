// SPDX-License-Identifier: MIT OR Apache-2.0
import { type UseQueryResult, useQueries } from "@tanstack/react-query";
import { useMemo } from "react";
import { useClient } from "../api/context";
import { ApiError } from "../api/errors";
import { listField } from "../api/gql";
import type { ModuleInfo } from "../api/types";
import {
  assembleGraph,
  buildGraphQuery,
  GRAPH_CAP,
  GRAPH_PAGE,
  type ModuleGraph,
  type TypeRead,
} from "../lib/graph";

const NO_TYPES: ModuleInfo["entityTypes"] = [];

interface TypeResult {
  read: TypeRead | undefined;
  error: Error | null;
  pending: boolean;
}

/** Folds the per-type results into values that only change when a result does. */
function combineReads(results: UseQueryResult<TypeRead, Error>[]) {
  return {
    reads: results.map((r): TypeResult => ({ read: r.data, error: r.error, pending: r.isPending })),
    refetch: () => results.forEach((r) => void r.refetch()),
  };
}

/** One list read per type (limit 100), folded into the module's graph. Cached as ["graph", ...]. */
export function useModuleGraph(
  m: ModuleInfo | undefined,
  consistency: "LATEST" | "BULK" = "LATEST",
  cap = GRAPH_CAP,
) {
  const client = useClient();
  const types = m?.entityTypes ?? NO_TYPES;
  const { reads, refetch } = useQueries({
    queries: types.map((t) => ({
      queryKey: ["graph", m?.name, t.name, consistency],
      enabled: !!m,
      retry: false,
      queryFn: async (): Promise<TypeRead> => {
        if (!m) throw new Error("module not loaded");
        const r = await client.moduleQuery<
          Record<string, (TypeRead & { truncated: boolean }) | null>
        >(m.name, buildGraphQuery(m, t), {
          limit: GRAPH_PAGE,
          consistency,
        });
        const data = r.data?.[listField(t.name)] ?? null;
        if (!data) {
          const e = r.errors[0];
          throw new ApiError(200, { message: e?.message ?? "no data", code: e?.code });
        }
        return data;
      },
    })),
    combine: combineReads,
  });
  const graph: ModuleGraph | null = useMemo(
    () =>
      m
        ? assembleGraph(
            m,
            types.map((t, i) => ({
              type: t,
              read: reads[i]?.read,
              error: reads[i]?.error,
              pending: reads[i]?.pending,
            })),
            cap,
          )
        : null,
    [m, types, reads, cap],
  );
  return { graph, refetch };
}
