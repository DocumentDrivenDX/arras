// SPDX-License-Identifier: MIT OR Apache-2.0
// An entity action run from the entity's page (FR-70): the kit's form model on the declared action,
// with the input that carries the entity's key prefilled. The browser adds only what is its own: after
// an apply the `gb` reads and every search show the new state, so the page and its neighbours are
// current under the receipt (ADR-015: the write is the declared action, validated then invoked as the
// viewer). A refusal stays on the form; none is held for the session.
import { useQueryClient } from "@tanstack/react-query";
import { useClient } from "../api/context";
import type { MetaData } from "../api/types";
import {
  type ActionFormModel,
  type EntityAction,
  invalidateAfterApply,
  useActionForm,
} from "../kit";
import type { TypeEntry } from "./meta";

export interface EntityActionState {
  form: ActionFormModel;
  /** The inputs the reader fills: every spec but the one that carries the page's key. */
  fields: ActionFormModel["specs"];
}

export function useEntityAction(
  entry: TypeEntry,
  keyText: string,
  entityAction: EntityAction,
): EntityActionState {
  const client = useClient();
  const qc = useQueryClient();
  const moduleName = entry.module.name;
  const { keyInput } = entityAction;
  const form = useActionForm({
    module: entry.module,
    action: entityAction.action.name,
    prefill: { [keyInput.name]: keyText },
    client,
    reloadModule: async () => {
      await qc.refetchQueries({ queryKey: ["meta"] });
      return qc.getQueryData<MetaData>(["meta"])?.modules.find((m) => m.name === moduleName);
    },
    onApplied: () => {
      void invalidateAfterApply(qc);
    },
  });
  return { form, fields: form.specs.filter((s) => s.name !== keyInput.name) };
}
