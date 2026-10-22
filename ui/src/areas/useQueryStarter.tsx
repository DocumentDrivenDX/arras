// SPDX-License-Identifier: MIT OR Apache-2.0
import { useEffect, useState } from "react";
import type { ModuleInfo } from "../api/types";
import { Button, Notice } from "../components/ui";
import { starterSql } from "../lib/starterSql";
import type { QuerySession } from "./queryHistory";

/** Another area opens the Query area on a type: `id` is new on each request, so the same type can be asked again. */
export interface QueryStarter {
  /** The qualified type name. */
  type: string;
  id: number;
}

/**
 * Opening the area with a starter puts its statement in the editor without running it. An empty draft is replaced;
 * a draft with text is never overwritten without a word: the starter is offered (`offer`), and the operator
 * replaces the draft or keeps it. Each starter is handled once per session, however often the area remounts.
 */
export function useQueryStarter(
  session: QuerySession,
  starter: QueryStarter | undefined,
  module: ModuleInfo | undefined,
  focus: () => void,
) {
  const [offer, setOffer] = useState<{ type: string; sql: string } | null>(null);
  const { draft, setDraft, starterSeen } = session;
  useEffect(() => {
    if (!starter || !module || starterSeen.current === starter) return;
    starterSeen.current = starter;
    const type = module.entityTypes.find((t) => t.name === starter.type);
    const sql = type ? starterSql(type) : null;
    if (sql === null) return;
    if (draft.sql.trim() === "") {
      setDraft({ sql, consistency: draft.consistency });
      focus();
    } else if (draft.sql !== sql) {
      setOffer({ type: starter.type, sql });
    }
  }, [starter, module, draft, setDraft, starterSeen, focus]);
  return {
    offer,
    accept: () => {
      if (offer) setDraft({ sql: offer.sql, consistency: draft.consistency });
      setOffer(null);
      focus();
    },
    dismiss: () => setOffer(null),
  };
}

/** The question asked when a starter arrives over a draft that has text. */
export function StarterOffer({
  type,
  onAccept,
  onDismiss,
}: {
  type: string;
  onAccept: () => void;
  onDismiss: () => void;
}) {
  const short = type.slice(type.lastIndexOf(".") + 1);
  return (
    <div className="px-3 pt-1.5" data-testid="query-starter-offer">
      <Notice tone="neutral" role="status">
        <span>Your draft is kept. Replace it with a starter query for {short}? </span>
        <Button onClick={onAccept}>Replace the draft with the {short} starter</Button>{" "}
        <Button onClick={onDismiss}>Keep my draft</Button>
      </Notice>
    </div>
  );
}
