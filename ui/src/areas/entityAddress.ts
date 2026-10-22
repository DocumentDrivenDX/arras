// SPDX-License-Identifier: MIT OR Apache-2.0
import { useEffect, useMemo, useRef } from "react";
import type { Column } from "../api/gql";
import type { Route } from "../route";
import type { Sort } from "./pageSort";

/**
 * What the Entities route says about the table (CONTRACT-010 D): the filter on the key column, the
 * key the page starts after and the sort. Page size, consistency, visible columns and every other
 * filter stay in memory.
 */
export interface TableAddress {
  filter?: Record<string, string>;
  after?: string;
  sort?: Route["sort"];
}

/** Asks for an address; `replace` rewrites the current history entry instead of adding one. */
export type WriteAddress = (address: TableAddress, how: { replace: boolean }) => void;

/** How long a filter must rest before it is written to the address. */
export const SETTLE_MS = 300;

/** The table's state that the address can carry. */
export interface AddressedState {
  filter: Record<string, string>;
  afterKeys: (string | null)[];
  page: number;
  sort: Sort | null;
}

/**
 * The part of an applied filter the address may carry: the key column's, whose value is a key. A
 * filter on any other column (typed text, a person in an attribution column) is never written.
 */
export function keyFilter(
  filter: Record<string, string>,
  keyName: string | undefined,
): Record<string, string> | undefined {
  if (!keyName || !Object.hasOwn(filter, keyName)) return undefined;
  const value = filter[keyName]?.trim();
  return value ? { [keyName]: value } : undefined;
}

/** The sort in the address's terms: the column's label, which is the property's name. */
export function sortToAddress(sort: Sort | null, cols: Column[]): TableAddress["sort"] {
  const col = sort ? cols.find((c) => c.id === sort.colId) : undefined;
  return sort && col ? { column: col.label, dir: sort.dir } : undefined;
}

/** The sort an address names, when its column is one of the type's. */
export function sortFromAddress(sort: TableAddress["sort"], cols: Column[]): Sort | null {
  const col = sort ? cols.find((c) => c.label === sort.column) : undefined;
  return sort && col ? { colId: col.id, dir: sort.dir } : null;
}

/** The address of a table state: only what the route may carry, key column filter included. */
export function addressOf(
  s: AddressedState,
  cols: Column[],
  keyName: string | undefined,
): TableAddress {
  return {
    filter: keyFilter(s.filter, keyName),
    after: s.afterKeys[s.page] ?? undefined,
    sort: sortToAddress(s.sort, cols),
  };
}

/** A string that is equal for equal addresses. */
export const addressKey = (a: TableAddress | undefined): string =>
  JSON.stringify([
    Object.entries(a?.filter ?? {}).sort(([x], [y]) => x.localeCompare(y)),
    a?.after ?? null,
    a?.sort ? [a.sort.column, a.sort.dir] : null,
  ]);

/**
 * The two ways the table writes its address: `push` for a move (a page, a sort), at once, and
 * `settle` for a refinement (a filter), which replaces the current entry once nothing newer has
 * come for `SETTLE_MS`. A push drops a refinement still waiting, since it carries the whole address.
 */
export function useAddressWriter(write: WriteAddress | undefined) {
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const latest = useRef(write);
  latest.current = write;
  useEffect(() => () => clearTimeout(timer.current), []);
  return useMemo(
    () => ({
      push: (a: TableAddress) => {
        clearTimeout(timer.current);
        latest.current?.(a, { replace: false });
      },
      settle: (a: TableAddress) => {
        clearTimeout(timer.current);
        timer.current = setTimeout(() => latest.current?.(a, { replace: true }), SETTLE_MS);
      },
    }),
    [],
  );
}
