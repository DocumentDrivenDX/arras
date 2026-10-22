// SPDX-License-Identifier: MIT OR Apache-2.0
import { shortName } from "../api/gql";
import type { ModuleInfo } from "../api/types";
import { Button, Chip, Empty, Notice, Spinner } from "../components/ui";
import { GRAPH_CAP, GRAPH_PAGE, type LaneSpec, laneTitle, type ModuleGraph } from "../lib/graph";
import { ENTITIES } from "../lib/vocabulary";
import { FreshnessBar } from "./EntityFreshness";
import { GraphView, type VEdge, type VNode } from "./GraphView";

export interface ChangedBy {
  label: string;
  /** `type:key` of each changed entity. */
  ids: string[];
}

export interface GraphViewModel {
  nodes: VNode[];
  edges: VEdge[];
  dimmed: Set<string> | undefined;
  lanes: LaneSpec[];
  matches: number | null;
}

/** The types hidden on arrival: every type but `only`, when `only` is one of the module's. */
export function othersOf(m: ModuleInfo | undefined, only: string | null | undefined): Set<string> {
  if (!(m && only) || !m.entityTypes.some((t) => t.name === only)) return new Set();
  return new Set(m.entityTypes.filter((t) => t.name !== only).map((t) => t.name));
}

export function toggled(set: Set<string>, v: string): Set<string> {
  const n = new Set(set);
  if (n.has(v)) n.delete(v);
  else n.add(v);
  return n;
}

function laneSpecs(graph: ModuleGraph, m: ModuleInfo, hiddenTypes: Set<string>): LaneSpec[] {
  const own = m.entityTypes
    .filter((t) => !hiddenTypes.has(t.name))
    .map((t) => ({
      id: t.name,
      title: laneTitle(t.name),
      foreign: false,
      count: graph.nodes.filter((n) => n.type === t.name).length,
    }));
  const foreignTypes = new Set(
    graph.nodes
      .filter((n) => n.stub && !m.entityTypes.some((t) => t.name === n.type))
      .map((n) => n.type),
  );
  const foreign = [...foreignTypes].map((t) => ({
    id: t,
    title: t,
    foreign: true,
    count: graph.nodes.filter((n) => n.type === t).length,
  }));
  return [...own, ...foreign];
}

const matchesNeedle = (n: VNode, needle: string) =>
  n.label.toLowerCase().includes(needle) || n.key.toLowerCase().includes(needle);

export function buildView(
  graph: ModuleGraph,
  m: ModuleInfo,
  hiddenTypes: Set<string>,
  hiddenRels: Set<string>,
  text: string,
  changedSet: Set<string>,
): GraphViewModel {
  const needle = text.trim().toLowerCase();
  const nodes: VNode[] = graph.nodes
    .filter((n) => !hiddenTypes.has(n.type))
    .map((n) => ({
      id: n.id,
      type: n.type,
      key: n.key,
      label: n.label,
      stub: n.stub,
      changed: changedSet.has(n.id),
    }));
  const ids = new Set(nodes.map((n) => n.id));
  const edges: VEdge[] = graph.edges.filter(
    (e) => !hiddenRels.has(e.rel) && ids.has(e.from) && ids.has(e.to),
  );
  const dimmed = needle
    ? new Set(nodes.filter((n) => !matchesNeedle(n, needle)).map((n) => n.id))
    : undefined;
  return {
    nodes,
    edges,
    dimmed,
    lanes: laneSpecs(graph, m, hiddenTypes),
    matches: needle ? nodes.length - (dimmed?.size ?? 0) : null,
  };
}

export function Seg<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: T[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <fieldset
      aria-label={label}
      className="m-0 inline-flex min-w-0 overflow-hidden rounded border border-strong p-0"
    >
      {options.map((o) => (
        <button
          key={o}
          type="button"
          aria-pressed={o === value}
          onClick={() => onChange(o)}
          className={`px-2 py-0.5 text-[12px] font-medium ${o === value ? "bg-accent text-accentfg" : "bg-surface text-fg hover:bg-surface2"}`}
        >
          {o}
        </button>
      ))}
    </fieldset>
  );
}

