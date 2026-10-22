// SPDX-License-Identifier: MIT OR Apache-2.0
// The console's hash route (CONTRACT-010 D): `#/<module>/<area>/...`, or `#/<prefix>/<module>/...`
// when a shell hosts it (operate mode, ADR-025). Every segment and every query value is percent-encoded.
//
//   query                              the area alone
//   model[/<type>][?view=umf]          the model, a type selected in it, or its UMF source
//   entities/<type>[/<key>]            a type's table, and one entity open on it
//     ?f.<col>=<key>&after=<key>&sort=<col>:<asc|desc>     the table's filter, page start and sort
//   `f.<col>` is written only for a key column, whose value is a key; a filter on any other column is
//   never written to the fragment, and the table's writer is responsible for leaving it out.
//   graph/<type>/<key>                 the entity selected in the graph
//   changes[/<type>/<key>]             a module's changes, or that entity's history
//     ?group=<id>&action=<name>&since=<instant>&until=<instant>&view=loads   a change group's receipt, the filters, the import loads
//   actions/<action>[?in.<name>=<key>&...]   an action, its ref inputs prefilled with entity keys
//
// `schema`, `data` and `audit` are aliases accepted for `model`, `entities` and `changes`, and the
// address is always written with the area's own id; likewise `admin` is an alias of the shell's
// `operate` prefix (and `browse` of its `explore`).
// An entity key may appear in the fragment (it is not sent to the server by
// navigation); a person, search text, a query's statement and any input value that is not a key do
// not. A fragment that does not parse as one of these (an unknown area, a stray or empty segment, a
// bad percent-escape) falls back to its module's area, and to the first module when the module itself
// does not parse; a query value that does not fit its field is left out.

export type Area = "model" | "graph" | "entities" | "actions" | "changes" | "query";
// Query is last, so the number keys of the areas before it keep their places whether or not Changes is shown.
export const AREAS: Area[] = ["model", "graph", "entities", "actions", "changes", "query"];

/** Aliases of the area ids, accepted in an address; the address is rewritten to the area's own id. */
export const AREA_ALIASES: Record<string, Area> = {
  schema: "model",
  data: "entities",
  audit: "changes",
};

/** The area an address segment names: a current id, an alias, or none. */
function areaOf(segment: string | undefined): Area | undefined {
  if (!segment) return undefined;
  if (AREAS.includes(segment as Area)) return segment as Area;
  return Object.hasOwn(AREA_ALIASES, segment) ? AREA_ALIASES[segment] : undefined;
}

/** The first path segment a shell gives the console (ADR-025). */
export const OPERATE_PREFIX = "operate";

/** An alias of that first segment (`admin`): accepted, and rewritten to `operate`. */
export const OPERATE_PREFIX_ALIAS = "admin";

/** Whether an address's first segment is the shell's prefix `prefix`, by its own id or its alias. */
const isPrefix = (segment: string | undefined, prefix: string | undefined): boolean =>
  !!prefix &&
  (segment === prefix || (prefix === OPERATE_PREFIX && segment === OPERATE_PREFIX_ALIAS));

export type SortDir = "asc" | "desc";
/** The views an address can select besides the default: Model's UMF source, and Changes' import loads. */
export type ModelView = "umf" | "loads";

export interface Route {
  module?: string;
  area: Area;
  /** The type selected in Model, shown in Entities, or the type of the entity in Graph and Changes. */
  type?: string;
  /** The entity open in Entities, selected in Graph or whose history Changes shows; with `type`. */
  key?: string;
  /** The action chosen in Actions, or the action Changes is filtered to. */
  action?: string;
  /** The change group whose receipt Changes shows. */
  group?: string;
  /** Entity keys to prefill into the chosen action's inputs, by input name. */
  input?: Record<string, string>;
  /** Model: the UMF source instead of the types. Changes: the import loads instead of the changes. */
  view?: ModelView;
  /** Entities: the table's filter, key column id to key. Only a key column's filter belongs here; other filter values are typed text and are never written to the fragment (the table's writer omits them). */
  filter?: Record<string, string>;
  /** Entities: the key the page starts after. */
  after?: string;
  /** Entities: the table's sort. */
  sort?: { column: string; dir: SortDir };
  /** Changes: the earliest and latest instants (ISO 8601). */
  since?: string;
  until?: string;
}

