// SPDX-License-Identifier: MIT OR Apache-2.0
// The search read of the static read-only profile (CONTRACT-010 C, CONTRACT-012): `_search` over the
// module's types, as `arras/search.py` composes it over a backend that declares `substring`. Per type
// it takes the first 50 entities, in key order, in which every word occurs (the backend's match), then
// re-checks and ranks them with the library's fold, and names every type it did not search and why.
import {
  GraphQLBoolean,
  type GraphQLFieldConfigMap,
  GraphQLInt,
  type GraphQLInterfaceType,
  GraphQLList,
  GraphQLObjectType,
  GraphQLString,
} from "graphql";
import {
  coded,
  type Fresh,
  FreshnessType,
  freshness,
  listOf,
  type Node,
  nn,
  type RequestContext,
  S,
} from "./common";
import type { EntityType } from "./model";
import type { Entity } from "./store";
import {
  BadText,
  byCodePoint,
  CANDIDATES,
  checkText,
  excerpt,
  MAX_LIMIT,
  MAX_TYPES,
  rank,
  type Segment,
} from "./text";
import { isSearchableType, placeholders, type ResolvedView, titleOf } from "./view";

interface Hit {
  type: string;
  key: string;
  score: number;
  label: string;
  excerpt: Segment[] | null;
  matched: string[];
  node: Node;
}
interface NotSearched {
  type: string;
  reason: string;
  backend: string | null;
}
interface Count {
  type: string;
  count: number;
  atLeast: boolean;
}
export interface SearchResult {
  text: string;
  hits: Hit[];
  counts: Count[];
  notSearched: NotSearched[];
  truncated: boolean;
  freshness: Fresh[];
}

const SegmentType = new GraphQLObjectType({
  name: "_Segment",
  fields: {
    text: { type: S, resolve: (s: Segment) => s.text },
    mark: { type: nn(GraphQLBoolean), resolve: (s: Segment) => s.mark },
  },
});
const CountType = new GraphQLObjectType({
  name: "_TypeCount",
  fields: {
    type: { type: S, resolve: (c: Count) => c.type },
    count: { type: nn(GraphQLInt), resolve: (c: Count) => c.count },
    atLeast: { type: nn(GraphQLBoolean), resolve: (c: Count) => c.atLeast },
  },
});
const NotSearchedType = new GraphQLObjectType({
  name: "_NotSearched",
  fields: {
    type: { type: S, resolve: (n: NotSearched) => n.type },
    reason: { type: S, resolve: (n: NotSearched) => n.reason },
    backend: { type: GraphQLString, resolve: (n: NotSearched) => n.backend },
  },
});

/** `_SearchPage`, `_SearchHit` and the types they use; a hit's `entity` is the module's own. */
export function searchPageFields(entity: GraphQLInterfaceType) {
  const hit = new GraphQLObjectType({
    name: "_SearchHit",
    fields: (): GraphQLFieldConfigMap<Hit, RequestContext> => ({
      type: { type: S, resolve: (h) => h.type },
      key: { type: S, resolve: (h) => h.key },
      score: { type: nn(GraphQLInt), resolve: (h) => h.score },
      label: { type: S, resolve: (h) => h.label },
      excerpt: {
        type: new GraphQLList(nn(SegmentType)),
        resolve: (h) => (h.excerpt?.length ? h.excerpt : null),
      },
      matched: { type: listOf(GraphQLString), resolve: (h) => h.matched },
      entity: { type: nn(entity), resolve: (h) => h.node },
    }),
  });
  const page = new GraphQLObjectType({
    name: "_SearchPage",
    fields: (): GraphQLFieldConfigMap<SearchResult, RequestContext> => ({
      text: { type: S, resolve: (p) => p.text },
      hits: { type: listOf(hit), resolve: (p) => p.hits },
      counts: { type: listOf(CountType), resolve: (p) => p.counts },
      notSearched: { type: listOf(NotSearchedType), resolve: (p) => p.notSearched },
      truncated: { type: nn(GraphQLBoolean), resolve: (p) => p.truncated },
      freshness: { type: listOf(FreshnessType), resolve: (p) => p.freshness },
    }),
  });
  return { page, types: [page, hit, SegmentType, CountType, NotSearchedType] };
}

const bad = (message: string) => coded("BAD_QUERY", message);

function chosenTypes(ctx: RequestContext, types: string[] | null | undefined): string[] {
  const local = ctx.store.module.entityTypes.map((t) => t.local);
  if (types === null || types === undefined)
    return local.filter((n) => (ctx.view.types.get(n)?.search.length ?? 0) > 0);
  const unknown = [...new Set(types)].filter((n) => !local.includes(n));
  if (unknown.length) throw bad(`${unknown.join(", ")} is not a type of ${ctx.store.module.name}`);
  return local.filter((n) => types.includes(n));
}

