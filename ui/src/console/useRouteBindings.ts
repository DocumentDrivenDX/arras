// SPDX-License-Identifier: MIT OR Apache-2.0
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ModuleInfo } from "../api/types";
import type { AuditAddress } from "../areas/auditAddress";
import type { TableAddress } from "../areas/entityAddress";
import type { Area, Route } from "../route";
import { namesUndeclared, useEntityMissing } from "./routeGate";
import type { Go } from "./useRoute";

interface How {
  replace: boolean;
}

/**
 * How the Operate areas meet the route (CONTRACT-010 D): the table's address the areas start from, the
 * writers that turn what they report into a route change, and whether the address names nothing that
 * can be opened (a type or action the module does not declare, an entity the viewer cannot read, a
 * group with no changes).
 */
export function useRouteBindings(
  module: ModuleInfo,
  route: Route,
  area: Area,
  go: Go,
  defaultType: string | undefined,
) {
  const m = module.name;
  const { filter, after, sort } = route;
  const address = useMemo<TableAddress>(() => ({ filter, after, sort }), [filter, after, sort]);
  const entitiesType = route.type ?? defaultType;
  const onAddress = (a: TableAddress, how: How) =>
    go({ module: m, area: "entities", type: entitiesType, key: route.key, ...a }, how);
  const onChanges = (a: AuditAddress, how: How) =>
    go(
      {
        module: m,
        area: "changes",
        type: a.key ? a.type : undefined,
        key: a.type ? a.key : undefined,
        group: a.group,
        action: a.action,
        since: a.since,
        until: a.until,
        view: a.loads ? "loads" : undefined,
      },
      how,
    );
  // A group with no changes is not found; the notice stands for the page until the address changes.
  const [emptyGroup, setEmptyGroup] = useState<string | undefined>();
  useEffect(() => {
    if (area !== "changes" || !route.group) setEmptyGroup(undefined);
  }, [area, route.group]);
  const onEmptyGroup = useCallback((g: string) => setEmptyGroup(g), []);
  const entityMissing = useEntityMissing(module, route, area);
  const notFound =
    namesUndeclared(module, route, area) ||
    entityMissing ||
    (area === "changes" && !!route.group && emptyGroup === route.group);
  // The route's fields, when they are about the area shown (Changes not served shows Model).
  const own = area === route.area ? route : undefined;
  return { address, onAddress, onChanges, onEmptyGroup, entitiesType, notFound, own };
}
