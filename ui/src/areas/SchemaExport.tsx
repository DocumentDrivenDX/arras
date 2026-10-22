// SPDX-License-Identifier: MIT OR Apache-2.0
import { useSchemaCatalog } from "../api/queries";
import { Button, Chip } from "../components/ui";
import { downloadText, type SaveFile } from "../lib/download";
import { ALL_FILE_NAME, catalogFile, exportFor, readable } from "./exportFiles";

/**
 * OPR-14: save a module's registered UMF document exactly as the viewer's schema catalog holds it
 * (`<module>.umf.json`), or every readable one as a catalog file. A module the catalog shows only as a
 * "not shown" note is never saved (the note is not the document), and a module with no entry (an
 * attached one) offers nothing. No new operation: this reads what the console already read.
 */
export function SchemaExport({ module, save = downloadText }: { module: string; save?: SaveFile }) {
  const catalog = useSchemaCatalog();
  if (!catalog.data) return null;
  const mine = exportFor(catalog.data, module);
  const { entries, notes } = readable(catalog.data);
  if (mine.state === "none" && entries.length === 0 && notes === 0) return null;
  return (
    <fieldset
      aria-label="Export"
      className="m-0 flex min-w-0 flex-wrap items-center gap-1 border-0 p-0"
      data-testid="schema-export"
    >
      {mine.state === "document" && (
        <Button
          title={`Save ${mine.fileName}: the document as registered`}
          onClick={() => save(mine.fileName, mine.entry.text)}
        >
          Export
        </Button>
      )}
      {mine.state === "too_large" && (
        <Chip
          tone="warn"
          title="The catalog shows a note instead of this document (it is over its size limit), so there is nothing to save"
        >
          Too large to export
        </Chip>
      )}
      {entries.length > 0 && (
        <Button
          title={`Save ${ALL_FILE_NAME}: ${entries.length} registered ${entries.length === 1 ? "document" : "documents"}${notes ? `; ${notes} too large to export ${notes === 1 ? "is" : "are"} left out` : ""}`}
          onClick={() => save(ALL_FILE_NAME, catalogFile(catalog.data))}
        >
          Export all
        </Button>
      )}
    </fieldset>
  );
}