/** The backend's text match: every word occurs, folded with `toLowerCase`, in one of the properties. */
const matches = (e: Entity, words: string[], props: string[]): boolean => {
  const values = props
    .map((p) => e.props[p])
    .filter((v): v is string => typeof v === "string")
    .map((v) => v.toLowerCase());
  return words.every((w) => values.some((v) => v.includes(w)));
};

function titledProps(view: ResolvedView): Set<string> {
  return new Set(placeholders(view.title));
}

function excerptOf(
  row: Record<string, unknown>,
  matched: string[],
  titled: Set<string>,
  words: string[],
): Segment[] {
  for (const name of matched) {
    const v = row[name];
    if (!titled.has(name) && typeof v === "string") return excerpt(v, words);
  }
  return [];
}

function searchType(
  ctx: RequestContext,
  t: EntityType,
  words: string[],
  consistency: string,
  acc: { hits: Hit[]; counts: Count[]; skipped: NotSearched[]; truncated: boolean },
): void {
  const view = ctx.view.types.get(t.local) as ResolvedView;
  const searchable = t.properties.filter(isSearchableType).map((p) => p.name);
  if (view.search.length === 0)
    return void acc.skipped.push({
      type: t.local,
      reason: "no_searchable_property",
      backend: null,
    });
  const props = view.search.filter((p) => searchable.includes(p));
  if (props.length === 0)
    return void acc.skipped.push({
      type: t.local,
      reason: "no_searchable_property",
      backend: "static",
    });
  if (!ctx.tryReserve(CANDIDATES))
    return void acc.skipped.push({ type: t.local, reason: "over_budget", backend: null });
  const all = (ctx.store.entities.get(t.local) ?? []).filter((e) => matches(e, words, props));
  const rows = all.slice(0, CANDIDATES);
  ctx.settle(CANDIDATES, rows.length);
  const fresh = freshness(ctx.store, consistency);
  const titled = titledProps(view);
  const found: Hit[] = [];
  for (const e of rows) {
    const ranked = rank(words, props, e.props);
    if (!ranked) continue;
    const seg = excerptOf(e.props, ranked.matched, titled, words);
    found.push({
      type: t.local,
      key: e.key,
      score: ranked.score,
      label: titleOf(view, e.props, e.key),
      excerpt: seg.length ? seg : null,
      matched: ranked.matched,
      node: { entity: e, fresh },
    });
  }
  const capped = rows.length >= CANDIDATES || all.length > CANDIDATES;
  acc.truncated = acc.truncated || capped;
  acc.counts.push({ type: t.local, count: found.length, atLeast: capped });
  acc.hits.push(...found);
}

interface SearchArgs {
  text: string;
  types?: string[] | null;
  limit?: number | null;
  consistency: string;
}

/** `_search`: the page, or the error the library would raise when no type could be searched. */
export function runSearch(ctx: RequestContext, args: SearchArgs): SearchResult {
  const limit = args.limit ?? 20;
  if (!(Number.isInteger(limit) && limit >= 1 && limit <= MAX_LIMIT))
    throw coded("LIMIT_EXCEEDED", `limit is 1 to ${MAX_LIMIT}`);
  let checked: { folded: string; words: string[] };
  try {
    checked = checkText(args.text);
  } catch (e) {
    if (e instanceof BadText) throw bad(e.message);
    throw e;
  }
  const names = chosenTypes(ctx, args.types);
  const acc = {
    hits: [] as Hit[],
    counts: [] as Count[],
    skipped: [] as NotSearched[],
    truncated: false,
  };
  names.forEach((name, i) => {
    const t = ctx.store.module.entityTypes.find((x) => x.local === name) as EntityType;
    if (i >= MAX_TYPES) acc.skipped.push({ type: name, reason: "over_budget", backend: null });
    else searchType(ctx, t, checked.words, args.consistency, acc);
  });
  if (acc.counts.length === 0 && acc.skipped.length > 0) failNothingSearched(acc.skipped);
  const order = new Map(ctx.store.module.entityTypes.map((t, i) => [t.local, i]));
  const ranked = [...acc.hits].sort(
    (a, b) =>
      b.score - a.score ||
      (order.get(a.type) ?? 0) - (order.get(b.type) ?? 0) ||
      byCodePoint(a.key, b.key),
  );
  return {
    text: checked.folded,
    hits: ranked.slice(0, limit),
    counts: acc.counts,
    notSearched: acc.skipped,
    truncated: acc.truncated || ranked.length > limit,
    freshness: acc.counts.length ? [freshness(ctx.store, args.consistency)] : [],
  };
}

function failNothingSearched(skipped: NotSearched[]): never {
  if (skipped.some((n) => n.reason === "over_budget"))
    throw coded("COST_EXCEEDED", "a request resolves at most 1000 entities");
  throw coded("UNSUPPORTED", "unsupported: text search", {
    supported: ["a type is searched where its backend declares search"],
  });
}
