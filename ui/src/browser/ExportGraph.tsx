// SPDX-License-Identifier: MIT OR Apache-2.0
// Export the module's graph as a file (CONTRACT-003, Export), offered where the host offers edits.
// It reads the whole graph as the viewer, a page at a time, and saves one file: the same bytes the
// library writes, so the file can be kept in version control and loaded again (`--records`).

import { useState } from "react";
import { useClient } from "../api/context";
import { ApiError } from "../api/errors";
import { Button } from "../ds";
import { downloadText, type SaveFile } from "../lib/download";
import { useBrowser } from "./context";
import { graphFileName, graphText, readGraph } from "./graphFile";

type State =
  | { status: "idle" }
  | { status: "working"; records: number }
  | { status: "done"; file: string; records: number; omitted: string[] }
  | { status: "error"; message: string };

const failure = (e: unknown): string =>
  e instanceof ApiError && ["no_access", "not_offered", "forbidden"].includes(e.kind)
    ? "You can't export this module."
    : e instanceof ApiError && e.kind === "unsupported"
      ? "This module's backend can't be exported."
      : "The export failed. Try again.";

export function ExportGraph({ module, save = downloadText }: { module: string; save?: SaveFile }) {
  const client = useClient();
  const { canEdit } = useBrowser();
  const [state, setState] = useState<State>({ status: "idle" });
  if (!canEdit) return null;
  const run = async () => {
    setState({ status: "working", records: 0 });
    try {
      const graph = await readGraph(client, module, (records) =>
        setState({ status: "working", records }),
      );
      const file = graphFileName(module);
      save(file, graphText(graph));
      setState({ status: "done", file, records: graph.records.length, omitted: graph.omitted });
    } catch (e) {
      setState({ status: "error", message: failure(e) });
    }
  };
  const working = state.status === "working";
  return (
    <div className="gb-export">
      <Button
        variant="secondary"
        size="sm"
        busy={working}
        disabled={working}
        onClick={() => void run()}
      >
        Export graph
      </Button>
      <span className="gb-export-note" role="status">
        {state.status === "working" && `${state.records} records read`}
        {state.status === "done" &&
          `Saved ${state.file}: ${state.records} records.${
            state.omitted.length > 0
              ? ` Not the whole graph: ${state.omitted.join(", ")} could not be read.`
              : ""
          }`}
      </span>
      {state.status === "error" && (
        <span className="gb-export-note gb-edit-error" role="alert">
          {state.message}
        </span>
      )}
    </div>
  );
}
