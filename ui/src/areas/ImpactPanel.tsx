// SPDX-License-Identifier: MIT OR Apache-2.0
import { type UseQueryResult, useQueries } from "@tanstack/react-query";
import { useMemo, useRef } from "react";
import { useClient } from "../api/context";
import { shortName } from "../api/gql";
import { useModule } from "../api/queries";
import type { Effect, Receipt } from "../api/types";
import { Button, Caption, Chip, Notice, Spinner } from "../components/ui";
import { buildImpact, type ImpactModel, nextSteps, summarize } from "../lib/impact";
import { type EntityData, fetchEntity } from "./entity";
import { GraphView } from "./GraphView";
import { useModuleGraph } from "./useGraph";

/** The "before" values read for updated entities; shared structurally, so stable between renders. */
const beforeData = (results: UseQueryResult<EntityData | null, Error>[]) =>
  results.map((r) => r.data);

/** What the action form tells the impact panel. */
export interface ImpactState {
  action: string;
  effects: Effect[];
  /** preview: validated; stale: inputs changed since; applied: invoked, the receipt is in. */
  status: "preview" | "stale" | "applied";
  valid: boolean;
  receipt: Receipt | null;
}

export interface ImpactPanelProps {
  module: string;
  state: ImpactState | null;
  onNextAction?: (action: string, prefill: Record<string, string>) => void;
}

function Legend() {
  const sw = (cls: string, text: string, glyph?: string) => (
    <span className="inline-flex items-center gap-1">
      <span
        aria-hidden="true"
        className={`inline-flex h-3.5 w-5 items-center justify-center rounded-sm border text-[10px] font-bold leading-none ${cls}`}
      >
        {glyph}
      </span>
      {text}
    </span>
  );
  return (
    <fieldset
      className="m-0 flex min-w-0 flex-wrap gap-x-3 gap-y-1 border-0 p-0 text-[11px] text-muted"
      aria-label="Legend"
      data-testid="impact-legend"
    >
      {sw("border-dashed border-ok bg-oksoft text-ok", "created", "+")}
      {sw("border-warn bg-warnsoft text-warn", "updated", "~")}
      {sw("border-bad bg-badsoft text-bad", "deleted", "×")}
      <span className="inline-flex items-center gap-1">
        <span aria-hidden="true" className="inline-block w-5 border-t-2 border-dashed border-ok" />
        link added
      </span>
      <span className="inline-flex items-center gap-1">
        <span aria-hidden="true" className="inline-block w-5 border-t-2 border-dashed border-bad" />
        link removed
      </span>
    </fieldset>
  );
}

type Model = ImpactModel;
type Graph = ReturnType<typeof useModuleGraph>["graph"];
type Mod = NonNullable<ReturnType<typeof useModule>["module"]>;

/** Up to six updated entities whose "before" values a by-key read can answer. */
function updatedRefs(m: Mod | undefined, effects: Effect[]) {
  if (!m) return [];
  const seen = new Set<string>();
  return effects
    .flatMap((e) => (e.kind === "update" && !e.ref.generated ? [e.ref] : []))
    .filter((r) => {
      if (seen.has(r.key)) return false;
      seen.add(r.key);
      return true;
    })
    .slice(0, 6)
    .map((r) => ({
      ref: r,
      type: m.entityTypes.find((t) => shortName(t.name) === shortName(r.type)),
    }));
}

function useImpactModel(name: string, m: Mod | undefined, graph: Graph, state: ImpactState | null) {
  const client = useClient();
  const effects = state?.effects ?? [];
  const updated = useMemo(() => updatedRefs(m, effects), [effects, m]);
  const before = useQueries({
    queries: updated.map(({ ref, type }) => ({
      queryKey: ["entity", name, type?.name, ref.key, "LATEST"],
      enabled: !!m && !!type && state?.status !== "applied",
      retry: false,
      queryFn: () => {
        if (!(m && type)) throw new Error("entity read without a loaded type");
        return fetchEntity(client, m, type, ref.key, "LATEST");
      },
    })),
    combine: beforeData,
  });
  const hasState = !!state;
  const receipt = state?.receipt;
  const live = useMemo<Model | null>(() => {
    if (!m || !hasState || effects.length === 0) return null;
    const values = new Map(
      updated.map((u, i) => [`${u.type?.name ?? u.ref.type}:${u.ref.key}`, before[i]]),
    );
    return buildImpact(m, graph, effects, values, receipt);
  }, [m, graph, effects, updated, before, hasState, receipt]);
  // After the invoke the graph re-reads and the neighbourhood moves on; keep the one that was approved.
  const frozen = useRef<Model | null>(null);
  if (state?.status !== "applied" && live) frozen.current = live;
  if (!state) frozen.current = null;
  return state?.status === "applied" ? (frozen.current ?? live) : live;
}

function StatusChip({ status }: { status: ImpactState["status"] | undefined }) {
  if (status === "preview") return <Chip tone="accent">preview: nothing applied</Chip>;
  if (status === "stale") return <Chip tone="warn">inputs changed; review again</Chip>;
  if (status === "applied") return <Chip tone="ok">applied</Chip>;
  return null;
}

function NoModel({ state }: { state: ImpactState | null }) {
  if (state) {
    if (state.valid) return null;
    return (
      <Notice tone="bad" role="status">
        The inputs are not valid, so there is nothing to preview. Fix the fields and review again.
      </Notice>
    );
  }
  return (
    <div
      className="rounded border border-dashed border-line px-3 py-6 text-center text-muted"
      data-testid="impact-empty"
    >
      <div className="font-medium text-fg">No change reviewed yet</div>
      <div className="mt-0.5">
        Fill the form and choose <em>Review changes</em>. The entities and links it would touch are
        drawn here before anything is applied.
      </div>
    </div>
  );
}

