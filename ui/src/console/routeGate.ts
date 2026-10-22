// SPDX-License-Identifier: MIT OR Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useClient } from "../api/context";
import { ApiError } from "../api/errors";
import type { ModuleInfo } from "../api/types";
import { fetchEntity } from "../areas/entity";
import type { Area, Route } from "../route";

/** The areas whose address can name an entity (`type` with `key`). */
const ENTITY_AREAS: readonly Area[] = ["entities", "graph", "changes"];
/** The areas whose address can name a type. */
const TYPE_AREAS: readonly Area[] = ["model", "entities", "graph", "changes"];

/**
 * True when the address names something the module does not declare: a type, or an action in
 * Actions. (An entity is read, not declared: `useEntityMissing`.) The route's own area only: when
 * the area shown is another (Changes not served), the route's fields are not about it.
 */
export function namesUndeclared(m: ModuleInfo, route: Route, area: Area): boolean {
  if (route.area !== area) return false;
  if (TYPE_AREAS.includes(area) && route.type && !m.entityTypes.some((t) => t.name === route.type))
    return true;
  return area === "actions" && !!route.action && !m.actions.some((a) => a.name === route.action);
}

/** An answer that says the entity is not there, or not readable by this viewer: the same page for both. */
const unreadable = (e: unknown) =>
  e instanceof ApiError && (e.kind === "not_found" || e.kind === "no_access");

/**
 * True when the address names an entity (Entities, Graph, Changes) that the viewer's by-key read
 * does not return. It shares the entity panel's read, so the entity is read once. Other failures
 * (the network, an unavailable backend) are not an answer, and the area shows them as it does.
 */
export function useEntityMissing(m: ModuleInfo, route: Route, area: Area): boolean {
  const client = useClient();
  const { type, key } = route;
  const t = m.entityTypes.find((x) => x.name === type);
  const asks = route.area === area && ENTITY_AREAS.includes(area) && !!t && !!key;
  const read = useQuery({
    queryKey: ["entity", m.name, type, key, "LATEST"],
    enabled: asks,
    retry: false,
    queryFn: () => {
      if (!(t && key)) throw new Error("entity read without a type and a key");
      return fetchEntity(client, m, t, key, "LATEST");
    },
  });
  if (!asks) return false;
  return read.data === null || unreadable(read.error);
}
