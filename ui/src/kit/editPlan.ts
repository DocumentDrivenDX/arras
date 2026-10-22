// SPDX-License-Identifier: MIT OR Apache-2.0
// Which properties of a node can be edited in place, and by which declared action. No write path is
// invented: a property is editable only where the module already declares an action whose one
// effect updates it (ADR-015), so an edit is that action's invoke.
//
// Two shapes qualify. An action whose other inputs can all be left out changes one property on its
// own (an inline edit). An action whose inputs are all values for properties of the update, some of
// them required, can only change those properties together (a form). Where several qualify for one
// property, the ranking is Rule 1a (SD-013): alone before together, then the fewest properties
// changed, then the first by name.
import type { ActionInfo, EntityTypeInfo, InputSpec, ModuleInfo } from "../api/types";
import { actsOn, inputOf } from "./effects";

export interface EditField {
  property: string;
  /** The action input that carries the new value. */
  input: InputSpec;
}

export interface EditPlan {
  /** The module-qualified action (`catalog.RenameUseCase`). */
  action: string;
  /** The input that carries the entity's key. */
  keyInput: string;
  /** The properties this edit changes: one for an inline edit, every property of the action for a form. */
  fields: EditField[];
  /** True when the properties can only be changed together. */
  form: boolean;
}

// Scalars the editor reads and writes as text; a binary, a list or a record is not one.
const EDITABLE = new Set(["string", "integer", "decimal", "boolean", "timestamp"]);

interface Parsed {
  keyInput: string;
  /** The update's properties that a scalar input sets, in declared order. */
  fields: EditField[];
  others: InputSpec[];
}

/** An action that is one update of `type`, keyed by a ref input, as its parts; else nothing. */
function parse(action: ActionInfo, type: string): Parsed | undefined {
  const [effect] = action.effects;
  if (action.effects.length !== 1 || !effect || effect.op !== "update") return undefined;
  if (!actsOn(effect, type)) return undefined;
  const keyName = inputOf(effect.key);
  const key = action.inputSpecs.find((s) => s.name === keyName);
  if (key?.kind !== "ref" || key.cardinality !== "one") return undefined;
  const props = (effect.properties ?? {}) as Record<string, unknown>;
  const fields: EditField[] = [];
  for (const [property, expr] of Object.entries(props)) {
    const input = action.inputSpecs.find((s) => s.name === inputOf(expr));
    if (input?.kind === "scalar" && input.cardinality !== "many") fields.push({ property, input });
  }
  return { keyInput: key.name, fields, others: action.inputSpecs.filter((s) => s !== key) };
}

/** The plan `parsed` gives for one of its own fields: alone, together, or neither. */
function planOf(action: ActionInfo, parsed: Parsed, own: EditField): EditPlan | undefined {
  const base = { action: action.name, keyInput: parsed.keyInput };
  // Alone: every other input can be left out, so only this one is sent.
  if (parsed.others.every((s) => s === own.input || s.cardinality !== "one"))
    return { ...base, fields: [own], form: false };
  // Together: every input is a value for a property of the update, so a form can ask for them all.
  if (parsed.others.every((s) => parsed.fields.some((f) => f.input === s)))
    return { ...base, fields: parsed.fields, form: true };
  return undefined;
}

/** The plan `action` gives for `property`, if it changes it alone or only together with others. */
function planFor(action: ActionInfo, type: string, property: string): EditPlan | undefined {
  const parsed = parse(action, type);
  const own = parsed?.fields.find((f) => f.property === property);
  return parsed && own ? planOf(action, parsed, own) : undefined;
}

const width = (a: ActionInfo) => Object.keys(a.effects[0]?.properties ?? {}).length;

/** Whether a property of the type can be edited as text at all: not the key, a list or a binary. */
function editable(type: EntityTypeInfo, property: string): boolean {
  if (property === type.key) return false;
  const info = type.properties.find((p) => p.name === property);
  return !!info && info.cardinality !== "many" && EDITABLE.has(info.type);
}

/**
 * How to edit `property` of `type`, or undefined if it cannot be. A change of the property alone
 * wins over a form; among several of a kind, the action that changes the fewest properties (a
 * rename over a general correction), then the first by name.
 */
export function editPlan(
  module: ModuleInfo,
  type: EntityTypeInfo,
  property: string,
): EditPlan | undefined {
  if (!editable(type, property)) return undefined;
  const plans = module.actions.flatMap((a) => {
    const plan = planFor(a, type.name, property);
    return plan ? [{ plan, a }] : [];
  });
  plans.sort(
    (x, y) =>
      Number(x.plan.form) - Number(y.plan.form) ||
      width(x.a) - width(y.a) ||
      x.a.name.localeCompare(y.a.name),
  );
  return plans[0]?.plan;
}

/**
 * The actions that qualify for an edit of some property of `type` (Rule 1): claimed whether or not
 * they win the ranking, so a loser is neither an inline control nor an entity action.
 */
export function editClaims(module: ModuleInfo, type: EntityTypeInfo): Set<string> {
  const claimed = new Set<string>();
  for (const a of module.actions) {
    const parsed = parse(a, type.name);
    if (parsed?.fields.some((f) => editable(type, f.property) && planOf(a, parsed, f)))
      claimed.add(a.name);
  }
  return claimed;
}
