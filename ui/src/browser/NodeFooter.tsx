// SPDX-License-Identifier: MIT OR Apache-2.0
// The card's footer (the `contentinfo` landmark): who changed the entity last and when, and how
// current what is shown is, with a stale answer marked (DESIGN-GB, Stale).
import type { BackendStatus } from "../api/types";
import type { TypeEntry } from "./meta";
import { OpenInOperate } from "./OperateLinks";
import type { Entity } from "./useNode";
import { When } from "./Value";

interface Fresh {
  backend: string;
  asOf: string;
  at: string;
  consistency: string;
}

const isFresh = (v: unknown): v is Fresh =>
  !!v && typeof v === "object" && "backend" in v && "at" in v;

/** The lag a backend reports when it is behind its record store; none for the record store. */
export function lagOf(status: BackendStatus[], backend: string): number {
  const lag = status.find((s) => s.backend === backend)?.lag;
  const n = lag === null || lag === undefined ? 0 : Number(lag);
  return Number.isFinite(n) ? n : 0;
}

export function Freshness({ fresh, status }: { fresh: Fresh; status: BackendStatus[] }) {
  const lag = lagOf(status, fresh.backend);
  const time = new Date(fresh.at).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
  return (
    <span
      className={lag > 0 ? "gb-stale" : undefined}
      role="status"
      data-testid="gb-freshness"
      data-stale={lag > 0 ? "true" : undefined}
    >
      {fresh.backend} · {lag > 0 ? `behind by ${lag}` : "current"} as of {time} ·{" "}
      {fresh.consistency}
    </span>
  );
}

export function Footer({
  entity,
  status,
  entry,
  keyText,
}: {
  entity: Entity;
  status: BackendStatus[];
  /** The node's type and key: where given, the footer offers the shell's links into Operate. */
  entry?: TypeEntry;
  keyText?: string;
}) {
  const by = entity.updatedBy ?? entity.createdBy;
  const at = entity.updatedAt ?? entity.createdAt;
  const fresh = isFresh(entity.freshness) ? entity.freshness : null;
  return (
    <footer className="gb-attr">
      <span data-testid="gb-attribution">
        {typeof by === "string" && by ? (
          <>
            Last changed by <b>{by}</b>
            {typeof at === "string" && at && (
              <>
                {" · "}
                <When value={at} time label="the last change" />
              </>
            )}
          </>
        ) : (
          "No change recorded"
        )}
      </span>
      {fresh && <Freshness fresh={fresh} status={status} />}
      {entry && keyText !== undefined && <OpenInOperate entry={entry} keyText={keyText} />}
    </footer>
  );
}
