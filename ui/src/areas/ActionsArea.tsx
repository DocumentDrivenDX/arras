// SPDX-License-Identifier: MIT OR Apache-2.0
import { useState } from "react";
import { useRefusals } from "../api/context";
import { useModule } from "../api/queries";
import { TabList } from "../components/Tabs";
import { Empty, ErrorPanel, Spinner } from "../components/ui";
import { contextOf, type EntityContext, refPrefill } from "../lib/actionGroups";
import { ActionForm } from "./ActionForm";
import { ActionList } from "./ActionList";
import { defaultAction } from "./actionRelevance";
import { BatchForm } from "./BatchForm";
import { ImpactPanel, type ImpactState } from "./ImpactPanel";

export interface ActionsAreaProps {
  module: string;
  action?: string;
  prefill?: Record<string, string>;
  onAction: (action: string | undefined) => void;
  /** A reverse or follow-up action chosen from the impact view, with its inputs prefilled. */
  onNextAction?: (action: string, prefill: Record<string, string>) => void;
  /** Jump to the graph with the changed entities highlighted. */
  onViewInGraph?: (change: { label: string; ids: string[] }) => void;
}

/** The entity the area was opened for, kept while other actions of the module are chosen. */
function useEntityContext(module: string, opened: EntityContext | undefined) {
  const [held, setHeld] = useState<{ module: string; ctx: EntityContext } | null>(null);
  if (
    opened &&
    (held?.module !== module || held.ctx.key !== opened.key || held.ctx.type !== opened.type)
  ) {
    setHeld({ module, ctx: opened });
  }
  return opened ?? (held?.module === module ? held.ctx : undefined);
}

/**
 * The actions a module declares (list), the form (or batch) for the chosen one, and the impact the
 * reviewed change would have on the graph. Never blank: with none chosen, the first action relevant to
 * the entity in context opens, else the first declared.
 */
export function ActionsArea({
  module: name,
  action,
  prefill: requested,
  onAction,
  onNextAction,
  onViewInGraph,
}: ActionsAreaProps) {
  const { module: m, meta } = useModule(name);
  const { refusals } = useRefusals();
  const [mode, setMode] = useState<"single" | "batch">("single");
  const [impact, setImpact] = useState<ImpactState | null>(null);
  const prefill = m ? refPrefill(m, action, requested) : undefined;
  const ctx = useEntityContext(name, m ? contextOf(m, action, prefill) : undefined);
  if (meta.isPending) return <Spinner label="Loading actions" />;
  if (meta.error) return <ErrorPanel error={meta.error} />;
  if (!m) return null;
  const current = defaultAction(m, action, ctx);
  if (!current) return <Empty title="This module declares no actions" />;
  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[200px_minmax(0,1fr)] min-[1280px]:grid-cols-[200px_minmax(380px,520px)_minmax(0,1fr)]">
      <ActionList
        module={m}
        current={current}
        context={ctx}
        refusals={refusals}
        onPick={(a) => {
          setImpact(null);
          onAction(a);
        }}
      />
      <div className="min-h-0 min-w-0 overflow-auto min-[1280px]:border-r min-[1280px]:border-line">
        <TabList
          label="Mode"
          className="flex gap-1 border-b border-line bg-surface px-3 pt-1.5"
          items={[
            { id: "single", label: "One" },
            { id: "batch", label: "Batch" },
          ]}
          selected={mode}
          onSelect={(id) => setMode(id === "batch" ? "batch" : "single")}
          tabClass={(on) =>
            `rounded-t border border-b-0 px-3 py-1 text-[12px] ${on ? "border-line bg-bg font-semibold" : "border-transparent text-muted"}`
          }
        />
        {mode === "single" ? (
          <ActionForm
            key={`${name}:${current}:${JSON.stringify(prefill ?? {})}`}
            module={name}
            action={current}
            prefill={action ? prefill : undefined}
            onState={setImpact}
            onViewInGraph={onViewInGraph}
          />
        ) : (
          <BatchForm key={`${name}:${current}`} module={name} action={current} />
        )}
      </div>
      {mode === "single" && (
        <div className="min-h-0 min-w-0 overflow-auto bg-surface min-[1280px]:bg-bg md:max-[1279px]:col-start-2 max-[1279px]:border-t max-[1279px]:border-line">
          <ImpactPanel module={name} state={impact} onNextAction={onNextAction} />
        </div>
      )}
    </div>
  );
}
