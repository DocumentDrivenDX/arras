// SPDX-License-Identifier: MIT OR Apache-2.0
import { useEffect, useRef, useState } from "react";
import type { Column } from "../api/gql";
import {
  type AddressedState,
  addressKey,
  addressOf,
  sortFromAddress,
  type TableAddress,
  useAddressWriter,
  type WriteAddress,
} from "./entityAddress";
import { nextSort, type Sort } from "./pageSort";
import { trimmedFilter } from "./useEntityList";

interface View extends AddressedState {
  /** What is typed in the filter fields; the applied `filter` follows on Enter or blur. */
  draft: Record<string, string>;
}

const viewFrom = (a: TableAddress | undefined, cols: Column[]): View => ({
  draft: { ...a?.filter },
  filter: { ...a?.filter },
  afterKeys: a?.after ? [null, a.after] : [null],
  page: a?.after ? 1 : 0,
  sort: sortFromAddress(a?.sort, cols),
});

export interface TableStateArgs {
  scope: string;
  cols: Column[];
  keyName: string | undefined;
  /** The address the route holds, when the table is bound to one. */
  address?: TableAddress;
  /** An entity is open on the table; the route then carries no page or sort, so it is not read. */
  entityOpen: boolean;
  onAddress?: WriteAddress;
}

/**
 * The table's filter, page position and sort, and how they meet the address.
 *
 * - They start from the address, and a different one that arrives while the table stays (Back, a link) is
 *   adopted; the address the table itself wrote comes back equal and changes nothing.
 * - A page move or a sort is written as a push; an applied filter is written as a replace once it settles.
 * - Only the key column's filter is written (`addressOf`); the others stay here.
 * - A new `scope` (another type or module) starts afresh from the address.
 */
export function useTableState(a: TableStateArgs) {
  const { scope, cols, keyName, address, entityOpen, onAddress } = a;
  const [view, setView] = useState<View>(() => viewFrom(address, cols));
  const [seen, setSeen] = useState({ scope, key: addressKey(address) });
  const writer = useAddressWriter(onAddress);
  const key = addressKey(address);
  const current = addressOf(view, cols, keyName);
  if (seen.scope !== scope) {
    setSeen({ scope, key });
    setView(viewFrom(address, cols));
  } else if (seen.key !== key) {
    setSeen({ scope, key });
    if (!entityOpen && key !== addressKey(current)) setView(viewFrom(address, cols));
  }

  const commit = (next: View, how: "push" | "settle") => {
    setView(next);
    const written = addressOf(next, cols, keyName);
    if (addressKey(written) === addressKey(current)) return;
    writer[how](written);
  };
  const first = { afterKeys: [null], page: 0 };

  // Closing the entity returns to the list as the table holds it: the route has to say its page and sort again.
  const open = useRef(entityOpen);
  useEffect(() => {
    if (open.current && !entityOpen) writer.settle(addressOf(view, cols, keyName));
    open.current = entityOpen;
  }, [entityOpen, writer, view, cols, keyName]);

  return {
    ...view,
    setDraft: (name: string, value: string) =>
      setView((v) => ({ ...v, draft: { ...v.draft, [name]: value } })),
    applyFilter: () => {
      const next = trimmedFilter(view.draft);
      if (JSON.stringify(next) === JSON.stringify(view.filter)) return;
      commit({ ...view, filter: next, ...first }, "settle");
    },
    clearFilter: () => commit({ ...view, draft: {}, filter: {}, ...first }, "settle"),
    restart: () => commit({ ...view, ...first }, "push"),
    sortBy: (colId: string) => commit({ ...view, sort: nextSort(view.sort, colId) }, "push"),
    clearSort: () => commit({ ...view, sort: null as Sort | null }, "push"),
    previous: () => commit({ ...view, page: view.page - 1 }, "push"),
    next: (after: string) =>
      commit(
        {
          ...view,
          afterKeys: [...view.afterKeys.slice(0, view.page + 1), after],
          page: view.page + 1,
        },
        "push",
      ),
  };
}
