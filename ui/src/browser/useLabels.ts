// SPDX-License-Identifier: MIT OR Apache-2.0
// Labels for a node page's neighbours, read in chunks by the planner (planner.ts). Each chunk is
// its own query keyed by its targets, so showing more labels reads only the new ones and a retry
// reads one chunk again.
import { type UseQueryResult, useQueries } from "@tanstack/react-query";
import { useMemo } from "react";
import { useClient } from "../api/context";
import { ApiError } from "../api/errors";
import type { MetaData } from "../api/types";
import { titleOf } from "../lib/template";
import { findQualified, revisionKey } from "./meta";
import {
  allAs,
  type LabelAnswer,
  type LabelPlan,
  type LabelState,
  planLabels,
  readLabels,
  type Target,
} from "./planner";

export interface Labels {
  labels: Record<string, LabelState>;
  /** Read the chunk holding this neighbour again. */
  retry: (id: string) => void;
}

type Result = UseQueryResult<Record<string, LabelState>, Error>;

function combine(plans: LabelPlan[]) {
  return (results: Result[]): Labels => {
    const labels: Record<string, LabelState> = {};
    const refetch: Record<string, () => void> = {};
    results.forEach((r, i) => {
      const plan = plans[i];
      if (!plan) return;
      const state: Record<string, LabelState> =
        r.data ?? (r.error ? allAs(plan, { state: "retry" }) : {});
      Object.assign(labels, state);
      for (const t of plan.targets) refetch[t.id] = () => void r.refetch();
    });
    return { labels, retry: (id) => refetch[id]?.() };
  };
}

/** A request the server refuses outright: a module the viewer cannot read is "not available". */
function failed(e: unknown, plan: LabelPlan): Record<string, LabelState> {
  const gone = e instanceof ApiError && (e.kind === "not_found" || e.kind === "no_access");
  if (!gone) throw e;
  return allAs(plan, { state: "na" });
}

/** A chunk with a neighbour to retry is stale at once, so reading the page again reads it again. */
const staleTime = (q: { state: { data?: Record<string, LabelState> } }) =>
  Object.values(q.state.data ?? {}).some((s) => s.state === "retry") ? 0 : 30_000;

export function useLabels(meta: MetaData | undefined, targets: Target[]): Labels {
  const client = useClient();
  const plans = useMemo(() => planLabels(targets, (q) => findQualified(meta, q)), [targets, meta]);
  // Targets with no plan (a type the viewer cannot describe) are not available.
  const planned = useMemo(() => new Set(plans.flatMap((p) => p.targets.map((t) => t.id))), [plans]);
  const revisions = meta?.modules.map(revisionKey).join("|") ?? "";
  const { labels, retry } = useQueries({
    queries: plans.map((plan) => ({
      queryKey: ["gb", "labels", plan.module, revisions, plan.targets.map((t) => t.id).join(" ")],
      staleTime,
      retry: false,
      queryFn: async (): Promise<Record<string, LabelState>> => {
        try {
          const r = await client.moduleQuery<NonNullable<LabelAnswer["data"]>>(
            plan.module,
            plan.query,
            plan.variables,
          );
          const answer: LabelAnswer = { data: r.data, errors: r.errors };
          return readLabels(plan, answer, (t, row) => {
            const entry = findQualified(meta, t.type);
            return entry ? titleOf(entry.view.title, row, t.key) : t.key;
          });
        } catch (e) {
          return failed(e, plan);
        }
      },
    })),
    combine: combine(plans),
  });
  return useMemo(() => {
    const all = { ...labels };
    for (const t of targets) if (!planned.has(t.id)) all[t.id] = { state: "na" };
    return { labels: all, retry };
  }, [labels, retry, targets, planned]);
}