export function GraphToolbar({
  consistency,
  onConsistency,
  graph,
  m,
  showKeys,
  onShowKeys,
  text,
  onText,
  onRefresh,
}: {
  consistency: "LATEST" | "BULK";
  onConsistency: (c: "LATEST" | "BULK") => void;
  graph: ModuleGraph | null | undefined;
  m: ModuleInfo;
  showKeys: boolean;
  onShowKeys: (v: boolean) => void;
  text: string;
  onText: (v: string) => void;
  onRefresh: () => void;
}) {
  return (
    <div className="flex min-h-[44px] flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-line bg-surface px-3 py-2">
      <Seg
        label="Consistency"
        value={consistency}
        options={["LATEST", "BULK"]}
        onChange={onConsistency}
      />
      <FreshnessBar freshness={graph?.freshness} module={m} />
      <div className="ml-auto flex items-center gap-2">
        <div className="flex items-center gap-1.5 text-[12px] text-muted">
          Label
          <Seg
            label="Entity text"
            value={showKeys ? "key" : "name"}
            options={["name", "key"]}
            onChange={(v) => onShowKeys(v === "key")}
          />
        </div>
        <input
          type="search"
          aria-label={`Filter ${ENTITIES}`}
          placeholder="Find in graph…"
          value={text}
          onChange={(e) => onText(e.target.value)}
          data-filter
          className="w-44 rounded border border-strong bg-surface px-2 py-0.5 text-[12px]"
        />
        <Button onClick={onRefresh} title="Read the graph again">
          Refresh
        </Button>
      </div>
    </div>
  );
}

function TypeToggles({
  m,
  graph,
  hiddenTypes,
  onToggle,
}: {
  m: ModuleInfo;
  graph: ModuleGraph | null | undefined;
  hiddenTypes: Set<string>;
  onToggle: (name: string) => void;
}) {
  const maxCount = Math.max(1, ...(graph?.types ?? []).map((t) => t.loaded));
  return (
    <fieldset
      aria-label="Types"
      className="m-0 flex min-w-0 flex-wrap items-center gap-1.5 border-0 p-0"
    >
      {m.entityTypes.map((t) => {
        const stat = graph?.types.find((s) => s.type === t.name);
        const on = !hiddenTypes.has(t.name);
        return (
          <button
            key={t.name}
            type="button"
            aria-pressed={on}
            onClick={() => onToggle(t.name)}
            title={`${on ? "Hide" : "Show"} ${shortName(t.name)} entities`}
            className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[12px] ${on ? "border-accent/60 bg-accentsoft font-medium" : "border-line bg-surface text-muted line-through"}`}
          >
            {shortName(t.name)}
            <span className="arras-mono">
              {stat ? `${stat.loaded}${stat.more ? "+" : ""}` : "…"}
            </span>
            <span aria-hidden="true" className="inline-block h-1.5 w-10 rounded-sm bg-line">
              <span
                className="block h-1.5 rounded-sm bg-accent"
                style={{ width: `${Math.round(((stat?.loaded ?? 0) / maxCount) * 100)}%` }}
              />
            </span>
          </button>
        );
      })}
    </fieldset>
  );
}

function RelToggles({
  m,
  graph,
  hiddenRels,
  onToggle,
}: {
  m: ModuleInfo;
  graph: ModuleGraph | null | undefined;
  hiddenRels: Set<string>;
  onToggle: (name: string) => void;
}) {
  const relCounts = new Map<string, number>();
  for (const e of graph?.edges ?? []) relCounts.set(e.rel, (relCounts.get(e.rel) ?? 0) + 1);
  return (
    <fieldset
      aria-label="Relationships"
      className="m-0 flex min-w-0 flex-wrap items-center gap-1.5 border-0 p-0"
    >
      {m.relationships.map((r) => {
        const on = !hiddenRels.has(r.name);
        return (
          <button
            key={r.name}
            type="button"
            aria-pressed={on}
            onClick={() => onToggle(r.name)}
            title={`${on ? "Hide" : "Show"} ${r.name} links (${r.sourceMultiplicity} → ${r.targetMultiplicity})`}
            className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[12px] ${on ? "border-strong bg-surface" : "border-line bg-surface text-muted line-through"}`}
          >
            <span aria-hidden="true" className="inline-block w-3 border-t-2 border-strong" />
            <span className="arras-mono">{r.name}</span>
            <span className="arras-mono text-muted">{relCounts.get(r.name) ?? 0}</span>
          </button>
        );
      })}
    </fieldset>
  );
}

