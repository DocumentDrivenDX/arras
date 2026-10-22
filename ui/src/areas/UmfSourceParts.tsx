// SPDX-License-Identifier: MIT OR Apache-2.0
import type { Selection } from "@documentdrivendx/umf-schema-browser";
import type { UseQueryResult } from "@tanstack/react-query";
import { type ReactNode, useMemo } from "react";
import type { ApiError } from "../api/errors";
import { shortName } from "../api/gql";
import type { SchemaCatalog } from "../api/types";
import { Button, Empty, ErrorPanel, Notice, Spinner } from "../components/ui";
import { describeSelection, type toEntries } from "./umfBrowser";

export type Mount =
  | { state: "loading" }
  | { state: "ready" }
  | { state: "failed"; why: string }
  | { state: "sign_in"; error: ApiError };

type Entries = ReturnType<typeof toEntries>;

function NotListed({ module, entries }: { module: string; entries: Entries | null }) {
  return (
    <div data-testid="umf-empty">
      <Empty
        title={
          entries?.length
            ? `No registered UMF document for ${module} is readable for you`
            : "No registered UMF documents are readable for you"
        }
      >
        The catalog lists the modules whose registered document you may read. The{" "}
        <em>Live registry</em> view still shows what this deployment serves.
      </Empty>
    </div>
  );
}

function LoadFailed({ why, base, onRetry }: { why: string; base: string; onRetry: () => void }) {
  return (
    <Notice tone="bad" role="alert">
      <strong>UMF&apos;s schema browser did not load</strong> ({why}). The host serves the
      package&apos;s assets at <span className="arras-mono">{base}</span> (
      <span className="arras-mono">explorer.js</span>,{" "}
      <span className="arras-mono">explorer.css</span>,{" "}
      <span className="arras-mono">style.css</span> and their chunks); check that they are deployed
      there and that the page&apos;s Content-Security-Policy allows them.{" "}
      <Button className="ml-1" onClick={onRetry}>
        Retry
      </Button>
    </Notice>
  );
}

function CatalogError({ error, onRetry }: { error: ApiError; onRetry: () => void }) {
  return (
    <div data-testid="umf-catalog-error">
      <ErrorPanel error={error} onRetry={onRetry} />
    </div>
  );
}

export function UmfStatus({
  catalog,
  listed,
  entries,
  module,
  mount,
  base,
  onRetry,
}: {
  catalog: UseQueryResult<SchemaCatalog, ApiError>;
  listed: boolean;
  entries: Entries | null;
  module: string;
  mount: Mount;
  base: string;
  onRetry: () => void;
}): ReactNode {
  if (catalog.isPending) return <Spinner label="Loading the registered documents" />;
  if (catalog.error) {
    return <CatalogError error={catalog.error} onRetry={() => void catalog.refetch()} />;
  }
  if (!listed) return <NotListed module={module} entries={entries} />;
  if (mount.state === "loading") return <Spinner label="Loading UMF's schema browser" />;
  if (mount.state === "sign_in") {
    return (
      <CatalogError
        error={mount.error}
        onRetry={() => {
          void catalog.refetch();
          onRetry();
        }}
      />
    );
  }
  if (mount.state === "failed") return <LoadFailed why={mount.why} base={base} onRetry={onRetry} />;
  return null;
}

export function SelectionBar({
  selected,
  entries,
  type,
  onOpenData,
  onShowGraph,
  onRefresh,
}: {
  selected: Selection | null;
  entries: Entries | null;
  type: string | null | undefined;
  onOpenData?: (type: string) => void;
  onShowGraph?: (type: string) => void;
  onRefresh: () => void;
}) {
  const where = useMemo(
    () => (selected && entries ? describeSelection(selected, entries) : null),
    [selected, entries],
  );
  return (
    <div
      className="flex min-h-[30px] flex-wrap items-center gap-2 text-[12px]"
      data-testid="umf-selection"
    >
      <span role="status" aria-live="polite">
        {where ? (
          <>
            Selected: <span className="arras-mono">{where.schema}</span>
            {where.item && (
              <>
                {" "}
                › <span className="arras-mono">{where.item}</span>
              </>
            )}
          </>
        ) : (
          <span className="text-muted">
            Select a definition in the browser to open its type in Entities or Graph.
          </span>
        )}
      </span>
      {type && onOpenData && (
        <Button onClick={() => onOpenData(type)}>Open {shortName(type)} in Entities</Button>
      )}
      {type && onShowGraph && (
        <Button onClick={() => onShowGraph(type)}>Show {shortName(type)} in Graph</Button>
      )}
      <Button
        className="ml-auto"
        title="Read the live registry again; the badges follow it"
        onClick={onRefresh}
      >
        Refresh badges
      </Button>
    </div>
  );
}
