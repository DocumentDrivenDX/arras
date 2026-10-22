// SPDX-License-Identifier: MIT OR Apache-2.0
import { defined } from "../test/defined";
// Two small checkers for the drift guard: a recursive key-structure comparison of two JSON values, and
// a structural check of a value against a schema of ui/openapi.json (the JSON Schema subset it uses:
// $ref, type (one or a list, with "null"), properties, required, additionalProperties, items, enum,
// const, oneOf/anyOf, minItems/maxItems, minimum/maximum). No dependency is needed for either.

export interface CompareOpts {
  /** Paths (as printed, `[]` for an array element) whose value may be null on one side only. */
  nullable?: string[];
  /** Paths of maps keyed by data (property names, arguments): their keys are not compared. */
  open?: string[];
}

const kindOf = (v: unknown) => (v === null ? "null" : Array.isArray(v) ? "array" : typeof v);

/** Array elements matched by shape in both directions; an empty array on either side matches any. */
function arrayDiff(real: unknown[], fake: unknown[], opts: CompareOpts, path: string): string[] {
  if (real.length === 0 || fake.length === 0) return [];
  // Report against the closest element: the same top-level keys first, then the fewest differences.
  const keys = (v: unknown) =>
    kindOf(v) === "object"
      ? Object.keys(v as object)
          .sort()
          .join(",")
      : kindOf(v);
  const rank = (a: { same: number; d: string[] }, b: { same: number; d: string[] }) => {
    if (a.d.length === 0) return -1;
    if (b.d.length === 0) return 1;
    return a.same - b.same || a.d.length - b.d.length;
  };
  const closest = (x: unknown, ys: unknown[], diff: (y: unknown) => string[]) =>
    defined(
      ys.map((y) => ({ same: keys(y) === keys(x) ? 0 : 1, d: diff(y) })).sort(rank)[0],
      "a closest candidate",
    ).d;
  const out: string[] = [];
  fake.forEach((f, i) => {
    const best = closest(f, real, (r) => shapeDiff(r, f, opts, `${path}[]`));
    if (best.length) out.push(`${path}[${i}] (fake) matches no real element: ${best.join("; ")}`);
  });
  real.forEach((r, i) => {
    const best = closest(r, fake, (f) => shapeDiff(r, f, opts, `${path}[]`));
    if (best.length) out.push(`${path}[${i}] (real) matches no fake element: ${best.join("; ")}`);
  });
  return out;
}

function objectDiff(
  ro: Record<string, unknown>,
  fo: Record<string, unknown>,
  opts: CompareOpts,
  path: string,
): string[] {
  const out: string[] = [];
  for (const k of Object.keys(ro))
    if (!(k in fo)) out.push(`${path}.${k}: only in the real answer`);
  for (const k of Object.keys(fo)) if (!(k in ro)) out.push(`${path}.${k}: only in the fake`);
  for (const k of Object.keys(ro))
    if (k in fo) out.push(...shapeDiff(ro[k], fo[k], opts, `${path}.${k}`));
  return out;
}

/**
 * Differences in structure between `real` and `fake`: the same keys at every level, the same JSON
 * type for every value, null only where both are null or the path is declared nullable, and array
 * elements matched by shape in both directions (an empty array on either side matches any array).
 */
export function shapeDiff(
  real: unknown,
  fake: unknown,
  opts: CompareOpts = {},
  path = "$",
): string[] {
  const kr = kindOf(real);
  const kf = kindOf(fake);
  if (kr === "null" || kf === "null") {
    if (kr === kf || (opts.nullable ?? []).some((p) => path.endsWith(p))) return [];
    return [`${path}: real is ${kr}, fake is ${kf}`];
  }
  if (kr !== kf) return [`${path}: real is ${kr}, fake is ${kf}`];
  if (kr === "array") return arrayDiff(real as unknown[], fake as unknown[], opts, path);
  if (kr !== "object") return [];
  if ((opts.open ?? []).some((p) => path.endsWith(p))) return [];
  return objectDiff(real as Record<string, unknown>, fake as Record<string, unknown>, opts, path);
}