const decode = (x: string): string | undefined => {
  try {
    return decodeURIComponent(x);
  } catch {
    return undefined;
  }
};

/** What an entity key can be in a fragment: text of 1 to 256 characters with no control characters. */
export const KEY_VALUE = /^\P{Cc}{1,256}$/u;

const IN = "in.";
const FILTER = "f.";
const ISO_INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/;

type Pair = [name: string, value: string];

/** The decoded `name=value` pairs of a query string; a pair that is not readable is dropped. */
function pairsOf(query: string): Pair[] {
  const out: Pair[] = [];
  for (const part of query.split("&")) {
    const eq = part.indexOf("=");
    if (eq <= 0) continue;
    const name = decode(part.slice(0, eq));
    const value = decode(part.slice(eq + 1));
    if (name !== undefined && value !== undefined) out.push([name, value]);
  }
  return out;
}

/** The pairs whose name starts with `prefix` (and names something after it), as a record. */
function prefixed(pairs: Pair[], prefix: string): Record<string, string> | undefined {
  const hits = pairs
    .filter(([n]) => n.startsWith(prefix) && n.length > prefix.length)
    .map(([n, v]): Pair => [n.slice(prefix.length), v]);
  return hits.length ? Object.fromEntries(hits) : undefined;
}

const first = (pairs: Pair[], name: string): string | undefined =>
  pairs.find(([n, v]) => n === name && v !== "")?.[1];

const instant = (v: string | undefined): string | undefined =>
  v !== undefined && ISO_INSTANT.test(v) && !Number.isNaN(Date.parse(v)) ? v : undefined;

function parseSort(v: string | undefined): Route["sort"] {
  const colon = v?.lastIndexOf(":") ?? -1;
  if (!v || colon <= 0) return undefined;
  const dir = v.slice(colon + 1);
  return dir === "asc" || dir === "desc" ? { column: v.slice(0, colon), dir } : undefined;
}

function modelTail(rest: string[], pairs: Pair[]): Partial<Route> | undefined {
  if (rest.length > 1) return undefined;
  const view = first(pairs, "view");
  return { type: rest[0], view: view === "umf" ? view : undefined };
}

function entitiesTail(rest: string[], pairs: Pair[]): Partial<Route> | undefined {
  if (rest.length > 2) return undefined;
  return {
    type: rest[0],
    key: rest[1],
    filter: prefixed(pairs, FILTER),
    after: first(pairs, "after"),
    sort: parseSort(first(pairs, "sort")),
  };
}

function changesTail(rest: string[], pairs: Pair[]): Partial<Route> | undefined {
  if (rest.length !== 0 && rest.length !== 2) return undefined;
  const subject =
    rest.length === 2 ? { type: rest[0], key: rest[1] } : { group: first(pairs, "group") };
  return {
    ...subject,
    action: first(pairs, "action"),
    since: instant(first(pairs, "since")),
    until: instant(first(pairs, "until")),
    view: first(pairs, "view") === "loads" ? "loads" : undefined,
  };
}

/** What follows the area, by area; undefined when it does not fit the area's shape. */
function tailFor(area: Area, rest: string[], query: string): Partial<Route> | undefined {
  const pairs = pairsOf(query);
  switch (area) {
    case "model":
      return modelTail(rest, pairs);
    case "entities":
      return entitiesTail(rest, pairs);
    case "graph":
      return rest.length === 2 ? { type: rest[0], key: rest[1] } : undefined;
    case "changes":
      return changesTail(rest, pairs);
    case "actions":
      return rest.length > 1 ? undefined : { action: rest[0], input: prefixed(pairs, IN) };
    default:
      return {};
  }
}

/** A route's fields that are set; the parse leaves out what an address does not say. */
const defined = (r: Partial<Route>): Partial<Route> =>
  Object.fromEntries(Object.entries(r).filter(([, v]) => v !== undefined));

