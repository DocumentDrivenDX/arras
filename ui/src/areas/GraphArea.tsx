// SPDX-License-Identifier: MIT OR Apache-2.0
import { useMemo, useState } from "react";
import { shortName } from "../api/gql";
import { useModule } from "../api/queries";
import { Empty, ErrorPanel, Spinner } from "../components/ui";
import { EntityPanel } from "./EntityPanel";
import type { Entry } from "./entity";
import {
  buildView,
  ChangedBanner,
  type ChangedBy,
  GraphCanvas,
  GraphNotices,
  GraphToolbar,
  Overview,
  othersOf,
  toggled,
} from "./graphAreaParts";
import { useModuleGraph } from "./useGraph";

export type { ChangedBy };

export interface GraphAreaProps {
  module: string;
  onAction?: (action: string, prefill: Record<string, string>) => void;
  onHistory?: (type: string, key: string) => void;
  onOpenModule?: (module: string) => void;
  /** An entity to select on arrival (from the Data area); the console's route holds it. */
  initial?: { type: string; key: string } | null;
  /** The selection changed from the canvas or the panel (null: the panel was closed). */
  onSelect?: (entity: { type: string; key: string } | null) => void;
  /** A type to show on arrival with the others hidden (from the UMF source view); the type toggles bring them back. */
  onlyType?: string | null;
  changed?: ChangedBy | null;
  onDismissChanged?: () => void;
}

/** US-061 and the graph itself: the module's entities in typed lanes, relationships as curves. */
export function GraphArea({
  module: name,
  onAction,
  onHistory,
  onOpenModule,
  initial,
  onSelect,
  onlyType,
  changed,
  onDismissChanged,
}: GraphAreaProps) {
  const { module: m, meta } = useModule(name);
  const [consistency, setConsistency] = useState<"LATEST" | "BULK">("LATEST");
  const { graph, refetch } = useModuleGraph(m, consistency);
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(() => othersOf(m, onlyType));
  const known = !!m;
  const hiddenScope = `${name}|${onlyType ?? ""}|${known}`;
  const [lastHiddenScope, setLastHiddenScope] = useState(hiddenScope);
  if (lastHiddenScope !== hiddenScope) {
    setLastHiddenScope(hiddenScope);
    setHiddenTypes(othersOf(m, onlyType));
  }
  const [hiddenRels, setHiddenRels] = useState<Set<string>>(new Set());
  const [text, setText] = useState("");
  const [showKeys, setShowKeys] = useState(false);
  const [trail, setTrail] = useState<Entry[]>(() =>
    initial ? [{ module: name, type: initial.type, key: initial.key }] : [],
  );
  const [lastTrailScope, setLastTrailScope] = useState({ name, initial });
  if (lastTrailScope.name !== name || lastTrailScope.initial !== initial) {
    setLastTrailScope({ name, initial });
    setTrail(initial ? [{ module: name, type: initial.type, key: initial.key }] : []);
  }

  const typeName = (t: string) =>
    m?.entityTypes.find((e) => shortName(e.name) === shortName(t))?.name ?? t;
  const last = trail[trail.length - 1];
  const selected = last ? `${typeName(last.type)}:${last.key}` : null;
  const changedSet = useMemo(() => new Set(changed?.ids ?? []), [changed]);

  const view = useMemo(
    () => (graph && m ? buildView(graph, m, hiddenTypes, hiddenRels, text, changedSet) : null),
    [graph, m, hiddenTypes, hiddenRels, text, changedSet],
  );

  if (meta.isPending) return <Spinner label="Loading schema" />;
  if (meta.error) return <ErrorPanel error={meta.error} />;
  if (!m) return null;
  if (m.entityTypes.length === 0) return <Empty title="This module declares no types" />;

  return (
    <div className="flex min-h-0 flex-1 flex-col" data-testid="graph-area">
      <GraphToolbar
        consistency={consistency}
        onConsistency={setConsistency}
        graph={graph}
        m={m}
        showKeys={showKeys}
        onShowKeys={setShowKeys}
        text={text}
        onText={setText}
        onRefresh={refetch}
      />
      <Overview
        m={m}
        graph={graph}
        hiddenTypes={hiddenTypes}
        hiddenRels={hiddenRels}
        matches={view?.matches}
        onToggleType={(n) => setHiddenTypes(toggled(hiddenTypes, n))}
        onToggleRel={(n) => setHiddenRels(toggled(hiddenRels, n))}
      />
      {changed && <ChangedBanner changed={changed} onDismiss={onDismissChanged} />}
      <GraphNotices graph={graph} />

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <GraphCanvas
            m={m}
            graph={graph}
            view={view}
            selected={selected}
            showKeys={showKeys}
            onSelect={(id) => {
              const n = graph?.nodes.find((x) => x.id === id);
              if (!n) return;
              setTrail([{ module: n.module, type: n.type, key: n.key }]);
              onSelect?.({ type: typeName(n.type), key: n.key });
            }}
          />
        </div>
        {trail.length > 0 && (
          <EntityPanel
            module={name}
            trail={trail}
            onTrail={setTrail}
            onClose={() => {
              setTrail([]);
              onSelect?.(null);
            }}
            onAction={onAction}
            onHistory={onHistory}
            onOpenModule={onOpenModule}
            consistency={consistency}
          />
        )}
      </div>
    </div>
  );
}
