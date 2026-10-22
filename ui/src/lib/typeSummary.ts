// SPDX-License-Identifier: MIT OR Apache-2.0
import type { ActionInfo, EntityTypeInfo, ModuleInfo } from "../api/types";

const shortOf = (n: string) => n.slice(n.lastIndexOf(".") + 1);
const sameType = (a: unknown, b: string) =>
  typeof a === "string" && (a === b || shortOf(a) === shortOf(b));

/** The module's actions that take the type as an input or write it, in declaration order. */
export function actionsFor(module: Pick<ModuleInfo, "actions">, type: string): ActionInfo[] {
  return module.actions.filter(
    (a) =>
      a.inputSpecs.some((i) => sameType(i.type, type)) ||
      a.effects.some((e) => sameType(e.type, type) || sameType(e.ref_type, type)),
  );
}

const list = (names: string[]) => names.join(", ");

/**
 * One line that says what a type's backends offer, in place of one line per backend: where the record is held,
 * which backends serve bulk reads, and whether text search and counts are served. Empty when no backend is declared.
 */
export function capabilityLine(t: EntityTypeInfo, record: string): string {
  const all = Object.entries(t.capabilities);
  if (all.length === 0) return "";
  const names = all.map(([b]) => b);
  const holds = all.filter(([, c]) => c.mutable).map(([b]) => b);
  const recordStore = holds.length ? holds : names.filter((b) => b === record);
  const replicas = names.filter((b) => !recordStore.includes(b));
  const searching = all.filter(([, c]) => c.search === "substring").map(([b]) => b);
  const counting = all.filter(([, c]) => c.count).map(([b]) => b);
  const parts = [
    recordStore.length ? `Record store: ${list(recordStore)}` : "",
    replicas.length ? `Bulk reads: ${list(replicas)}` : "",
    searching.length
      ? `Text search: ${searching.length === all.length ? "every backend" : list(searching)}`
      : "No text search",
    counting.length
      ? `Counts: ${counting.length === all.length ? "every backend" : list(counting)}`
      : "",
  ];
  return parts.filter(Boolean).join(" · ");
}
