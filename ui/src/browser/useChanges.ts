// SPDX-License-Identifier: MIT OR Apache-2.0
// An entity's history: the operate surface's `changes` by qualified type and key (the module is
// inferred), newest first, 20 a page by the contract's cursor. Read only while the panel is open and
// only for an operator; a 403 and a 501 are answers, not failures.
import { useInfiniteQuery } from "@tanstack/react-query";
import { useClient } from "../api/context";
import { ApiError } from "../api/errors";
import type { Change } from "../api/types";

export const HISTORY_PAGE = 20;

export type ChangesState =
  | { status: "loading" }
  | { status: "forbidden" }
  | { status: "none" }
  | { status: "error" }
  | { status: "ready"; changes: Change[]; more: boolean; fetchingMore: boolean };

function stateOf(q: {
  error: unknown;
  data?: { pages: { items: Change[] }[] };
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
}): ChangesState {
  if (q.error) {
    const status = q.error instanceof ApiError ? q.error.status : 0;
    return { status: status === 403 ? "forbidden" : status === 501 ? "none" : "error" };
  }
  if (!q.data) return { status: "loading" };
  return {
    status: "ready",
    changes: q.data.pages.flatMap((p) => p.items),
    more: q.hasNextPage,
    fetchingMore: q.isFetchingNextPage,
  };
}

export function useChanges(type: string, key: string, enabled: boolean) {
  const client = useClient();
  const q = useInfiniteQuery({
    queryKey: ["gb", "changes", type, key],
    enabled,
    retry: false,
    staleTime: 0,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      client.changes({ type, key, limit: HISTORY_PAGE, after: pageParam }),
    getNextPageParam: (last) => last.nextCursor ?? undefined,
  });
  return { state: stateOf(q), more: () => void q.fetchNextPage(), retry: () => void q.refetch() };
}