type Schema = Record<string, unknown>;

function typeErrors(value: unknown, schema: Schema, path: string): string[] {
  if (schema.type === undefined) return [];
  const types = Array.isArray(schema.type) ? (schema.type as string[]) : [schema.type as string];
  const k = kindOf(value);
  const ok = types.some(
    (t) =>
      t === k ||
      (t === "integer" && typeof value === "number" && Number.isInteger(value)) ||
      (t === "number" && k === "number"),
  );
  return ok ? [] : [`${path}: ${JSON.stringify(value)} is not ${types.join(" or ")}`];
}

function scalarErrors(value: unknown, schema: Schema, path: string): string[] {
  const out: string[] = [];
  if (schema.enum && !(schema.enum as unknown[]).includes(value))
    out.push(`${path}: ${JSON.stringify(value)} not in ${JSON.stringify(schema.enum)}`);
  if ("const" in schema && schema.const !== value)
    out.push(`${path}: is not ${JSON.stringify(schema.const)}`);
  if (typeof value === "number") {
    if (typeof schema.minimum === "number" && value < schema.minimum)
      out.push(`${path}: below ${schema.minimum}`);
    if (typeof schema.maximum === "number" && value > schema.maximum)
      out.push(`${path}: above ${schema.maximum}`);
  }
  return out;
}

function arrayErrors(value: unknown[], schema: Schema, doc: Schema, path: string): string[] {
  const out: string[] = [];
  if (typeof schema.minItems === "number" && value.length < schema.minItems)
    out.push(`${path}: fewer than ${schema.minItems} items`);
  if (typeof schema.maxItems === "number" && value.length > schema.maxItems)
    out.push(`${path}: more than ${schema.maxItems} items`);
  if (schema.items)
    value.forEach((v, i) => {
      out.push(...schemaErrors(v, schema.items as Schema, doc, `${path}[${i}]`));
    });
  return out;
}

function objectErrors(
  o: Record<string, unknown>,
  schema: Schema,
  doc: Schema,
  path: string,
): string[] {
  const out: string[] = [];
  const props = (schema.properties ?? {}) as Record<string, Schema>;
  for (const r of (schema.required ?? []) as string[])
    if (!(r in o)) out.push(`${path}.${r}: required`);
  for (const [k, v] of Object.entries(o)) {
    const prop = props[k];
    if (prop) out.push(...schemaErrors(v, prop, doc, `${path}.${k}`));
    else if (schema.additionalProperties === false) out.push(`${path}.${k}: not allowed`);
    else if (schema.additionalProperties && typeof schema.additionalProperties === "object")
      out.push(...schemaErrors(v, schema.additionalProperties as Schema, doc, `${path}.${k}`));
  }
  return out;
}

/** Where `value` does not satisfy `schema` (resolved in `doc`); empty when it does. */
export function schemaErrors(value: unknown, schema: Schema, doc: Schema, path = "$"): string[] {
  if (typeof schema.$ref === "string") {
    const target = (schema.$ref as string)
      .replace(/^#\//, "")
      .split("/")
      .reduce<unknown>((o, k) => (o as Record<string, unknown>)?.[k], doc) as Schema | undefined;
    if (!target) return [`${path}: unresolved ${schema.$ref as string}`];
    return schemaErrors(value, target, doc, path);
  }
  const alts = (schema.oneOf ?? schema.anyOf) as Schema[] | undefined;
  if (alts) {
    const results = alts.map((s) => schemaErrors(value, s, doc, path));
    const passing = results.filter((r) => r.length === 0).length;
    if (schema.oneOf ? passing !== 1 : passing < 1)
      return [
        `${path}: matches ${passing} of ${alts.length} alternatives (${results.flat().join("; ")})`,
      ];
  }
  const wrongType = typeErrors(value, schema, path);
  if (wrongType.length) return wrongType;
  const out = scalarErrors(value, schema, path);
  if (Array.isArray(value)) out.push(...arrayErrors(value, schema, doc, path));
  else if (value !== null && typeof value === "object")
    out.push(...objectErrors(value as Record<string, unknown>, schema, doc, path));
  return out;
}
