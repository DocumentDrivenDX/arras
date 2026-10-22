// SPDX-License-Identifier: MIT OR Apache-2.0
import { skipToken, useQuery } from "@tanstack/react-query";
import { shortName } from "../api/gql";
import type { ModuleInfo } from "../api/types";
import type { EntityData } from "../areas/entity";
import { useRefLabels } from "../areas/useRefLabels";
import { ViewInExplore } from "../components/ExploreLink";
import { NavLink } from "../components/NavLink";
import { entityActions } from "../kit";
import { contextOf, refPrefill } from "../lib/actionGroups";
import { refId, titleSelection } from "../lib/relLabels";
import { titleOf } from "../lib/template";
import { AREA_LABELS, HISTORY } from "../lib/vocabulary";
import type { Area, Route } from "../route";

interface EntityId {
  type: string;
  key: string;
}

/** The entity a route is about, with its full type name: an Entities, Graph or Changes entity, or an Actions prefill. */
export function entityInContext(m: ModuleInfo, route: Route): EntityId | undefined {
  let found: EntityId | undefined;
  if (route.area === "actions")
    found = contextOf(m, route.action, refPrefill(m, route.action, route.input));
  else if (route.type && route.key && ["entities", "graph", "changes"].includes(route.area))
    found = { type: route.type, key: route.key };
  if (!found) return undefined;
  const short = shortName(found.type);
  const t = m.entityTypes.find((x) => shortName(x.name) === short);
  return { type: t?.name ?? found.type, key: found.key };
}

/** The entity's title when the entity panel already read its properties, else one cached label read. */
export function useEntityName(
  m: ModuleInfo | undefined,
  ent: EntityId | undefined,
): string | undefined {
  const t = m?.entityTypes.find((x) => x.name === ent?.type);
  const select = t && titleSelection(t);
  // Subscribes to the entity panel's read without making one.
  const read = useQuery<EntityData | null>({
    queryKey: ["entity", m?.name, ent?.type, ent?.key, "LATEST"],
    queryFn: skipToken,
  });
  const props = read.data?.props;
  const have = !!(t?.view && select && props && select.every((p) => p === "key" || p in props));
  const ref = m && ent ? { module: m.name, ...ent } : undefined;
  const labels = useRefLabels(m, have || !ref ? [] : [ref]);
  if (!ent || !ref) return undefined;
  return have && t?.view ? titleOf(t.view.title, props ?? {}, ent.key) : labels[refId(ref)];
}

/** The route of the area's own list: the entity left, the area kept. */
const listRoute = (m: string, route: Route): Route => {
  switch (route.area) {
    case "entities":
      return { module: m, area: "entities", type: route.type };
    case "actions":
      return { module: m, area: "actions", action: route.action };
    default:
      return { module: m, area: route.area };
  }
};

interface View {
  id: Area;
  text: string;
  to: Route;
}

/** The entity's views: Entities, Graph, History (when Changes is served) and Actions (when one takes it). */
function viewLinks(m: ModuleInfo, route: Route, ent: EntityId, auditShown: boolean): View[] {
  const entity = (id: "entities" | "graph" | "changes", text: string): View => ({
    id,
    text,
    to: { module: m.name, area: id, type: ent.type, key: ent.key },
  });
  const views = [entity("entities", AREA_LABELS.entities), entity("graph", AREA_LABELS.graph)];
  if (auditShown) views.push(entity("changes", HISTORY));
  // In Actions the link is the current action as it is; elsewhere the first action that takes the entity.
  const first = entityActions(m, ent.type)[0];
  const to: Route | undefined =
    route.area === "actions"
      ? route
      : first && {
          module: m.name,
          area: "actions",
          action: first.action.name,
          input: { [first.keyInput.name]: ent.key },
        };
  if (to?.action)
    views.push({
      id: "actions",
      text: AREA_LABELS.actions,
      to,
    });
  return views;
}

const LINK = "rounded px-1.5 py-0.5 text-[12px] text-accent hover:underline";
const CURRENT = "rounded bg-accentsoft px-1.5 py-0.5 text-[12px] font-semibold text-fg";

/**
 * Where you are: the entity the route names, its type and key (and name), links to its Entities,
 * Graph, History and Actions views with the current one marked, and a control that returns to the
 * area's list. Nothing when no entity is in context.
 */
export function EntityContextBar({
  module: m,
  route,
  auditShown,
  go,
}: {
  module: ModuleInfo;
  route: Route;
  auditShown: boolean;
  go: (r: Route) => void;
}) {
  // The prefill of an address is read only as far as it fits the action (`refPrefill`).
  const fits: Route =
    route.area === "actions"
      ? { ...route, input: refPrefill(m, route.action, route.input) }
      : route;
  const ent = entityInContext(m, fits);
  if (!ent) return null;
  return <Bar m={m} route={fits} ent={ent} auditShown={auditShown} go={go} />;
}

function Bar({
  m,
  route,
  ent,
  auditShown,
  go,
}: {
  m: ModuleInfo;
  route: Route;
  ent: EntityId;
  auditShown: boolean;
  go: (r: Route) => void;
}) {
  const name = useEntityName(m, ent);
  const label = shortName(ent.type);
  const area = route.area;
  return (
    <nav
      aria-label="Entity context"
      data-testid="entity-context"
      className="mb-1.5 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[12px]"
    >
      <span className="min-w-0 break-words font-semibold" data-testid="entity-context-name">
        {label} · <span className="arras-mono">{ent.key}</span>
        {name && name !== ent.key && <span className="ml-1 font-normal text-muted">{name}</span>}
      </span>
      <span className="flex flex-wrap items-center gap-0.5">
        {viewLinks(m, route, ent, auditShown).map((v) => (
          <NavLink
            key={v.id}
            to={v.to}
            aria-current={area === v.id ? "page" : undefined}
            aria-label={`${v.text} of ${label} ${ent.key}`}
            className={area === v.id ? CURRENT : LINK}
          >
            {v.text}
          </NavLink>
        ))}
      </span>
      <ViewInExplore
        target={{ entity: { module: m.name, type: ent.type, key: ent.key } }}
        area={area === "changes" ? "history" : "entities"}
        label={`${label} ${ent.key}`}
        className={LINK}
      />
      <button
        type="button"
        className="rounded px-1.5 text-muted hover:text-fg"
        aria-label={`Clear ${label} ${ent.key}; back to the ${AREA_LABELS[area]} list`}
        title="Back to the list"
        onClick={() => go(listRoute(m.name, route))}
      >
        ×
      </button>
    </nav>
  );
}
