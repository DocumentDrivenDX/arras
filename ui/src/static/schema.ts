// SPDX-License-Identifier: MIT OR Apache-2.0
// The per-module GraphQL schema of the static read-only profile (CONTRACT-006, CONTRACT-012): the
// types, fields, arguments, error codes and budgets of `arras/gqlschema.py`, resolved over the
// in-memory `Store` instead of a backend query. Read-only: there is no Mutation and no Subscription.
import {
  GraphQLBoolean,
  type GraphQLFieldConfig,
  type GraphQLFieldConfigMap,
  GraphQLInt,
  GraphQLInterfaceType,
  GraphQLList,
  GraphQLObjectType,
  type GraphQLOutputType,
  GraphQLSchema,
  GraphQLString,
  validateSchema,
} from "graphql";
import {
  BigInt_,
  Consistency,
  coded,
  DateTime,
  type Fresh,
  FreshnessType,
  freshness,
  JSONScalar,
  listOf,
  MAX_LIMIT,
  MAX_RELATIONSHIP_KEYS,
  type Node,
  nn,
  type RequestContext,
  S,
  SCALARS,
} from "./common";
import {
  type EntityType,
  InvalidDocument,
  type ModuleModel,
  type Prop,
  relationshipsOf,
} from "./model";
import { runSearch, searchPageFields } from "./search";
import type { Entity } from "./store";
import { byCodePoint } from "./text";

const FOREIGN = "ForeignEntity";

const ATTRIBUTION: Record<string, [GraphQLOutputType, (e: Entity) => unknown]> = {
  createdBy: [GraphQLString, (e) => e.originalAuthor],
  createdAt: [DateTime, (e) => e.originalAt],
  updatedBy: [GraphQLString, (e) => e.originalAuthor],
  updatedAt: [DateTime, (e) => e.originalAt],
};

const attributionFields = (): GraphQLFieldConfigMap<Node, RequestContext> => {
  const out: GraphQLFieldConfigMap<Node, RequestContext> = {};
  for (const [name, [type, get]] of Object.entries(ATTRIBUTION))
    out[name] = { type, resolve: (n) => get(n.entity) };
  return out;
};

const lowerFirst = (s: string) => s.slice(0, 1).toLowerCase() + s.slice(1);

function gqlType(p: Prop): GraphQLOutputType {
  let base: GraphQLOutputType = p.scalar ? (SCALARS[p.type] ?? JSONScalar) : JSONScalar;
  if (p.cardinality === "many") base = new GraphQLList(nn(base));
  return p.cardinality === "one" ? nn(base) : base;
}

interface Ref {
  type: string;
  key: string;
}

function refType(mod: ModuleModel, entity: GraphQLInterfaceType): GraphQLObjectType {
  const target = (r: Ref, _args: unknown, ctx: RequestContext): Node | null => {
    const dot = r.type.indexOf(".");
    const module = r.type.slice(0, dot);
    const local = r.type.slice(dot + 1);
    if (module !== mod.name) return null; // another module is read from its own endpoint
    if (!mod.entityTypes.some((t) => t.local === local)) return null;
    ctx.reserveTarget();
    const found = ctx.store.get(local, r.key);
    ctx.settle(1, found ? 1 : 0);
    return found ? { entity: found, fresh: freshness(ctx.store, "latest") } : null;
  };
  return new GraphQLObjectType({
    name: "Ref",
    fields: () => ({
      module: { type: S, resolve: (r: Ref) => r.type.slice(0, r.type.indexOf(".")) },
      type: { type: S, resolve: (r: Ref) => r.type },
      key: { type: S, resolve: (r: Ref) => r.key },
      target: { type: entity, resolve: target },
    }),
  });
}

