// SPDX-License-Identifier: MIT OR Apache-2.0
// One GraphQL request against the static backend (CONTRACT-006, CONTRACT-012): the same limits as the
// console surface (`arras/console/__init__.py`), the same validation, the same error codes, and the
// response in the same shape (`data`, `errors` with `extensions.code`, `extensions.revision`). A request
// the surface answers with an HTTP status (a syntax error, an unknown module) is a `Refusal` carrying it.
import {
  type DocumentNode,
  execute,
  type FieldNode,
  type FragmentDefinitionNode,
  GraphQLError,
  type GraphQLSchema,
  Kind,
  parse,
  type SelectionSetNode,
  validate,
} from "graphql";
import { coded, RequestContext } from "./common";
import { buildMetaSchema } from "./meta";
import { buildModuleSchema } from "./schema";
import type { Store } from "./store";

export const MAX_DEPTH = 6;
export const MAX_FIELDS = 50;
const MAX_INTROSPECTION_DEPTH = 20;
const MAX_INTROSPECTION_FIELDS = 500;
const MAX_TOKENS = 5000;

/** An answer the console surface gives as an HTTP status rather than a GraphQL result. */
export class Refusal extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export interface WireError {
  message: string;
  extensions: Record<string, unknown>;
  path?: (string | number)[];
  locations?: { line: number; column: number }[];
}

export interface WireResult {
  data: Record<string, unknown> | null;
  errors?: WireError[];
  extensions: { revision?: Record<string, number | null> };
}

type Four = [number, number, number, number];
const ZERO: Four = [0, 0, 0, 0];

class Measurer {
  private readonly memo = new Map<string, Four>();
  private readonly active = new Set<string>();
  constructor(private readonly frags: Map<string, FragmentDefinitionNode>) {}

  spread(name: string, intro: boolean): Four {
    const key = `${name}:${intro}`;
    const hit = this.memo.get(key);
    if (hit) return hit;
    const frag = this.frags.get(name);
    if (this.active.has(name) || !frag) return ZERO;
    this.active.add(name);
    const out = this.walk(frag.selectionSet, intro);
    this.active.delete(name);
    this.memo.set(key, out);
    return out;
  }

  field(s: FieldNode, intro: boolean): Four {
    const name = s.name.value;
    if (name === "__typename") return ZERO;
    const isIntro = (name === "__schema" || name === "__type") && !intro;
    const sub = s.selectionSet ? this.walk(s.selectionSet, intro || isIntro) : ZERO;
    if (isIntro) return [0, 0, Math.max(1 + sub[0], sub[2]), 1 + sub[1] + sub[3]];
    return [1 + sub[0], 1 + sub[1], sub[2], sub[3]];
  }

  walk(sel: SelectionSetNode, intro: boolean): Four {
    const acc: Four = [0, 0, 0, 0];
    for (const s of sel.selections) {
      let part: Four;
      if (s.kind === Kind.FIELD) part = this.field(s, intro);
      else if (s.kind === Kind.INLINE_FRAGMENT) part = this.walk(s.selectionSet, intro);
      else part = this.spread(s.name.value, intro);
      acc[0] = Math.max(acc[0], part[0]);
      acc[1] += part[1];
      acc[2] = Math.max(acc[2], part[2]);
      acc[3] += part[3];
    }
    return acc;
  }
}

/** Depth and field selections of the operation, fragments expanded once each, introspection apart. */
export function measure(doc: DocumentNode, operationName?: string | null): Four | null {
  const frags = new Map<string, FragmentDefinitionNode>();
  for (const d of doc.definitions)
    if (d.kind === Kind.FRAGMENT_DEFINITION) frags.set(d.name.value, d);
  const op = doc.definitions.find(
    (d) =>
      d.kind === Kind.OPERATION_DEFINITION &&
      (operationName == null || d.name?.value === operationName),
  );
  if (!op || op.kind !== Kind.OPERATION_DEFINITION) return null;
  return new Measurer(frags).walk(op.selectionSet, false);
}

