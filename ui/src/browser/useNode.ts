// SPDX-License-Identifier: MIT OR Apache-2.0
// A node page's read: the page request or requests of the planner, answered as one entity, and the
// state a page shows for each way it can go. An entity that is absent, hidden from the viewer or at
// an unreadable location is the same state ("na"); a backend that is down is not.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { ArrasClient } from "../api/client";
import { useClient } from "../api/context";
import { ApiError } from "../api/errors";
import { byKeyField } from "../api/gql";
import { revisionKey, type TypeEntry } from "./meta";
import { pageQueries } from "./planner";

export type Entity = Record<string, unknown>;

async function readEntity(client: ArrasClient, entry: TypeEntry, key: string): Promise<Entity> {
  const field = byKeyField(entry.type.name);
  const answers = await Promise.all(
    pageQueries(entry).map((q) =>
      client.moduleQuery<Record<string, Entity | null>>(entry.module.name, q, { key }),
    ),
  );
  const merged: Entity = {};
  for (const r of answers) {
    const row = r.data?.[field];
    if (row) {
      Object.assign(merged, row);
      continue;
    }
    const e = r.errors[0];
    throw new ApiError(e ? 200 : 404, {
      message: e?.message ?? "not found",
      code: e?.code ?? "NOT_FOUND",
      backend: e?.backend,
      reason: e?.reason,
    });
  }
  return merged;
}

export type NodeState =
  | { status: "loading" }
  | { status: "na" }
  | { status: "down"; backend: string | undefined }
  | { status: "expired" }
  | { status: "error"; error: unknown }
  | { status: "ready"; entity: Entity };

const GONE = new Set(["not_found", "no_access", "forbidden", "invalid"]);

export function stateOf(error: unknown): NodeState {
  if (error instanceof ApiError) {
    if (GONE.has(error.kind)) return { status: "na" };
    if (error.kind === "unavailable") return { status: "down", backend: error.backend };
    if (error.kind === "sign_in") return { status: "expired" };
  }
  return { status: "error", error };
}

const sameNode = (k: readonly unknown[], entry: TypeEntry | undefined, key: string | undefined) =>
  k[2] === entry?.module.name && k[3] === entry?.type.name && k[4] === key;

export function useNode(entry: TypeEntry | undefined, key: string | undefined) {
  const client = useClient();
  const q = useQuery({
    queryKey: [
      "gb",
      "node",
      entry?.module.name,
      entry?.type.name,
      key,
      entry && revisionKey(entry.module),
    ],
    enabled: !!entry && key !== undefined,
    retry: false,
    staleTime: 10_000,
    // Under a new registry revision the same node is read again behind what it showed, so the page
    // keeps its height and its place; another node starts from a skeleton.
    placeholderData: (previous, previousQuery) =>
      previousQuery && sameNode(previousQuery.queryKey, entry, key)
        ? keepPreviousData(previous)
        : undefined,
    queryFn: () => {
      if (!entry || key === undefined) throw new Error("no node");
      return readEntity(client, entry, key);
    },
  });
  const state: NodeState = q.isPending
    ? { status: "loading" }
    : q.error
      ? stateOf(q.error)
      : { status: "ready", entity: q.data };
  return { state, retry: () => void q.refetch(), fetching: q.isFetching };
}
