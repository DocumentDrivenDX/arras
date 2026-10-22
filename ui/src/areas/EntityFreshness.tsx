// SPDX-License-Identifier: MIT OR Apache-2.0
import { useStatus } from "../api/queries";
import type { Freshness, ModuleInfo } from "../api/types";
import { Chip } from "../components/ui";
import { fmtTime } from "../lib/format";

/** The freshness of a page: backend, position, time, consistency and (for replicas) lag. */
export function FreshnessBar({
  freshness,
  module,
}: {
  freshness: Freshness | null | undefined;
  module?: ModuleInfo;
}) {
  const status = useStatus();
  if (!freshness) return null;
  const st = status.data?.find((s) => s.backend === freshness.backend);
  const replica = module ? freshness.backend !== module.record : false;
  const recordDown = module
    ? status.data?.find((s) => s.backend === module.record)?.available === false
    : false;
  const notCurrent = replica || recordDown;
  return (
    <div className="flex flex-wrap items-center gap-1.5" data-testid="freshness">
      <Chip tone={freshness.consistency === "BULK" ? "warn" : "ok"} title="Read consistency">
        {freshness.consistency}
      </Chip>
      <Chip
        tone={replica ? "warn" : "accent"}
        title={replica ? "A replica answered" : "The record store answered"}
      >
        {replica ? "replica" : "record"}: {freshness.backend}
      </Chip>
      <Chip title="The backend's position for this read">position {freshness.asOf}</Chip>
      <Chip title="When the read was current">{fmtTime(freshness.at)}</Chip>
      {st?.lag != null && <Chip tone="warn">replica lag {st.lag}</Chip>}
      {notCurrent && <Chip tone="warn">not current</Chip>}
      {recordDown && <Chip tone="bad">{module?.record} unavailable</Chip>}
    </div>
  );
}

export function FreshnessLine({
  freshness,
  hasData,
  module,
}: {
  freshness: Freshness | null | undefined;
  hasData: boolean;
  module: ModuleInfo;
}) {
  return (
    <div className="border-b border-line bg-surface px-3 py-1">
      {hasData ? (
        <FreshnessBar freshness={freshness} module={module} />
      ) : (
        <span className="text-muted">No freshness yet</span>
      )}
    </div>
  );
}
