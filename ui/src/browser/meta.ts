// SPDX-License-Identifier: MIT OR Apache-2.0
// The browser's view of the registry: one meta read that also carries each type's resolved view
// (CONTRACT-010 B). It is read once per registry revision (the revision is part of every key that
// depends on it) and the browser re-reads it when the window is focused again, so a registry that
// changed shows up under its new revision without losing the reader's place.
import { shortName } from "../api/gql";
import { useMeta } from "../api/queries";
import type { EntityTypeInfo, MetaData, ModuleInfo, TypeView } from "../api/types";

export function useBrowserMeta() {
  return useMeta(true, { staleTime: 30_000, refetchOnWindowFocus: true });
}

export interface TypeEntry {
  module: ModuleInfo;
  type: EntityTypeInfo;
  view: TypeView;
}

export const revisionKey = (m: ModuleInfo) => JSON.stringify(m.revision);

/** A type by module and its short name (`Solution`) or qualified name (`catalog.Solution`). */
export function findType(
  meta: MetaData | undefined,
  moduleName: string | undefined,
  typeName: string | undefined,
): TypeEntry | undefined {
  const module = meta?.modules.find((m) => m.name === moduleName);
  const type = module?.entityTypes.find(
    (t) => t.name === typeName || shortName(t.name) === typeName,
  );
  if (!module || !type?.view) return undefined;
  return { module, type, view: type.view };
}

/** A type from a reference's qualified name (`catalog.Solution`). */
export function findQualified(
  meta: MetaData | undefined,
  qualified: string,
): TypeEntry | undefined {
  const dot = qualified.lastIndexOf(".");
  return dot < 0 ? undefined : findType(meta, qualified.slice(0, dot), qualified.slice(dot + 1));
}

/** The module's types the viewer may read, in declaration order, each with its view. */
export function typesOf(module: ModuleInfo): TypeEntry[] {
  return module.entityTypes.flatMap((type) =>
    type.view ? [{ module, type, view: type.view }] : [],
  );
}

export const typeTitle = (entry: TypeEntry) => entry.view.pluralLabel;

/** Does any type of the module have a backend that serves text search? (an older server has none) */
export function searchServed(module: ModuleInfo): boolean {
  return module.entityTypes.some((t) =>
    Object.values(t.capabilities).some((c) => c.search === "substring"),
  );
}
