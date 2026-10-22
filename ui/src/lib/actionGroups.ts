// SPDX-License-Identifier: MIT OR Apache-2.0
// The Actions area's list: actions grouped by the type their effects act on, filtered by text, with
// the ones that concern an entity in context set apart, and the action to open when none is chosen.
import { shortName } from "../api/gql";
import type { ActionInfo, EffectDecl, ModuleInfo } from "../api/types";
import { KEY_VALUE } from "../route";

export const OTHER_GROUP = "Other";

const refTypeOf = (e: EffectDecl) => String((e.ref_type ?? e.refType ?? "") as string);

/** The type an effect acts on: the one it creates, updates or deletes, or a link's source type. */
function effectType(m: ModuleInfo, e: EffectDecl): string | undefined {
  if (e.op === "create") return e.type ? shortName(e.type) : undefined;
  if (e.op === "update" || e.op === "delete") {
    const t = refTypeOf(e);
    return t ? shortName(t) : undefined;
  }
  if (e.op === "link" || e.op === "unlink") {
    const rel = m.relationships.find((r) => r.name === e.type);
    const source = rel?.source[0];
    return source ? shortName(source) : undefined;
  }
  return undefined;
}

/** The type an action is about: the first of its effects that names one, else none. */
export function targetType(m: ModuleInfo, action: ActionInfo): string | undefined {
  for (const e of action.effects) {
    const t = effectType(m, e);
    if (t) return t;
  }
  return undefined;
}

export interface ActionGroup {
  /** The short type name, or "Other". */
  title: string;
  actions: ActionInfo[];
}

/** Text matches an action's name or description, ignoring case; empty text matches everything. */
export function matchesFilter(a: ActionInfo, text: string): boolean {
  const q = text.trim().toLowerCase();
  if (!q) return true;
  return a.name.toLowerCase().includes(q) || a.description.toLowerCase().includes(q);
}

/**
 * The actions that pass `filter`, grouped by target type in the order the module declares its types
 * (declaration order within a group); actions with no target type fall in "Other", last.
 */
export function groupActions(m: ModuleInfo, filter = ""): ActionGroup[] {
  const order = m.entityTypes.map((t) => shortName(t.name));
  const groups = new Map<string, ActionInfo[]>();
  for (const a of m.actions) {
    if (!matchesFilter(a, filter)) continue;
    const t = targetType(m, a);
    const title = t && order.includes(t) ? t : OTHER_GROUP;
    groups.set(title, [...(groups.get(title) ?? []), a]);
  }
  const titled = [...order, OTHER_GROUP].flatMap((title) => {
    const actions = groups.get(title);
    return actions ? [{ title, actions }] : [];
  });
  return titled;
}

export interface EntityContext {
  /** The short type name of the entity the area was opened for. */
  type: string;
  key: string;
}

/** The entity an action opened with a prefill is for: the ref input the prefill fills, and its type. */
export function contextOf(
  m: ModuleInfo,
  action: string | undefined,
  prefill: Record<string, string> | undefined,
): EntityContext | undefined {
  const info = m.actions.find((a) => a.name === action);
  if (!info || !prefill) return undefined;
  for (const s of info.inputSpecs) {
    const key = prefill[s.name];
    if (s.kind === "ref" && s.cardinality === "one" && key) {
      return { type: shortName(s.type), key };
    }
  }
  return undefined;
}

/**
 * The entries of an address's prefill that fit the chosen action: a ref input of that action given a
 * key. Typed text, numbers and names the action does not take are left out (CONTRACT-010 D); none
 * left is undefined.
 */
export function refPrefill(
  m: ModuleInfo,
  action: string | undefined,
  prefill: Record<string, string> | undefined,
): Record<string, string> | undefined {
  const info = m.actions.find((a) => a.name === action);
  if (!info || !prefill) return undefined;
  const refs = new Set(info.inputSpecs.filter((s) => s.kind === "ref").map((s) => s.name));
  const kept = Object.entries(prefill).filter(([n, v]) => refs.has(n) && KEY_VALUE.test(v));
  return kept.length ? Object.fromEntries(kept) : undefined;
}
