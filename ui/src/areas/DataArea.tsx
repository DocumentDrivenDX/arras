// SPDX-License-Identifier: MIT OR Apache-2.0

import { useEffect, useRef, useState } from "react";
import { shortName } from "../api/gql";
import { useModule } from "../api/queries";
import { TabList } from "../components/Tabs";
import { Empty, ErrorPanel, Spinner } from "../components/ui";
import { Button } from "../ds";
import { EntityPanel } from "./EntityPanel";
import { EntityTable } from "./EntityTable";
import type { Entry } from "./entity";
import type { TableAddress, WriteAddress } from "./entityAddress";

export interface DataAreaProps {
  module: string;
  type?: string;
  /** The key of the entity open on the table (from the route); with `onEntity` the route owns it. */
  entity?: string | null;
  /** The table's filter on the key column, page start and sort, from the route; the table starts from them. */
  address?: TableAddress;
  /** The table changed its address: a page or sort as a push, a settled filter as a replace. */
  onAddress?: WriteAddress;
  onType: (type: string) => void;
  /** The open entity changed: a key, or null when the panel is closed. */
  onEntity?: (key: string | null) => void;
  onAction?: (action: string, prefill: Record<string, string>) => void;
  onHistory?: (type: string, key: string) => void;
  onOpenModule?: (module: string) => void;
  onGraph?: (type: string, key: string) => void;
  /** Open the Query area on this type; the table's "Query this type" button shows only when given. */
  onQuery?: (type: string) => void;
}

const rootTrail = (
  module: string,
  type: string | undefined,
  key: string | null | undefined,
): Entry[] => (type && key ? [{ module, type, key }] : []);

/**
 * Closing the panel returns the keyboard to the table's row, unless the user already moved focus somewhere
 * the panel did not hold (the table stays mounted while a narrow viewport shows the panel alone).
 */
function useRefocusRow(
  open: boolean,
  panel: React.RefObject<HTMLElement | null>,
  table: React.RefObject<HTMLElement | null>,
) {
  const was = useRef(open);
  useEffect(() => {
    if (was.current && !open) {
      const a = document.activeElement;
      if (!a || a === document.body || panel.current?.contains(a))
        table.current?.querySelector<HTMLElement>('button[data-row-stop][tabindex="0"]')?.focus();
    }
    was.current = open;
  }, [open, panel, table]);
}

/**
 * The open entity and the references followed from it. The trail's root is the route's entity: a different module,
 * type or entity from outside (Back, a link) replaces the trail; a root the panel itself chose already is the route's.
 */
function useTrail(
  name: string,
  type: string | undefined,
  entity: string | null | undefined,
  onEntity: ((key: string | null) => void) | undefined,
) {
  const [trail, setTrail] = useState<Entry[]>(() => rootTrail(name, type, entity));
  const scope = `${name}|${type ?? ""}|${entity ?? ""}`;
  const [lastScope, setLastScope] = useState(scope);
  if (lastScope !== scope) {
    setLastScope(scope);
    const root = trail[0];
    if (!root || root.module !== name || root.type !== type || root.key !== (entity ?? null))
      setTrail(rootTrail(name, type, entity));
  }
  const setOpen = (t: Entry[]) => {
    setTrail(t);
    if (t[0]?.key !== trail[0]?.key) onEntity?.(t[0]?.key ?? null);
  };
  return [trail, setOpen] as const;
}

/**
 * Type picker, table and entity panel (US-061). From `md` up the table and the panel sit side by side; below it
 * they take turns: opening an entity replaces the table with the panel under a "Back to list" bar (the table
 * stays mounted, so its page, filter, sort and focused row are as they were).
 */
export function DataArea({
  module: name,
  type,
  entity,
  address,
  onAddress,
  onType,
  onEntity,
  onAction,
  onHistory,
  onOpenModule,
  onGraph,
  onQuery,
}: DataAreaProps) {
  const { module: m, meta } = useModule(name);
  const current = type ?? m?.entityTypes[0]?.name;
  const [trail, setOpen] = useTrail(name, current, entity, onEntity);
  const panelRef = useRef<HTMLDivElement>(null);
  const tableRef = useRef<HTMLDivElement>(null);
  useRefocusRow(!!trail[0], panelRef, tableRef);
  if (meta.isPending) return <Spinner label="Loading schema" />;
  if (meta.error) return <ErrorPanel error={meta.error} />;
  if (!m) return null;
  if (m.entityTypes.length === 0) return <Empty title="This module declares no types" />;
  const open = trail[0];
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <TabList
        label="Types"
        className="flex gap-1 overflow-x-auto border-b border-line bg-surface px-3 pt-1.5"
        items={m.entityTypes.map((t) => ({ id: t.name, label: shortName(t.name) }))}
        selected={current}
        onSelect={onType}
        tabClass={(on) =>
          `rounded-t border border-b-0 px-3 py-1 text-[12px] ${on ? "border-line bg-bg font-semibold text-fg" : "border-transparent text-muted hover:text-fg"}`
        }
      />
      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        {current && (
          <div
            ref={tableRef}
            className={`min-h-0 min-w-0 flex-1 flex-col ${open ? "hidden md:flex" : "flex"}`}
            data-testid="data-table-pane"
          >
            <EntityTable
              module={name}
              type={current}
              selectedKey={trail[0]?.key ?? null}
              address={address}
              onAddress={onAddress}
              onOpen={(key) => setOpen([{ module: name, type: current, key }])}
              onQuery={onQuery}
            />
          </div>
        )}
        {open && (
          <div
            ref={panelRef}
            className="flex min-h-0 flex-1 flex-col overflow-auto md:contents"
            data-testid="data-panel-pane"
          >
            <div className="sticky top-0 z-10 border-b border-line bg-surface px-3 py-1.5 md:hidden">
              <Button variant="text" size="sm" onClick={() => setOpen([])}>
                ← Back to list
              </Button>
            </div>
            <EntityPanel
              module={name}
              trail={trail}
              onTrail={setOpen}
              onClose={() => setOpen([])}
              onAction={onAction}
              onHistory={onHistory}
              onOpenModule={onOpenModule}
              onGraph={onGraph}
            />
          </div>
        )}
      </div>
    </div>
  );
}
