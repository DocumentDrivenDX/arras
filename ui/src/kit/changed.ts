// SPDX-License-Identifier: MIT OR Apache-2.0
// The entities a change touched, for the "changed by" highlight: from the validated effects and the
// receipt's refs. Ids are `Type:key` (qualified), never put in a URL.
import type { Effect, ModuleInfo, Receipt } from "../api/types";

const qualify = (m: ModuleInfo, type: string) => (type.includes(".") ? type : `${m.name}.${type}`);
const idOf = (m: ModuleInfo, r: { type: string; key: string }) => `${qualify(m, r.type)}:${r.key}`;

/** Keys of the entities a change touches. */
export function changedIds(m: ModuleInfo, effects: Effect[], receipt?: Receipt | null): string[] {
  const ids = new Set<string>();
  for (const e of effects) {
    if ("ref" in e) {
      if (!(e.ref.generated && !e.ref.key)) ids.add(idOf(m, e.ref));
    } else {
      ids.add(idOf(m, e.source));
      ids.add(idOf(m, e.target));
    }
  }
  for (const r of receipt?.refs ?? []) ids.add(idOf(m, r));
  return [...ids];
}
