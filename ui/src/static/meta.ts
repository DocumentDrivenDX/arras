// SPDX-License-Identifier: MIT OR Apache-2.0
// The meta schema of the static read-only profile (CONTRACT-006, CONTRACT-012): the registry's one
// module, its types, relationships, actions, resolved views and the one backend's status, as
// `build_meta_schema` answers them. The backend is named `static`; it is the system of record and the
// only reader, so a module has no replicas and no providers.
import {
  GraphQLBoolean,
  type GraphQLFieldConfigMap,
  GraphQLInt,
  GraphQLList,
  GraphQLObjectType,
  type GraphQLOutputType,
  GraphQLSchema,
  GraphQLString,
} from "graphql";
import { JSONScalar, listOf, nn, S } from "./common";
import { type EntityType, relationshipsOf } from "./model";
import { BACKEND, type Store } from "./store";
import type { ResolvedView } from "./view";

type Spec = [GraphQLOutputType, (o: never) => unknown];

function rec(name: string, fields: Record<string, Spec>): GraphQLObjectType {
  return new GraphQLObjectType({
    name,
    fields: () => {
      const out: GraphQLFieldConfigMap<unknown, unknown> = {};
      for (const [k, [type, get]] of Object.entries(fields))
        out[k] = { type, resolve: (o) => get(o as never) };
      return out;
    },
  });
}
const spec = <T>(type: GraphQLOutputType, get: (o: T) => unknown): Spec => [type, get as never];

const PropertyInfoT = rec("PropertyInfo", {
  name: spec<{ name: string }>(S, (p) => p.name),
  type: spec<{ type: string }>(S, (p) => p.type),
  required: spec<{ cardinality: string }>(nn(GraphQLBoolean), (p) => p.cardinality === "one"),
  cardinality: spec<{ cardinality: string }>(S, (p) => p.cardinality),
});
const BackendStatusT = rec("BackendStatus", {
  backend: spec<Store>(S, () => BACKEND),
  available: spec<Store>(nn(GraphQLBoolean), () => true),
  reason: spec<Store>(GraphQLString, () => null),
  detail: spec<Store>(GraphQLString, () => null),
  position: spec<Store>(GraphQLString, (s) => s.asOf),
  lag: spec<Store>(GraphQLString, () => null),
});
const ViewSectionT = rec("ViewSection", {
  label: spec<ResolvedView["sections"][0]>(S, (s) => s.label),
  properties: spec<ResolvedView["sections"][0]>(listOf(GraphQLString), (s) => s.properties),
  collapsed: spec<ResolvedView["sections"][0]>(nn(GraphQLBoolean), (s) => s.collapsed),
});
const FieldViewT = rec("FieldView", {
  property: spec<ResolvedView["fields"][0]>(S, (f) => f.property),
  label: spec<ResolvedView["fields"][0]>(S, (f) => f.label),
  format: spec<ResolvedView["fields"][0]>(S, (f) => f.format),
  hideWhenEmpty: spec<ResolvedView["fields"][0]>(nn(GraphQLBoolean), (f) => f.hideWhenEmpty),
  tones: spec<ResolvedView["fields"][0]>(JSONScalar, (f) => f.tones),
});
const RelationshipViewT = rec("RelationshipView", {
  field: spec<ResolvedView["relationships"][0]>(S, (r) => r.field),
  label: spec<ResolvedView["relationships"][0]>(S, (r) => r.label),
  hideWhenEmpty: spec<ResolvedView["relationships"][0]>(nn(GraphQLBoolean), (r) => r.hideWhenEmpty),
  order: spec<ResolvedView["relationships"][0]>(nn(GraphQLInt), (r) => r.order),
});
const ViewT = rec("View", {
  declared: spec<ResolvedView>(nn(GraphQLBoolean), (v) => v.declared),
  label: spec<ResolvedView>(S, (v) => v.label),
  pluralLabel: spec<ResolvedView>(S, (v) => v.pluralLabel),
  icon: spec<ResolvedView>(S, (v) => v.icon),
  tone: spec<ResolvedView>(S, (v) => v.tone),
  title: spec<ResolvedView>(S, (v) => v.title),
  summary: spec<ResolvedView>(GraphQLString, (v) => v.summary),
  sections: spec<ResolvedView>(listOf(ViewSectionT), (v) => v.sections),
  search: spec<ResolvedView>(listOf(GraphQLString), (v) => v.search),
  fields: spec<ResolvedView>(listOf(FieldViewT), (v) => v.fields),
  relationships: spec<ResolvedView>(listOf(RelationshipViewT), (v) => v.relationships),
});
const ModuleViewT = rec("ModuleView", {
  title: spec<{ title: string }>(S, (v) => v.title),
  description: spec<{ description: string | null }>(GraphQLString, (v) => v.description),
});

