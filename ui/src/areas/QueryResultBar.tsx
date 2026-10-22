// SPDX-License-Identifier: MIT OR Apache-2.0
import type { Freshness, ModuleInfo, QueryResult } from "../api/types";
import { Chip } from "../components/ui";
import { FreshnessBar } from "./EntityFreshness";

const rowsText = (n: number) => `${n} ${n === 1 ? "row" : "rows"}`;

/** What a screen reader hears for the run in progress or the answer that arrived. */
export function liveText(running: boolean, result: QueryResult | null): string {
  if (running) return "Running…";
  if (!result) return "";
  return `${rowsText(result.rows.length)}${result.truncated ? ", truncated" : ""}`;
}

/** Which module's backends answered, so the freshness shows "replica" or "record" for the right module. */
export function ownerOf(
  modules: ModuleInfo[],
  f: Freshness | null,
  fallback?: ModuleInfo,
): ModuleInfo | undefined {
  if (!f) return fallback;
  return (
    modules.find((m) => m.replicas.includes(f.backend)) ??
    modules.find((m) => m.record === f.backend) ??
    fallback
  );
}

const revisionText = (r: QueryResult["revision"]) =>
  Object.entries(r)
    .map(([b, n]) => `${b} ${n ?? "none"}`)
    .join(", ") || "none";

/** The row count, freshness (the existing component), revision and `truncated` of an answer. */
export function QueryInfoBar({
  result,
  owner,
}: {
  result: QueryResult;
  owner: ModuleInfo | undefined;
}) {
  const f = result.freshness;
  return (
    <div
      className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line bg-surface px-3 py-1"
      data-testid="query-info"
    >
      <span className="font-medium" data-testid="query-count-rows">
        {rowsText(result.rows.length)}
      </span>
      {f && (
        <FreshnessBar
          freshness={{ ...f, consistency: f.consistency.toUpperCase() }}
          module={owner}
        />
      )}
      <Chip title="The revision of each backend the answer was computed at">
        revision {revisionText(result.revision)}
      </Chip>
      {result.truncated && (
        <Chip tone="warn" title="The limit cut the rows: continue with a keyset predicate">
          truncated
        </Chip>
      )}
    </div>
  );
}
