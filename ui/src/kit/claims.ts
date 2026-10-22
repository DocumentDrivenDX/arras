// SPDX-License-Identifier: MIT OR Apache-2.0
// Rule 1 (SD-013): for one entity type an action is claimed by the first plan it qualifies for, in the
// order editPlan, linkPlan, retirePlan, createPlan. Claimed means qualifies, not wins: where two
// actions qualify for the same thing the winner drives the control and the loser is offered nowhere.
// An action no plan qualifies for and that takes the type is an entity action.
import type { ModuleInfo } from "../api/types";
import { askable } from "./askable";
import { createPlans } from "./createPlan";
import { editClaims } from "./editPlan";
import { type EntityAction, entityActions } from "./entityActions";
import { linkClaims } from "./linkPlan";
import { retirePlans } from "./retirePlan";

export type Claim = "edit" | "link" | "retire" | "create";

const CLAIMED_BY: Claim[] = ["edit", "link", "retire", "create"];

/** The claim each action of the module has for `type` (qualified), by qualified action name. */
export function claimsOf(module: ModuleInfo, type: string): Map<string, Claim> {
  const entry = module.entityTypes.find((t) => t.name === type || t.name.endsWith(`.${type}`));
  const names: Record<Claim, Set<string>> = {
    edit: entry ? editClaims(module, entry) : new Set(),
    link: linkClaims(module, type),
    retire: new Set(retirePlans(module, type).map((p) => p.action)),
    create: new Set(createPlans(module, type).map((p) => p.action)),
  };
  const out = new Map<string, Claim>();
  for (const claim of CLAIMED_BY)
    for (const name of names[claim]) if (!out.has(name)) out.set(name, claim);
  return out;
}

/**
 * The actions of the module that take `type` as a ref input and that no plan claims, most relevant
 * first: the entity's Actions menu. An action claimed by an edit, a link, a retire or a create plan
 * (winner or loser) is not in it, nor is one whose inputs or effects the generic form cannot ask for
 * and summarise (Rule 4).
 */
export function entityActionsOf(module: ModuleInfo, type: string): EntityAction[] {
  const claims = claimsOf(module, type);
  return entityActions(module, type).filter((x) => !claims.has(x.action.name) && askable(x.action));
}