export function format(e: GraphQLError): WireError {
  const out: WireError = { message: e.message, extensions: { ...(e.extensions ?? {}) } };
  out.extensions.code ??= "BAD_QUERY";
  if (e.path?.length) out.path = [...e.path];
  if (e.locations?.length)
    out.locations = e.locations.map((l) => ({ line: l.line, column: l.column }));
  return out;
}

function internalOrSelf(e: GraphQLError): GraphQLError {
  const inner = e.originalError;
  if (inner && !(inner instanceof GraphQLError))
    return withPath(coded("INTERNAL_ERROR", "internal error"), e);
  return e;
}

function withPath(fresh: GraphQLError, from: GraphQLError): GraphQLError {
  return new GraphQLError(fresh.message, {
    nodes: from.nodes,
    path: from.path,
    extensions: fresh.extensions,
  });
}

function reply(
  data: WireResult["data"],
  errors: readonly GraphQLError[],
  revision: WireResult["extensions"]["revision"],
): WireResult {
  const body: WireResult = { data, extensions: revision ? { revision } : {} };
  if (errors.length) body.errors = errors.map((e) => format(internalOrSelf(e)));
  return body;
}

function limitsFault(doc: DocumentNode, operationName?: string | null): GraphQLError | null {
  const m = measure(doc, operationName) ?? ZERO;
  if (m[0] > MAX_DEPTH) return coded("DEPTH_EXCEEDED", `queries are at most ${MAX_DEPTH} deep`);
  if (m[1] > MAX_FIELDS)
    return coded("COST_EXCEEDED", `queries select at most ${MAX_FIELDS} fields`);
  if (m[2] > MAX_INTROSPECTION_DEPTH || m[3] > MAX_INTROSPECTION_FIELDS)
    return coded("COST_EXCEEDED", "that introspection query is too large");
  return null;
}

const schemas = new WeakMap<Store, GraphQLSchema>();
const metaSchema = buildMetaSchema();

/** The module's schema, built once per loaded store (it cannot change: the store is immutable). */
export function moduleSchema(store: Store): GraphQLSchema {
  let s = schemas.get(store);
  if (!s) {
    s = buildModuleSchema(store.module);
    schemas.set(store, s);
  }
  return s;
}

export interface Request {
  query: string;
  variables?: Record<string, unknown> | null;
  operationName?: string | null;
}

function parseOrRefuse(query: string): DocumentNode {
  try {
    return parse(query, { maxTokens: MAX_TOKENS });
  } catch (e) {
    if (e instanceof GraphQLError) throw new Refusal(400, "BAD_QUERY", e.message);
    throw new Refusal(400, "BAD_QUERY", "the query is nested too deeply");
  }
}

/** Run one request against the module's endpoint (`module` given) or the meta endpoint (`null`). */
export function run(store: Store, module: string | null, req: Request): WireResult {
  if (module !== null && module !== store.module.name)
    throw new Refusal(404, "NOT_FOUND", "no such module");
  const meta = module === null;
  const schema = meta ? metaSchema : moduleSchema(store);
  const revision = meta ? undefined : store.revision;
  const doc = parseOrRefuse(req.query);
  const fault = limitsFault(doc, req.operationName);
  if (fault) return reply(null, [fault], revision);
  const problems = validate(schema, doc);
  if (problems.length)
    return reply(
      null,
      problems.map((p) => coded("BAD_QUERY", p.message)),
      revision,
    );
  const result = execute({
    schema,
    document: doc,
    rootValue: meta ? store : undefined,
    contextValue: meta ? {} : new RequestContext(store, store.resolved),
    variableValues: req.variables ?? undefined,
    operationName: req.operationName ?? undefined,
  });
  if (result instanceof Promise) throw new Error("a resolver answered asynchronously");
  return reply((result.data ?? null) as WireResult["data"], result.errors ?? [], revision);
}
