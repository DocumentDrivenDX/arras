// SPDX-License-Identifier: MIT OR Apache-2.0
// The write half of an in-place change (ADR-015): the host offers it, and a change is the module's
// declared action, checked with `validate` and applied with `invoke`, never a write of a surface's
// own. `useActionCore` is the validate-then-invoke of a one-shot change (a property edit, a link or
// unlink); the form model in `useActionForm.ts` is the same two calls with a review between them.
// The surface invalidates its own reads in `onApplied`; the kit knows no cache.
import { useRef, useState } from "react";
import { useClient } from "../api/context";
import { ApiError } from "../api/errors";
import type { ModuleInfo, Receipt } from "../api/types";
import { newKey } from "../lib/inputs";

const REFUSED = new Set(["no_access", "not_offered", "forbidden"]);

/** Any thrown value as an `ApiError`. */
export const toApiError = (e: unknown): ApiError =>
  e instanceof ApiError
    ? e
    : new ApiError(0, { type: "Error", message: e instanceof Error ? e.message : String(e) });

/** Why a call failed, in words for the reader; the cause's own message where it has one. */
export function reasonOf(e: unknown): string {
  if (!(e instanceof ApiError)) return "The change could not be sent. Try again.";
  if (REFUSED.has(e.kind)) return "You can't change this.";
  if (e.kind === "revision_conflict")
    return "The model changed while you were editing. Reload the page and try again.";
  const first = e.violations[0]?.message ?? e.failures[0]?.reason;
  return first ?? e.message;
}

export interface ActionState {
  saving: boolean;
  error: string | null;
  /** Check, then apply, `action` with `inputs`; true once it is applied. */
  run: (action: string, inputs: Record<string, unknown>) => Promise<boolean>;
  /** Show a fault found before anything was sent. */
  fail: (message: string) => void;
  clearError: () => void;
}

export function useActionCore(
  module: ModuleInfo,
  onApplied: (receipt: Receipt) => void | Promise<void>,
): ActionState {
  const client = useClient();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sending = useRef(false);
  const idem = useRef<{ sig: string; key: string } | null>(null);

  const run = async (action: string, inputs: Record<string, unknown>): Promise<boolean> => {
    if (sending.current) return false; // one change per click
    const req = { inputs, expected_revision: module.revision };
    sending.current = true;
    setSaving(true);
    setError(null);
    try {
      const checked = await client.validate(module.name, action, req);
      if (!checked.ok) {
        setError(checked.violations[0]?.message ?? checked.failures[0]?.reason ?? "Not allowed.");
        return false;
      }
      const sig = `${action} ${JSON.stringify(inputs)}`;
      if (idem.current?.sig !== sig) idem.current = { sig, key: newKey() };
      const receipt = await client.invoke(module.name, action, {
        ...req,
        idempotency_key: idem.current.key,
      });
      await onApplied(receipt);
      idem.current = null; // applied: the same inputs sent again are a new change
      return true;
    } catch (e) {
      setError(reasonOf(e));
      return false;
    } finally {
      sending.current = false;
      setSaving(false);
    }
  };

  return { saving, error, run, fail: setError, clearError: () => setError(null) };
}
