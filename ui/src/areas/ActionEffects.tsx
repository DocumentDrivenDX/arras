// SPDX-License-Identifier: MIT OR Apache-2.0
import { shortName } from "../api/gql";
import type { Effect, Receipt } from "../api/types";
import { EntityLink, GroupLink, useAuditShown } from "../components/NavLink";
import { Chip, CopyButton, Notice } from "../components/ui";
import { keyed } from "../lib/format";
import { AREA_LABELS } from "../lib/vocabulary";

const fmt = (v: unknown) => (typeof v === "string" ? JSON.stringify(v) : JSON.stringify(v));

function Ref({ r }: { r: { type: string; key: string; generated?: boolean } }) {
  return (
    <span className="arras-mono">
      {shortName(r.type)} {r.generated ? <em className="text-muted">(new key)</em> : r.key}
    </span>
  );
}

/** The effects an invoke would apply: kind, ref, set/unset or link/unlink. */
export function EffectList({ effects }: { effects: Effect[] }) {
  const deletes = effects.some((e) => e.kind === "delete");
  return (
    <div data-testid="effects">
      {deletes && (
        <Notice tone="bad" role="alert">
          <strong>A delete cannot be undone from the console.</strong> Confirm only if you intend to
          remove the entity.
        </Notice>
      )}
      <ul className="m-0 mt-1 list-none space-y-1 p-0">
        {keyed(effects, (e) => JSON.stringify(e)).map(({ key, item: e }) => (
          <li
            key={key}
            className="flex flex-wrap items-baseline gap-1.5 rounded border border-line bg-surface px-2 py-1"
            data-testid="effect"
          >
            <Chip tone={e.kind === "delete" ? "bad" : e.kind === "create" ? "ok" : "accent"}>
              {e.kind}
            </Chip>
            {"relationship" in e ? (
              <>
                <span className="arras-mono">{e.relationship}</span>
                <Ref r={e.source} /> → <Ref r={e.target} />
              </>
            ) : (
              <Ref r={e.ref} />
            )}
            {e.kind === "create" &&
              Object.entries(e.properties).map(([k, v]) => (
                <span key={k} className="arras-mono text-muted">
                  {k}={fmt(v)}
                </span>
              ))}
            {e.kind === "update" && (
              <>
                {Object.entries(e.set).map(([k, v]) => (
                  <span key={k} className="arras-mono">
                    set {k}={fmt(v)}
                  </span>
                ))}
                {e.unset.map((k) => (
                  <span key={k} className="arras-mono text-warn">
                    unset {k}
                  </span>
                ))}
              </>
            )}
          </li>
        ))}
        {effects.length === 0 && <li className="text-muted">No effects: nothing would change.</li>}
      </ul>
    </div>
  );
}

/** One changed entity of a receipt: the type opens it in Entities (unless it was deleted), History beside it. */
function ReceiptEntity({
  module,
  type,
  entityKey,
  gone,
}: {
  module: string;
  type: string;
  entityKey: string;
  gone: boolean;
}) {
  const auditShown = useAuditShown();
  const label = `${shortName(type)} ${entityKey}`;
  return (
    <span className="flex flex-wrap gap-x-2">
      {gone ? (
        <span className="arras-mono">{entityKey}</span>
      ) : (
        <EntityLink
          module={module}
          area="entities"
          type={type}
          entityKey={entityKey}
          className="arras-mono text-accent hover:underline"
          aria-label={`Open ${label} in ${AREA_LABELS.entities}`}
        >
          {entityKey}
        </EntityLink>
      )}
      {auditShown && (
        <EntityLink
          module={module}
          area="changes"
          type={type}
          entityKey={entityKey}
          aria-label={`Open ${label} history`}
        >
          History
        </EntityLink>
      )}
    </span>
  );
}

/**
 * What an apply changed. With `module`, each changed entity opens in Entities and History and the group
 * opens in Changes; `deleted` (`type:key`) are the entities that no longer exist, shown as text.
 */
export function ReceiptView({
  r,
  module,
  deleted = [],
}: {
  r: Receipt;
  module?: string;
  deleted?: string[];
}) {
  const auditShown = useAuditShown();
  return (
    <div className="rounded border border-ok/40 bg-oksoft p-3" role="status" data-testid="receipt">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <strong>{r.replayed ? "Already applied" : "Applied"}</strong>
        <span className="arras-mono">{r.action}</span>
        {r.replayed && (
          <Chip tone="warn" title="This idempotency key was seen before; nothing was applied again">
            replay
          </Chip>
        )}
      </div>
      <table className="arras-table w-full bg-surface">
        <thead>
          <tr>
            <th>Entity</th>
            <th>Key</th>
            <th>Version</th>
          </tr>
        </thead>
        <tbody>
          {r.refs.map((x) => (
            <tr key={`${x.type}:${x.key}`}>
              <td>{x.type}</td>
              <td className="arras-mono">
                {module ? (
                  <ReceiptEntity
                    module={module}
                    type={x.type}
                    entityKey={x.key}
                    gone={deleted.includes(`${x.type}:${x.key}`)}
                  />
                ) : (
                  x.key
                )}
              </td>
              <td className="num">{x.version}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        <Chip>created {r.created}</Chip>
        <Chip>updated {r.updated}</Chip>
        <Chip>deleted {r.deleted}</Chip>
        <Chip>linked {r.linked}</Chip>
        <Chip>unlinked {r.unlinked}</Chip>
        <Chip title="Use this group to find the change in the Changes area">
          group {r.group ?? "—"}
        </Chip>
        {r.group && <CopyButton text={r.group} label="Copy group id" />}
        {r.group && module && auditShown && (
          <GroupLink
            module={module}
            group={r.group}
            aria-label={`View group ${r.group} in ${AREA_LABELS.changes}`}
          >
            View in {AREA_LABELS.changes}
          </GroupLink>
        )}
        <Chip title="The backend position this change reached">token {r.token ?? "—"}</Chip>
      </div>
    </div>
  );
}
