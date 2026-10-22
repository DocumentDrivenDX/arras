// SPDX-License-Identifier: MIT OR Apache-2.0
import type { ModuleInfo } from "../api/types";
import { DEFAULT_BRAND, titleName, useBrand } from "../lib/brand";
import { joinTitle, moduleTitle, useDocumentTitle } from "../lib/documentTitle";
import { AREA_LABELS } from "../lib/vocabulary";
import type { Area, Route } from "../route";
import { entityInContext, useEntityName } from "./EntityContextBar";

export { useDocumentTitle };

/** What the page is about, when it is about one thing: the entity's key, the action, or the selected type. */
function subjectOf(route: Route): string | undefined {
  return route.key ?? route.action ?? route.type;
}

/** What the title may know beyond the route: the module as the registry describes it, and the entity's name. */
export interface TitleContext {
  /** The module's view title stands for its name. */
  module?: ModuleInfo;
  /** The entity's title-template name, when it has been read; the key stands for it until then. */
  entityName?: string;
}

/**
 * `<entity name, action or selected type> · <Area label> · <module title> · <brand name>`, empty
 * parts dropped, joined by the rule Explore's titles use. It carries only what the page already
 * shows. The subject is the route's, so it is left out when the area shown is not the route's
 * (Changes is not served).
 */
export function titleFor(
  route: Route,
  area: Area,
  name: string = DEFAULT_BRAND.name,
  ctx: TitleContext = {},
): string {
  if (!route.module) return name;
  const own = area === route.area;
  const subject = own ? (route.key && ctx.entityName) || subjectOf(route) : undefined;
  const place = ctx.module ? moduleTitle(ctx.module) : route.module;
  return joinTitle([subject, AREA_LABELS[area], place], name);
}

/** Keeps the document title naming the console's place: the entity by its template name once read. */
export function useOperateTitle(route: Route, area: Area, module: ModuleInfo | undefined) {
  const ent = module ? entityInContext(module, route) : undefined;
  const entityName = useEntityName(module, ent);
  useDocumentTitle(titleFor(route, area, titleName(useBrand()), { module, entityName }));
}
