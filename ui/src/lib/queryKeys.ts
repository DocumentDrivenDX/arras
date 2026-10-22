// SPDX-License-Identifier: MIT OR Apache-2.0
import type { EntityTypeInfo, QueryColumn } from "../api/types";

/** A name as written in a statement: bare, or a Weft quoted identifier (a doubled quote is one quote). */
const IDENT = '(?:[A-Za-z][A-Za-z0-9_]*|"(?:[^"]|"")+")';
const FROM_TYPE = new RegExp(`\\bfrom\\s+(${IDENT})\\s*\\.\\s*(${IDENT})`, "gi");
const COMMA_LIST = new RegExp(`^\\s*(?:as\\s+)?(?:${IDENT})?\\s*,`, "i");
const unquote = (s: string) => (s.startsWith('"') ? s.slice(1, -1).replaceAll('""', '"') : s);

/** Statement text with its string literals and comments blanked, so a keyword inside one is not read. */
function bare(sql: string): string {
  return sql
    .replace(/'(?:[^']|'')*'/g, "''")
    .replace(/--[^\n]*/g, " ")
    .replace(/\/\*[\s\S]*?\*\//g, " ");
}

/**
 * The type whose key a result's key column holds: the one `FROM <module>.<Type>` of a statement that reads a single
 * type (no JOIN, no second FROM, no comma list, no set operation), when that type is one the module declares.
 * The statement is not parsed: anything this does not recognise gives `null`, and the cells stay plain text.
 */
export function keyedType(
  sql: string,
  module: string,
  types: readonly EntityTypeInfo[],
): EntityTypeInfo | null {
  const text = bare(sql);
  const found = [...text.matchAll(FROM_TYPE)];
  const only = found[0];
  if (found.length !== 1 || !only) return null;
  if ((text.match(/\bfrom\b/gi) ?? []).length !== 1) return null;
  if (/\b(join|union|intersect|except)\b/i.test(text)) return null;
  const [whole, mod, name] = only;
  if (mod === undefined || name === undefined || unquote(mod) !== module) return null;
  if (COMMA_LIST.test(text.slice((only.index ?? 0) + whole.length))) return null;
  return types.find((t) => t.name === `${module}.${unquote(name)}`) ?? null;
}

/** The result column that holds the entity key: the declared key's own scalar column. */
export function keyColumn(
  columns: readonly QueryColumn[],
  type: EntityTypeInfo | null,
): string | null {
  if (!type) return null;
  const c = columns.find((x) => x.name === type.key);
  return c?.scalar ? c.name : null;
}
