// SPDX-License-Identifier: MIT OR Apache-2.0
// A property edit: the inputs of the plan's action for the typed texts, run by `useAction`.
import type { EditPlan } from "../kit";
import { editInputs, labelOf } from "./editing";
import type { TypeEntry } from "./meta";
import { useAction } from "./useAction";

export interface EditState {
  saving: boolean;
  error: string | null;
  /** Check and apply the new text of each property by name; true once it is applied. */
  save: (texts: Record<string, string>) => Promise<boolean>;
  clearError: () => void;
}

export function useEdit(entry: TypeEntry, key: string, plan: EditPlan): EditState {
  const action = useAction(entry.module);
  const save = async (texts: Record<string, string>): Promise<boolean> => {
    const built = editInputs(plan, key, texts, (p) => labelOf(entry, p));
    if (built.error !== undefined) {
      action.fail(built.error);
      return false;
    }
    return action.run(plan.action, built.inputs);
  };
  return { saving: action.saving, error: action.error, save, clearError: action.clearError };
}
