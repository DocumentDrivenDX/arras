// SPDX-License-Identifier: MIT OR Apache-2.0
import { useState } from "react";
import { ApiError } from "../api/errors";
import { useModule, useSchemaOffered } from "../api/queries";
import type { ActionInfo, EffectDecl } from "../api/types";
import { Button, Chip, ErrorPanel, Section, Spinner } from "../components/ui";
import { keyed } from "../lib/format";
import { Diagram } from "./Diagram";
import { SchemaExport } from "./SchemaExport";
import { SchemaImport } from "./SchemaImport";
import { Types } from "./SchemaTypes";
import { DEFAULT_EXPLORER_BASE, UmfSource } from "./UmfSource";

type View = "live" | "umf" | "import";

export function describeEffect(e: EffectDecl): string {
  const bits = [e.op, e.type ?? e.ref_type ?? ""].filter(Boolean).join(" ");
  const props =
    e.properties && typeof e.properties === "object" ? Object.keys(e.properties as object) : [];
  const unset = Array.isArray(e.unset) ? (e.unset as string[]) : [];
  return `${bits}${props.length ? ` (sets ${props.join(", ")})` : ""}${unset.length ? ` (unsets ${unset.join(", ")})` : ""}`;
}

function ActionDecl({ a }: { a: ActionInfo }) {
  return (
    <details
      className="rounded border border-line bg-surface"
      data-testid={`action-decl-${a.name}`}
    >
      <summary className="cursor-pointer px-2 py-1.5">
        <span className="font-medium">{a.name}</span>
        <span className="ml-2 text-muted">{a.description}</span>
      </summary>
      <div className="grid gap-3 border-t border-line p-2 md:grid-cols-3">
        <div>
          <div className="mb-1 text-[11px] font-semibold uppercase text-muted">Inputs</div>
          {a.inputSpecs.length === 0 ? (
            <div className="text-muted">none</div>
          ) : (
            <ul className="m-0 list-none space-y-0.5 p-0">
              {a.inputSpecs.map((i) => (
                <li key={i.name}>
                  <span className="arras-mono">{i.name}</span>:{" "}
                  <span className="arras-mono">{i.type}</span> <Chip>{i.kind}</Chip>{" "}
                  <Chip>{i.cardinality}</Chip>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <div className="mb-1 text-[11px] font-semibold uppercase text-muted">Preconditions</div>
          {a.preconditions.length === 0 ? (
            <div className="text-muted">none</div>
          ) : (
            <ul className="m-0 list-none space-y-0.5 p-0">
              {a.preconditions.map((p) => (
                <li key={p.id}>
                  <span className="arras-mono">{p.id}</span>: {p.reason}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <div className="mb-1 text-[11px] font-semibold uppercase text-muted">Effects</div>
          <ul className="m-0 list-none space-y-0.5 p-0">
            {keyed(a.effects, (e) => describeEffect(e)).map(({ key, item: e }) => (
              <li key={key} className="arras-mono">
                {describeEffect(e)}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </details>
  );
}

/**
 * The model's view. The UMF source is the route's when it holds the choice (`onView`); the Live
 * registry and Import are the page's own, so Back to the types returns to the one last used.
 */
function useModelView(umf: boolean | undefined, onView: ((umf: boolean) => void) | undefined) {
  const [local, setLocal] = useState<View>("live");
  const view: View = onView ? (umf ? "umf" : local === "import" ? "import" : "live") : local;
  const choose = (v: View) => {
    setLocal(v);
    if (onView && (v === "umf" || view === "umf")) onView(v === "umf");
  };
  return [view, choose] as const;
}

function ViewBar({
  view,
  offered,
  onView,
}: {
  view: View;
  offered: boolean;
  /** The second argument: the choice was made with the keyboard (a click with no pointer). */
  onView: (v: View, byKeyboard: boolean) => void;
}) {
  const choices: (readonly [View, string])[] = [
    ["live", "Live registry"],
    ["umf", "UMF source"],
    ...(offered ? ([["import", "Import"]] as const) : []),
  ];
  return (
    <fieldset aria-label="Model view" className="m-0 flex min-w-0 gap-1 border-0 p-0">
      {choices.map(([v, label]) => (
        <Button
          key={v}
          variant={view === v ? "primary" : "default"}
          aria-pressed={view === v}
          onClick={(e) => onView(v, e.detail === 0)}
        >
          {label}
        </Button>
      ))}
    </fieldset>
  );
}

/**
 * US-060: a module's types, relationships (with the diagram), actions, placement and revision, as
 * this deployment serves them; and (OPR-11) its registered UMF document in UMF's own explorer.
 */
export function SchemaBrowser({
  module: name,
  explorerBase = DEFAULT_EXPLORER_BASE,
  onOpenData,
  onShowGraph,
  onOpenActions,
  onOpenQuery,
  selectedType,
  umf,
  onSelectType,
  onView,
}: {
  module: string;
  explorerBase?: string;
  /** The type the route selects (a card in the live registry, the selection in the UMF source). */
  selectedType?: string;
  /** The route shows the UMF source; with `onView` the route owns that choice. */
  umf?: boolean;
  /** A type was chosen in the live registry or in the UMF source; undefined clears the choice. */
  onSelectType?: (type: string | undefined) => void;
  /** The UMF source was opened (true) or left (false). */
  onView?: (umf: boolean) => void;
  /** From a type card and the UMF source view: open an entity type in Data. */
  onOpenData?: (type: string) => void;
  /** From a type card and the UMF source view: show an entity type in Graph. */
  onShowGraph?: (type: string) => void;
  /** From a type card that has actions: open the actions for a type (the second argument names its first one). */
  onOpenActions?: (type: string, action?: string) => void;
  /** From a type card: open Query on a starter statement for the type. */
  onOpenQuery?: (type: string) => void;
}) {
  const { module: m, meta } = useModule(name);
  const [diagram, setDiagram] = useState(true);
  const [view, setView] = useModelView(umf, onView);
  // Opened with the keyboard (a click with no pointer, `detail` 0): focus moves into the browser.
  const [byKeyboard, setByKeyboard] = useState(false);
  // Import is offered only where the host mounted the schema surface (CONTRACT-011).
  const offered = useSchemaOffered().data === true;
  if (meta.isPending) return <Spinner label="Loading model" />;
  if (meta.error) return <ErrorPanel error={meta.error} onRetry={() => void meta.refetch()} />;
  if (!m) return <ErrorPanel error={new ApiError(404, { message: "not found" })} />;
  const views = (
    <ViewBar
      view={view}
      offered={offered}
      onView={(v, byKeyboard) => {
        setByKeyboard(byKeyboard);
        setView(v);
      }}
    />
  );
  if (view === "import" && offered) {
    return (
      <div className="flex min-h-0 flex-1 flex-col gap-3 p-3" data-testid="schema">
        <div className="flex flex-wrap items-center gap-2">
          {views}
          <SchemaExport module={m.name} />
        </div>
        <SchemaImport module={m.name} />
      </div>
    );
  }
  if (view === "umf") {
    return (
      <div className="flex min-h-0 flex-1 flex-col gap-3 p-3" data-testid="schema">
        <div className="flex flex-wrap items-center gap-2">
          {views}
          <SchemaExport module={m.name} />
        </div>
        <UmfSource
          module={m.name}
          explorerBase={explorerBase}
          onOpenData={onOpenData}
          onShowGraph={onShowGraph}
          type={selectedType}
          onSelectType={onSelectType}
          focusOnReady={byKeyboard}
        />
      </div>
    );
  }
  return (
    <div className="p-3" data-testid="schema">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {views}
        <SchemaExport module={m.name} />
        <Chip tone="accent" title="The reader that is the system of record: it serves LATEST">
          record: {m.record}
        </Chip>
        <Chip title="Replicas serve BULK reads">replicas: {m.replicas.join(", ") || "none"}</Chip>
        <Chip title="The registry revision at load; refresh to re-read">
          revision: <span className="arras-mono">{JSON.stringify(m.revision)}</span>
        </Chip>
        <Button className="ml-auto" onClick={() => void meta.refetch()}>
          Refresh
        </Button>
      </div>

      <Section title={`Types (${m.entityTypes.length})`}>
        <Types
          m={m}
          links={{ onOpenData, onShowGraph, onOpenActions, onOpenQuery }}
          selected={selectedType}
          onSelect={onSelectType}
        />
      </Section>

      <Section
        title={`Relationships (${m.relationships.length})`}
        aside={
          <Button
            variant={diagram ? "primary" : "default"}
            aria-pressed={diagram}
            onClick={() => setDiagram((d) => !d)}
          >
            Diagram
          </Button>
        }
      >
        <div
          className={`grid items-start gap-3 ${diagram ? "min-[1400px]:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]" : ""}`}
        >
          {m.relationships.length === 0 ? (
            <div className="text-muted">This module declares no relationships.</div>
          ) : (
            <section
              className="min-w-0 overflow-x-auto"
              aria-label="Relationships"
              // biome-ignore lint/a11y/noNoninteractiveTabindex: a table that scrolls sideways on a phone is reached by keyboard (axe scrollable-region-focusable)
              tabIndex={0}
            >
              <table className="arras-table w-full rounded border border-line bg-surface">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Source</th>
                    <th>Target</th>
                    <th>Multiplicity</th>
                    <th>Lifecycle</th>
                    <th>Inverse</th>
                  </tr>
                </thead>
                <tbody>
                  {m.relationships.map((r) => (
                    <tr key={r.name} data-testid={`rel-${r.name}`}>
                      <td className="arras-mono">{r.name}</td>
                      <td>{r.source.join(", ")}</td>
                      <td>{r.target.join(", ")}</td>
                      <td className="arras-mono">
                        {r.sourceMultiplicity} → {r.targetMultiplicity}
                      </td>
                      <td>{r.lifecycle}</td>
                      <td className="arras-mono">{r.inverse ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
          {diagram && <Diagram module={m} />}
        </div>
      </Section>

      <Section title={`Actions (${m.actions.length})`}>
        <div className="space-y-1">
          {m.actions.map((a) => (
            <ActionDecl key={a.name} a={a} />
          ))}
          {m.actions.length === 0 && (
            <div className="text-muted">This module declares no actions.</div>
          )}
        </div>
      </Section>
    </div>
  );
}
