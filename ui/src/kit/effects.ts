// SPDX-License-Identifier: MIT OR Apache-2.0
// Reading the wire's tagged shapes of a declared action's effects (CONTRACT-003, the meta read): an
// expression is `{name}` (the meta read) or `{input}` (the UMF document) for an input, `{alias}` for
// an earlier effect's alias and `{kind: "uuid"}` (or `{generate}`) for a generated key.
import { shortName } from "../api/gql";
import type { EffectDecl } from "../api/types";

interface Tagged {
  name?: unknown;
  input?: unknown;
  alias?: unknown;
  kind?: unknown;
  generate?: unknown;
}

const tagged = (expr: unknown): Tagged =>
  expr && typeof expr === "object" ? (expr as Tagged) : {};

/** The input an expression names, if it is an input. */
export function inputOf(expr: unknown): string | undefined {
  const o = tagged(expr);
  const n = o.name ?? o.input;
  return typeof n === "string" ? n : undefined;
}

/** The alias an expression names, if it is an earlier effect's alias. */
export function aliasKeyOf(expr: unknown): string | undefined {
  const a = tagged(expr).alias;
  return typeof a === "string" ? a : undefined;
}

/** True when the expression is a generated key. */
export function isGenerated(expr: unknown): boolean {
  const o = tagged(expr);
  return o.kind === "uuid" || o.generate !== undefined;
}

/** The alias an effect declares for what it creates (`alias` in the meta read, `as` in the document). */
export function declaredAlias(e: EffectDecl): string | undefined {
  const a = e.alias ?? e.as;
  return typeof a === "string" && a ? a : undefined;
}

/** The meta read spells the field `ref_type`; the UMF document spells it `refType`. */
export const refTypeOf = (e: EffectDecl): string =>
  String((e.ref_type ?? e.refType ?? "") as string);

/** True when the effect acts on this type (qualified or short). */
export const actsOn = (e: EffectDecl, type: string): boolean =>
  shortName(refTypeOf(e)) === shortName(type);
