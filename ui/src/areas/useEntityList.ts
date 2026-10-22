// SPDX-License-Identifier: MIT OR Apache-2.0
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type KeyboardEvent, useEffect, useMemo, useState } from "react";
import { useClient } from "../api/context";
import { buildListQuery, type Column, type filterable, listField } from "../api/gql";
import type { Freshness, ModuleInfo } from "../api/types";
import type { Sort } from "./pageSort";

interface Page {
  items: Record<string, unknown>[];
  truncated: boolean;
  freshness: Freshness | null;
}

/** The sort as the pager names it: the column's label and direction; null when none is on or its column is hidden. */
export function sortSummary(sort: Sort | null, visible: Column[]) {
  const col = sort ? visible.find((c) => c.id === sort.colId) : undefined;
  return sort && col ? { label: col.label, dir: sort.dir } : null;
}

type FilterCaps = ReturnType<typeof filterable>;

/** The name a column's filter is sent under (CONTRACT-001), or null when the backends declare none. */
export function filterNameFor(
  c: Column,
  t: { key: string } | undefined,
  fcap: FilterCaps,
): string | null {
  if (c.kind === "key") return t && fcap.columns.includes(t.key) ? t.key : null;
  if (c.kind === "prop") return fcap.columns.includes(c.field) ? c.field : null;
  if (c.kind === "rel") return fcap.relationships.includes(c.field) ? c.field : null;
  return null;
}

const FOCUS_MOVES: Record<string, (f: number, count: number) => number> = {
  ArrowDown: (f, count) => Math.min(count - 1, f + 1),
  ArrowUp: (f) => Math.max(0, f - 1),
  Home: () => 0,
  End: (_f, count) => Math.max(0, count - 1),
};

/** The row buttons of the table under `root`, in row order. */
function rowStops(root: HTMLElement | null): HTMLElement[] {
  return Array.from(root?.querySelectorAll<HTMLElement>("button[data-row-stop]") ?? []);
}

export function toggledColumns(visibleIds: string[], c: Column): string[] | null {
  const on = visibleIds.includes(c.id);
  if (on && c.kind === "key") return null;
  return on ? visibleIds.filter((x) => x !== c.id) : [...visibleIds, c.id];
}

export function trimmedFilter(draft: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(draft)
      .filter(([, v]) => v.trim() !== "")
      .map(([k, v]) => [k, v.trim()]),
  );
}

interface ListArgs {
  name: string;
  type: string;
  t: { name: string } | undefined;
  m: ModuleInfo | undefined;
  visible: Column[];
  filter: Record<string, string>;
  limit: number;
  afterKey: string | null;
  consistency: "LATEST" | "BULK";
}

export function useListQuery({
  name,
  type,
  t,
  m,
  visible,
  filter,
  limit,
  afterKey,
  consistency,
}: ListArgs) {
  const client = useClient();
  const queryText = useMemo(() => (t ? buildListQuery(t.name, visible) : ""), [t, visible]);
  return useQuery({
    queryKey: ["list", name, type, visible.map((c) => c.id), filter, limit, afterKey, consistency],
    enabled: !!t && !!m,
    retry: false,
    placeholderData: (prev) => prev,
    queryFn: async () => {
      const r = await client.moduleQuery<Record<string, Page | null>>(name, queryText, {
        filter: Object.keys(filter).length ? filter : null,
        limit,
        afterKey,
        consistency,
      });
      const data = r.data?.[listField(type)] ?? null;
      return { data, errors: r.errors };
    },
  });
}

/** The table's row focus: moves with the arrow keys, returns to the first row on a new read. */
export function useRowFocus(
  data: unknown,
  count: number,
  root: React.RefObject<HTMLElement | null>,
  filterInput: React.RefObject<HTMLElement | null>,
  singleKeys: boolean,
) {
  const [focus, setFocus] = useState(0);
  const [focusData, setFocusData] = useState(data);
  if (focusData !== data) {
    setFocusData(data);
    setFocus(0);
  }
  const onRowKey = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (e.key === "/" && singleKeys) {
      e.preventDefault();
      filterInput.current?.focus();
      return;
    }
    const move = FOCUS_MOVES[e.key];
    if (!move) return;
    e.preventDefault();
    const next = move(index, count);
    setFocus(next);
    rowStops(root.current)[next]?.focus();
  };
  const focusRow = () => rowStops(root.current)[focus]?.focus();
  return { focus, setFocus, onRowKey, focusRow };
}

/** Replica lag and position change with each read. */
export function useStatusRefresh(data: unknown) {
  const qc = useQueryClient();
  useEffect(() => {
    if (data) void qc.invalidateQueries({ queryKey: ["status"] });
  }, [data, qc]);
}
