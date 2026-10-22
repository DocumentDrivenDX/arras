// SPDX-License-Identifier: MIT OR Apache-2.0
// The graph file an export writes (CONTRACT-003, Export): the module's records, read a page at a time,
// as the same bytes `arras.graphfile.dumps` writes, so a file saved here and one written by the
// library are interchangeable and a file kept in version control only changes when the graph does.
// Keys are sorted (by code point, as Python sorts), indent is two spaces, the text ends in a newline,
// and nothing that varies between runs is in it: no time, no person, no revision.
import type { ArrasClient } from "../api/client";
import { assertIntegers, NotIntegerError, notAnInteger, parseLossless } from "../api/losslessJson";

export const GRAPH_FORMAT = "arras.graph";
export const GRAPH_VERSION = 1;
const PAGE = 500;
/** A module's graph is never walked past this many pages: a cursor that does not end is a fault. */
const MAX_PAGES = 10_000;

export const graphFileName = (module: string) => `${module}.graph.json`;

const code = (ch: string | undefined): number => ch?.codePointAt(0) ?? 0;

/** Order by code point, as Python orders strings (a plain `<` orders by UTF-16 unit). */
const byCodePoint = (a: string, b: string): number => {
  const x = Array.from(a);
  const y = Array.from(b);
  for (let i = 0; i < Math.min(x.length, y.length); i++) {
    const d = code(x[i]) - code(y[i]);
    if (d !== 0) return d;
  }
  return x.length - y.length;
};

/**
 * JSON with every object's keys sorted, as `json.dumps(..., sort_keys=True, indent=2)` writes it. A
 * `bigint` (an integer past 2^53, read by `parseLossless`) is written digit for digit.
 */
export function canonical(value: unknown, indent = ""): string {
  if (typeof value === "bigint") return value.toString();
  if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
  const inner = `${indent}  `;
  if (Array.isArray(value)) {
    if (value.length === 0) return "[]";
    return `[\n${value.map((v) => inner + canonical(v, inner)).join(",\n")}\n${indent}]`;
  }
  const keys = Object.keys(value).sort(byCodePoint);
  if (keys.length === 0) return "{}";
  const rows = keys.map(
    (k) =>
      `${inner}${JSON.stringify(k)}: ${canonical((value as Record<string, unknown>)[k], inner)}`,
  );
  return `{\n${rows.join(",\n")}\n${indent}}`;
}

export interface GraphFile {
  module: string;
  records: Record<string, unknown>[];
  complete: boolean;
  omitted: string[];
}

const INTEGER_TEXT = /^-?\d+$/;

/**
 * The path and text of the first number in `value` that the file would not hold as an integer (a fraction,
 * an exponent, `NaN` or `Infinity`): the readers refuse such a number, so it is not written.
 */
function firstUnwritable(value: unknown, path = ""): { path: string; token: string } | null {
  if (typeof value === "number") {
    const token = String(value);
    return INTEGER_TEXT.test(token) ? null : { path, token };
  }
  if (value === null || typeof value !== "object") return null;
  const members: [string, unknown][] = Array.isArray(value)
    ? value.map((v, i) => [`${path}[${i}]`, v])
    : Object.entries(value).map(([k, v]) => [path ? `${path}.${k}` : k, v]);
  for (const [at, v] of members) {
    const found = firstUnwritable(v, at);
    if (found) return found;
  }
  return null;
}

/**
 * The file's text for a graph. A number in it that is not an integer is not written (a decimal is a string):
 * an `Error` names its path, as the readers do for the same number, so a file they would refuse is never made.
 */
export function graphText(g: GraphFile): string {
  const body: Record<string, unknown> = {
    format: GRAPH_FORMAT,
    version: GRAPH_VERSION,
    module: g.module,
    complete: g.complete,
    records: g.records,
  };
  if (g.omitted.length > 0) body.omitted = g.omitted;
  const bad = firstUnwritable(body);
  if (bad) throw new Error(notAnInteger(bad));
  return `${canonical(body)}\n`;
}

const isObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

/**
 * Read a graph file, as `arras.graphfile.loads` does: a number in it is an integer, kept exactly (a decimal
 * is a string), and an `Error` says what is wrong with its shape. A file that does not say it is `complete`
 * is not known to be whole.
 */
export function parseGraphFile(text: string): GraphFile {
  let raw: unknown;
  try {
    raw = parseLossless(text);
  } catch (e) {
    if (e instanceof NotIntegerError) throw e;
    throw new Error(`not JSON: ${e instanceof Error ? e.message : String(e)}`);
  }
  assertIntegers(text);
  if (!isObject(raw)) throw new Error("a graph file is a JSON object");
  if (raw.format !== GRAPH_FORMAT)
    throw new Error(`not a graph file: "format" is "${GRAPH_FORMAT}"`);
  if (raw.version !== GRAPH_VERSION)
    throw new Error(`this release reads graph file version ${GRAPH_VERSION}`);
  const { module, records, omitted } = raw;
  if (typeof module !== "string" || module === "")
    throw new Error('"module" names the module the records belong to');
  if (!Array.isArray(records) || !records.every(isObject))
    throw new Error('"records" is a list of entity and relationship records');
  return {
    module,
    records,
    complete: raw.complete === true,
    omitted: Array.isArray(omitted) ? omitted.map(String) : [],
  };
}

/** Read the whole of `module` as the viewer, a page at a time. */
export async function readGraph(
  client: ArrasClient,
  module: string,
  onPage?: (records: number) => void,
): Promise<GraphFile> {
  const records: Record<string, unknown>[] = [];
  const omitted = new Set<string>();
  let after: string | undefined;
  for (let i = 0; i < MAX_PAGES; i++) {
    const page = await client.export({ module, limit: PAGE, ...(after ? { after } : {}) });
    records.push(...page.items);
    for (const t of page.omitted) omitted.add(t);
    onPage?.(records.length);
    if (page.nextCursor === null) {
      return {
        module,
        records,
        complete: omitted.size === 0,
        omitted: [...omitted].sort(byCodePoint),
      };
    }
    after = page.nextCursor;
  }
  throw new Error("the export did not end");
}
