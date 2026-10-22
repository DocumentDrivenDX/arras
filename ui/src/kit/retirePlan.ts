// SPDX-License-Identifier: MIT OR Apache-2.0
// A retire plan (SD-013, Rule 3): the declared action whose one effect is a `delete` of the type,
// keyed by a `ref` input, with every other input optional. A type with no such action has no Retire.
import type { ActionInfo, ModuleInfo } from "../api/types";
import { refAccepts } from "../lib/inputs";
import { actsOn, inputOf } from "./effects";

export interface RetirePlan {
  /** The module-qualified action (`catalog.RetireSolution`). */
  action: string;
  /** The input that carries the entity's key. */
  keyInput: string;
}

/** The plan `action` gives for `type`, if it is one delete of the type keyed by a ref input. */
function planFor(action: ActionInfo, type: string): RetirePlan | undefined {
  const [effect] = action.effects;
  if (action.effects.length !== 1 || !effect || effect.op !== "delete" || !actsOn(effect, type))
    return undefined;
  const key = action.inputSpecs.find((s) => s.name === inputOf(effect.key));
  if (key?.kind !== "ref" || key.cardinality !== "one" || !refAccepts(key, type)) return undefined;
  if (action.inputSpecs.some((s) => s !== key && s.cardinality === "one")) return undefined;
  return { action: action.name, keyInput: key.name };
}

/** Every retire plan of `type`, the first by name first. */
export function retirePlans(module: ModuleInfo, type: string): RetirePlan[] {
  return module.actions
    .flatMap((a) => {
      const plan = planFor(a, type);
      return plan ? [plan] : [];
    })
    .sort((x, y) => x.action.localeCompare(y.action));
}

/** How to retire an entity of `type`, or undefined where no declared action deletes the type. */
export const retirePlan = (module: ModuleInfo, type: string): RetirePlan | undefined =>
  retirePlans(module, type)[0];
