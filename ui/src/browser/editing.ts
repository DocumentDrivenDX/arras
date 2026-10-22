// SPDX-License-Identifier: MIT OR Apache-2.0
// The browser's side of editing a property in place: the text an editor starts with, a property's
// label in the type's view, and the action's inputs for the typed texts. Which action edits which
// property is the kit's `editPlan` (SD-013).
import type { EditField, EditPlan } from "../kit";
import { checkScalar } from "../lib/inputs";
import type { TypeEntry } from "./meta";

/** The text an editor starts with: the stored value as the action will read it back. */
export const draftOf = (value: unknown): string =>
  value === null || value === undefined ? "" : String(value);

/** A property's label in the type's view. */
export const labelOf = (entry: TypeEntry, property: string): string =>
  entry.view.fields.find((f) => f.property === property)?.label ?? property;

/** One typed value as the action's input, nothing to send for an empty optional one in a form, or what is wrong. */
function encodeField(
  plan: EditPlan,
  { input }: EditField,
  text: string,
  label: string,
): { skip: true } | { value: unknown } | { error: string } {
  if (text.trim() !== "") {
    const encoded = checkScalar(input.type, text);
    return encoded.error
      ? { error: `${label}: expected ${encoded.error}.` }
      : { value: encoded.value };
  }
  if (input.cardinality === "one") return { error: `${label}: enter a value.` };
  // A form leaves an empty optional value as it is; an inline edit has nothing else to send.
  return plan.form ? { skip: true } : { error: "Enter a value; an edit here cannot clear one." };
}

/** The action's inputs for the typed texts (by property), or the first thing wrong with them. */
export function editInputs(
  plan: EditPlan,
  key: string,
  texts: Record<string, string>,
  label: (property: string) => string,
): { inputs: Record<string, unknown>; error?: undefined } | { error: string; inputs?: undefined } {
  const inputs: Record<string, unknown> = { [plan.keyInput]: key };
  for (const field of plan.fields) {
    const r = encodeField(plan, field, texts[field.property] ?? "", label(field.property));
    if ("error" in r) return { error: r.error };
    if ("value" in r) inputs[field.input.name] = r.value;
  }
  return { inputs };
}
