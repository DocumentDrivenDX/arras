// SPDX-License-Identifier: MIT OR Apache-2.0
// What the console exports (OPR-14): the registered UMF documents exactly as the viewer's schema catalog
// holds them (CONTRACT-009), with no new operation. Pure functions, so the rules are tested without a browser.
import type { SchemaCatalog, SchemaCatalogEntry } from "../api/types";
import { entryId } from "./umfBrowser";

/** `schemaFormat` of a catalog entry that is a registered UMF document. */
export const DOCUMENT_FORMAT = "umf";
/** `schemaFormat` of a catalog entry that is only a "not shown" note for a document over the catalog's limits. */
export const NOTE_FORMAT = "json-schema";

export const ALL_FILE_NAME = "arras-schema-catalog.json";
export const fileNameFor = (module: string) => `${module}.umf.json`;

export type ModuleExport =
  | { state: "document"; entry: SchemaCatalogEntry; fileName: string }
  /** The catalog shows a note instead of the document (it is over its size limits): never saved. */
  | { state: "too_large" }
  /** The catalog has no entry for the module (an attached module, or one the viewer cannot read). */
  | { state: "none" };

/** What export offers for a module, from the catalog alone. */
export function exportFor(catalog: SchemaCatalog | undefined, module: string): ModuleExport {
  const entry = catalog?.entries.find((e) => e.id === entryId(module));
  if (!entry) return { state: "none" };
  if (entry.schemaFormat === DOCUMENT_FORMAT)
    return { state: "document", entry, fileName: fileNameFor(module) };
  if (entry.schemaFormat === NOTE_FORMAT) return { state: "too_large" };
  return { state: "none" };
}

/** The entries that carry a real document, and how many are only notes. */
export function readable(catalog: SchemaCatalog | undefined): {
  entries: SchemaCatalogEntry[];
  notes: number;
} {
  const all = catalog?.entries ?? [];
  return {
    entries: all.filter((e) => e.schemaFormat === DOCUMENT_FORMAT),
    notes: all.filter((e) => e.schemaFormat === NOTE_FORMAT).length,
  };
}

/** The "Export all" file: `{version: 1, entries}` of the entries that carry real documents, as the catalog has them. */
export function catalogFile(catalog: SchemaCatalog): string {
  return `${JSON.stringify({ version: 1, entries: readable(catalog).entries }, null, 2)}\n`;
}
