// SPDX-License-Identifier: MIT OR Apache-2.0
// What an edit control needs to know about the node page it is on.
import { createContext } from "react";
import type { TypeEntry } from "./meta";
import type { Entity } from "./useNode";

export interface Target {
  entry: TypeEntry;
  keyText: string;
  /** The entity as read, for the current values a form starts from. */
  entity: Entity;
}

const Ctx = createContext<Target | null>(null);
export const EditTarget = Ctx.Provider;
export const EditTargetContext = Ctx;