export function parseHash(hash: string, prefix?: string): Route {
  const raw = hash.replace(/^#\/?/, "");
  const q = raw.indexOf("?");
  const path = q < 0 ? raw : raw.slice(0, q);
  let segments = path.split("/");
  while (segments.length > 0 && segments[segments.length - 1] === "") segments.pop();
  if (isPrefix(segments[0], prefix)) segments = segments.slice(1);
  const [rawModule, rawArea, ...rest] = segments;
  const module = rawModule ? decode(rawModule) : undefined;
  if (!module) return { area: "model" };
  const area = areaOf(rawArea);
  if (!area) return { module, area: "model" };
  const parts = rest.map(decode);
  const ok = parts.every((p): p is string => !!p);
  const tail = ok ? tailFor(area, parts as string[], q < 0 ? "" : raw.slice(q + 1)) : undefined;
  return { module, area, ...defined(tail ?? {}) };
}

/**
 * The canonical form of a fragment whose first segment is the prefix alias (`admin`) or whose area
 * segment is an alias (`schema`, `data`, `audit`), else undefined: what a shell rewrites the address
 * to, once.
 */
export function canonicalHash(hash: string, prefix?: string): string | undefined {
  const segments = hash.replace(/^#\/?/, "").split("?")[0]?.split("/") ?? [];
  const prefixed = isPrefix(segments[0], prefix);
  const area = segments[prefixed ? 2 : 1];
  const oldPrefix = prefixed && segments[0] !== prefix;
  if (!oldPrefix && (!area || !Object.hasOwn(AREA_ALIASES, area))) return undefined;
  return formatHash(parseHash(hash, prefix), prefix);
}

const enc = encodeURIComponent;

function tailOf(r: Route): string[] {
  switch (r.area) {
    case "model":
      return r.type ? [r.type] : [];
    case "entities":
      return r.type ? [r.type, ...(r.key ? [r.key] : [])] : [];
    case "graph":
    case "changes":
      return r.type && r.key ? [r.type, r.key] : [];
    case "actions":
      return r.action ? [r.action] : [];
    default:
      return [];
  }
}

const pair = (name: string, value: string): string => `${enc(name)}=${enc(value)}`;
const set = (name: string, v: string | undefined): string[] => (v ? [pair(name, v)] : []);
const record = (prefix: string, m: Record<string, string> | undefined): string[] =>
  Object.entries(m ?? {}).map(([k, v]) => pair(prefix + k, v));

function entitiesQuery(r: Route): string[] {
  if (!r.type) return [];
  const page = r.key ? [] : [...set("after", r.after), ...set("sort", sortOf(r.sort))];
  return [...record(FILTER, r.filter), ...page];
}

function queryPairs(r: Route): string[] {
  switch (r.area) {
    case "model":
      return set("view", r.view === "umf" ? r.view : undefined);
    case "entities":
      return entitiesQuery(r);
    case "changes":
      return [
        ...(r.type && r.key ? [] : set("group", r.group)),
        ...set("action", r.action),
        ...set("since", r.since),
        ...set("until", r.until),
        ...set("view", r.view === "loads" ? r.view : undefined),
      ];
    case "actions":
      return r.action ? record(IN, r.input) : [];
    default:
      return [];
  }
}

function sortOf(s: Route["sort"]): string | undefined {
  return s ? `${s.column}:${s.dir}` : undefined;
}

function queryOf(r: Route): string {
  const pairs = queryPairs(r);
  return pairs.length ? `?${pairs.join("&")}` : "";
}

export function formatHash(r: Route, prefix?: string): string {
  const head = prefix ? [enc(prefix)] : [];
  if (!r.module) return head.length ? `#/${head[0]}` : "#/";
  const rest = [r.module, r.area, ...tailOf(r)].map(enc);
  return `#/${[...head, ...rest].join("/")}${queryOf(r)}`;
}

/** True when two routes are the same location (what the fragment says, not how it was built). */
export const sameRoute = (a: Route, b: Route, prefix?: string): boolean =>
  formatHash(a, prefix) === formatHash(b, prefix);

/** The fragment that opens an entity in Entities or Graph, or its history in Changes, under the console's `prefix`. */
export function entityHref(
  module: string,
  area: "entities" | "graph" | "changes",
  type: string,
  key: string,
  prefix?: string,
): string {
  return formatHash({ module, area, type, key }, prefix);
}

/** The fragment that opens an action, with ref inputs prefilled from entity keys. */
export function actionHref(
  module: string,
  action: string,
  input?: Record<string, string>,
  prefix?: string,
): string {
  return formatHash({ module, area: "actions", action, input }, prefix);
}

/** The fragment that opens the receipt of one change group in Changes. */
export function groupHref(module: string, group: string, prefix?: string): string {
  return formatHash({ module, area: "changes", group }, prefix);
}
