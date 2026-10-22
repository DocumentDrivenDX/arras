// SPDX-License-Identifier: MIT OR Apache-2.0
import type { ArrasClient } from "../api/client";
import { ApiError } from "../api/errors";
import { ATTRIBUTION, buildEntityQuery, byKeyField, relationFields } from "../api/gql";
import type { EntityTypeInfo, ModuleInfo, Ref } from "../api/types";

export interface EntityData {
  key: string;
  type: string;
  version?: string | number | null;
  createdBy?: string | null;
  createdAt?: string | null;
  updatedBy?: string | null;
  updatedAt?: string | null;
  props: Record<string, unknown>;
  rels: Record<string, Ref[]>;
  /** An entity of another module: interface fields only. */
  foreign?: boolean;
  freshness?: { backend: string; asOf: string; at: string; consistency: string } | null;
}

/** One place in the panel's trail: an entity, with data when a follow already loaded it. */
export interface Entry {
  module: string;
  type: string;
  key: string;
  seed?: EntityData;
}

export function toEntity(
  m: ModuleInfo | undefined,
  raw: Record<string, unknown>,
  foreign = false,
): EntityData {
  const type = String(raw.type ?? "");
  const relNames = new Set(m && !foreign ? relationFields(m, type).map((r) => r.field) : []);
  const reserved = new Set(["key", "type", "freshness", "target", ...ATTRIBUTION]);
  const props: Record<string, unknown> = {};
  const rels: Record<string, Ref[]> = {};
  for (const [k, v] of Object.entries(raw)) {
    if (reserved.has(k)) continue;
    if (relNames.has(k)) rels[k] = Array.isArray(v) ? (v as Ref[]) : [];
    else props[k] = v;
  }
  return {
    key: String(raw.key),
    type,
    version: raw.version as string | number | null | undefined,
    createdBy: raw.createdBy as string | null | undefined,
    createdAt: raw.createdAt as string | null | undefined,
    updatedBy: raw.updatedBy as string | null | undefined,
    updatedAt: raw.updatedAt as string | null | undefined,
    props,
    rels,
    foreign,
    freshness: raw.freshness as EntityData["freshness"],
  };
}

/** One by-key read of an entity with its properties, attribution and relationships. */
export async function fetchEntity(
  client: ArrasClient,
  m: ModuleInfo,
  t: EntityTypeInfo,
  key: string,
  consistency: "LATEST" | "BULK" = "LATEST",
): Promise<EntityData | null> {
  const r = await client.moduleQuery<Record<string, Record<string, unknown> | null>>(
    m.name,
    buildEntityQuery(m, t),
    { key, consistency },
  );
  const raw = r.data?.[byKeyField(t.name)] ?? null;
  if (!raw) {
    const e = r.errors[0];
    if (e) throw new ApiError(200, { message: e.message, code: e.code });
    return null;
  }
  return toEntity(m, raw);
}
