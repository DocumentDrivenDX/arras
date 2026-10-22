// SPDX-License-Identifier: MIT OR Apache-2.0
// The answer to a search (DESIGN-GB, Screens 1 and 5): a banner for what was not searched, a status
// line (count, ranked, truncated), the hits, and the freshness of the answer. A type that could not
// be searched is named, never counted as having no hits.
import type { UseQueryResult } from "@tanstack/react-query";
import { shortName } from "../api/gql";
import type { NotSearched, SearchHit, SearchPage } from "../api/types";
import { EntityRow } from "./EntityRow";
import { Glyph } from "./icons";
import type { TypeEntry } from "./meta";
import { BackendDown, Failed, Skeleton } from "./states";
import { stateOf } from "./useNode";

const REASON: Record<string, (n: NotSearched) => string> = {
  unavailable: (n) => `Its backend${n.backend ? ` (${n.backend})` : ""} is unavailable.`,
  no_capability: () => "Its backend does not serve text search.",
  no_searchable_property: () => "It has no searchable property.",
  over_budget: () => "The search was too large to include it.",
};

export function NotSearchedBanner({
  items,
  entries,
}: {
  items: NotSearched[];
  entries: TypeEntry[];
}) {
  if (items.length === 0) return null;
  const label = (t: string) => entries.find((e) => shortName(e.type.name) === t)?.view.label ?? t;
  return (
    <div className="gb-banner" role="status" data-testid="gb-banner">
      <Glyph name="alert" size={18} />
      <div>
        {items.map((n) => (
          <div key={n.type}>
            <b>{label(n.type)} was not searched.</b> {REASON[n.reason]?.(n) ?? ""}
          </div>
        ))}
        <div>The other types answered.</div>
      </div>
    </div>
  );
}

function Hit({ hit, entries }: { hit: SearchHit; entries: TypeEntry[] }) {
  const entry = entries.find((e) => shortName(e.type.name) === hit.type);
  if (!entry) return null;
  return (
    <li>
      <EntityRow
        entry={entry}
        row={{
          key: hit.key,
          title: hit.label || hit.key,
          excerpt: hit.excerpt,
          fields: hit.entity,
        }}
      />
    </li>
  );
}

function Status({ page, text }: { page: SearchPage; text: string }) {
  const n = page.hits.length;
  return (
    <p className="gb-note-line" role="status" data-testid="gb-status">
      {n} {n === 1 ? "result" : "results"} for <b>{text}</b> · ranked
      {page.truncated && " · showing the best 50 of each type"}
    </p>
  );
}

function Searched({ page, entries }: { page: SearchPage; entries: TypeEntry[] }) {
  const f = page.freshness.map((x) => `${x.backend} · ${x.consistency}`).join(", ");
  return (
    <>
      <ul className="gb-hits">
        {page.hits.map((h) => (
          <Hit key={`${h.type}:${h.key}`} hit={h} entries={entries} />
        ))}
      </ul>
      {f && (
        <p className="gb-fresh-line" data-testid="gb-answer-freshness">
          Answer from {f}
        </p>
      )}
    </>
  );
}

export function NoResults({
  page,
  entries,
  narrowed,
}: {
  page: SearchPage;
  entries: TypeEntry[];
  narrowed: boolean;
}) {
  const plural = (t: string) =>
    entries.find((e) => shortName(e.type.name) === t)?.view.pluralLabel ?? t;
  const searched = page.counts.map((c) => plural(c.type));
  const skipped = page.notSearched.map((n) => plural(n.type));
  return (
    <section className="gb-state" data-testid="gb-state" aria-labelledby="gb-state-title">
      <span className="gb-state-icon">
        <Glyph name="search" size={26} />
      </span>
      <h1 id="gb-state-title">No results for “{page.text}”</h1>
      <p>
        Searched {searched.join(", ") || "nothing"}.
        {skipped.length > 0 && ` Not searched: ${skipped.join(", ")}.`}
      </p>
      {narrowed && <p>Choose All to search every type.</p>}
    </section>
  );
}

export interface ResultsProps {
  query: UseQueryResult<SearchPage, Error>;
  text: string;
  entries: TypeEntry[];
  narrowed: boolean;
}

export function Results({ query: q, text, entries, narrowed }: ResultsProps) {
  if (q.isPending) return <Skeleton label="Searching" />;
  if (q.error) {
    const s = stateOf(q.error);
    return s.status === "down" ? (
      <BackendDown backend={s.backend} onRetry={() => void q.refetch()} />
    ) : (
      <Failed onRetry={() => void q.refetch()} />
    );
  }
  const page = q.data;
  const dim = q.isPlaceholderData;
  return (
    <div className={dim ? "gb-dim" : undefined} aria-busy={dim}>
      <NotSearchedBanner items={page.notSearched} entries={entries} />
      {page.hits.length === 0 ? (
        <NoResults page={page} entries={entries} narrowed={narrowed} />
      ) : (
        <>
          <Status page={page} text={page.text || text} />
          <Searched page={page} entries={entries} />
        </>
      )}
    </div>
  );
}
