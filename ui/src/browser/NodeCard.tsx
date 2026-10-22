// SPDX-License-Identifier: MIT OR Apache-2.0
// The node card: header (tone rule, icon tile, title, summary, badges), the sections of the
// resolved view, and the footer with attribution and freshness (DESIGN-GB, Screen 2).
import { useContext, useEffect } from "react";
import type { BackendStatus, FieldView, TypeView } from "../api/types";
import { editPlan } from "../kit";
import { evaluate, placeholders, segments, titleOf, valueText } from "../lib/template";
import { useBrowser } from "./context";
import { Editable, EditTarget, EditToggle } from "./Editable";
import { EditMenu } from "./EditMenu";
import { EditTargetContext } from "./editContext";
import { takeEntityFocus } from "./focusAfter";
import { Icon } from "./icons";
import type { TypeEntry } from "./meta";
import { Footer } from "./NodeFooter";
import { toneClass } from "./tones";
import type { Entity } from "./useNode";
import { Badge, isEmpty, NotSet, Value } from "./Value";

export const entityTitle = (view: TypeView, entity: Entity, key: string) =>
  titleOf(view.title, entity, key);

const fieldOf = (view: TypeView, property: string): FieldView =>
  view.fields.find((f) => f.property === property) ?? {
    property,
    label: property,
    format: "text",
    hideWhenEmpty: false,
    tones: null,
  };

function headerBadges(view: TypeView, entity: Entity): { field: FieldView; text: string }[] {
  return view.fields
    .filter((f) => f.format === "badge" && !isEmpty(entity[f.property]))
    .slice(0, 2)
    .map((field) => ({ field, text: valueText(entity[field.property]) }));
}

/** A property shown as a header badge is not repeated in the sections. */
const inHeader = (view: TypeView, entity: Entity) =>
  new Set(headerBadges(view, entity).map((b) => b.field.property));

/**
 * A header template's text, each property it places editable where a declared action edits it
 * (`editPlan`; never the key). The text is as `evaluate` composes it; the pencil sits beside the
 * value it changes. `muted` names properties whose pencil is drawn elsewhere.
 */
function Templated({
  template,
  view,
  entity,
  muted,
}: {
  template: string;
  view: TypeView;
  entity: Entity;
  muted: Set<string>;
}) {
  const { editing } = useBrowser();
  const get = (n: string) => valueText(entity[n]);
  return (
    <>
      {segments(template, get).map((seg, i) => {
        const key = `${i}-${seg.property ?? ""}`;
        const p = seg.property;
        if (p === undefined || entity[p] === undefined) return seg.text;
        const body = seg.text.trim() === "" && editing ? <NotSet /> : seg.text;
        return (
          <Editable key={key} field={fieldOf(view, p)} value={entity[p]} pencil={!muted.has(p)}>
            {body}
          </Editable>
        );
      })}
    </>
  );
}

/** Properties after the first that share an action with an earlier one (a form edits several at
 *  once): one pencil per action in the header, on the first. */
function useRepeats(entity: Entity, order: string[]): Set<string> {
  const target = useContext(EditTargetContext);
  const seen = new Set<string>();
  const muted = new Set<string>();
  if (!target) return muted;
  for (const p of new Set(order)) {
    if (entity[p] === undefined) continue;
    const plan = editPlan(target.entry.module, target.entry.type, p);
    if (!plan) continue;
    if (seen.has(plan.action)) muted.add(p);
    else seen.add(plan.action);
  }
  return muted;
}

