// SPDX-License-Identifier: MIT OR Apache-2.0
import { useAuditProbe } from "../api/queries";
import type { ModuleInfo } from "../api/types";
import type { Area } from "../route";

/**
 * Whether the module's Changes area is shown, and the area to show for the one asked for. The journal
 * is the record store's: one that applies no actions has none to list, and says so.
 */
export function useAudit(current: ModuleInfo | undefined, rawArea: Area) {
  const probe = useAuditProbe(current?.name);
  const recordProvides =
    !!current && current.entityTypes.some((t) => t.capabilities[current.record]?.mutable);
  const auditShown = !!current && !(probe.data === "unsupported" && recordProvides);
  const area: Area = rawArea === "changes" && !auditShown && probe.isSuccess ? "model" : rawArea;
  return { auditShown, area };
}
