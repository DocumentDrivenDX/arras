// SPDX-License-Identifier: MIT OR Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useClient } from "../api/context";
import { shortName } from "../api/gql";
import { useModule } from "../api/queries";
import { Button, CopyButton, ErrorPanel, Notice, Section, Spinner } from "../components/ui";
import { type PropertyAction, propertyActions } from "../kit";
import { fmtTime, fmtValue } from "../lib/format";
import { requestInputFocus, useFormFocus } from "../lib/formFocus";
import { EntityActionBar } from "./EntityActionBar";
import { Relationships } from "./EntityRelationships";
import { type EntityData, type Entry, fetchEntity } from "./entity";

export interface EntityPanelProps {
  module: string;
  /** The trail of entities opened; the last is shown. */
  trail: Entry[];
  onTrail: (t: Entry[]) => void;
  onClose: () => void;
  onAction?: (action: string, prefill: Record<string, string>) => void;
  onHistory?: (type: string, key: string) => void;
  onOpenModule?: (module: string) => void;
  /** Show this entity in the Graph area (offered from the Data area). */
  onGraph?: (type: string, key: string) => void;
  consistency?: "LATEST" | "BULK";
}

function Attribution({ e }: { e: EntityData }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
      <dt className="text-muted">Version</dt>
      <dd className="m-0 arras-mono" data-testid="entity-version">
        {e.version ?? "—"}
      </dd>
      <dt className="text-muted">Created by</dt>
      <dd className="m-0" data-testid="entity-created-by">
        {e.createdBy ?? "—"}
      </dd>
      <dt className="text-muted">Created at</dt>
      <dd className="m-0">{fmtTime(e.createdAt)}</dd>
      <dt className="text-muted">Updated by</dt>
      <dd className="m-0" data-testid="entity-updated-by">
        {e.updatedBy ?? "—"}
      </dd>
      <dt className="text-muted">Updated at</dt>
      <dd className="m-0">{fmtTime(e.updatedAt)}</dd>
    </dl>
  );
}

function EntityHeader({
  entry,
  trail,
  onTrail,
  onClose,
  headingRef,
}: Pick<EntityPanelProps, "trail" | "onTrail" | "onClose"> & {
  entry: Entry;
  headingRef: React.Ref<HTMLHeadingElement>;
}) {
  return (
    <div className="flex items-center gap-1.5 border-b border-line px-3 py-2">
      <div className="min-w-0 flex-1">
        <div className="truncate text-[11px] text-muted">
          {trail.length > 1 && (
            <button
              type="button"
              className="mr-1 text-accent underline"
              onClick={() => onTrail(trail.slice(0, -1))}
            >
              ← back
            </button>
          )}
          {shortName(entry.type)}
        </div>
        <div className="flex items-center gap-1">
          <h2
            ref={headingRef}
            tabIndex={-1}
            className="m-0 truncate text-[13px] font-semibold arras-mono outline-none focus-visible:underline"
            title={entry.key}
          >
            {entry.key}
          </h2>
          <CopyButton text={entry.key} label="Copy key" />
        </div>
      </div>
      <Button variant="ghost" aria-label="Close entity panel" onClick={onClose}>
        ✕
      </Button>
    </div>
  );
}

function ForeignNotice({
  entry,
  onOpenModule,
}: {
  entry: Entry;
  onOpenModule: EntityPanelProps["onOpenModule"];
}) {
  return (
    <Notice tone="warn">
      This entity belongs to module <strong>{entry.module}</strong>, so only its interface fields
      are shown.{" "}
      {onOpenModule && (
        <button
          type="button"
          className="text-accent underline"
          onClick={() => onOpenModule(entry.module)}
        >
          Open module {entry.module}
        </button>
      )}{" "}
      to read the rest.
    </Notice>
  );
}

function PropertyRow({
  name,
  value,
  change,
  onChange,
}: {
  name: string;
  value: unknown;
  change: PropertyAction | undefined;
  onChange: (c: PropertyAction) => void;
}) {
  return (
    <div className="contents">
      <dt className="text-muted arras-mono">{name}</dt>
      <dd className="m-0 flex items-start gap-1 break-words">
        <span className="min-w-0 flex-1" data-testid={`prop-${name}`}>
          {value === null || value === undefined ? (
            <span className="text-muted">—</span>
          ) : (
            fmtValue(value)
          )}
        </span>
        {change && (
          <button
            type="button"
            className="shrink-0 rounded px-1 text-[11px] text-accent hover:bg-surface2"
            aria-label={`Change ${name}`}
            title={`Change ${name} with ${shortName(change.action)}`}
            onClick={() => onChange(change)}
          >
            <span aria-hidden="true">✎</span>
          </button>
        )}
      </dd>
    </div>
  );
}

