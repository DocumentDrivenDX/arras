// SPDX-License-Identifier: MIT OR Apache-2.0
import { useMemo, useRef, useState } from "react";
import {
  type Column,
  columnsFor,
  defaultColumns,
  filterable,
  nextAfterKey,
  selectionCost,
} from "../api/gql";
import { useModule } from "../api/queries";
import { useSingleKeys } from "../components/SingleKeys";
import { Empty, ErrorPanel, Spinner } from "../components/ui";
import { HiddenFilters, hiddenFilters } from "./EntityFilters";
import { FreshnessLine } from "./EntityFreshness";
import { Grid } from "./EntityGrid";
import { Pager, QueryErrors, Toolbar } from "./EntityTableParts";
import type { TableAddress, WriteAddress } from "./entityAddress";
import { sortRows } from "./pageSort";
import {
  filterNameFor,
  sortSummary,
  toggledColumns,
  useListQuery,
  useRowFocus,
  useStatusRefresh,
} from "./useEntityList";
import { useTableState } from "./useTableState";

export { FreshnessBar } from "./EntityFreshness";

export interface EntityTableProps {
  module: string;
  type: string;
  selectedKey?: string | null;
  /** Called when a row is opened (Enter or click). */
  onOpen?: (key: string) => void;
  /** Opens the Query area on this type; the toolbar button shows only when given. */
  onQuery?: (type: string) => void;
  /** The filter on the key column, the page start and the sort the route holds; the table starts from them. */
  address?: TableAddress;
  /** Told each change of the address: a page or sort as a push, a settled filter as a replace. */
  onAddress?: WriteAddress;
}

/** US-061: a dense, paged, filterable table of one type with LATEST/BULK and the page's freshness. Pages follow
 * the key: page `i` reads the entities after `afterKeys[i]`, the last key of the page before. */
export function EntityTable({
  module: name,
  type,
  selectedKey,
  onOpen,
  onQuery,
  address,
  onAddress,
}: EntityTableProps) {
  const { module: m, meta } = useModule(name);
  const singleKeys = useSingleKeys();
  const t = m?.entityTypes.find((e) => e.name === type);
  const allCols = useMemo(() => (m && t ? columnsFor(m, t) : []), [m, t]);
  const [colIds, setColIds] = useState<string[] | null>(null);
  const [consistency, setConsistency] = useState<"LATEST" | "BULK">("LATEST");
  const [limit, setLimit] = useState(50);
  const [lastReset, setLastReset] = useState(`${name}|${type}`);
  const filterRef = useRef<HTMLInputElement | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const state = useTableState({
    scope: `${name}|${type}`,
    cols: allCols,
    keyName: t?.key,
    address,
    entityOpen: selectedKey != null,
    onAddress,
  });

  // A different type or module starts a fresh table.
  const reset = `${name}|${type}`;
  if (lastReset !== reset) {
    setLastReset(reset);
    setColIds(null);
  }

  const visibleIds = colIds ?? defaultColumns(allCols);
  const visible = allCols.filter((c) => visibleIds.includes(c.id));
  const cost = selectionCost(visible);
  const fcap = m && t ? filterable(m, t) : { columns: [], relationships: [] };
  const filterName = (c: Column) => filterNameFor(c, t, fcap);

  const list = useListQuery({
    name,
    type,
    t,
    m,
    visible,
    filter: state.filter,
    limit,
    afterKey: state.afterKeys[state.page] ?? null,
    consistency,
  });
  const data = list.data?.data ?? null;
  const errors = list.data?.errors ?? [];
  // The list read orders by key only: a sort reorders the page already read.
  const rows = data?.items;
  const items = useMemo(
    () => sortRows(rows ?? [], visible, state.sort),
    [rows, visible, state.sort],
  );

  useStatusRefresh(data);
  const { focus, setFocus, onRowKey, focusRow } = useRowFocus(
    data,
    items.length,
    rootRef,
    filterRef,
    singleKeys,
  );

  if (meta.isPending) return <Spinner label="Loading schema" />;
  if (meta.error) return <ErrorPanel error={meta.error} />;
  if (!m || !t) return <Empty title="No such type" />;

  const toggleCol = (c: Column) => {
    const next = toggledColumns(visibleIds, c);
    if (next) setColIds(next);
  };
  const firstFilterCol = visible.find((c) => filterName(c));
  const hasFilter = Object.keys(state.filter).length > 0;
  const next = nextAfterKey(data);

  return (
    <div ref={rootRef} className="flex min-h-0 min-w-0 flex-1 flex-col" data-testid="entity-table">
      <Toolbar
        consistency={consistency}
        onConsistency={(c) => {
          setConsistency(c);
          state.restart();
        }}
        allCols={allCols}
        visibleIds={visibleIds}
        visibleCount={visible.length}
        cost={cost}
        onToggle={toggleCol}
        limit={limit}
        onLimit={(n) => {
          setLimit(n);
          state.restart();
        }}
        hasFilter={hasFilter}
        onClearFilter={state.clearFilter}
        onQuery={onQuery && (() => onQuery(t.name))}
      />

      <FreshnessLine freshness={data?.freshness} hasData={!!data} module={m} />

      <HiddenFilters
        entries={hiddenFilters(allCols, visibleIds, fcap, filterName)}
        draft={state.draft}
        onDraft={state.setDraft}
        onApply={state.applyFilter}
      />

      <QueryErrors errors={errors} onRetry={() => void list.refetch()} fetching={list.isFetching} />
      {list.error && <ErrorPanel error={list.error} onRetry={() => void list.refetch()} />}

      <Grid
        typeName={t.name}
        visible={visible}
        items={items}
        focus={focus}
        selectedKey={selectedKey}
        draft={state.draft}
        hasFilter={hasFilter}
        pending={list.isPending}
        failed={!!list.error}
        hasErrors={errors.length > 0}
        sort={state.sort}
        onSort={(c) => state.sortBy(c.id)}
        filterName={filterName}
        firstFilterCol={firstFilterCol}
        filterRef={filterRef}
        onRowKey={onRowKey}
        onFilterEscape={focusRow}
        onDraft={state.setDraft}
        onApplyFilter={state.applyFilter}
        onRowClick={(i, key) => {
          setFocus(i);
          onOpen?.(key);
        }}
      />

      <Pager
        page={state.page}
        rowCount={items.length}
        fetching={list.isFetching}
        data={data}
        hasNext={next !== undefined}
        sorted={sortSummary(state.sort, visible)}
        onClearSort={state.clearSort}
        onPrevious={state.previous}
        onNext={() => next !== undefined && state.next(next)}
      />
    </div>
  );
}
