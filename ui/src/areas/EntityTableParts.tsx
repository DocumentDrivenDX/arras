// SPDX-License-Identifier: MIT OR Apache-2.0

import { type Column, MAX_PAGE, MAX_SELECTIONS } from "../api/gql";
import { Button, Chip, Notice } from "../components/ui";
import { Button as WidgetButton } from "../ds";
import { keyed } from "../lib/format";
import { useHideKeyHints } from "../lib/useMediaQuery";
import type { Sort } from "./pageSort";

export interface PageData {
  truncated: boolean;
}

export interface QueryError {
  code?: string | null;
  message: string;
}

export function ConsistencyToggle({
  consistency,
  onChange,
}: {
  consistency: "LATEST" | "BULK";
  onChange: (c: "LATEST" | "BULK") => void;
}) {
  return (
    <fieldset aria-label="Consistency" className="m-0 flex min-w-0 border-0 p-0">
      {(["LATEST", "BULK"] as const).map((c) => (
        <button
          key={c}
          type="button"
          aria-pressed={consistency === c}
          onClick={() => onChange(c)}
          title={c === "LATEST" ? "Read the record store" : "Read the replica (may lag)"}
          className={`border border-strong px-2 py-0.5 text-[12px] first:rounded-l last:rounded-r ${consistency === c ? "bg-accent text-accentfg" : "bg-surface text-fg hover:bg-surface2"}`}
        >
          {c}
        </button>
      ))}
    </fieldset>
  );
}

export function ColumnPicker({
  allCols,
  visibleIds,
  visibleCount,
  cost,
  onToggle,
}: {
  allCols: Column[];
  visibleIds: string[];
  visibleCount: number;
  cost: number;
  onToggle: (c: Column) => void;
}) {
  return (
    <details className="relative">
      <summary className="cursor-pointer rounded border border-strong bg-surface px-2 py-0.5 text-[12px]">
        Columns ({visibleCount})
      </summary>
      <div className="absolute z-20 mt-1 max-h-72 w-56 overflow-auto rounded border border-strong bg-surface p-2 shadow-lg">
        {allCols.map((c) => {
          const on = visibleIds.includes(c.id);
          const blocked = !on && cost + c.cost > MAX_SELECTIONS;
          return (
            <label
              key={c.id}
              className={`flex items-center gap-1.5 py-0.5 ${blocked ? "opacity-50" : ""}`}
              title={blocked ? "A request may select at most 50 fields" : undefined}
            >
              <input
                type="checkbox"
                checked={on}
                disabled={blocked || c.kind === "key"}
                onChange={() => onToggle(c)}
              />
              <span className={c.kind === "key" ? "font-semibold" : ""}>{c.label}</span>
              <span className="ml-auto text-[10px] text-muted">{c.kind}</span>
            </label>
          );
        })}
        <div className="mt-1 border-t border-line pt-1 text-[11px] text-muted">
          {cost} of {MAX_SELECTIONS} field selections
        </div>
      </div>
    </details>
  );
}

export function PageSizeSelect({
  limit,
  onChange,
}: {
  limit: number;
  onChange: (n: number) => void;
}) {
  return (
    <label className="flex items-center gap-1 text-[12px] text-muted">
      Page size
      <select
        className="rounded border border-strong bg-surface px-1 py-0.5 text-fg"
        value={limit}
        onChange={(e) => onChange(Number(e.target.value))}
      >
        {[25, 50, MAX_PAGE].map((n) => (
          <option key={n}>{n}</option>
        ))}
      </select>
    </label>
  );
}

function errorHint(code: string | null | undefined): string {
  if (code === "COST_EXCEEDED" || code === "DEPTH_EXCEEDED")
    return " — hide some columns and retry.";
  if (code === "UNAVAILABLE") return " The table stays usable; try the other consistency or retry.";
  return "";
}

export function QueryErrors({
  errors,
  onRetry,
  fetching,
}: {
  errors: QueryError[];
  onRetry: () => void;
  fetching: boolean;
}) {
  if (errors.length === 0) return null;
  return (
    <div className="space-y-1 px-3 py-1.5">
      {keyed(errors, (e) => `${e.code}:${e.message}`).map(({ key, item: e }) => (
        <Notice key={key} tone="bad" role="alert">
          <strong>{e.code ?? "Error"}</strong>: {e.message}
          {errorHint(e.code)}
        </Notice>
      ))}
      <Button onClick={onRetry} disabled={fetching}>
        Retry
      </Button>
    </div>
  );
}

/** Pages in key order: Next reads the entities after the page's last key; Previous returns to a page read. */
export function Pager({
  page,
  rowCount,
  fetching,
  data,
  hasNext,
  sorted,
  onPrevious,
  onNext,
  onClearSort,
}: {
  page: number;
  rowCount: number;
  fetching: boolean;
  data: PageData | null;
  hasNext: boolean;
  /** The sort of this page, when one is on: its column's label and direction. */
  sorted?: { label: string; dir: Sort["dir"] } | null;
  onPrevious: () => void;
  onNext: () => void;
  onClearSort?: () => void;
}) {
  const partial = hasNext || page > 0 || !!data?.truncated;
  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-line bg-surface px-3 py-1.5">
      <Button disabled={page === 0} onClick={onPrevious}>
        ← Previous
      </Button>
      <span className="text-muted" data-testid="page-info">
        Page {page + 1} · {rowCount} rows{fetching ? " · loading" : ""}
      </span>
      <Button disabled={!hasNext} onClick={onNext}>
        Next →
      </Button>
      {data?.truncated && (
        <Chip
          tone="warn"
          title="The limit cut the page: Next reads the entities after its last key"
        >
          truncated
        </Chip>
      )}
      {sorted && (
        <span className="text-[11px] text-muted" data-testid="sort-note">
          Sorted by {sorted.label} {sorted.dir === "asc" ? "ascending" : "descending"}: this page
          only
          {partial ? "; other pages stay in key order and are not included" : ""}.{" "}
          <button type="button" className="text-accent underline" onClick={onClearSort}>
            Back to key order
          </button>
        </span>
      )}
    </div>
  );
}

export interface ToolbarProps {
  consistency: "LATEST" | "BULK";
  onConsistency: (c: "LATEST" | "BULK") => void;
  allCols: Column[];
  visibleIds: string[];
  visibleCount: number;
  cost: number;
  onToggle: (c: Column) => void;
  limit: number;
  onLimit: (n: number) => void;
  hasFilter: boolean;
  onClearFilter: () => void;
  /** Opens the Query area on this type; the button shows only when given. */
  onQuery?: () => void;
}

export function Toolbar(p: ToolbarProps) {
  const hideHints = useHideKeyHints();
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-line bg-surface px-3 py-1.5">
      <ConsistencyToggle consistency={p.consistency} onChange={p.onConsistency} />
      <ColumnPicker
        allCols={p.allCols}
        visibleIds={p.visibleIds}
        visibleCount={p.visibleCount}
        cost={p.cost}
        onToggle={p.onToggle}
      />
      <PageSizeSelect limit={p.limit} onChange={p.onLimit} />
      {p.hasFilter && <Button onClick={p.onClearFilter}>Clear filter</Button>}
      {p.onQuery && (
        <WidgetButton variant="secondary" size="sm" onClick={p.onQuery}>
          Query this type
        </WidgetButton>
      )}
      {!hideHints && (
        <span className="ml-auto text-[11px] text-muted" data-testid="table-key-hint">
          Keys: <kbd>↑</kbd> <kbd>↓</kbd> move, <kbd>Enter</kbd> opens, <kbd>/</kbd> filters
        </span>
      )}
    </div>
  );
}