function PropRow({ p }: { p: Model["changes"][number]["props"][number] }) {
  return (
    <tr>
      <td className="arras-mono pr-2 align-top text-muted">{p.prop}</td>
      <td className="arras-mono">
        {p.before !== null && (
          <>
            <span className="text-bad line-through decoration-1">{p.before}</span>
            <span className="px-1 text-muted">
              <span aria-hidden="true">→</span>
              <span className="sr-only">becomes</span>
            </span>
          </>
        )}
        <span className="text-ok">{p.after}</span>
      </td>
    </tr>
  );
}

function PropertyChanges({ model, applied }: { model: Model; applied: boolean }) {
  const changes = model.changes.filter((c) => c.props.length > 0);
  if (changes.length === 0) return null;
  return (
    <div data-testid="impact-changes">
      <Caption>{applied ? "Changed properties" : "Property changes"}</Caption>
      <ul className="m-0 mt-1 list-none space-y-1 p-0">
        {changes.map((c) => (
          <li key={c.id} className="rounded border border-line bg-surface px-2 py-1">
            <div className="flex items-center gap-1.5">
              <Chip tone={c.status === "created" ? "ok" : "warn"}>
                {c.status === "created" ? "new" : "updated"}
              </Chip>
              <span className="text-muted">{shortName(c.type)}</span>
              <span className="arras-mono font-medium">{c.key || "(new key)"}</span>
            </div>
            <table className="mt-0.5 w-full text-[12px]">
              <tbody>
                {c.props.map((p) => (
                  <PropRow key={p.prop} p={p} />
                ))}
              </tbody>
            </table>
          </li>
        ))}
      </ul>
    </div>
  );
}

function NextSteps({
  steps,
  onNextAction,
}: {
  steps: ReturnType<typeof nextSteps>;
  onNextAction?: ImpactPanelProps["onNextAction"];
}) {
  return (
    <div data-testid="next-steps">
      <Caption>Next steps</Caption>
      {steps.length === 0 ? (
        <div className="mt-0.5 text-muted">
          No declared action reverses this. Nothing is offered that the module does not declare.
        </div>
      ) : (
        <ul className="m-0 mt-1 list-none space-y-1 p-0">
          {steps.map((s) => (
            <li key={`${s.action.name}|${s.why}`} className="flex flex-wrap items-center gap-1.5">
              <Button onClick={() => onNextAction?.(s.action.name, s.prefill)}>
                {shortName(s.action.name)}…
              </Button>
              <span className="text-muted">{s.why}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ModelView({
  model,
  state,
  graph,
  applied,
  steps,
  onNextAction,
}: {
  model: Model;
  state: ImpactState | null;
  graph: Graph;
  applied: boolean;
  steps: ReturnType<typeof nextSteps>;
  onNextAction?: ImpactPanelProps["onNextAction"];
}) {
  const stale = state?.status === "stale";
  return (
    <>
      <p className="m-0 text-[13px]" data-testid="impact-summary">
        {summarize(model, applied)}
      </p>
      {stale && <Notice tone="warn">This picture is for the previous inputs.</Notice>}
      <div className={`rounded border border-line bg-surface ${stale ? "opacity-60" : ""}`}>
        {graph?.pending ? <Spinner label="Reading the neighbourhood" /> : null}
        <GraphView
          compact
          nodes={model.nodes}
          edges={model.edges}
          lanes={model.lanes}
          applied={applied}
          testId="impact-graph"
          ariaLabel={`Entities this change ${applied ? "touched" : "would touch"} and their neighbours`}
          maxHeight={360}
        />
      </div>
      {model.omitted > 0 && (
        <div className="text-[11px] text-muted">{model.omitted} more neighbours not drawn.</div>
      )}
      <Legend />
      <PropertyChanges model={model} applied={applied} />
      {applied && <NextSteps steps={steps} onNextAction={onNextAction} />}
    </>
  );
}

/**
 * The neighbourhood a change touches, with what it does drawn on it: created nodes green and dashed,
 * updated amber with before and after, deleted red and struck through, added and removed links as
 * dashed edges. Once applied the same view keeps solid colours. Drawing it never writes.
 */
export function ImpactPanel({ module: name, state, onNextAction }: ImpactPanelProps) {
  const { module: m } = useModule(name);
  const { graph } = useModuleGraph(m);
  const effects = state?.effects ?? [];
  const model = useImpactModel(name, m, graph, state);
  const applied = state?.status === "applied";
  const steps = useMemo(
    () => (m && applied ? nextSteps(m, effects, state?.action) : []),
    [m, applied, effects, state?.action],
  );

  if (!m) return null;
  return (
    <aside
      aria-label="Impact"
      data-testid="impact"
      data-state={state?.status ?? "none"}
      className="flex min-w-0 flex-col gap-3 p-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="m-0 text-[13px] font-semibold">Impact</h2>
        <StatusChip status={state?.status} />
      </div>
      {model ? (
        <ModelView
          model={model}
          state={state}
          graph={graph}
          applied={applied}
          steps={steps}
          onNextAction={onNextAction}
        />
      ) : (
        <NoModel state={state} />
      )}
    </aside>
  );
}
