// SPDX-License-Identifier: MIT OR Apache-2.0
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useClient, useRefusals } from "../api/context";
import { useModule } from "../api/queries";
import type { Receipt } from "../api/types";
import { invalidateAfterApply, useActionForm as useKitForm } from "../kit";
import type { ImpactState } from "./ImpactPanel";

export type { Checked } from "../kit";

export interface UseActionFormArgs {
  module: string;
  action: string;
  prefill?: Record<string, string>;
  onDone?: (r: Receipt) => void;
  onState?: (s: ImpactState | null) => void;
}

/** The console's use of the kit's form model: its meta read, its refusals, its cache keys and its impact view. */
export function useActionForm({
  module: name,
  action,
  prefill,
  onDone,
  onState,
}: UseActionFormArgs) {
  const client = useClient();
  const qc = useQueryClient();
  const { module: m, meta } = useModule(name);
  const { refusals, refuse } = useRefusals();
  const form = useKitForm({
    module: m,
    action,
    prefill,
    client,
    refusal: refusals[action] ?? null,
    onRefused: (e) => refuse(action, e),
    reloadModule: async () => {
      const reloaded = await client.meta();
      qc.setQueryData(["meta"], reloaded);
      return reloaded.modules.find((x) => x.name === name);
    },
    onApplied: (r) => {
      void invalidateAfterApply(qc);
      onDone?.(r);
    },
  });

  // The impact view follows what has been validated and applied; it never reads the form's inputs.
  const { checked, receipt, effects, status, valid } = form;
  const report = useRef(onState);
  report.current = onState;
  useEffect(() => {
    report.current?.(!checked && !receipt ? null : { action, effects, status, valid, receipt });
  }, [action, checked, receipt, effects, status, valid]);
  useEffect(() => () => report.current?.(null), []);
  const receiptRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (receipt) receiptRef.current?.focus();
  }, [receipt]);

  return { ...form, m, meta, receiptRef };
}
