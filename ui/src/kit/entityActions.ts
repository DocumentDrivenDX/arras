// SPDX-License-Identifier: MIT OR Apache-2.0
// Which declared actions concern an entity, and which of them change one property. Everything is
// read from the module's declared actions (their inputs and effects), never from their names. The
// ranking among updates is Rule 1a (SD-013): an update that changes a property alone before one that
// changes it together with others, then the fewest properties, then the first by name; no other
// heuristic. These only choose which declared action's form to open (ADR-015).
import type { ActionInfo, InputSpec, ModuleInfo } from "../api/types";
import { refAccepts } from "../lib/inputs";
import { actsOn, inputOf } from "./effects";

export interface UpdateOf {
  action: ActionInfo;
  /** The ref input that carries the entity's key. */
  keyInput: InputSpec;
  /** Property of the type to the input that supplies it (only properties set from an input). */
  properties: Record<string, InputSpec>;
  /** How many properties the update sets, from an input or not. */
  width: number;
}

/** The update of `type` this action declares, keyed by a ref input that accepts the type. */
export function updateOf(action: ActionInfo, type: string): UpdateOf | undefined {
  for (const e of action.effects) {
    if (e.op !== "update" || !actsOn(e, type)) continue;
    const keyName = inputOf(e.key);
    const keyInput = action.inputSpecs.find((s) => s.name === keyName);
    if (keyInput?.cardinality !== "one" || !refAccepts(keyInput, type)) continue;
    const declared = (e.properties ?? {}) as Record<string, unknown>;
    const properties: Record<string, InputSpec> = {};
    for (const [property, expr] of Object.entries(declared)) {
      const input = action.inputSpecs.find((s) => s.name === inputOf(expr));
      if (input) properties[property] = input;
    }
    return { action, keyInput, properties, width: Object.keys(declared).length };
  }
  return undefined;
}

/** How many inputs other than the key (and `value`) must be given: they make the update "together". */
const required = (u: UpdateOf, value?: InputSpec) =>
  u.action.inputSpecs.filter((s) => s !== u.keyInput && s !== value && s.cardinality === "one")
    .length;

/** Rule 1a over updates; `alone` says whether an update changes the property in question alone. */
const rank = (alone: (u: UpdateOf) => boolean) => (x: UpdateOf, y: UpdateOf) =>
  Number(!alone(x)) - Number(!alone(y)) ||
  x.width - y.width ||
  x.action.name.localeCompare(y.action.name);

/** As an entity's action: alone when at most one input besides the key must be given. */
const compareUpdates = rank((u) => required(u) <= 1);

export interface EntityAction {
  action: ActionInfo;
  /** The input that carries the entity's key. */
  keyInput: InputSpec;
  /** True when the action updates this type (a candidate for the action bar). */
  updates: boolean;
}

/**
 * The declared actions that take this entity as a ref input, most relevant first: updates of the
 * type (Rule 1a), then every other action that takes it (links, deletions, ...) by name. Which of
 * them a plan claims is `claims.ts`'s question; this list is every one.
 */
export function entityActions(module: ModuleInfo, type: string): EntityAction[] {
  const updates: UpdateOf[] = [];
  const others: EntityAction[] = [];
  for (const a of module.actions) {
    const u = updateOf(a, type);
    if (u) {
      updates.push(u);
      continue;
    }
    const key = a.inputSpecs.find((s) => refAccepts(s, type));
    if (key) others.push({ action: a, keyInput: key, updates: false });
  }
  updates.sort(compareUpdates);
  others.sort((x, y) => x.action.name.localeCompare(y.action.name));
  return [
    ...updates.map((u) => ({ action: u.action, keyInput: u.keyInput, updates: true })),
    ...others,
  ];
}

/** How many actions stand in the bar as primary buttons; the rest go in the menu. */
export const PRIMARY_ACTIONS = 3;

export function splitActions(list: EntityAction[]): {
  primary: EntityAction[];
  rest: EntityAction[];
} {
  const primary = list.filter((x) => x.updates).slice(0, PRIMARY_ACTIONS);
  return { primary, rest: list.filter((x) => !primary.includes(x)) };
}

export interface PropertyAction {
  action: string;
  keyInput: string;
  /** The input that carries the property's new value. */
  input: string;
}

/**
 * For each property of `type`, the declared action that updates it (Rule 1a, taken for that
 * property): one that needs nothing else but the value before one that needs more, then the fewest
 * properties, then the first by name. A property no action updates has no entry.
 */
export function propertyActions(module: ModuleInfo, type: string): Record<string, PropertyAction> {
  const updates = module.actions.flatMap((a) => {
    const u = updateOf(a, type);
    return u ? [u] : [];
  });
  const out: Record<string, PropertyAction> = {};
  for (const property of new Set(updates.flatMap((u) => Object.keys(u.properties)))) {
    const setting = updates.filter((u) => u.properties[property]);
    const value = (u: UpdateOf) => u.properties[property];
    setting.sort(rank((u) => required(u, value(u)) === 0));
    const [best] = setting;
    const input = best && value(best);
    if (best && input)
      out[property] = { action: best.action.name, keyInput: best.keyInput.name, input: input.name };
  }
  return out;
}
