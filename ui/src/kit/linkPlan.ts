// SPDX-License-Identifier: MIT OR Apache-2.0
// Which relationship groups of a node page can have links added or removed, and by which declared
// actions (CONTRACT-010 F). As for properties, no write path is invented: a link can be added where
// the module declares an action whose one effect is a `link` of that relationship between two
// reference inputs, and removed where one is an `unlink`.
import type { ActionInfo, EffectDecl, InputSpec, ModuleInfo, RelationshipInfo } from "../api/types";
import { inputOf } from "./effects";

export interface LinkPlan {
  /** The module-qualified action (`catalog.AddressUseCase`). */
  action: string;
  /** The input that carries the page's key, and the one that carries the other end's key. */
  pageInput: string;
  otherInput: string;
  /** The type the other input takes, qualified (`catalog.UseCase`): the one end of the group this action can reach. */
  otherType: string;
}

export interface GroupLinks {
  relationship: RelationshipInfo;
  /** True when the group is the relationship's own name (the page is its source), false for its inverse. */
  forward: boolean;
  /** The qualified types the other end may be. */
  otherTypes: string[];
  add?: LinkPlan;
  remove?: LinkPlan;
}

type Direction = Omit<GroupLinks, "add" | "remove">;

const refInput = (action: ActionInfo, expr: unknown): InputSpec | undefined => {
  const spec = action.inputSpecs.find((s) => s.name === inputOf(expr));
  return spec?.kind === "ref" && spec.cardinality === "one" ? spec : undefined;
};

/** A type name as `module.Type`: a name that already has its module is kept, a bare one is the module's own. */
const qualified = (module: ModuleInfo, name: string) =>
  name.includes(".") ? name : `${module.name}.${name}`;

const typeOf = (module: ModuleInfo, spec: InputSpec) => qualified(module, spec.type);
const accepts = (module: ModuleInfo, types: string[], spec: InputSpec) =>
  types.some((t) => qualified(module, t) === typeOf(module, spec));

/** The plan `action` gives for `op` on `rel` seen from a page of `pageType`, if it is one. */
function planFor(
  module: ModuleInfo,
  action: ActionInfo,
  op: "link" | "unlink",
  g: Direction,
  pageType: string,
): LinkPlan | undefined {
  const [e]: EffectDecl[] = action.effects;
  if (action.effects.length !== 1 || !e || e.op !== op || e.type !== g.relationship.name)
    return undefined;
  const source = refInput(action, e.source);
  const target = refInput(action, e.target);
  if (!source || !target || source === target) return undefined;
  const [page, other] = g.forward ? [source, target] : [target, source];
  if (typeOf(module, page) !== qualified(module, pageType) || !accepts(module, g.otherTypes, other))
    return undefined;
  // Every other input must be one that can be left out: only the two keys are sent.
  if (action.inputSpecs.some((s) => s !== source && s !== target && s.cardinality === "one"))
    return undefined;
  return {
    action: action.name,
    pageInput: page.name,
    otherInput: other.name,
    otherType: typeOf(module, other),
  };
}

const byName = (a: ActionInfo, b: ActionInfo) => a.name.localeCompare(b.name);

/** The direction of `relationship` a group named `field` shows a page of `pageType` (qualified), if any. */
function directionOf(
  module: ModuleInfo,
  relationship: RelationshipInfo,
  field: string,
  pageType: string,
): Direction | undefined {
  const forward = relationship.name === field;
  const mine = forward ? relationship.source : relationship.target;
  if (!mine.some((t) => qualified(module, t) === qualified(module, pageType))) return undefined;
  return {
    relationship,
    forward,
    otherTypes: (forward ? relationship.target : relationship.source).map((t) =>
      qualified(module, t),
    ),
  };
}

/**
 * The link plans for the relationship group `field` of a page of `pageType` (qualified), or nothing
 * when the field is no relationship of the module. Where several actions fit, Rule 1a ranks them:
 * the first by name wins.
 */
export function groupLinks(
  module: ModuleInfo,
  pageType: string,
  field: string,
): GroupLinks | undefined {
  const relationship = module.relationships.find((r) => r.name === field || r.inverse === field);
  const base = relationship && directionOf(module, relationship, field, pageType);
  if (!base) return undefined;
  const actions = [...module.actions].sort(byName);
  const find = (op: "link" | "unlink") => {
    for (const a of actions) {
      const plan = planFor(module, a, op, base, pageType);
      if (plan) return plan;
    }
    return undefined;
  };
  const add = find("link");
  const remove = find("unlink");
  return add || remove ? { ...base, add, remove } : undefined;
}

/**
 * The actions that qualify as a link or an unlink in some relationship group of a page of
 * `pageType` (Rule 1): claimed whether or not they win the ranking.
 */
export function linkClaims(module: ModuleInfo, pageType: string): Set<string> {
  const directions = module.relationships.flatMap((relationship) =>
    [relationship.name, relationship.inverse ?? ""].flatMap((field) => {
      const base = field ? directionOf(module, relationship, field, pageType) : undefined;
      return base ? [base] : [];
    }),
  );
  const qualifies = (a: ActionInfo) =>
    directions.some(
      (d) => planFor(module, a, "link", d, pageType) || planFor(module, a, "unlink", d, pageType),
    );
  return new Set(module.actions.filter(qualifies).map((a) => a.name));
}

/** True when an entity of `type` (qualified) is one the plan's other input takes. */
export const planTakes = (plan: LinkPlan, type: string): boolean => type === plan.otherType;

/** The inputs for one link change: the page's key and the other end's. */
export const linkInputs = (plan: LinkPlan, pageKey: string, otherKey: string) => ({
  [plan.pageInput]: pageKey,
  [plan.otherInput]: otherKey,
});
