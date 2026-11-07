// SPDX-License-Identifier: MIT OR Apache-2.0
// The registry's reading of one module document, as the static read-only profile holds it
// (CONTRACT-012). It mirrors `arras.model` for what a read needs; every name here has the same
// meaning as its Python namesake.

import type { Domain } from "./domain";

export type Cardinality = "one" | "optional" | "many";

export const SCALAR_FAMILIES = [
  "string",
  "integer",
  "decimal",
  "boolean",
  "binary",
  "timestamp",
] as const;

export interface Violation {
  path: string;
  code: string;
  message: string;
}

/** A document the registry would refuse: every fault, each with its document path. */
export class InvalidDocument extends Error {
  readonly violations: Violation[];
  constructor(violations: Violation[]) {
    super(violations.map((v) => `${v.path}: ${v.message}`).join("; "));
    this.violations = violations;
  }
}

export interface Prop {
  name: string;
  /** A scalar family, or the name of a value object. */
  type: string;
  scalar: boolean;
  cardinality: Cardinality;
}

export interface EntityType {
  /** Module-qualified: `catalog.UseCase`. */
  name: string;
  local: string;
  key: string;
  properties: Prop[];
}

export interface Rel {
  name: string;
  source: string[];
  target: string[];
  sourceMultiplicity: string;
  targetMultiplicity: string;
  lifecycle: string;
  inverse: string | null;
}

export interface InputSpec {
  name: string;
  type: string;
  kind: "scalar" | "record" | "ref";
  cardinality: Cardinality;
}

/** A declared action. The static profile runs none, so it keeps the name and inputs only. */
export interface Action {
  name: string;
  description: string;
  inputSpecs: InputSpec[];
}

export interface ModuleModel {
  name: string;
  /** Numeric domains by `type\u0000field` (the document's field facets): `domain.ts`. */
  domains: Map<string, Domain>;
  entityTypes: EntityType[];
  relationships: Rel[];
  actions: Action[];
}

export const propertyOf = (t: EntityType, name: string): Prop | undefined =>
  t.properties.find((p) => p.name === name);

export const entityTypeOf = (m: ModuleModel, local: string): EntityType | undefined =>
  m.entityTypes.find((t) => t.local === local);

/** (field name, the type on the other end) for every relationship the type takes part in. */
export function relationshipsOf(m: ModuleModel, t: EntityType): [string, string][] {
  const out: [string, string][] = [];
  for (const r of m.relationships) {
    if (r.source.includes(t.name)) out.push([r.name, r.target[0] ?? ""]);
    if (r.inverse && r.target.includes(t.name)) out.push([r.inverse, r.source[0] ?? ""]);
  }
  return out;
}