function entityType(
  mod: ModuleModel,
  t: EntityType,
  entity: GraphQLInterfaceType,
  ref: GraphQLObjectType,
): GraphQLObjectType {
  return new GraphQLObjectType({
    name: t.local,
    interfaces: [entity],
    fields: () => {
      const out: GraphQLFieldConfigMap<Node, RequestContext> = {
        key: { type: S, resolve: (n) => n.entity.key },
        type: { type: S, resolve: () => t.name },
        version: { type: BigInt_, resolve: () => 1 },
        freshness: { type: nn(FreshnessType), resolve: (n) => n.fresh },
        ...attributionFields(),
      };
      for (const p of t.properties)
        out[p.name] = { type: gqlType(p), resolve: (n) => n.entity.props[p.name] ?? null };
      for (const [name, other] of relationshipsOf(mod, t))
        out[name] = {
          type: listOf(ref),
          resolve: (n, _a, ctx): Ref[] =>
            ctx.store
              .relatedKeys(n.entity, name)
              .slice(0, MAX_RELATIONSHIP_KEYS)
              .map((key) => ({ type: other, key })),
        };
      return out;
    },
  });
}

function pageType(t: EntityType, obj: GraphQLObjectType): GraphQLObjectType {
  interface Page {
    items: Node[];
    truncated: boolean;
    freshness: Fresh;
  }
  return new GraphQLObjectType<Page>({
    name: `${t.local}Page`,
    fields: {
      items: { type: listOf(obj), resolve: (p) => p.items },
      truncated: { type: nn(GraphQLBoolean), resolve: (p) => p.truncated },
      freshness: { type: nn(FreshnessType), resolve: (p) => p.freshness },
    },
  });
}

function byKeyField(
  t: EntityType,
  obj: GraphQLObjectType,
): GraphQLFieldConfig<unknown, RequestContext> {
  return {
    type: obj,
    args: {
      key: { type: S },
      consistency: { type: Consistency, defaultValue: "latest" },
      atLeast: { type: GraphQLString },
    },
    resolve: (_r, args: { key: string; consistency: string }, ctx) => {
      ctx.reserve(1);
      const found = ctx.store.get(t.local, args.key);
      ctx.settle(1, found ? 1 : 0);
      return found ? { entity: found, fresh: freshness(ctx.store, args.consistency) } : null;
    },
  };
}

const IDENT = /^[A-Za-z_][A-Za-z0-9_]*$/;

/** Python's `==` between a stored value and a JSON filter value, for the families a filter compares. */
function sameValue(stored: unknown, wanted: unknown): boolean {
  if (stored === null || stored === undefined || wanted === null || wanted === undefined)
    return false;
  const integer = (v: unknown) => typeof v === "bigint" || typeof v === "number";
  if (integer(stored) && integer(wanted))
    return BigInt(stored as number) === BigInt(wanted as number);
  return stored === wanted;
}

interface ListArgs {
  filter?: unknown;
  limit?: number | null;
  consistency: string;
  afterKey?: string | null;
}

function filtered(
  ctx: RequestContext,
  t: EntityType,
  filter: Record<string, unknown>,
  afterKey: string | null | undefined,
  relationships: Set<string>,
  properties: Set<string>,
): Entity[] {
  const conds: ((e: Entity) => boolean)[] = [];
  for (const [k, v] of Object.entries(filter)) {
    if (!IDENT.test(k) || !(properties.has(k) || relationships.has(k)))
      throw coded("BAD_QUERY", `'${k}' is not a property or relationship of ${t.local}`);
    if (relationships.has(k))
      conds.push((e) => typeof v === "string" && ctx.store.relatedKeys(e, k).includes(v));
    else conds.push((e) => sameValue(e.props[k], v));
  }
  if (afterKey !== null && afterKey !== undefined) {
    if (typeof afterKey !== "string") throw coded("BAD_QUERY", "afterKey is a key");
    conds.push((e) => byCodePoint(e.key, afterKey) > 0);
  }
  return (ctx.store.entities.get(t.local) ?? []).filter((e) => conds.every((c) => c(e)));
}

