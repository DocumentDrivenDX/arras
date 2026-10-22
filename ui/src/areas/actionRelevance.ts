// SPDX-License-Identifier: MIT OR Apache-2.0
// The Actions area's choice of what to open: the actions that take the entity in context, most
// relevant first, and the action to open when none is chosen.
import { shortName } from "../api/gql";
import type { ActionInfo, ModuleInfo } from "../api/types";
import { entityActions } from "../kit";
import type { EntityContext } from "../lib/actionGroups";

/** The actions that take the entity in context as a ref input, most relevant first. */
export function relevantTo(m: ModuleInfo, ctx: EntityContext | undefined): ActionInfo[] {
  if (!ctx) return [];
  const type = m.entityTypes.find((t) => shortName(t.name) === ctx.type)?.name ?? ctx.type;
  return entityActions(m, type).map((x) => x.action);
}

/** The action to open: the one asked for, else the first relevant to the entity in context, else the first declared. */
export function defaultAction(
  m: ModuleInfo,
  asked: string | undefined,
  ctx: EntityContext | undefined,
): string | undefined {
  if (asked && m.actions.some((a) => a.name === asked)) return asked;
  return relevantTo(m, ctx)[0]?.name ?? m.actions[0]?.name;
}
