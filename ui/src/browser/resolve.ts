// SPDX-License-Identifier: MIT OR Apache-2.0
// Which page a location is. A fragment that does not parse, a module, type or key that is absent or
// that the viewer may not read: all are the same "not available" page (US-067-AC6, US-071-AC3).
import type { MetaData, ModuleInfo } from "../api/types";
import type { Parsed } from "./location";
import { findType, type TypeEntry } from "./meta";

export type Resolved =
  | { kind: "none" }
  /** Not available; the module is there when it resolved, so the page can lead back to its entry. */
  | { kind: "na"; module?: ModuleInfo }
  | { kind: "chooser"; modules: ModuleInfo[] }
  /** The module's entry, or a type's list from after the key `after` (a position, never a search). */
  | { kind: "entry"; module: ModuleInfo; type?: string; after?: string }
  | { kind: "node"; entry: TypeEntry; key: string; history: boolean };

export function resolveLocation(meta: MetaData, parsed: Parsed): Resolved {
  const modules = meta.modules;
  if (modules.length === 0) return { kind: "none" };
  if (parsed.kind === "invalid") return { kind: "na" };
  const loc = parsed.kind === "explore" ? parsed.loc : {};
  const only = modules.length === 1 ? modules[0] : undefined;
  const module = loc.module ? modules.find((m) => m.name === loc.module) : only;
  if (!loc.module && !module) return { kind: "chooser", modules };
  if (!module) return { kind: "na" };
  if (!loc.type) return { kind: "entry", module };
  const entry = findType(meta, module.name, loc.type);
  if (!entry) return { kind: "na", module };
  if (loc.key === undefined)
    return { kind: "entry", module, type: loc.type, ...(loc.after ? { after: loc.after } : {}) };
  return { kind: "node", entry, key: loc.key, history: loc.history === true };
}

export const moduleOf = (r: Resolved): ModuleInfo | undefined =>
  r.kind === "entry" ? r.module : r.kind === "node" ? r.entry.module : undefined;
