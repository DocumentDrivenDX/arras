// SPDX-License-Identifier: MIT OR Apache-2.0
// The cross-mode link primitive (SD-013 Rule 7, FR-71): a function from a target to the link that
// opens it in the other mode. It is the only place that converts between Explore's grammar
// (`#/explore/<module>/<short type>/<key>`) and Operate's (`#/operate/<module>/<area>/<qualified type>/...`).
// The shell hands each mode its half; a mode given none draws no cross-mode link.
//
// Where the fragment is the location the link is an anchor (`href`) and `go()` sets the fragment;
// where the host owns the location there is no `href`, and `go()` switches mode and sets the other
// mode's route.
import { type ExploreLocation, formatExplore } from "../browser/location";
import type { CrossLink, LinkArea, LinkTarget, LinkTo } from "../kit";
import { formatHash, OPERATE_PREFIX, type Route } from "../route";
import { exploreForRoute, routeForExplore } from "./modeRoute";

export type { CrossLink, LinkArea, LinkTarget, LinkTo };

const shortOf = (module: string, type: string) =>
  type.startsWith(`${module}.`) ? type.slice(module.length + 1) : type;

const qualified = (module: string, type: string) =>
  type.startsWith(`${module}.`) ? type : `${module}.${type}`;

const isHistory = (area: LinkArea | undefined) => area === "history" || area === "changes";

function entityRoute(
  e: Extract<LinkTarget, { entity: unknown }>["entity"],
  area?: LinkArea,
): Route {
  const { module, type, key, action } = e;
  if (area === "actions" && action)
    return {
      module,
      area: "actions",
      action: action.name,
      ...(Object.keys(action.input).length ? { input: action.input } : {}),
    };
  if (area === "model") return { module, area: "model", type: qualified(module, type) };
  return routeForExplore({ module, type: shortOf(module, type), key, history: isHistory(area) });
}

/** Operate's route for a target: Entities by default; History and Changes, Actions or Model by `area`. */
export function operateRouteFor(target: LinkTarget, area?: LinkArea): Route {
  if ("group" in target)
    return { module: target.group.module, area: "changes", group: target.group.id };
  if ("entity" in target) return entityRoute(target.entity, area);
  if ("type" in target) {
    const { module, type, after } = target.type;
    if (area === "model") return { module, area: "model", type: qualified(module, type) };
    if (isHistory(area)) return { module, area: "changes" };
    return routeForExplore({ module, type: shortOf(module, type), after });
  }
  return isHistory(area) ? { module: target.module, area: "changes" } : routeForExplore(target);
}

/** Explore's location for a target: the entity (its History for `history`), else the type's list, else the module. */
export function exploreLocationFor(target: LinkTarget, area?: LinkArea): ExploreLocation {
  if ("group" in target) return { module: target.group.module };
  if ("entity" in target) {
    const { module, type, key } = target.entity;
    return exploreForRoute({
      module,
      area: isHistory(area) ? "changes" : "entities",
      type: qualified(module, type),
      key,
    });
  }
  if ("type" in target) {
    const { module, type, after } = target.type;
    return exploreForRoute({ module, area: "entities", type: qualified(module, type), after });
  }
  return exploreForRoute({ module: target.module, area: "model" });
}

/**
 * The target an Explore location names, with the area that keeps its History; none for the start
 * page. Explore's types are short names: the module qualifies them.
 */
export function targetOfLocation(
  loc: ExploreLocation,
): { target: LinkTarget; area?: LinkArea } | undefined {
  const { module, type, key, history, after } = loc;
  if (!module) return undefined;
  if (!type) return { target: { module } };
  const qual = qualified(module, type);
  if (key)
    return {
      target: { entity: { module, type: qual, key } },
      area: history ? "history" : undefined,
    };
  return { target: { type: { module, type: qual, ...(after ? { after } : {}) } } };
}

export interface LinkHost {
  /** The fragment is the location (hash mode): links are anchors. False where the host owns it. */
  hash: boolean;
  /** Where the host owns the location: show Operate at this route. */
  openOperate: (route: Route) => void;
  /** Where the host owns the location: show Explore at this location. */
  openExplore: (loc: ExploreLocation) => void;
}

const toFragment = (href: string): CrossLink => ({
  href,
  go: () => {
    window.location.hash = href;
  },
});

/** The two halves of the primitive for a host: Explore's `toOperate` and Operate's `toExplore`. */
export function crossLinks(host: LinkHost): { toOperate: LinkTo; toExplore: LinkTo } {
  return {
    toOperate: (target, area) => {
      const route = operateRouteFor(target, area);
      return host.hash
        ? toFragment(formatHash(route, OPERATE_PREFIX))
        : { go: () => host.openOperate(route) };
    },
    toExplore: (target, area) => {
      const loc = exploreLocationFor(target, area);
      return host.hash ? toFragment(formatExplore(loc)) : { go: () => host.openExplore(loc) };
    },
  };
}
