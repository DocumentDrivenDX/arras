// SPDX-License-Identifier: MIT OR Apache-2.0
// How a run of the shared read corpus compares an answer (`arras/conformance/read_cases.json`,
// CONTRACT-012): the same reduction `tools/gen_static_reads.py` applies to the Python reference's
// answer. The profile-specific parts of an answer (the backend's name and position, freshness times,
// attribution, a type's mutability, locations) are dropped; an error is its code, its path and, except
// for a `BAD_QUERY` (whose text is the GraphQL implementation's own), its message and extensions.
import type { WireResult } from "./execute";
import { Refusal } from "./execute";

const DROP = new Set([
  "freshness",
  "createdBy",
  "createdAt",
  "updatedBy",
  "updatedAt",
  "position",
  "revision",
  "mutable",
  "latency_class",
  "locations",
]);

export function normalise(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(normalise);
  if (value !== null && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value))
      if (!DROP.has(k)) out[k === "memory" ? "static" : k] = normalise(v);
    return out;
  }
  return value === "memory" ? "static" : value;
}

export interface Normal {
  status: number;
  data?: unknown;
  errors?: { code: unknown; path?: unknown; message?: string; extensions?: unknown }[];
}

/** The answer of a run, or the HTTP status the surface gives instead, as the corpus states it. */
export function normaliseResult(answer: WireResult | Refusal): Normal {
  if (answer instanceof Refusal)
    return {
      status: answer.status,
      errors: [{ code: answer.code, message: answer.message }].map((e) =>
        e.code === "BAD_QUERY" ? { code: e.code } : e,
      ),
    };
  const out: Normal = { status: 200 };
  if (answer.data !== undefined) out.data = normalise(answer.data);
  const errors = (answer.errors ?? []).map((e) => {
    const code = e.extensions.code;
    const item: Normal["errors"] extends (infer T)[] | undefined ? T : never = { code };
    if (e.path) item.path = e.path;
    if (code !== "BAD_QUERY") {
      item.message = e.message;
      const extra = Object.fromEntries(
        Object.entries(e.extensions).filter(([k]) => k !== "code" && k !== "violations"),
      );
      if (Object.keys(extra).length) item.extensions = normalise(extra);
    }
    return item;
  });
  if (errors.length) out.errors = errors;
  return out;
}
