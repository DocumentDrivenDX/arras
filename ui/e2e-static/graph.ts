// SPDX-License-Identifier: MIT OR Apache-2.0
// What the specs know of an example graph, read from its own file, so a change to the example is a
// change to the expectation and no name is written twice.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

interface Rec {
  type?: string;
  key?: string;
  relationship?: string;
  source?: string;
  target?: string;
  properties?: Record<string, unknown>;
}

export function loadGraph(example: string, file: string): Rec[] {
  const path = resolve(import.meta.dirname, "../../examples", example, file);
  return (JSON.parse(readFileSync(path, "utf8")) as { records: Rec[] }).records;
}

export const entity = (records: Rec[], type: string, key: string): Rec => {
  const found = records.find((r) => r.type === type && r.key === key);
  if (!found) throw new Error(`${type} ${key} is not in the graph`);
  return found;
};

/** The first relationship record of `name`, with both ends. */
export const firstLink = (records: Rec[], name: string): Rec => {
  const found = records.find((r) => r.relationship === name);
  if (!found) throw new Error(`no ${name} link in the graph`);
  return found;
};

export const nameOf = (r: Rec): string =>
  String(r.properties?.name ?? r.properties?.title ?? r.key);
