// SPDX-License-Identifier: MIT OR Apache-2.0
// The interface's words, in one place (SD-013, Vocabulary). Tabs, links, the palette, the shortcuts
// help and the tests read their labels from here, so one word names one thing.
//
// The instance words are entity and link; the model words are entity type and relationship. The UI
// says neither node, edge nor vertex: the drawing does, the page is an "entity page".
import type { Area } from "../route";

/** The two modes: Explore, the instance tool, and Operate, the model and platform tool (their API ids stay `user` and `admin`). */
export const EXPLORE = "Explore";
export const OPERATE = "Operate";

/** The Operate areas, by route id. */
export const AREA_LABELS: Record<Area, string> = {
  model: "Model",
  graph: "Graph",
  entities: "Entities",
  actions: "Actions",
  changes: "Changes",
  query: "Query",
};

/** One entity's changes (Changes is a module's). */
export const HISTORY = "History";
/** The lock that offers an interface's writes. */
export const EDIT_MODE = "Edit mode";
/** Instances as files; the model's UMF documents are Export model. */
export const EXPORT_GRAPH = "Export graph";
export const EXPORT_MODEL = "Export model";

/** Instance words, then model words. */
export const ENTITY = "entity";
export const ENTITIES = "entities";
export const LINK = "link";
export const ENTITY_TYPE = "entity type";
export const RELATIONSHIP = "relationship";

/** The keyboard help (and the control that opens it). */
export const KEYBOARD_SHORTCUTS = "Keyboard shortcuts";
/** The palette command that moves from Explore to the same place in Operate. */
export const OPEN_IN_OPERATE = "Open in Operate";

/** What each label means; the registry the tests hold to one label per meaning. */
export const LABELS = {
  "mode.explore": EXPLORE,
  "mode.operate": OPERATE,
  "area.model": AREA_LABELS.model,
  "area.graph": AREA_LABELS.graph,
  "area.entities": AREA_LABELS.entities,
  "area.actions": AREA_LABELS.actions,
  "area.changes": AREA_LABELS.changes,
  "area.query": AREA_LABELS.query,
  "entity.history": HISTORY,
  "lock.edit": EDIT_MODE,
  "help.keys": KEYBOARD_SHORTCUTS,
  "command.openInAdmin": OPEN_IN_OPERATE,
  "export.graph": EXPORT_GRAPH,
  "export.model": EXPORT_MODEL,
  "word.entity": ENTITY,
  "word.link": LINK,
  "word.entityType": ENTITY_TYPE,
  "word.relationship": RELATIONSHIP,
} as const;

/** Words a user-visible label never says (the drawing's words, not the interface's). */
export const FORBIDDEN_WORDS = ["node", "nodes", "edge", "edges", "vertex", "vertices"] as const;

/** The labels that name more than one meaning (compared without case); empty when the registry is sound. */
export function duplicateLabels(labels: Record<string, string>): string[] {
  const seen = new Map<string, number>();
  for (const label of Object.values(labels)) {
    const k = label.toLowerCase();
    seen.set(k, (seen.get(k) ?? 0) + 1);
  }
  return [...seen].filter(([, n]) => n > 1).map(([k]) => k);
}

/** The forbidden words a label says. */
export function forbiddenIn(label: string): string[] {
  const words = label.toLowerCase().split(/[^a-z]+/);
  return FORBIDDEN_WORDS.filter((w) => words.includes(w));
}
