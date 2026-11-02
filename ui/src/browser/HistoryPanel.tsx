// SPDX-License-Identifier: MIT OR Apache-2.0
import { useId } from "react";
// An entity's History (FR-69): who changed it, when, by which action and what the change touched.
// It opens at `.../<key>/history` and closes back to the entity. A journal the backend does not keep
// (501) and a missing journal grant (403) are a sentence each, never an error panel.

import { useMemo } from "react";
import { shortName } from "../api/gql";
import type { Change } from "../api/types";
import { Button, Notice } from "../ds";
import { CrossAnchor } from "../kit";
import { fmtTime } from "../lib/format";
import { changeLinkFor } from "./changeLink";
import { actionText, type Touched, touchedOf } from "./changeText";
import { linkProps, useBrowser } from "./context";
import { formatExplore, readViewState } from "./location";
import { findQualified, type TypeEntry } from "./meta";
import { useChanges } from "./useChanges";
import { type Labels, useLabels } from "./useLabels";

function Touch({ verb, target, labels }: Touched & { labels: Labels }) {
  const { meta, go } = useBrowser();
  const label = labels.labels[target.id];
  const entry = findQualified(meta, target.type);
  if (label?.state === "ok" && entry) {
    const loc = { module: entry.module.name, type: shortName(target.type), key: target.key };
    return (
      <li>
        {verb} {entry.view.label} <a {...linkProps(go, loc)}>{label.title}</a>
      </li>
    );
  }
  const text = !label ? "Loading" : label.state === "retry" ? "Could not be read" : "Not available";
  return (
    <li className="gb-hist-na" aria-busy={!label || undefined}>
      {verb} <span>{text}</span>
    </li>
  );
}

function Group({ id, module }: { id: string; module: string }) {
  const link = changeLinkFor(useBrowser(), module, id);
  if (!link) return <span className="gb-hist-group">{id}</span>;
  return (
    <CrossAnchor link={link} className="gb-hist-group">
      {id}
    </CrossAnchor>
  );
}

function Row({ change, labels, module }: { change: Change; labels: Labels; module: string }) {
  return (
    <li className="gb-hist-row" data-testid="gb-change">
      <div className="gb-hist-head">
        <span className="gb-hist-by">{change.by}</span>
        <time dateTime={change.at}>{fmtTime(change.at)}</time>
        <span className="gb-hist-action">{actionText(change.action)}</span>
        <Group id={change.group} module={module} />
      </div>
      <ul className="gb-hist-touched">
        {touchedOf(change).map((t) => (
          <Touch key={t.target.id} {...t} labels={labels} />
        ))}
      </ul>
    </li>
  );
}

function List({
  module,
  changes,
  more,
  fetchingMore,
  onMore,
}: {
  module: string;
  changes: Change[];
  more: boolean;
  fetchingMore: boolean;
  onMore: () => void;
}) {
  const { meta } = useBrowser();
  const targets = useMemo(
    () => changes.flatMap((c) => touchedOf(c).map((t) => t.target)),
    [changes],
  );
  const labels = useLabels(meta, targets);
  if (changes.length === 0) return <p>No changes are recorded for this entity.</p>;
  return (
    <>
      <ol className="gb-hist-list">
        {changes.map((c) => (
          <Row key={c.group} change={c} labels={labels} module={module} />
        ))}
      </ol>
      {more && (
        <Button variant="secondary" busy={fetchingMore} onClick={onMore}>
          Show more
        </Button>
      )}
    </>
  );
}

export function HistoryPanel({
  entry,
  keyText,
  title,
}: {
  entry: TypeEntry;
  keyText: string;
  title: string;
}) {
  const heading = useId();
  const { go, ownsHistory } = useBrowser();
  const { state, more, retry } = useChanges(entry.type.name, keyText, true);
  const close = () => {
    const loc = { module: entry.module.name, type: shortName(entry.type.name), key: keyText };
    const opened = formatExplore({ ...loc, history: true });
    // Opened from the entity: going back lands on it. A fresh load of the history address has no
    // entity entry behind it, so the entity replaces it.
    if (ownsHistory !== false && window.location.hash === opened && readViewState().fromEntity)
      window.history.back();
    else go(loc, { replace: true });
  };
  return (
    <section className="gb-hist" aria-labelledby={heading} data-testid="gb-history">
      <div className="gb-hist-bar">
        <h2 id={heading}>History</h2>
        <Button variant="text" onClick={close}>
          Back to {title}
        </Button>
      </div>
      {state.status === "loading" && <p role="status">Loading</p>}
      {state.status === "forbidden" && (
        <Notice tone="info">You do not have access to the history of changes.</Notice>
      )}
      {state.status === "none" && (
        <Notice tone="info">This backend keeps no history of changes.</Notice>
      )}
      {state.status === "error" && (
        <p>
          The history could not be read.{" "}
          <Button variant="text" onClick={retry}>
            Try again
          </Button>
        </p>
      )}
      {state.status === "ready" && (
        <List
          module={entry.module.name}
          changes={state.changes}
          more={state.more}
          fetchingMore={state.fetchingMore}
          onMore={more}
        />
      )}
    </section>
  );
}