function PropertiesSection({
  props,
  changes,
  onChange,
}: {
  props: EntityData["props"];
  changes: Record<string, PropertyAction>;
  onChange: (c: PropertyAction) => void;
}) {
  return (
    <Section title="Properties">
      {Object.keys(props).length === 0 ? (
        <div className="text-muted">No declared properties are shown.</div>
      ) : (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
          {Object.entries(props).map(([k, v]) => (
            <PropertyRow key={k} name={k} value={v} change={changes[k]} onChange={onChange} />
          ))}
        </dl>
      )}
    </Section>
  );
}

/** The panel's focus: into its heading when it opens, back to where it was opened from when it closes. */
function usePanelFocus(
  ready: boolean,
  shown: string | undefined,
  heading: React.RefObject<HTMLHeadingElement | null>,
) {
  const opener = useRef<Element | null>(null);
  opener.current ??= document.activeElement;
  // each entity shown takes the focus once
  useEffect(() => {
    if (ready && shown !== undefined) heading.current?.focus();
  }, [ready, shown, heading]);
  useEffect(
    () => () => {
      const back = opener.current;
      const idle = !document.activeElement || document.activeElement === document.body;
      if (idle && back instanceof HTMLElement && back.isConnected) back.focus();
    },
    [],
  );
}

/** The entity beside the table: properties, attribution, relationships to follow, actions and history. */
export function EntityPanel({
  module: name,
  trail,
  onTrail,
  onClose,
  onAction,
  onHistory,
  onOpenModule,
  onGraph,
  consistency = "LATEST",
}: EntityPanelProps) {
  const formFocus = useFormFocus();
  const client = useClient();
  const { module: m } = useModule(name);
  const entry = trail[trail.length - 1];
  const t = m?.entityTypes.find((x) => x.name === entry?.type);
  const sameModule = entry?.module === name;
  const needFetch = !!entry && !entry.seed && sameModule && !!m && !!t;
  const q = useQuery({
    queryKey: ["entity", name, entry?.type, entry?.key, consistency],
    enabled: needFetch,
    retry: false,
    queryFn: () => {
      if (!(entry && m && t)) throw new Error("entity read without a loaded type");
      return fetchEntity(client, m, t, entry.key, consistency);
    },
  });
  const heading = useRef<HTMLHeadingElement>(null);
  usePanelFocus(
    !!entry && !!m,
    entry ? `${entry.module}:${entry.type}:${entry.key}` : undefined,
    heading,
  );
  if (!entry || !m) return null;
  const data: EntityData | null | undefined = entry.seed ?? q.data;
  const changes = sameModule ? propertyActions(m, entry.type) : {};
  const change = (c: PropertyAction) => {
    requestInputFocus(formFocus, c.action, c.input);
    onAction?.(c.action, { [c.keyInput]: entry.key });
  };

  return (
    <aside
      className="flex min-h-0 w-full shrink-0 flex-col self-stretch border-t border-line bg-surface md:w-[360px] md:border-l md:border-t-0"
      aria-label="Entity"
      data-testid="entity-panel"
      onKeyDown={(e) => {
        if (e.key === "Escape" && !e.defaultPrevented) onClose();
      }}
    >
      <EntityHeader
        entry={entry}
        trail={trail}
        onTrail={onTrail}
        onClose={onClose}
        headingRef={heading}
      />
      {sameModule && data && (
        <EntityActionBar
          module={m}
          entry={entry}
          onAction={onAction}
          onHistory={onHistory}
          onGraph={onGraph}
        />
      )}
      <div className="min-h-0 flex-1 overflow-auto p-3">
        {!sameModule && <ForeignNotice entry={entry} onOpenModule={onOpenModule} />}
        {needFetch && q.isPending && <Spinner />}
        {q.error && <ErrorPanel error={q.error} />}
        {data === null && !q.isPending && (
          <Notice tone="warn">Not found, or you cannot read it.</Notice>
        )}
        {data && (
          <>
            <PropertiesSection
              props={data.props}
              changes={onAction ? changes : {}}
              onChange={change}
            />
            <Section title="Attribution">
              <Attribution e={data} />
            </Section>
            {sameModule && (
              <Relationships
                m={m}
                entry={entry}
                data={data}
                onFollowed={(e) => onTrail([...trail, e])}
              />
            )}
          </>
        )}
      </div>
    </aside>
  );
}
