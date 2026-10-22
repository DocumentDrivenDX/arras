// SPDX-License-Identifier: MIT OR Apache-2.0
// Creating an entity from a type's list: the kit's form model on the create plan's declared action.
// The browser adds only what is its own: after the apply the `gb` reads and every search show the new
// state (ADR-015: the write is the declared action, validated then invoked as the viewer), and the
// created entity opens from the validated create key, confirmed by the receipt.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useClient } from "../api/context";
import { shortName } from "../api/gql";
import type { MetaData } from "../api/types";
import {
  type ActionFormModel,
  type CreatePlan,
  createdKey,
  invalidateAfterApply,
  useActionForm,
} from "../kit";
import { useBrowser } from "./context";
import { requestEntityFocus } from "./focusAfter";
import type { TypeEntry } from "./meta";

export interface NewEntityState {
  form: ActionFormModel;
  /** The key of the entity made, once the receipt names it; undefined until then or where it cannot. */
  created: string | undefined;
}

export function useNewEntity(
  entry: TypeEntry,
  plan: CreatePlan,
  /** The dialog is closed before the browser opens the entity (focus follows the page). */
  onLeave: () => void,
): NewEntityState {
  const client = useClient();
  const qc = useQueryClient();
  const { go } = useBrowser();
  const moduleName = entry.module.name;
  const form = useActionForm({
    module: entry.module,
    action: plan.action,
    client,
    reloadModule: async () => {
      await qc.refetchQueries({ queryKey: ["meta"] });
      return qc.getQueryData<MetaData>(["meta"])?.modules.find((m) => m.name === moduleName);
    },
    onApplied: () => {
      void invalidateAfterApply(qc);
    },
  });
  const { receipt, effects } = form;
  const created = receipt ? createdKey(plan, effects, receipt) : undefined;
  const opened = useRef(false);
  useEffect(() => {
    if (created === undefined || opened.current) return;
    opened.current = true;
    requestEntityFocus();
    onLeave();
    go({ module: moduleName, type: shortName(plan.type), key: created });
  }, [created, go, moduleName, plan.type, onLeave]);
  return { form, created };
}
