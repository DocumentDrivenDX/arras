// SPDX-License-Identifier: MIT OR Apache-2.0
// The Entry (DESIGN-GB, Screen 1): the module's title and description, the type chips, and either
// a type's entities, the search's hits, or one card per type. It shows no count until a search has
// been made, and no search at all on a server that does not serve one.
import { useEffect } from "react";
import { shortName } from "../api/gql";
import { checkText, useSearch } from "../api/search";
import type { ModuleInfo } from "../api/types";
import { usePageEffects } from "../lib/pageEffects";
import { useBrowser } from "./context";
import { ExportGraph } from "./ExportGraph";
import { Icon } from "./icons";
import { readViewState } from "./location";
import { type TypeEntry, typesOf } from "./meta";
import { Results } from "./Results";
import { TypeChips } from "./TypeChips";
import { TypeList } from "./TypeList";
import { toneClass } from "./tones";

export interface EntryProps {
  module: ModuleInfo;
  /** The search text once it has settled (debounced), and the type the reader chose (none is "All"). */
  text: string;
  types: string[];
  onTypes: (types: string[]) => void;
  /** A type's list starts after this key (the address's `?after=`). */
  after?: string;
}

function Heading({ module }: { module: ModuleInfo }) {
  const view = module.view;
  return (
    <div className="gb-entry-h">
      <h1>{view?.title ?? module.name}</h1>
      {view?.description && <p>{view.description}</p>}
      <ExportGraph module={module.name} />
    </div>
  );
}

function TypeCards({ entries, onPick }: { entries: TypeEntry[]; onPick: (type: string) => void }) {
  return (
    <ul className="gb-cards">
      {entries.map((e) => (
        <li key={e.type.name}>
          <button
            type="button"
            className={`gb-type-card gb-card ${toneClass(e.view.tone)}`}
            onClick={() => onPick(shortName(e.type.name))}
          >
            <span className="gb-ico gb-ico-md">
              <Icon name={e.view.icon} size={22} />
            </span>
            <span className="gb-type-card-t">{e.view.pluralLabel}</span>
            <span className="gb-type-card-s">List them</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

/** Restore the scroll position the reader left the Entry at (US-071-AC4), once the page has content. */
function useRestoreScroll(ready: boolean) {
  const { ownsHistory } = useBrowser();
  const pageEffects = usePageEffects();
  useEffect(() => {
    if (!ready || ownsHistory === false || !pageEffects) return;
    const y = readViewState().scroll;
    if (y) window.scrollTo(0, y);
  }, [ready, ownsHistory, pageEffects]);
}

export function Entry({ module, text, types, onTypes, after }: EntryProps) {
  const entries = typesOf(module);
  const check = checkText(text);
  const q = useSearch(module, check.ok ? check.text : "", types, check.ok);
  useRestoreScroll(check.ok ? !q.isPending : true);
  const selected = types[0] ?? null;
  const chosen = entries.find((e) => shortName(e.type.name) === selected);
  return (
    <>
      <Heading module={module} />
      <TypeChips
        entries={entries}
        selected={selected}
        onSelect={(t) => onTypes(t ? [t] : [])}
        counts={check.ok ? q.data?.counts : undefined}
        notSearched={check.ok ? q.data?.notSearched : undefined}
      />
      {check.ok ? (
        <Results query={q} text={check.text} entries={entries} narrowed={chosen !== undefined} />
      ) : (
        <>
          {check.reason !== "empty" && (
            <p className="gb-note-line" role="status" data-testid="gb-hint">
              {hint(check.reason)}
            </p>
          )}
          {chosen ? (
            <TypeList key={chosen.type.name} entry={chosen} after={after} />
          ) : (
            <TypeCards entries={entries} onPick={(t) => onTypes([t])} />
          )}
        </>
      )}
    </>
  );
}

function hint(reason: "short" | "long" | "words" | "empty"): string {
  if (reason === "long") return "Use at most 200 characters.";
  if (reason === "words") return "Use at most six words.";
  return "Type at least two characters to search.";
}
