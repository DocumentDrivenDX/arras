// SPDX-License-Identifier: MIT OR Apache-2.0
// What the pickers share (the link dialog's and the reference field's): the entities at the other end
// listed at once, narrowed as the reader types, or searched for when a type has more than the list
// holds; where the list cannot be read, the reader types the key.

import { keepPreviousData, useQueries } from "@tanstack/react-query";
import { useState } from "react";
import { useClient } from "../api/context";
import { shortName } from "../api/gql";
import { checkText, SEARCH_LIMIT, searchEntities, searchKey, useSearchPause } from "../api/search";
import type { ModuleInfo } from "../api/types";
import type { SelectOption } from "../ds";
import { searchServed, type TypeEntry } from "./meta";
import { type LinkOption, type LinkOptions, OPTION_LIMIT, useLinkOptions } from "./useLinkOptions";

export interface Row {
  type: string;
  key: string;
  label: string;
  typeLabel: string;
}

const matches = (o: LinkOption, text: string) => {
  const t = text.trim().toLowerCase();
  return !t || o.label.toLowerCase().includes(t) || o.key.toLowerCase().includes(t);
};

export const idOf = (r: { type: string; key: string }) => `${r.type}:${r.key}`;

/** The end types grouped by their module, each with the short names its search is restricted to. */
function byModule(ends: TypeEntry[]): { module: ModuleInfo; types: string[] }[] {
  const groups = new Map<string, { module: ModuleInfo; types: string[] }>();
  for (const e of ends) {
    const g = groups.get(e.module.name) ?? { module: e.module, types: [] };
    g.types.push(shortName(e.type.name));
    groups.set(e.module.name, g);
  }
  return [...groups.values()];
}

/**
 * The rows to offer: the search's hits for an incomplete list once there is text, else the list narrowed by
 * the text. The search covers every module an end type belongs to, not only the first one's.
 */
function useRows(
  ends: TypeEntry[],
  listed: LinkOptions,
  text: string,
): { rows: Row[]; searching: boolean; pending: boolean } {
  const client = useClient();
  const check = checkText(useSearchPause(text));
  const groups = byModule(ends).filter((g) => searchServed(g.module));
  // A complete list narrows locally; an incomplete one is searched once there is something to search for.
  const searching = listed.truncated && check.ok && groups.length > 0;
  const answers = useQueries({
    queries: groups.map((g) => {
      const q = check.ok ? check.text : "";
      return {
        queryKey: searchKey(g.module, q, g.types, SEARCH_LIMIT),
        enabled: searching,
        retry: false,
        staleTime: 10_000,
        placeholderData: keepPreviousData,
        queryFn: () => searchEntities(client, g.module, q, g.types, SEARCH_LIMIT),
      };
    }),
  });
  const hits = groups
    .flatMap((g, i) =>
      (answers[i]?.data?.hits ?? []).map((h) => ({
        score: h.score,
        row: {
          type: `${g.module.name}.${h.type}`,
          key: h.key,
          label: h.label,
          typeLabel: h.type,
        },
      })),
    )
    .sort((a, b) => b.score - a.score)
    .map((h) => h.row);
  return {
    rows: searching ? hits : listed.options.filter((o) => matches(o, text)),
    searching,
    pending: searching && answers.some((a) => a.isPending),
  };
}

const noteFor = (rows: Row[], pending: boolean, searching: boolean, truncated: boolean) => {
  if (pending) return "Searching…";
  if (rows.length === 0) return "Nothing matches.";
  return truncated && !searching
    ? `Showing the first ${OPTION_LIMIT} of each type. Type to search for others.`
    : undefined;
};

export const optionsOf = (rows: Row[], linked: Set<string>, showType: boolean): SelectOption[] =>
  rows.map((r) => {
    const taken = linked.has(idOf(r));
    const name = showType ? `${r.typeLabel} · ${r.label}` : r.label;
    return { value: idOf(r), label: taken ? `${name} (already linked)` : name, disabled: taken };
  });

/** What the picker shows and what is chosen: the text, the rows it narrows to, the pick, and the notes. */
export function usePick(ends: TypeEntry[]) {
  const [text, setText] = useState("");
  const [picked, setPicked] = useState<Row | null>(null);
  const end = ends[0];
  const listed = useLinkOptions(ends);
  const { rows, searching, pending } = useRows(ends, listed, text);
  // The choices are listed, so the reader can pick without typing; where the list could not be read,
  // the reader types the key and the action says whether it names something.
  const listable = !!end && !(listed.failed && listed.options.length === 0);
  const chosen = listable
    ? picked
    : text.trim()
      ? ({ key: text.trim(), label: text.trim() } as Row)
      : null;
  return {
    text,
    setText,
    picked,
    setPicked,
    rows,
    listable,
    chosen,
    loading: listed.loading && listed.options.length === 0,
    hint: listable ? noteFor(rows, pending, searching, listed.truncated) : undefined,
  };
}