interface TypeNode {
  store: Store;
  type: EntityType;
}

/** What a backend declares for a type (CONTRACT-004): the memory adapter's capabilities, read-only. */
function capabilities(store: Store, t: EntityType) {
  const columns = t.properties
    .filter(
      (p) =>
        p.scalar &&
        ["string", "integer", "decimal", "boolean"].includes(p.type) &&
        (p.cardinality === "one" || p.name === t.key),
    )
    .map((p) => p.name);
  const relationships = relationshipsOf(store.module, t).map(([n]) => n);
  const searchable = t.properties
    .filter((p) => p.scalar && p.type === "string" && p.cardinality !== "many")
    .map((p) => p.name);
  return {
    [BACKEND]: {
      read: true,
      columns,
      relationships,
      count: true,
      mutable: false,
      latency_class: "batch",
      search: "substring",
      searchable,
    },
  };
}

const EntityTypeInfoT = rec("EntityTypeInfo", {
  name: spec<TypeNode>(S, (n) => n.type.name),
  key: spec<TypeNode>(S, (n) => n.type.key),
  properties: spec<TypeNode>(listOf(PropertyInfoT), (n) => n.type.properties),
  capabilities: spec<TypeNode>(nn(JSONScalar), (n) => capabilities(n.store, n.type)),
  view: spec<TypeNode>(nn(ViewT), (n) => n.store.viewOf(n.type.local)),
});
const RelationshipInfoT = rec("RelationshipInfo", {
  name: spec<{ name: string }>(S, (r) => r.name),
  source: spec<{ source: string[] }>(listOf(GraphQLString), (r) => r.source),
  target: spec<{ target: string[] }>(listOf(GraphQLString), (r) => r.target),
  sourceMultiplicity: spec<{ sourceMultiplicity: string }>(S, (r) => r.sourceMultiplicity),
  targetMultiplicity: spec<{ targetMultiplicity: string }>(S, (r) => r.targetMultiplicity),
  lifecycle: spec<{ lifecycle: string }>(S, (r) => r.lifecycle),
  inverse: spec<{ inverse: string | null }>(GraphQLString, (r) => r.inverse),
});
type ActionN = Store["module"]["actions"][0];
const InputSpecT = rec("InputSpec", {
  name: spec<ActionN["inputSpecs"][0]>(S, (s) => s.name),
  type: spec<ActionN["inputSpecs"][0]>(S, (s) => s.type),
  kind: spec<ActionN["inputSpecs"][0]>(S, (s) => s.kind),
  cardinality: spec<ActionN["inputSpecs"][0]>(S, (s) => s.cardinality),
});
const ActionInfoT = rec("ActionInfo", {
  name: spec<ActionN>(S, (a) => a.name),
  description: spec<ActionN>(S, (a) => a.description),
  inputs: spec<ActionN>(nn(JSONScalar), (a) => a.inputSpecs),
  inputSpecs: spec<ActionN>(listOf(InputSpecT), (a) => a.inputSpecs),
  // The static profile runs no action, so it states none of its guards or effects (CONTRACT-012).
  preconditions: spec<ActionN>(nn(JSONScalar), () => []),
  effects: spec<ActionN>(nn(JSONScalar), () => []),
});
const ModuleT = rec("Module", {
  name: spec<Store>(S, (s) => s.module.name),
  record: spec<Store>(S, () => BACKEND),
  replicas: spec<Store>(listOf(GraphQLString), () => []),
  providers: spec<Store>(nn(JSONScalar), () => ({})),
  revision: spec<Store>(nn(JSONScalar), (s) => s.revision),
  entityTypes: spec<Store>(listOf(EntityTypeInfoT), (s) =>
    s.module.entityTypes.map((type) => ({ store: s, type })),
  ),
  relationships: spec<Store>(listOf(RelationshipInfoT), (s) => s.module.relationships),
  actions: spec<Store>(listOf(ActionInfoT), (s) => s.module.actions),
  view: spec<Store>(nn(ModuleViewT), (s) => s.resolved.module),
});

/** The meta schema; its root value is the one `Store`. */
export function buildMetaSchema(): GraphQLSchema {
  return new GraphQLSchema({
    query: new GraphQLObjectType({
      name: "Query",
      fields: {
        modules: { type: listOf(ModuleT), resolve: (s: Store) => [s] },
        status: { type: nn(new GraphQLList(nn(BackendStatusT))), resolve: (s: Store) => [s] },
      },
    }),
  });
}
