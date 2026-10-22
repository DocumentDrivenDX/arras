// SPDX-License-Identifier: MIT OR Apache-2.0
// The shell's hash grammar (ADR-025, CONTRACT-010 D and E): `#/explore/<module>/<type>/<key>` is
// Explore, `#/operate/<module>/<area>/...` is Operate (route.ts), and a fragment with neither prefix is
// the Operator Console's own form: Operate for an operator, the Explore entry for anyone else. Operate
// is an offer to operators only; a fragment naming it, opened by anyone else, shows Explore.
// `#/browse` and `#/admin` are alias ids of the two prefixes: they are accepted and rewritten (`canonicalMode`).
//
// The two modes carry what is open across the switch, both ways: the module, the type and the entity
// (`operateFor`, `exploreFor`), and fall back from the entity to its type's list and then to the module.
import {
  EXPLORE,
  EXPLORE_ALIAS,
  type ExploreLocation,
  formatExplore,
  parseExplore,
} from "../browser/location";
import { formatHash, OPERATE_PREFIX, OPERATE_PREFIX_ALIAS, parseHash, type Route } from "../route";

export type Mode = "user" | "admin";
export const OPERATE = OPERATE_PREFIX;

export type HashKind = "explore" | "operate" | "legacy" | "none";

export function hashKind(hash: string): HashKind {
  // The query is cut first: `#/explore?after=x` is an Explore address, not a segment named `explore?after=x`.
  const path = hash.replace(/^#\/?/, "").split("?")[0] ?? "";
  const first = path.split("/")[0] ?? "";
  if (first === EXPLORE || first === EXPLORE_ALIAS) return "explore";
  if (first === OPERATE || first === OPERATE_PREFIX_ALIAS) return "operate";
  return first === "" ? "none" : "legacy";
}

/**
 * The fragment with its first segment in its canonical form when it is an alias id (`browse`, `admin`),
 * else undefined: what the shell rewrites the address to, in place, once.
 */
export function canonicalMode(hash: string): string | undefined {
  const m = /^(#\/?)(browse|admin)(?=[/?]|$)/.exec(hash);
  if (!m) return undefined;
  return `${m[1]}${m[2] === EXPLORE_ALIAS ? EXPLORE : OPERATE}${hash.slice(m[0].length)}`;
}

export interface ModeInput {
  hash: string;
  /** The modes the host offers this viewer; never assumed to include Operate. */
  modes: readonly Mode[];
  defaultMode: Mode | undefined;
  /** The mode remembered for this session (history.state), if any. */
  remembered: Mode | undefined;
}

/** The mode a fragment asks for, within what the viewer is offered. */
export function effectiveMode(i: ModeInput): Mode {
  if (!i.modes.includes("admin")) return "user";
  switch (hashKind(i.hash)) {
    case "explore":
      return "user";
    case "operate":
    case "legacy":
      return "admin";
    case "none":
      return i.remembered ?? i.defaultMode ?? "user";
  }
}

/** The legacy console form as an Operate route, so the prefix always says which mode it is. */
export function operateHash(hash: string): string {
  return formatHash(parseHash(hash, OPERATE), OPERATE);
}

/**
 * The console's route for an Explore location: Entities on the module and type, with the entity open
 * (Changes for the entity when the address is its History) or the list's position as the page start.
 */
export function routeForExplore(loc: ExploreLocation): Route {
  const { module, type, key, history, after } = loc;
  if (!module) return { area: "model" };
  if (!type) return { module, area: "model" };
  const qualified = `${module}.${type}`;
  if (key && history) return { module, area: "changes", type: qualified, key };
  if (key) return { module, area: "entities", type: qualified, key };
  return { module, area: "entities", type: qualified, ...(after ? { after } : {}) };
}

/**
 * The Explore location for the console's route: the entity (its History for an entity's changes), else
 * its type's list (from the table's page start), else the module.
 */
export function exploreForRoute(route: Route): ExploreLocation {
  const { module, type, key, area, after } = route;
  if (!module) return {};
  if (!type || (area !== "entities" && area !== "graph" && area !== "changes")) return { module };
  const short = type.startsWith(`${module}.`) ? type.slice(module.length + 1) : type;
  if (key) return { module, type: short, key, ...(area === "changes" ? { history: true } : {}) };
  return { module, type: short, ...(area === "entities" && after ? { after } : {}) };
}

/**
 * Where Operate opens from the current fragment: from an Explore location the module and type carry
 * over to Entities, with the node's entity open; a module alone opens the module's model (US-072-AC2).
 * An Operate fragment stays as it is.
 */
export function operateFor(hash: string): string {
  switch (hashKind(hash)) {
    case "operate":
      return hash;
    case "legacy":
      return operateHash(hash);
    case "none":
      return formatHash({ area: "model" }, OPERATE);
    case "explore": {
      const parsed = parseExplore(hash);
      const loc = parsed.kind === "explore" ? parsed.loc : {};
      return formatHash(routeForExplore(loc), OPERATE);
    }
  }
}

/**
 * Where Explore opens from the current fragment: the browser's page for the entity open in the
 * console (module, type, key), else the type's list, else the module's entry. An Explore fragment
 * stays as it is.
 */
export function exploreFor(hash: string): string {
  if (hashKind(hash) === "explore") return hash;
  if (hashKind(hash) === "none") return formatExplore({});
  return formatExplore(exploreForRoute(parseHash(hash, OPERATE)));
}
