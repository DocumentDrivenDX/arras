// SPDX-License-Identifier: MIT OR Apache-2.0
// What the module reader's parts share (CONTRACT-012): the name rules of CONTRACT-002, the violation
// constructor and the case-folded name registry of `arras/umf.py` and `arras/names.py`.
import type { Violation } from "./model";

export const MODULE_NAME = /^[a-z][a-z0-9_]{0,40}$/;
const NAME = /^[A-Za-z][A-Za-z0-9_]{0,63}$/;
const RESERVED = new Set(
  (
    "Query Mutation Subscription Entity Page Ref Freshness Revision Module Status JSON DateTime " +
    "BigInt Decimal Base64 String Int Float Boolean ID ref key type version revision freshness " +
    "references Consistency"
  ).split(" "),
);

export type Obj = Record<string, unknown>;
export const isObj = (v: unknown): v is Obj =>
  typeof v === "object" && v !== null && !Array.isArray(v);
export const obj = (v: unknown): Obj => (isObj(v) ? v : {});
export const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
export const doc = (path: string, message: string): Violation => ({
  path,
  code: "invalid_document",
  message,
});

export function checkName(name: string, path: string, entityType = false): Violation | null {
  if (!NAME.test(name))
    return {
      path,
      code: "invalid_name",
      message: `'${name}' must match [A-Za-z][A-Za-z0-9_]{0,63}`,
    };
  if (RESERVED.has(name))
    return { path, code: "invalid_name", message: `'${name}' is a reserved name` };
  if (entityType && (name.endsWith("Page") || name.endsWith("List")))
    return {
      path,
      code: "invalid_name",
      message: `type name '${name}' must not end in Page or List`,
    };
  return null;
}

/** Names that share one case-folded namespace within a module. */
export class Names {
  seen = new Map<string, string>();
  constructor(readonly out: Violation[]) {}
  add(name: string, path: string): void {
    const folded = name.toLowerCase();
    const was = this.seen.get(folded);
    if (was === undefined) {
      this.seen.set(folded, name);
      return;
    }
    const how = was === name ? "is declared twice" : "differs only by case from";
    const other = was === name ? "" : ` '${was}'`;
    this.out.push({ path, code: "invalid_name", message: `'${name}' ${how}${other}` });
  }
}

export const text = (v: unknown, path: string, what: string, out: Violation[]): string | null => {
  if (typeof v === "string" && v) return v;
  out.push(doc(path, `${what} is missing`));
  return null;
};
