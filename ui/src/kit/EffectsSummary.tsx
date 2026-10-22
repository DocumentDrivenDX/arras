// SPDX-License-Identifier: MIT OR Apache-2.0

import type { Effect } from "../api/types";
import { Notice } from "../ds";
import { keyed } from "../lib/format";
import { summarizeEffects } from "./summarizeEffects";

/** Where the effects come from: a validation not yet applied, one the form has since changed, or a receipt. */
export type EffectsStatus = "preview" | "stale" | "applied";

const STATUS_LINE: Record<EffectsStatus, string> = {
  preview: "Preview: these changes have not been applied.",
  stale: "Out of date: the inputs changed since this preview. Validate again.",
  applied: "Applied: these changes were made.",
};

export function EffectsSummary({
  effects,
  status,
}: {
  effects: readonly Effect[];
  status: EffectsStatus;
}) {
  const sentences = summarizeEffects(effects);
  const deletes = effects.some((e) => e.kind === "delete");
  return (
    <div data-testid="effects-summary" data-status={status}>
      <p role="status" data-testid="effects-status" className="m-0 mb-1">
        {STATUS_LINE[status]}
      </p>
      {deletes && status !== "applied" && (
        <Notice tone="warning" title="A delete cannot be undone here">
          Confirm only if you intend to remove the entity.
        </Notice>
      )}
      <ul className="m-0 list-none space-y-1 p-0">
        {keyed(sentences, (s) => s).map(({ key, item }) => (
          <li key={key} data-testid="effect-sentence">
            {item}
          </li>
        ))}
        {sentences.length === 0 && <li>No effects: nothing would change.</li>}
      </ul>
    </div>
  );
}
