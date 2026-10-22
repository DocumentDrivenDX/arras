// SPDX-License-Identifier: MIT OR Apache-2.0

import { useEffect, useRef } from "react";
import type { EntityTypeInfo, ModuleInfo } from "../api/types";
import { ViewInExplore } from "../components/ExploreLink";
import { useExploreLink } from "../components/NavLink";
import { Button, Chip } from "../components/ui";
import { Button as WidgetButton } from "../ds";
import { actionsFor, capabilityLine } from "../lib/typeSummary";
import { AREA_LABELS } from "../lib/vocabulary";

/** What each type card offers: a callback present means its link is shown. */
export interface TypeLinks {
  onOpenData?: (type: string) => void;
  onShowGraph?: (type: string) => void;
  /** The second argument is the first of the type's actions, when it has one; the link shows only then. */
  onOpenActions?: (type: string, action?: string) => void;
  onOpenQuery?: (type: string) => void;
}

function PropertyItem({ p }: { p: EntityTypeInfo["properties"][number] }) {
  return (
    <li
      className="inline-flex items-baseline gap-1 rounded border border-line bg-bg px-1.5 py-0.5 text-[12px]"
      title={`${p.name}: ${p.type}, ${p.required ? "required" : "optional"}, ${p.cardinality}`}
    >
      <span className="arras-mono font-medium">{p.name}</span>
      <span className="text-muted">{p.type}</span>
      {p.required && (
        <span className="text-bad">
          <span aria-hidden="true">*</span>
          <span className="sr-only">required</span>
        </span>
      )}
      {p.cardinality !== "one" && p.cardinality !== "optional" && (
        <span className="text-muted">[{p.cardinality}]</span>
      )}
    </li>
  );
}

function BackendCapabilities({
  backend,
  c,
  record,
}: {
  backend: string;
  c: EntityTypeInfo["capabilities"][string];
  record: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      <Chip tone={backend === record ? "accent" : "neutral"}>{backend}</Chip>
      <Chip tone={c.mutable ? "ok" : "neutral"}>{c.mutable ? "mutable" : "read-only"}</Chip>
      {c.latency_class && <Chip>{c.latency_class}</Chip>}
      {c.count && <Chip>count</Chip>}
      <span className="text-muted">
        filter columns: <span className="arras-mono">{(c.columns ?? []).join(", ") || "none"}</span>
        {c.relationships?.length ? (
          <>
            {" "}
            relationships: <span className="arras-mono">{c.relationships.join(", ")}</span>
          </>
        ) : null}
      </span>
    </div>
  );
}

function CardLinks({ t, links, action }: { t: EntityTypeInfo; links: TypeLinks; action?: string }) {
  const short = t.name.slice(t.name.lastIndexOf(".") + 1);
  const items: [string, string, (() => void) | undefined][] = [
    [
      AREA_LABELS.entities,
      `${AREA_LABELS.entities} of ${short}`,
      links.onOpenData && (() => links.onOpenData?.(t.name)),
    ],
    [
      AREA_LABELS.graph,
      `${AREA_LABELS.graph} of ${short}`,
      links.onShowGraph && (() => links.onShowGraph?.(t.name)),
    ],
    [
      AREA_LABELS.actions,
      `${AREA_LABELS.actions} of ${short}`,
      action !== undefined && links.onOpenActions
        ? () => links.onOpenActions?.(t.name, action)
        : undefined,
    ],
    [
      AREA_LABELS.query,
      `${AREA_LABELS.query} ${short}`,
      links.onOpenQuery && (() => links.onOpenQuery?.(t.name)),
    ],
  ];
  const shown = items.filter(([, , go]) => go);
  const toExplore = useExploreLink();
  if (shown.length === 0 && !toExplore) return null;
  return (
    <nav
      aria-label={`${short} links`}
      className="flex flex-wrap gap-1 border-t border-line px-2.5 py-1.5"
    >
      {shown.map(([text, label, go]) => (
        <Button key={text} aria-label={label} onClick={go}>
          {text}
        </Button>
      ))}
      <ViewInExplore
        target={{ type: { module: t.name.slice(0, t.name.lastIndexOf(".")), type: t.name } }}
        label={short}
      />
    </nav>
  );
}

function TypeCard({
  t,
  m,
  links,
  selected,
  onSelect,
}: {
  t: EntityTypeInfo;
  m: Pick<ModuleInfo, "record" | "actions">;
  links: TypeLinks;
  selected: boolean;
  onSelect?: (type: string | undefined) => void;
}) {
  const line = capabilityLine(t, m.record);
  const card = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (selected) card.current?.scrollIntoView?.({ block: "nearest" });
  }, [selected]);
  return (
    <div
      ref={card}
      className={`rounded border bg-surface ${selected ? "border-accent" : "border-line"}`}
      data-testid={`type-${t.name}`}
      aria-current={selected ? "true" : undefined}
    >
      <div className="flex items-center justify-between border-b border-line px-2.5 py-1.5">
        {onSelect ? (
          <WidgetButton
            variant="text"
            size="sm"
            aria-pressed={selected}
            aria-label={`Select ${t.name}`}
            onClick={() => onSelect(selected ? undefined : t.name)}
          >
            {t.name}
          </WidgetButton>
        ) : (
          <span className="font-semibold">{t.name}</span>
        )}
        <span className="text-[12px] text-muted">
          key <span className="arras-mono">{t.key}</span>
        </span>
      </div>
      <ul
        className="m-0 flex list-none flex-wrap gap-1 p-2.5"
        aria-label={`Properties of ${t.name}`}
      >
        {t.properties.map((p) => (
          <PropertyItem key={p.name} p={p} />
        ))}
      </ul>
      {line && (
        <p
          className="m-0 border-t border-line px-2.5 pt-1.5 text-[12px]"
          data-testid="type-summary"
        >
          {line}
        </p>
      )}
      <details className="px-2.5 pb-1.5 text-[12px]" data-testid="type-details">
        <summary className="cursor-pointer text-muted">Details</summary>
        <div className="mt-1 space-y-1">
          {Object.entries(t.capabilities).map(([backend, c]) => (
            <BackendCapabilities key={backend} backend={backend} c={c} record={m.record} />
          ))}
        </div>
      </details>
      <CardLinks t={t} links={links} action={actionsFor(m, t.name)[0]?.name} />
    </div>
  );
}

export function Types({
  m,
  links,
  selected,
  onSelect,
}: {
  m: ModuleInfo;
  links: TypeLinks;
  /** The type the route selects. */
  selected?: string;
  /** A type was chosen (or chosen again, to clear it); the cards offer the choice only when given. */
  onSelect?: (type: string | undefined) => void;
}) {
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(340px,1fr))] gap-3">
      {m.entityTypes.map((t) => (
        <TypeCard
          key={t.name}
          t={t}
          m={m}
          links={links}
          selected={t.name === selected}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}
