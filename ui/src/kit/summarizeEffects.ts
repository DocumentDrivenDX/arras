// SPDX-License-Identifier: MIT OR Apache-2.0
// A text sentence per effect an invoke would apply (SD-013): the type and the key, or "a new key"
// where the server generates it. No markup; the same words serve a list, a title and a test.
import { shortName } from "../api/gql";
import type { Effect, EntityRef } from "../api/types";
import { fmtValue } from "../lib/format";

const value = (v: unknown) => (typeof v === "string" ? JSON.stringify(v) : fmtValue(v));

/** `Solution sol-1`, or `a new Solution` for a key the server generates. */
export function refLabel(r: EntityRef): string {
  return r.generated ? `a new ${shortName(r.type)}` : `${shortName(r.type)} ${r.key}`;
}

function createSentence(e: Extract<Effect, { kind: "create" }>): string {
  const props = Object.entries(e.properties).map(([k, v]) => `${k} ${value(v)}`);
  return `Create ${refLabel(e.ref)}${props.length ? ` with ${props.join(", ")}` : ""}.`;
}

function updateSentence(e: Extract<Effect, { kind: "update" }>): string {
  const sets = Object.entries(e.set).map(([k, v]) => `${k} to ${value(v)}`);
  const parts = [
    ...(sets.length ? [`set ${sets.join(", ")}`] : []),
    ...(e.unset.length ? [`unset ${e.unset.join(", ")}`] : []),
  ];
  return `Update ${refLabel(e.ref)}: ${parts.length ? parts.join("; ") : "no property changes"}.`;
}

/** One sentence for one effect. */
export function summarizeEffect(e: Effect): string {
  switch (e.kind) {
    case "create":
      return createSentence(e);
    case "update":
      return updateSentence(e);
    case "delete":
      return `Delete ${refLabel(e.ref)}.`;
    case "link":
      return `Link ${e.relationship} from ${refLabel(e.source)} to ${refLabel(e.target)}.`;
    case "unlink":
      return `Unlink ${e.relationship} from ${refLabel(e.source)} to ${refLabel(e.target)}.`;
  }
}

/** One sentence per effect, in order. */
export function summarizeEffects(effects: readonly Effect[]): string[] {
  return effects.map(summarizeEffect);
}
