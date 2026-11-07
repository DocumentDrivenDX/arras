// SPDX-License-Identifier: MIT OR Apache-2.0
// What the schema and the search share (CONTRACT-006, CONTRACT-012): the request's budgets, the
// scalars, the freshness type and the error constructor of `arras/gqlschema.py`.
import {
  GraphQLBoolean,
  GraphQLEnumType,
  GraphQLError,
  GraphQLList,
  GraphQLNonNull,
  GraphQLObjectType,
  type GraphQLOutputType,
  GraphQLScalarType,
  GraphQLString,
} from "graphql";
import type { Entity, Store } from "./store";
import { MAX_ENTITIES } from "./text";
import type { ResolvedModule } from "./view";

export const MAX_LIMIT = 100;
export const MAX_TARGETS = 100;
export const MAX_RELATIONSHIP_KEYS = 100;

export const coded = (code: string, message: string, more: Record<string, unknown> = {}) =>
  new GraphQLError(message, { extensions: { code, ...more } });

/** One request: the one store snapshot, the entity budget and the open-target budget. */
export class RequestContext {
  entities = 0;
  targets = 0;
  constructor(
    readonly store: Store,
    readonly view: ResolvedModule,
  ) {}

  reserve(n: number): void {
    if (this.entities + n > MAX_ENTITIES)
      throw coded("COST_EXCEEDED", `a request resolves at most ${MAX_ENTITIES} entities`);
    this.entities += n;
  }
  tryReserve(n: number): boolean {
    if (this.entities + n > MAX_ENTITIES) return false;
    this.entities += n;
    return true;
  }
  reserveTarget(): void {
    if (this.targets >= MAX_TARGETS)
      throw coded("COST_EXCEEDED", `a request opens at most ${MAX_TARGETS} relationship targets`);
    this.reserve(1);
    this.targets += 1;
  }
  settle(reserved: number, actual: number): void {
    this.entities -= reserved - actual;
  }
}

// --- scalars -------------------------------------------------------------------------------

const passthrough = (v: unknown): unknown => v;
export const JSONScalar = new GraphQLScalarType({
  name: "JSON",
  serialize: passthrough,
  parseValue: passthrough,
});
export const DateTime = new GraphQLScalarType({ name: "DateTime", serialize: (v) => String(v) });
export const BigInt_ = new GraphQLScalarType({
  name: "BigInt",
  serialize: (v) => String(v),
  parseValue: (v) => BigInt(v as string | number),
});
export const DecimalScalar = new GraphQLScalarType({
  name: "Decimal",
  serialize: (v) => String(v),
});
export const Base64 = new GraphQLScalarType({ name: "Base64", serialize: (v) => String(v) });
export const Consistency = new GraphQLEnumType({
  name: "Consistency",
  values: { LATEST: { value: "latest" }, BULK: { value: "bulk" } },
});
export const SCALARS: Record<
  string,
  GraphQLScalarType | typeof GraphQLString | typeof GraphQLBoolean
> = {
  string: GraphQLString,
  integer: BigInt_,
  decimal: DecimalScalar,
  boolean: GraphQLBoolean,
  binary: Base64,
  timestamp: DateTime,
};

export interface Fresh {
  backend: string;
  asOf: string;
  at: string;
  consistency: string;
}

export const nn = <T extends GraphQLOutputType>(t: T) => new GraphQLNonNull(t);
export const S = nn(GraphQLString);
export const listOf = (t: GraphQLOutputType) => nn(new GraphQLList(nn(t)));

export const FreshnessType = new GraphQLObjectType({
  name: "Freshness",
  fields: {
    backend: { type: S, resolve: (f: Fresh) => f.backend },
    asOf: { type: S, resolve: (f: Fresh) => f.asOf },
    at: { type: nn(DateTime), resolve: (f: Fresh) => f.at },
    consistency: { type: nn(Consistency), resolve: (f: Fresh) => f.consistency },
  },
});

/** The freshness of a read: this backend, the graph's position, the consistency asked for. */
export const freshness = (store: Store, consistency: string): Fresh => ({
  backend: "static",
  asOf: store.asOf,
  at: store.at,
  consistency,
});

// --- nodes ---------------------------------------------------------------------------------

export interface Node {
  entity: Entity;
  fresh: Fresh;
}
