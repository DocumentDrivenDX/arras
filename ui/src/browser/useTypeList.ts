// SPDX-License-Identifier: MIT OR Apache-2.0
// A type's entities in key order, in pages of at most 50, through the existing list read (US-066-AC2):
// the first page starts after the key the list's address names (`afterKey`, none at the start) and the
// next page is the entities after the last key shown.
import { useInfiniteQuery } from "@tanstack/react-query";
import { useClient } from "../api/context";
import { ApiError } from "../api/errors";
import { listField, nextAfterKey } from "../api/gql";
import { badgeField } from "../api/search";
import { placeholders } from "../lib/template";
import { revisionKey, type TypeEntry } from "./meta";

export const PAGE = 50;

/** The properties a row reads: the title's, the summary's and the badge's. */
function rowProps(entry: TypeEntry): string[] {
  const known = new Set(entry.type.properties.map((p) => p.name));
  const wanted = [
    ...placeholders(entry.view.title),
    ...placeholders(entry.view.summary),
    ...(badgeField(entry) ? [badgeField(entry)?.property ?? ""] : []),
  ];
  return [...new Set(wanted)].filter((n) => known.has(n));
}

export interface ListPage {
  items: Record<string, unknown>[];
  /** The limit cut the page: more follow its last key. */
  truncated: boolean;
}

/** The list read from after `start` (the beginning when none); each start is its own read. */
export function useTypeList(entry: TypeEntry, start: string | undefined) {
  const client = useClient();
  const field = listField(entry.type.name);
  const query = `query($limit: Int, $afterKey: String) { ${field}(limit: $limit, afterKey: $afterKey) { items { key ${rowProps(entry).join(" ")} } truncated } }`;
  return useInfiniteQuery({
    queryKey: [
      "gb",
      "list",
      entry.module.name,
      revisionKey(entry.module),
      entry.type.name,
      start ?? null,
    ],
    initialPageParam: start ?? (null as string | null),
    retry: false,
    queryFn: async ({ pageParam }): Promise<ListPage> => {
      const r = await client.moduleQuery<Record<string, ListPage | null>>(
        entry.module.name,
        query,
        { limit: PAGE, afterKey: pageParam },
      );
      const page = r.data?.[field];
      if (page) return page;
      const e = r.errors[0];
      throw new ApiError(200, {
        message: e?.message ?? "no data",
        code: e?.code,
        backend: e?.backend,
      });
    },
    getNextPageParam: (last) => nextAfterKey(last),
  });
}
