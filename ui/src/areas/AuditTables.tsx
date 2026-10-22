// SPDX-License-Identifier: MIT OR Apache-2.0
import { shortName } from "../api/gql";
import type { Change, ChangeOp, Load } from "../api/types";
import { ViewInExplore } from "../components/ExploreLink";
import { EntityLink, GroupLink, useAuditShown } from "../components/NavLink";
import { Empty } from "../components/ui";
import { fmtTime, keyed } from "../lib/format";
import { AREA_LABELS, HISTORY } from "../lib/vocabulary";

/** One changed entity: its type and key open it in Entities (a deleted one has nothing to open), History beside it. */
function EntityRef({
  module,
  type,
  entityKey,
  version,
  gone,
}: {
  module: string;
  type: string;
  entityKey: string;
  version?: number;
  gone?: boolean;
}) {
  const auditShown = useAuditShown();
  const label = `${shortName(type)} ${entityKey}`;
  return (
    <>
      {gone ? (
        label
      ) : (
        <EntityLink
          module={module}
          area="entities"
          type={type}
          entityKey={entityKey}
          aria-label={`Open ${label} in ${AREA_LABELS.entities}`}
        >
          {label}
        </EntityLink>
      )}
      {version !== undefined && <span className="text-muted"> v{version}</span>}
      {auditShown && (
        <>
          {" "}
          <EntityLink
            module={module}
            area="changes"
            type={type}
            entityKey={entityKey}
            aria-label={`Open ${label} history`}
            title={`${HISTORY} of ${label}`}
          >
            {HISTORY}
          </EntityLink>
        </>
      )}
      {!gone && (
        <>
          {" "}
          <ViewInExplore target={{ entity: { module, type, key: entityKey } }} label={label} />
        </>
      )}
    </>
  );
}

function Ops({ module, ops }: { module: string; ops: ChangeOp[] }) {
  return (
    <ul className="m-0 list-none p-0">
      {keyed(ops, (o) => JSON.stringify(o)).map(({ key, item: o }) => (
        <li key={key} className="arras-mono">
          {o.kind === "link" || o.kind === "unlink" ? (
            <>
              {o.kind} {o.relationship}:{" "}
              {o.source ? (
                <EntityRef module={module} type={o.source.type} entityKey={o.source.key} />
              ) : null}{" "}
              →{" "}
              {o.target ? (
                <EntityRef module={module} type={o.target.type} entityKey={o.target.key} />
              ) : null}
            </>
          ) : (
            <>
              {o.kind}{" "}
              {o.type && o.key ? (
                <EntityRef
                  module={module}
                  type={o.type}
                  entityKey={o.key}
                  version={o.version}
                  gone={o.kind === "delete"}
                />
              ) : (
                o.key
              )}
            </>
          )}
        </li>
      ))}
    </ul>
  );
}

export function ChangesTable({ module, rows }: { module: string; rows: Change[] }) {
  return (
    <>
      <table
        className="arras-table w-full rounded border border-line bg-surface"
        data-testid="changes"
      >
        <thead>
          <tr>
            <th>When</th>
            <th>Person</th>
            <th>Action</th>
            <th>Entities touched</th>
            <th>Group</th>
            <th>Backend</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.group} data-testid="change-row" style={{ whiteSpace: "normal" }}>
              <td>{fmtTime(c.at)}</td>
              <td>{c.by}</td>
              <td className="arras-mono">{c.action}</td>
              <td style={{ whiteSpace: "normal" }}>
                <Ops module={module} ops={c.ops} />
              </td>
              <td className="arras-mono">
                <GroupLink
                  module={module}
                  group={c.group}
                  aria-label={`Open receipt for group ${c.group}`}
                >
                  {c.group}
                </GroupLink>
              </td>
              <td>{c.backend}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <Empty title="No changes match" />}
    </>
  );
}

export function LoadsTable({ loads }: { loads: Load[] }) {
  return (
    <>
      <table
        className="arras-table w-full rounded border border-line bg-surface"
        data-testid="loads"
      >
        <thead>
          <tr>
            <th>When</th>
            <th>Load</th>
            <th>Initiated by</th>
            <th>Created</th>
            <th>Skipped</th>
            <th>Rejected</th>
          </tr>
        </thead>
        <tbody>
          {loads.map((l) => (
            <tr key={l.load_id}>
              <td>{fmtTime(l.at)}</td>
              <td className="arras-mono">{l.load_id}</td>
              <td>{l.initiated_by}</td>
              <td className="num">{l.created}</td>
              <td className="num">{l.skipped}</td>
              <td className="num">{l.rejected}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {loads.length === 0 && <Empty title="No loads recorded for this module" />}
    </>
  );
}

/** The entity whose History the view shows, as a filter that can be removed. */
export function HistoryChip({
  module,
  type,
  entityKey,
  onClear,
}: {
  module: string;
  type: string;
  entityKey: string;
  onClear: () => void;
}) {
  const label = `${shortName(type)} ${entityKey}`;
  return (
    <div
      className="mb-2 inline-flex items-center gap-1 rounded border border-accent/40 bg-accentsoft px-2 py-0.5 text-[12px]"
      data-testid="history-chip"
    >
      <span>
        {HISTORY} of{" "}
        <EntityLink
          module={module}
          area="entities"
          type={type}
          entityKey={entityKey}
          aria-label={`Open ${label} in ${AREA_LABELS.entities}`}
        >
          {label}
        </EntityLink>
      </span>
      <button
        type="button"
        className="rounded px-1 text-muted hover:text-fg"
        aria-label={`Clear history filter (${label})`}
        onClick={onClear}
      >
        ×
      </button>
    </div>
  );
}