export function Header({ view, entity, title }: { view: TypeView; entity: Entity; title: string }) {
  const summary = view.summary ? evaluate(view.summary, (n) => valueText(entity[n])).trim() : "";
  const badges = headerBadges(view, entity);
  const { editing } = useBrowser();
  const placed = new Set([...placeholders(view.title), ...placeholders(view.summary)]);
  const muted = useRepeats(entity, [...placed, ...badges.map((b) => b.field.property)]);
  // The key stands in for a title that comes out empty: nothing to edit there.
  const titled = titleOf(view.title, entity, "") !== "";
  useEffect(() => {
    if (takeEntityFocus()) document.getElementById("gb-title")?.focus();
  }, []);
  return (
    <header className="gb-card-h">
      <EditToggle />
      <EditMenu />
      <span className="gb-ico gb-ico-lg">
        <Icon name={view.icon} size={30} />
      </span>
      <div>
        <div className="gb-eyebrow">{view.label}</div>
        <h1 id="gb-title" tabIndex={-1}>
          {titled ? (
            <Templated template={view.title} view={view} entity={entity} muted={muted} />
          ) : (
            title
          )}
        </h1>
        {view.summary && (summary || editing) && (
          // A div, not a p: the open editor is a block of its own and may not sit in a paragraph.
          <div className="gb-sum">
            <Templated template={view.summary} view={view} entity={entity} muted={muted} />
          </div>
        )}
        <div className="gb-badges">
          {badges.map(({ field, text }) => (
            <span key={field.property} title={field.label}>
              <Editable
                field={field}
                value={entity[field.property]}
                pencil={!muted.has(field.property) && !placed.has(field.property)}
              >
                <Badge tone={field.tones?.[text]}>{text}</Badge>
              </Editable>
            </span>
          ))}
        </div>
      </div>
    </header>
  );
}

function Row({ field, entity }: { field: FieldView; entity: Entity }) {
  const value = entity[field.property];
  if (value === undefined) return null; // the backend left it out for this viewer
  if (isEmpty(value) && field.hideWhenEmpty) return null;
  return (
    <>
      <dt>{field.label}</dt>
      <dd data-testid={`prop-${field.property}`}>
        <Editable field={field} value={value}>
          {isEmpty(value) ? <NotSet /> : <Value field={field} value={value} />}
        </Editable>
      </dd>
    </>
  );
}

function Props({ view, entity, names }: { view: TypeView; entity: Entity; names: string[] }) {
  return (
    <dl className="gb-props">
      {names.map((n) => (
        <Row key={n} field={fieldOf(view, n)} entity={entity} />
      ))}
    </dl>
  );
}

const shown = (view: TypeView, entity: Entity, names: string[]) =>
  names.filter((n) => {
    const f = fieldOf(view, n);
    return entity[n] !== undefined && !(isEmpty(entity[n]) && f.hideWhenEmpty);
  });

function Section({
  view,
  entity,
  section,
  badged,
}: {
  view: TypeView;
  entity: Entity;
  section: TypeView["sections"][number];
  badged: Set<string>;
}) {
  const names = shown(
    view,
    entity,
    section.properties.filter((n) => !badged.has(n)),
  );
  if (names.length === 0) return null;
  const body = <Props view={view} entity={entity} names={names} />;
  return (
    <section className="gb-sec">
      {section.collapsed ? (
        <details>
          <summary>
            <h3 className="gb-sec-h">{section.label}</h3>
          </summary>
          {body}
        </details>
      ) : (
        <>
          <h3 className="gb-sec-h">{section.label}</h3>
          {body}
        </>
      )}
    </section>
  );
}

export function Sections({ view, entity }: { view: TypeView; entity: Entity }) {
  const badged = inHeader(view, entity);
  return (
    <>
      {view.sections.map((s) => (
        <Section key={s.label} view={view} entity={entity} section={s} badged={badged} />
      ))}
    </>
  );
}

export interface NodeCardProps {
  view: TypeView;
  entity: Entity;
  keyText: string;
  status: BackendStatus[];
  /** The node's type: where given, a property the viewer may change is offered an edit. */
  entry?: TypeEntry;
}

export function NodeCard({ view, entity, keyText, status, entry }: NodeCardProps) {
  return (
    <article className={`gb-card ${toneClass(view.tone)}`} aria-labelledby="gb-title">
      <EditTarget value={entry ? { entry, keyText, entity } : null}>
        <Header view={view} entity={entity} title={entityTitle(view, entity, keyText)} />
        <Sections view={view} entity={entity} />
      </EditTarget>
      <Footer entity={entity} status={status} entry={entry} keyText={keyText} />
    </article>
  );
}