export function Overview({
  m,
  graph,
  hiddenTypes,
  hiddenRels,
  matches,
  onToggleType,
  onToggleRel,
}: {
  m: ModuleInfo;
  graph: ModuleGraph | null | undefined;
  hiddenTypes: Set<string>;
  hiddenRels: Set<string>;
  matches: number | null | undefined;
  onToggleType: (name: string) => void;
  onToggleRel: (name: string) => void;
}) {
  return (
    <div
      className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-b border-line bg-bg px-3 py-1.5"
      data-testid="overview"
    >
      <TypeToggles m={m} graph={graph} hiddenTypes={hiddenTypes} onToggle={onToggleType} />
      <RelToggles m={m} graph={graph} hiddenRels={hiddenRels} onToggle={onToggleRel} />
      {matches !== null && matches !== undefined && (
        <span className="text-[12px] text-muted" role="status">
          {matches} match{matches === 1 ? "" : "es"}
        </span>
      )}
    </div>
  );
}

export function ChangedBanner({
  changed,
  onDismiss,
}: {
  changed: ChangedBy;
  onDismiss?: () => void;
}) {
  return (
    <div className="border-b border-warn/40 bg-warnsoft px-3 py-1.5" data-testid="changed-banner">
      <div className="flex items-center gap-2 text-[12px]">
        <Chip tone="warn">changed</Chip>
        <span>
          Changed by <strong className="arras-mono">{changed.label}</strong>: {changed.ids.length}{" "}
          {changed.ids.length === 1 ? "entity" : "entities"} outlined.
        </span>
        <Button className="ml-auto" onClick={onDismiss}>
          Dismiss
        </Button>
      </div>
    </div>
  );
}

export function GraphNotices({ graph }: { graph: ModuleGraph | null | undefined }) {
  const total = graph?.loaded ?? 0;
  const failed = (graph?.types ?? []).filter((t) => t.error);
  return (
    <>
      {graph && (graph.more || graph.shown < total) && (
        <div className="px-3 pt-2">
          <Notice tone="warn" role="status">
            <span data-testid="truncation">
              Showing {graph.shown} of {total}
              {graph.more ? "+" : ""} entities
            </span>{" "}
            ({GRAPH_PAGE} read per type, {GRAPH_CAP} drawn, connected entities first). Use the
            Entities area for the rest
            {graph.hiddenEdges > 0
              ? `; ${graph.hiddenEdges} links to entities not shown are hidden`
              : ""}
            .
          </Notice>
        </div>
      )}
      {failed.length > 0 && (
        <div className="px-3 pt-2">
          <Notice tone="bad" role="alert">
            Could not read {failed.map((f) => shortName(f.type)).join(", ")}; the rest of the graph
            is shown.
          </Notice>
        </div>
      )}
    </>
  );
}

export function GraphCanvas({
  m,
  graph,
  view,
  selected,
  showKeys,
  onSelect,
}: {
  m: ModuleInfo;
  graph: ModuleGraph | null | undefined;
  view: GraphViewModel | null;
  selected: string | null;
  showKeys: boolean;
  onSelect: (id: string) => void;
}) {
  if (!graph || (graph.pending > 0 && graph.nodes.length === 0)) {
    return <Spinner label="Reading the graph" />;
  }
  if (graph.nodes.length === 0) {
    return (
      <Empty title="No entities yet">
        Entities appear here once an action such as{" "}
        {m.actions[0] ? shortName(m.actions[0].name) : "an action"} creates them.
      </Empty>
    );
  }
  if (!view) return null;
  return (
    <GraphView
      nodes={view.nodes}
      edges={view.edges}
      lanes={view.lanes}
      selectedId={selected}
      showKeys={showKeys}
      dimmed={view.dimmed}
      ariaLabel={`Graph of module ${m.name}: ${graph.shown} entities, ${graph.edges.length} links. Arrow keys move between entities, Enter opens one.`}
      onSelect={onSelect}
    />
  );
}
