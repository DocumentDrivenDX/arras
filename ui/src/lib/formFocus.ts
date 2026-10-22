// SPDX-License-Identifier: MIT OR Apache-2.0
// A request to focus one input of an action's form when it opens (from a property's "Change"
// control). Held in memory only; a request nobody takes lapses, so a form opened later by hand is
// not surprised by it.

const TTL_MS = 5000;
let pending: { action: string; input: string; at: number } | null = null;

export function requestInputFocus(action: string, input: string, now = Date.now()): void {
  pending = { action, input, at: now };
}

/** The input to focus for `action`, once; undefined when none was asked for it or it lapsed. */
export function takeInputFocus(action: string, now = Date.now()): string | undefined {
  const p = pending;
  if (!p || p.action !== action) return undefined;
  pending = null;
  return now - p.at <= TTL_MS ? p.input : undefined;
}
