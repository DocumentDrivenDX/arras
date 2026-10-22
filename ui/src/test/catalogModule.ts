// SPDX-License-Identifier: MIT OR Apache-2.0
// The example catalog (examples/catalog/catalog.umf.json) as the meta read describes it: the
// declared actions, entity types and relationships the kit's derivations run over, so their vectors
// are on the real catalog rather than on a hand-made one. An input expression is `{name}`, an alias
// `{alias}` and a generated key `{kind: "uuid"}`, as the library's meta read spells them.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type {
  ActionInfo,
  EffectDecl,
  EntityTypeInfo,
  InputSpec,
  ModuleInfo,
  RelationshipInfo,
} from "../api/types";
import { REV } from "./fake";

interface UmfType {
  kind: string;
  name?: string;
  type?: string;
}
interface UmfInput {
  name: string;
  type: UmfType;
  cardinality: InputSpec["cardinality"];
}

const read = (name: string) => {
  const file = join(import.meta.dirname, `../../../examples/${name}/${name}.umf.json`);
  // biome-ignore lint/suspicious/noExplicitAny: the UMF document is read untyped
  return JSON.parse(readFileSync(file, "utf8")).modules[0] as any;
};

const expr = (e: Record<string, unknown> | undefined): unknown => {
  if (!e) return null;
  if ("input" in e) return { name: e.input };
  if ("generate" in e) return { kind: "uuid" };
  return e;
};

const effect = (e: Record<string, unknown>): EffectDecl => ({
  op: e.op as string,
  alias: (e.as as string | undefined) ?? null,
  type: (e.type as string | undefined) ?? null,
  ref_type: (e.refType as string | undefined) ?? null,
  key: expr(e.key as Record<string, unknown> | undefined),
  source: expr(e.source as Record<string, unknown> | undefined),
  target: expr(e.target as Record<string, unknown> | undefined),
  properties: Object.fromEntries(
    Object.entries((e.properties ?? {}) as Record<string, Record<string, unknown>>).map(
      ([k, v]) => [k, expr(v)],
    ),
  ),
  unset: [],
  over: null,
  body: [],
});

const action = (
  mod: string,
  a: {
    id: string;
    description: string;
    inputs: UmfInput[];
    effects: Record<string, unknown>[];
  },
): ActionInfo => ({
  name: `${mod}.${a.id}`,
  description: a.description,
  inputSpecs: a.inputs.map((i) => ({
    name: i.name,
    type: i.type.name ?? i.type.type ?? "",
    kind: i.type.kind as InputSpec["kind"],
    cardinality: i.cardinality,
  })),
  preconditions: [],
  effects: a.effects.map(effect),
});

const entity = (
  mod: string,
  e: {
    id: string;
    extensions: {
      "umf.ddd": {
        fields: Record<string, { type: UmfType; cardinality: string }>;
        identity: { fields: string[] };
      };
    };
  },
): EntityTypeInfo => ({
  name: `${mod}.${e.id}`,
  key: e.extensions["umf.ddd"].identity.fields[0] ?? "code",
  properties: Object.entries(e.extensions["umf.ddd"].fields).map(([name, f]) => ({
    name,
    type: f.type.name ?? "string",
    required: f.cardinality === "one",
    cardinality: f.cardinality,
  })),
  capabilities: {},
});

const relationship = (
  mod: string,
  r: {
    name: string;
    source: { element: string }[];
    target: { element: string }[];
    inverse?: string;
  },
): RelationshipInfo => ({
  name: r.name,
  source: r.source.map((s) => `${mod}.${s.element}`),
  target: r.target.map((s) => `${mod}.${s.element}`),
  sourceMultiplicity: "0..*",
  targetMultiplicity: "0..*",
  lifecycle: "independent",
  inverse: r.inverse ?? null,
});

/** An example module (examples/<name>/<name>.umf.json), as the meta read describes it. */
export function exampleModule(name: string): ModuleInfo {
  const doc = read(name);
  return {
    name,
    record: "memory",
    replicas: [],
    providers: {},
    revision: { ...REV },
    entityTypes: doc.elements
      .filter(
        (e: { kind: string; extensions?: Record<string, { kind?: string }> }) =>
          e.kind === "record" && e.extensions?.["umf.ddd"]?.kind === "entity",
      )
      .map((e: Parameters<typeof entity>[1]) => entity(name, e)),
    relationships: doc.relationships.map((r: Parameters<typeof relationship>[1]) =>
      relationship(name, r),
    ),
    actions: doc.actions.map((a: Parameters<typeof action>[1]) => action(name, a)),
  };
}

/** The catalog module of the example, as the meta read describes it. */
export const exampleCatalog = () => exampleModule("catalog");
