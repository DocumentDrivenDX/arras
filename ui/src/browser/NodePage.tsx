// SPDX-License-Identifier: MIT OR Apache-2.0
// A node page: breadcrumb, the card (header, sections, attribution, freshness) and a side column
// with the neighbourhood picture above the relationship groups (DESIGN-GB, Screens 2 and 3).

import { useMemo, useState } from "react";
import { shortName } from "../api/gql";
import type { BackendStatus } from "../api/types";
import { Button } from "../ds";
import { linkProps, useBrowser } from "./context";
import { HistoryPanel } from "./HistoryPanel";
import { MAX_NODES } from "./layoutGroups";
import { formatExplore, saveViewState } from "./location";
import type { TypeEntry } from "./meta";
import { Neighbourhood } from "./Neighbourhood";
import { entityTitle, NodeCard } from "./NodeCard";
import { groupsOf, PAGE_LABELS, targetOf, wantedRefs } from "./planner";
import { Relations } from "./Relations";
import { BackendDown, Expired, Failed, NotAvailable, Skeleton } from "./states";
import { useLabels } from "./useLabels";
import { type Entity, useNode } from "./useNode";

export interface CrumbRoot {
  label: string;
}

function Crumbs({ root, entry, keyText }: { root: CrumbRoot; entry: TypeEntry; keyText: string }) {
  const { go } = useBrowser();
  return (
    <nav className="gb-crumbs" aria-label="Breadcrumb">
      <a {...linkProps(go, { module: entry.module.name })}>{root.label}</a>
      <span aria-hidden="true">›</span>
      <a {...linkProps(go, { module: entry.module.name, type: shortName(entry.type.name) })}>
        {entry.view.pluralLabel}
      </a>
      <span aria-hidden="true">›</span>
      <span aria-current="page">{keyText}</span>
    </nav>
  );
}

function Ready({
  entry,
  keyText,
  entity,
  root,
  history,
}: {
  entry: TypeEntry;
  keyText: string;
  entity: Entity;
  root: CrumbRoot;
  /** The address is the entity's History: the panel shows for an operator, else the page alone. */
  history?: boolean;
}) {
  const { meta, canEdit, go, ownsHistory } = useBrowser();
  const open = history === true && canEdit;
  const [shown, setShown] = useState<Record<string, number>>({});
  const groups = useMemo(() => groupsOf(entry.view, entity), [entry.view, entity]);
  const targets = useMemo(
    () => wantedRefs(groups, shown, MAX_NODES).map(targetOf),
    [groups, shown],
  );
  const labels = useLabels(meta, targets);
  const title = entityTitle(entry.view, entity, keyText);
  const status: BackendStatus[] = meta.status;
  return (
    <div className={open ? "gb-hist-shown" : undefined}>
      <Crumbs root={root} entry={entry} keyText={keyText} />
      {canEdit && !open && (
        <div className="gb-hist-open">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              const loc = {
                module: entry.module.name,
                type: shortName(entry.type.name),
                key: keyText,
                history: true,
              };
              go(loc);
              if (ownsHistory !== false && window.location.hash === formatExplore(loc))
                saveViewState({ fromEntity: true });
            }}
          >
            History
          </Button>
        </div>
      )}
      {open && <HistoryPanel entry={entry} keyText={keyText} title={title} />}
      <div className="gb-page">
        <NodeCard
          view={entry.view}
          entity={entity}
          keyText={keyText}
          status={status}
          entry={entry}
        />
        <aside className="gb-side" aria-label="Relationships">
          <Neighbourhood
            entry={entry}
            centreKey={keyText}
            centreTitle={title}
            groups={groups}
            labels={labels}
          />
          <Relations
            groups={groups}
            labels={labels}
            shown={shown}
            centre={{ entry, key: keyText }}
            onMore={(field) =>
              setShown((s) => ({ ...s, [field]: (s[field] ?? PAGE_LABELS) + PAGE_LABELS }))
            }
          />
        </aside>
      </div>
    </div>
  );
}

export function NodePage({
  entry,
  keyText,
  root,
  history,
}: {
  entry: TypeEntry;
  keyText: string;
  root: CrumbRoot;
  /** The address is the entity's History. */
  history?: boolean;
}) {
  const { go } = useBrowser();
  const { state, retry } = useNode(entry, keyText);
  switch (state.status) {
    case "loading":
      return <Skeleton label="Loading" />;
    case "na":
      return (
        <NotAvailable
          onBack={() => go({ module: entry.module.name })}
          backTo={entry.module.view?.title ?? entry.module.name}
        />
      );
    case "down":
      return <BackendDown backend={state.backend} onRetry={retry} />;
    case "expired":
      return <Expired />;
    case "error":
      return <Failed onRetry={retry} />;
    case "ready":
      return (
        <Ready
          entry={entry}
          keyText={keyText}
          entity={state.entity}
          root={root}
          history={history}
        />
      );
  }
}
