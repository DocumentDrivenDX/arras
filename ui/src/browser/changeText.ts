// SPDX-License-Identifier: MIT OR Apache-2.0
// What a journal change says in words: its action and the entities its ops touched (either end of a
// link counts). Pure, so the panel and its tests share it.
import { moduleOf, shortName } from "../api/gql";
import type { Change, ChangeOp } from "../api/types";
import type { Target } from "./planner";
import { refId } from "./planner";

export interface Touched {
  verb: string;
  target: Target;
}

const VERBS: Record<string, string> = {
  create: "created",
  update: "updated",
  delete: "deleted",
  link: "linked",
  unlink: "unlinked",
};

const qualify = (module: string, type: string) => (type.includes(".") ? type : `${module}.${type}`);

function targetFor(module: string, r: { type: string; key: string }): Target {
  const type = qualify(module, r.type);
  return { id: refId({ type, key: r.key }), module: moduleOf(type), type, key: r.key };
}

function opEnds(module: string, op: ChangeOp): Target[] {
  const ends = [
    op.source,
    op.target,
    op.type && op.key ? { type: op.type, key: op.key } : undefined,
  ];
  return ends
    .filter((e): e is { type: string; key: string } => !!e)
    .map((e) => targetFor(module, e));
}

/** The entities a change touched, once each, in the order its ops name them. */
export function touchedOf(change: Change): Touched[] {
  const seen = new Set<string>();
  const out: Touched[] = [];
  for (const op of change.ops) {
    const verb = VERBS[op.kind] ?? op.kind;
    for (const target of opEnds(change.module, op)) {
      if (seen.has(target.id)) continue;
      seen.add(target.id);
      out.push({ verb, target });
    }
  }
  return out;
}

export const actionText = (action: string) => shortName(action);
