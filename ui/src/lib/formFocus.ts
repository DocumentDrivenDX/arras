// SPDX-License-Identifier: MIT OR Apache-2.0
import { createContext, useContext, useRef } from "react";

// Focus handoff belongs to one provider session; unclaimed requests expire.
const TTL_MS = 5000;
export interface FormFocus {
  pending: { action: string; input: string; at: number } | null;
}
export const createFormFocus = (): FormFocus => ({ pending: null });
export const FormFocusContext = createContext<FormFocus | null>(null);
export function useFormFocus(): FormFocus {
  const shared = useContext(FormFocusContext);
  const local = useRef(createFormFocus()).current;
  return shared ?? local;
}
export function requestInputFocus(
  scope: FormFocus,
  action: string,
  input: string,
  now = Date.now(),
): void {
  scope.pending = { action, input, at: now };
}
export function takeInputFocus(
  scope: FormFocus,
  action: string,
  now = Date.now(),
): string | undefined {
  const p = scope.pending;
  if (!p || p.action !== action) return undefined;
  scope.pending = null;
  return now - p.at <= TTL_MS ? p.input : undefined;
}
