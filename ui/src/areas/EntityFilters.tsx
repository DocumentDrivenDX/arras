// SPDX-License-Identifier: MIT OR Apache-2.0

import type { Column } from "../api/gql";
import { TextField } from "../ds";

/** A filter the backend declares (CONTRACT-001): equality on a column, or on a relationship's target key. */
export interface FilterEntry {
  /** The name sent in the read's `filter` argument. */
  name: string;
  label: string;
  rel: boolean;
}

/**
 * The declared filters the table has no header cell for: those of hidden columns, and any declared name no column
 * stands for. Every filter the backend lists is reachable; none is invented.
 */
export function hiddenFilters(
  allCols: Column[],
  visibleIds: string[],
  declared: { columns: string[]; relationships: string[] },
  filterName: (c: Column) => string | null,
): FilterEntry[] {
  const out: FilterEntry[] = [];
  const seen = new Set<string>();
  for (const c of allCols) {
    const name = filterName(c);
    if (!name || seen.has(name)) continue;
    seen.add(name);
    if (!visibleIds.includes(c.id)) out.push({ name, label: c.label, rel: c.kind === "rel" });
  }
  for (const name of declared.columns) {
    if (!seen.has(name)) out.push({ name, label: name, rel: false });
    seen.add(name);
  }
  for (const name of declared.relationships) {
    if (!seen.has(name)) out.push({ name, label: name, rel: true });
    seen.add(name);
  }
  return out;
}

/** Filters of columns that are not shown: equality on a whole value, applied like the header filters. */
export function HiddenFilters({
  entries,
  draft,
  onDraft,
  onApply,
}: {
  entries: FilterEntry[];
  draft: Record<string, string>;
  onDraft: (name: string, value: string) => void;
  onApply: () => void;
}) {
  if (entries.length === 0) return null;
  const active = entries.filter((e) => (draft[e.name] ?? "").trim() !== "").length;
  return (
    <details className="border-b border-line bg-surface px-3 py-1" data-testid="hidden-filters">
      <summary className="cursor-pointer text-[12px] text-muted">
        More filters ({entries.length}
        {active > 0 ? `, ${active} active` : ""}): columns that are not shown
      </summary>
      <div className="grid grid-cols-1 gap-2 py-2 sm:grid-cols-2 lg:grid-cols-3">
        {entries.map((e) => (
          <TextField
            key={e.name}
            label={`Filter ${e.label}`}
            placeholder={e.rel ? "= key" : "="}
            value={draft[e.name] ?? ""}
            onChange={(ev) => onDraft(e.name, ev.target.value)}
            onBlur={onApply}
            onKeyDown={(ev) => {
              if (ev.key === "Enter") onApply();
            }}
          />
        ))}
      </div>
    </details>
  );
}
