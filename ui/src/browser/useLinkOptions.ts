// SPDX-License-Identifier: MIT OR Apache-2.0
// The choices for the other end of a link: every entity of the types the relationship allows, in key
// order, up to the list read's page (CONTRACT-006: at most 100 a page), so the picker can show them
// at once and narrow them as the reader types. A type with more than a page says so (`truncated`),
// and the picker then searches for what is not listed.
import { useQueries } from "@tanstack/react-query";
import { useClient } from "../api/context";
import { ApiError } from "../api/errors";
import { listField } from "../api/gql";
import { titleOf } from "../lib/template";
import { revisionKey, type TypeEntry } from "./meta";
import { titleSelection } from "./planner";

/** The most entities of one type the picker lists: the list read's own page limit. */
export const OPTION_LIMIT = 100;

export interface LinkOption {
  /** The qualified type (`catalog.UseCase`) and the key. */
  type: string;
  key: string;
  label: string;
  typeLabel: string;
}

interface OptionPage {
  items: Record<string, unknown>[];
  truncated: boolean;
}

export interface LinkOptions {
  options: LinkOption[];
  /** Some type has more entities than were listed. */
  truncated: boolean;
  loading: boolean;
  failed: boolean;
}

export function useLinkOptions(ends: TypeEntry[]): LinkOptions {
  const client = useClient();
  const results = useQueries({
    queries: ends.map((entry) => {
      const field = listField(entry.type.name);
      const props = titleSelection(entry).join(" ");
      const query = `query($limit: Int) { ${field}(limit: $limit) { items { key ${props} } truncated } }`;
      return {
        queryKey: ["gb", "options", entry.module.name, revisionKey(entry.module), entry.type.name],
        retry: false,
        staleTime: 10_000,
        queryFn: async (): Promise<OptionPage> => {
          const r = await client.moduleQuery<Record<string, OptionPage | null>>(
            entry.module.name,
            query,
            { limit: OPTION_LIMIT },
          );
          const page = r.data?.[field];
          if (page) return page;
          throw new ApiError(200, { message: r.errors[0]?.message ?? "no data" });
        },
      };
    }),
  });
  const options = results.flatMap((r, i) => {
    const entry = ends[i];
    return entry
      ? (r.data?.items ?? []).map((item) => ({
          type: entry.type.name,
          key: String(item.key),
          label: titleOf(entry.view.title, item, String(item.key)),
          typeLabel: entry.view.label,
        }))
      : [];
  });
  return {
    options,
    truncated: results.some((r) => r.data?.truncated),
    loading: results.some((r) => r.isPending),
    failed: results.some((r) => r.isError),
  };
}
