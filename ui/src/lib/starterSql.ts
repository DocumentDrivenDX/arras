// SPDX-License-Identifier: MIT OR Apache-2.0
import { weftName, weftType } from "../api/gql";
import type { EntityTypeInfo } from "../api/types";

/** The rows a starter asks for. */
export const STARTER_LIMIT = 50;
/** Declared properties selected besides the key. */
export const STARTER_PROPERTIES = 4;

const NAME = /^[A-Za-z][A-Za-z0-9_]{0,63}$/;

/**
 * A starting statement for a type: the key, then its first few declared properties, as Weft quoted identifiers
 * (`weftName`, `weftType`), ordered by the key. Only names the registry admits are written; a property whose name
 * is not is left out, and without an admitted key there is no starter (`null`). Nothing is parsed.
 */
export function starterSql(type: EntityTypeInfo): string | null {
  if (!NAME.test(type.key)) return null;
  const names = type.properties
    .map((p) => p.name)
    .filter((n) => n !== type.key && NAME.test(n))
    .slice(0, STARTER_PROPERTIES);
  const select = [type.key, ...names].map((n) => `u.${weftName(n)}`).join(", ");
  return `SELECT ${select} FROM ${weftType(type.name)} u ORDER BY u.${weftName(type.key)} LIMIT ${STARTER_LIMIT}`;
}
