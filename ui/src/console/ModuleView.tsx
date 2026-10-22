// SPDX-License-Identifier: MIT OR Apache-2.0
import { useEffect, useMemo, useState } from "react";
import type { ModuleInfo } from "../api/types";
import { ActionsArea } from "../areas/ActionsArea";
import { AuditView } from "../areas/AuditView";
import { NotFound } from "../areas/ConsoleNotices";
import { DataArea } from "../areas/DataArea";
import { GraphArea } from "../areas/GraphArea";
import { QueryArea } from "../areas/QueryArea";
import { SchemaBrowser } from "../areas/SchemaBrowser";
import type { QueryStarter } from "../areas/useQueryStarter";
import { NavProvider } from "../components/NavLink";
import type { LinkTo } from "../kit";
import type { Area, Route } from "../route";
import { EntityContextBar } from "./EntityContextBar";
import { ModuleHeader } from "./ModuleHeader";
import type { Go } from "./useRoute";
import { useRouteBindings } from "./useRouteBindings";
import type { ViewState } from "./viewState";

/**
 * One module: its header (title, context slot, area tabs) and the chosen area. The open entity, the
 * graph selection, the history entity and the action prefill are read from `route`; each area reports
 * a navigation through `go`, which pushes a history entry.
 */
export function ModuleView({
  module: current,
  route,
  go,
  area,
  auditShown,
  s,
  explorerBase,
  toExplore,
  fragment,
}: {
  module: ModuleInfo;
  route: Route;
  go: Go;
  area: Area;
  auditShown: boolean;
  s: ViewState;
  explorerBase?: string;
  /** The link into Explore, handed in by the shell for an operator. */
  toExplore?: LinkTo;
  /** Where the fragment is the location, the prefix its routes carry (see `NavProvider`). */
  fragment?: { prefix?: string };
}) {
  const m = current.name;
  const { lastAction, setLastAction } = s;
  // A starter statement another area opens the Query area with (a type's card in Model).
  const [starter, setStarter] = useState<QueryStarter | undefined>();
  // The Entities area always names its type, so the address is the screen (the first type by default).
  const defaultType = current.entityTypes[0]?.name;
  useEffect(() => {
    if (area === "entities" && !route.type && defaultType)
      go({ module: m, area: "entities", type: defaultType }, { replace: true });
  }, [area, route.type, defaultType, m, go]);
  const { type: routeType, key: routeKey } = route;
  const selected = useMemo(
    () => (routeType && routeKey ? { type: routeType, key: routeKey } : null),
    [routeType, routeKey],
  );
  const { address, onAddress, onChanges, onEmptyGroup, entitiesType, notFound, own } =
    useRouteBindings(current, route, area, go, defaultType);
  const { filter } = route;
  const umfShown = area === "model" && own?.view === "umf";
  const openAction = (action: string | undefined, pre?: Record<string, string>) => {
    setLastAction(action);
    go({
      module: m,
      area: "actions",
      action,
      input: pre && Object.keys(pre).length ? pre : undefined,
    });
  };
  const openHistory = auditShown
    ? (type: string, key: string) => go({ module: m, area: "changes", type, key })
    : undefined;
  return (
    <NavProvider go={go} auditShown={auditShown} toExplore={toExplore} fragment={fragment}>
      <div className="flex min-h-0 flex-1 flex-col">
        <ModuleHeader
          module={m}
          context={
            <EntityContextBar module={current} route={route} auditShown={auditShown} go={go} />
          }
          area={area}
          auditShown={auditShown}
          onArea={(a) =>
            go({
              module: m,
              area: a,
              type: a === "entities" ? route.type : undefined,
              action: a === "actions" ? (route.action ?? lastAction) : undefined,
            })
          }
        />
        <div className="flex min-h-0 flex-1 flex-col overflow-auto" role="tabpanel">
          {notFound && <NotFound module={m} />}
          {!notFound && area === "model" && (
            <SchemaBrowser
              module={m}
              explorerBase={explorerBase}
              selectedType={own?.type}
              umf={umfShown}
              onSelectType={(type) =>
                go({
                  module: m,
                  area: "model",
                  type,
                  view: own?.view === "umf" ? "umf" : undefined,
                })
              }
              onView={(umf) =>
                go({ module: m, area: "model", type: own?.type, view: umf ? "umf" : undefined })
              }
              onOpenData={(type) => go({ module: m, area: "entities", type })}
              onShowGraph={(type) => {
                s.setGraphType(type);
                go({ module: m, area: "graph" });
              }}
              onOpenActions={(_type, action) => openAction(action)}
              onOpenQuery={(type) => {
                setStarter((n) => ({ type, id: (n?.id ?? 0) + 1 }));
                go({ module: m, area: "query" });
              }}
            />
          )}
          {!notFound && area === "graph" && (
            <GraphArea
              module={m}
              initial={route.area === "graph" ? selected : null}
              onSelect={(e) => go({ module: m, area: "graph", type: e?.type, key: e?.key })}
              onlyType={s.graphType}
              changed={s.changed}
              onDismissChanged={() => s.setChanged(null)}
              onAction={openAction}
              onHistory={openHistory}
              onOpenModule={(mod) => go({ module: mod, area: "graph" })}
            />
          )}
          {!notFound && area === "entities" && (
            <DataArea
              module={m}
              type={route.type}
              entity={route.key}
              address={address}
              onAddress={onAddress}
              onType={(t) => go({ module: m, area: "entities", type: t })}
              onEntity={(key) =>
                go({
                  module: m,
                  area: "entities",
                  type: entitiesType,
                  key: key ?? undefined,
                  filter,
                })
              }
              onAction={openAction}
              onGraph={(type, key) => go({ module: m, area: "graph", type, key })}
              onHistory={openHistory}
              onOpenModule={(mod) => go({ module: mod, area: "entities" })}
              onQuery={(type) => {
                setStarter((n) => ({ type, id: (n?.id ?? 0) + 1 }));
                go({ module: m, area: "query" });
              }}
            />
          )}
          {!notFound && area === "actions" && (
            <ActionsArea
              module={m}
              action={route.action ?? lastAction}
              prefill={route.input}
              onAction={(a) => openAction(a)}
              onNextAction={openAction}
              onViewInGraph={(c) => {
                s.setChanged(c);
                go({ module: m, area: "graph" });
              }}
            />
          )}
          {!notFound && area === "query" && (
            <QueryArea
              module={m}
              starter={starter}
              onOpenEntity={(type, key) => go({ module: m, area: "entities", type, key })}
            />
          )}
          {!notFound && area === "changes" && auditShown && (
            <AuditView
              key={m}
              module={m}
              entity={selected}
              group={route.group}
              action={route.action}
              since={route.since}
              until={route.until}
              loads={route.view === "loads"}
              onAddress={onChanges}
              onEmptyGroup={onEmptyGroup}
            />
          )}
        </div>
      </div>
    </NavProvider>
  );
}
