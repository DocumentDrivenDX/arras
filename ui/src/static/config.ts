// SPDX-License-Identifier: MIT OR Apache-2.0
// `arras-static.json`, the one file that names what a static host shows (CONTRACT-012): where the module
// document and the graph file are, as paths relative to the page (no scheme, no host, no `..`), so a page
// cannot be made to load another origin's graph.
import type { Brand } from "../lib/brand";

export interface StaticConfig {
  module: string;
  graph: string;
  brand?: Brand;
}

const RELATIVE = /^(?!\/)(?![A-Za-z][A-Za-z0-9+.-]*:)(?!.*(?:^|\/)\.\.(?:\/|$))[^\s?#\\]+$/;

export function readConfig(text: string): StaticConfig {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    throw new Error("arras-static.json is not JSON");
  }
  const c = raw as Record<string, unknown> | null;
  const path = (k: string): string => {
    const v = c?.[k];
    if (typeof v !== "string" || !RELATIVE.test(v))
      throw new Error(`arras-static.json: "${k}" is a path relative to the page`);
    return v;
  };
  const brand = c?.brand;
  return {
    module: path("module"),
    graph: path("graph"),
    ...(brand && typeof brand === "object" ? { brand: brand as Brand } : {}),
  };
}