function listField(
  mod: ModuleModel,
  t: EntityType,
  page: GraphQLObjectType,
): GraphQLFieldConfig<unknown, RequestContext> {
  const properties = new Set(t.properties.map((p) => p.name));
  const relationships = new Set(relationshipsOf(mod, t).map(([n]) => n));
  return {
    type: page,
    args: {
      filter: { type: JSONScalar },
      limit: { type: GraphQLInt, defaultValue: 50 },
      consistency: { type: Consistency, defaultValue: "latest" },
      afterKey: { type: GraphQLString },
    },
    resolve: (_r, args: ListArgs, ctx) => {
      const limit = args.limit ?? 50;
      if (!(limit >= 1 && limit <= MAX_LIMIT))
        throw coded("LIMIT_EXCEEDED", `limit is 1 to ${MAX_LIMIT}`);
      const f = args.filter;
      if (f !== null && f !== undefined && (typeof f !== "object" || Array.isArray(f)))
        throw coded("BAD_QUERY", "filter is an object");
      const rows = filtered(
        ctx,
        t,
        (f ?? {}) as Record<string, unknown>,
        args.afterKey,
        relationships,
        properties,
      );
      ctx.reserve(limit);
      const taken = rows.slice(0, limit);
      ctx.settle(limit, taken.length);
      const fresh = freshness(ctx.store, args.consistency);
      return {
        items: taken.map((entity) => ({ entity, fresh })),
        truncated: rows.length > limit,
        freshness: fresh,
      };
    },
  };
}

/** The schema for `mod`; `InvalidDocument` (`invalid_name`) if it cannot be served. */
export function buildModuleSchema(mod: ModuleModel): GraphQLSchema {
  for (const r of mod.relationships)
    if (r.source.length > 1 || r.target.length > 1)
      throw new InvalidDocument([
        {
          path: `relationships.${r.name}`,
          code: "invalid_name",
          message: "the console serves one type per end",
        },
      ]);
  const entity = new GraphQLInterfaceType({
    name: "Entity",
    fields: () => ({
      key: { type: GraphQLString },
      type: { type: GraphQLString },
      version: { type: BigInt_ },
      freshness: { type: nn(FreshnessType) },
      createdBy: { type: GraphQLString },
      createdAt: { type: DateTime },
      updatedBy: { type: GraphQLString },
      updatedAt: { type: DateTime },
    }),
    resolveType: (n: Node) => n.entity.type.local,
  });
  const ref = refType(mod, entity);
  const foreign = new GraphQLObjectType({
    name: FOREIGN,
    interfaces: [entity],
    fields: {
      key: { type: GraphQLString, resolve: () => null },
      type: { type: GraphQLString, resolve: () => null },
      version: { type: BigInt_, resolve: () => null },
      freshness: { type: nn(FreshnessType), resolve: (n: Node) => n.fresh },
      createdBy: { type: GraphQLString, resolve: () => null },
      createdAt: { type: DateTime, resolve: () => null },
      updatedBy: { type: GraphQLString, resolve: () => null },
      updatedAt: { type: DateTime, resolve: () => null },
    },
  });
  const objects = new Map<string, GraphQLObjectType>();
  const pages = new Map<string, GraphQLObjectType>();
  const queryFields: GraphQLFieldConfigMap<unknown, RequestContext> = {};
  for (const t of mod.entityTypes) {
    const obj = entityType(mod, t, entity, ref);
    objects.set(t.local, obj);
    pages.set(t.local, pageType(t, obj));
  }
  for (const t of mod.entityTypes) {
    const lf = lowerFirst(t.local);
    queryFields[lf] = byKeyField(t, objects.get(t.local) as GraphQLObjectType);
    queryFields[`${lf}List`] = listField(mod, t, pages.get(t.local) as GraphQLObjectType);
  }
  const search = searchPageFields(entity);
  queryFields._search = {
    type: nn(search.page),
    args: {
      text: { type: S },
      types: { type: new GraphQLList(S) },
      limit: { type: GraphQLInt, defaultValue: 20 },
      consistency: { type: Consistency, defaultValue: "latest" },
      atLeast: { type: GraphQLString },
    },
    resolve: (_r, args, ctx) => runSearch(ctx, args),
  };
  const schema = new GraphQLSchema({
    query: new GraphQLObjectType({ name: "Query", fields: queryFields }),
    types: [...objects.values(), ...pages.values(), foreign, ref, FreshnessType, ...search.types],
  });
  const errors = validateSchema(schema);
  if (errors.length)
    throw new InvalidDocument(
      errors.map((e) => ({ path: "module", code: "invalid_name", message: e.message })),
    );
  return schema;
}
