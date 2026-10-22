// SPDX-License-Identifier: MIT OR Apache-2.0
// The one search read (CONTRACT-010 C) for the browser's search box, the link picker and the
// console's palette: a GraphQL `_search` request to the module's endpoint, the text in the POST body
// only. The text is checked here the way the server checks it, an answer is keyed by module, revision,
// text, types and limit (so the answer to an earlier text is never shown for a later one, and the
// previous answer stays only as a marked placeholder while the next loads), and every key begins
// `["gb", "search"]` so an applied action reaches it (`invalidateSearch`). No text, word or server
// message is put in an error or a log.
import {
  keepPreviousData,
  type QueryClient,
  type UseQueryResult,
  useQuery,
} from "@tanstack/react-query";
import { useDebounced } from "../lib/useDebounced";
import type { ArrasClient } from "./client";
import { useClient } from "./context";
import { ApiError } from "./errors";
import { shortName } from "./gql";
import type { ModuleInfo, SearchHit, SearchPage, TypeView } from "./types";

export const MIN_CHARS = 2;
export const MAX_CHARS = 200;
export const MAX_WORDS = 6;
/** Hits the browser asks for; the palette asks for `PALETTE_LIMIT`. */
export const SEARCH_LIMIT = 50;
export const PALETTE_LIMIT = 8;
export const SEARCH_DEBOUNCE_MS = 250;

export type TextCheck =
  | { ok: true; text: string }
  | { ok: false; reason: "empty" | "short" | "long" | "words" };

export const normalise = (raw: string) => raw.trim().replace(/\s+/g, " ");

/** The text rules of CONTRACT-010 C; the server checks again (`BAD_QUERY`). */
export function checkText(raw: string): TextCheck {
  const text = normalise(raw);
  const chars = Array.from(text).length;
  if (text === "") return { ok: false, reason: "empty" };
  if (chars < MIN_CHARS) return { ok: false, reason: "short" };
  if (chars > MAX_CHARS) return { ok: false, reason: "long" };
  if (text.split(" ").length > MAX_WORDS) return { ok: false, reason: "words" };
  return { ok: true, text };
}

/** A hit as every surface reads it; the palette uses the fields it shows. */
export type PaletteHit = SearchHit;

/** The first `badge` field of a type: the value a hit shows on the right. */
export const badgeField = (entry: { view: TypeView }) =>
  entry.view.fields.find((f) => f.format === "badge");

/** The search selection: every field a surface shows, with each type's badge as an optional fragment. */
export function searchQuery(module: ModuleInfo): string {
  const frags = module.entityTypes
    .flatMap((t) => {
      const b = t.view && badgeField({ view: t.view });
      return b ? [`... on ${shortName(t.name)} { ${b.property} }`] : [];
    })
    .join(" ");
  return `query($text: String!, $types: [String!], $limit: Int) { _search(text: $text, types: $types, limit: $limit) { text hits { type key score label excerpt { text mark } matched entity { key type ${frags} } } counts { type count atLeast } notSearched { type reason backend } truncated freshness { backend asOf at consistency } } }`;
}

/** One search of the module; a failure is an `ApiError` carrying the server's code and nothing else. */
export async function searchEntities(
  client: Pick<ArrasClient, "moduleQuery">,
  module: ModuleInfo,
  text: string,
  types: string[] | null,
  limit: number = SEARCH_LIMIT,
): Promise<SearchPage> {
  const r = await client.moduleQuery<{ _search: SearchPage | null }>(
    module.name,
    searchQuery(module),
    { text, types: types?.length ? types : null, limit },
  );
  const page = r.data?._search;
  if (page) return page;
  const e = r.errors[0];
  throw new ApiError(200, {
    message: "search was not answered",
    code: e?.code,
    backend: e?.backend,
  });
}

/** The module's revision as a cache key part: a registry that moved is another search. */
const revisionKey = (m: ModuleInfo) => JSON.stringify(Object.entries(m.revision).sort());

/** The one cache-key family: a different text, type set or limit is a different entry. */
export const searchKey = (module: ModuleInfo, text: string, types: string[], limit: number) =>
  ["gb", "search", module.name, revisionKey(module), text, [...types].sort(), limit] as const;

/** `value` once it has held still for the search pause. */
export const useSearchPause = <T>(value: T): T => useDebounced(value, SEARCH_DEBOUNCE_MS);

/** After an applied action every search is stale; both modes call this. */
export const invalidateSearch = (qc: QueryClient) =>
  qc.invalidateQueries({ queryKey: ["gb", "search"] });

/**
 * The search read for `text` as given (the caller has checked and, where it wants a pause, debounced
 * it). While the next text loads, the previous answer is kept and `isPlaceholderData` is true.
 */
export function useSearch(
  module: ModuleInfo,
  text: string,
  types: string[],
  enabled: boolean,
  limit: number = SEARCH_LIMIT,
): UseQueryResult<SearchPage, ApiError> {
  const client = useClient();
  return useQuery<SearchPage, ApiError>({
    queryKey: searchKey(module, text, types, limit),
    enabled,
    retry: false,
    staleTime: 10_000,
    placeholderData: keepPreviousData,
    queryFn: () => searchEntities(client, module, text, types, limit),
  });
}

export interface EntitySearch {
  /** The check of the text as typed (not as last settled). */
  check: TextCheck;
  /** The answer in `data` is for the text as typed; false while a newer text is waited on or asked. */
  current: boolean;
  data: SearchPage | undefined;
  error: ApiError | null;
}

/** The debounced search read; nothing is asked unless `enabled` and the text can be searched. */
export function useEntitySearch(
  module: ModuleInfo,
  raw: string,
  enabled: boolean,
  types: string[] = [],
  limit: number = PALETTE_LIMIT,
): EntitySearch {
  const settled = checkText(useSearchPause(raw));
  const check = checkText(raw);
  const text = settled.ok ? settled.text : "";
  const q = useSearch(module, text, types, enabled && settled.ok, limit);
  const asked = enabled && settled.ok && check.ok;
  return {
    check,
    current: asked && check.ok && check.text === text && !q.isPlaceholderData && !q.isFetching,
    data: asked ? q.data : undefined,
    error: asked ? q.error : null,
  };
}
