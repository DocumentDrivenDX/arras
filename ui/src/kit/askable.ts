// SPDX-License-Identifier: MIT OR Apache-2.0
// What the generic form can ask for and summarise (SD-013 Rule 4, CONTRACT-010 F): every input is a
// kind and a cardinality `ActionFields` draws and `lib/inputs` encodes, and every effect is one of
// the five the text summary words. An action outside that is Operate's, never a broken dialog.
import type { ActionInfo } from "../api/types";

const INPUT_KINDS = new Set(["scalar", "record", "ref"]);
const CARDINALITIES = new Set(["one", "optional", "many"]);
const EFFECT_OPS = new Set(["create", "update", "delete", "link", "unlink"]);

/** True when the form can ask every input of the action and the summary can word every effect. */
export function askable(action: ActionInfo): boolean {
  return (
    action.inputSpecs.every((s) => INPUT_KINDS.has(s.kind) && CARDINALITIES.has(s.cardinality)) &&
    action.effects.every((e) => EFFECT_OPS.has(e.op))
  );
}
