// SPDX-License-Identifier: MIT OR Apache-2.0
// Retiring an entity from its page: the kit's form model on the plan's action with the ref input
// prefilled with the page's key. The browser adds only what is its own: after the apply it opens the
// type's list by replacing the entity's history entry, and the `gb` reads and every search show the
// state without it (ADR-015: the write is the declared action, validated then invoked as the viewer).
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useClient } from "../api/context";
import { shortName } from "../api/gql";
import type { MetaData } from "../api/types";
import { type ActionFormModel, invalidateAfterApply, type RetirePlan, useActionForm } from "../kit";
import { useBrowser } from "./context";
import { requestListFocus } from "./focusAfter";
import type { TypeEntry } from "./meta";

export interface RetireState {
  form: ActionFormModel;
  /** Validate, then invoke once the check passes; a refusal stays on the form. */
  retire: () => Promise<void>;
  /** The inputs the reader may fill: every spec but the key. */
  optional: ActionFormModel["specs"];
}

export function useRetire(entry: TypeEntry, keyText: string, plan: RetirePlan): RetireState {
  const client = useClient();
  const qc = useQueryClient();
  const { go } = useBrowser();
  const moduleName = entry.module.name;
  const form = useActionForm({
    module: entry.module,
    action: plan.action,
    prefill: { [plan.keyInput]: keyText },
    client,
    reloadModule: async () => {
      await qc.refetchQueries({ queryKey: ["meta"] });
      return qc.getQueryData<MetaData>(["meta"])?.modules.find((m) => m.name === moduleName);
    },
    onApplied: () => {
      // The entity's page is gone: the list replaces its history entry, so Back does not return to it.
      requestListFocus();
      go({ module: moduleName, type: shortName(entry.type.name) }, { replace: true });
      void invalidateAfterApply(qc);
    },
  });
  // `confirm` reads the form as rendered, so it runs once the validation has rendered as passed; a
  // validation that was refused, a changed input or an error ends the request instead.
  const [asked, setAsked] = useState(false);
  const { canConfirm, confirm, validate: check, validating, fresh, stale, error, built } = form;
  const failed = (fresh && !fresh.ok) || stale || error || Object.keys(built.errors).length > 0;
  useEffect(() => {
    if (!asked) return;
    if (canConfirm) {
      setAsked(false);
      void confirm();
    } else if (!validating && failed) setAsked(false);
  }, [asked, canConfirm, confirm, validating, failed]);
  const retire = async () => {
    setAsked(true);
    // The form model's check: the one validate call, made by the kit. No result (a revision conflict
    // rebuilt the form) ends the request: a later passing validation must not confirm it unasked.
    const result = await check();
    if (!result) setAsked(false);
  };
  return { form, retire, optional: form.specs.filter((s) => s.name !== plan.keyInput) };
}
