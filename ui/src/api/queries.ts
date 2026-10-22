// SPDX-License-Identifier: MIT OR Apache-2.0
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useClient, useSchemaApi } from "./context";
import { ApiError } from "./errors";
import type { MetaData, ModuleInfo, SchemaCatalog } from "./types";

export function useVersion() {
  const client = useClient();
  return useQuery({
    queryKey: ["version"],
    queryFn: () => client.version(),
    retry: false,
    staleTime: Infinity,
  });
}

/** The one meta read both modes share: the registry with each type's resolved view (CONTRACT-010 B). */
export function useMeta(
  enabled = true,
  options: { staleTime?: number; refetchOnWindowFocus?: boolean } = {},
) {
  const client = useClient();
  return useQuery<MetaData, ApiError>({
    queryKey: ["meta"],
    queryFn: () => client.meta(),
    enabled,
    retry: false,
    ...options,
  });
}

export function useModule(name: string | undefined): {
  module?: ModuleInfo;
  meta: ReturnType<typeof useMeta>;
} {
  const meta = useMeta();
  return { module: name ? meta.data?.modules.find((m) => m.name === name) : undefined, meta };
}

/** Backend status (position, lag); refetched when a table page loads. */
export function useStatus() {
  const client = useClient();
  return useQuery({
    queryKey: ["status"],
    queryFn: () => client.status(),
    retry: false,
    staleTime: 2_000,
  });
}

export type AuditProbe = "ok" | "unsupported" | "refused" | "sign_in" | "error";

const PROBE_BY_KIND: Partial<Record<ApiError["kind"], AuditProbe>> = {
  unsupported: "unsupported",
  no_access: "refused",
  not_offered: "refused",
  sign_in: "sign_in",
};

/** Is the audit served for this module? A 501 hides the area; any other answer shows it. */
export function useAuditProbe(module: string | undefined) {
  const client = useClient();
  return useQuery<AuditProbe>({
    queryKey: ["audit-probe", module],
    enabled: !!module,
    retry: false,
    staleTime: 60_000,
    queryFn: async () => {
      try {
        await client.changes({ module, limit: 1 });
        return "ok";
      } catch (e) {
        return e instanceof ApiError ? (PROBE_BY_KIND[e.kind] ?? "error") : "error";
      }
    },
  });
}

export function useRefresh() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries();
}

/** The query key of the viewer's schema catalog; shared by the UMF source view, import and export. */
export const SCHEMA_CATALOG_KEY = ["umf-schema-catalog"] as const;

/** The viewer's catalog of registered UMF documents (CONTRACT-009), as the console's client reads it. */
export function useSchemaCatalog() {
  const client = useClient();
  return useQuery<SchemaCatalog, ApiError>({
    queryKey: SCHEMA_CATALOG_KEY,
    queryFn: () => client.schemaCatalog(),
    retry: false,
  });
}

/** Does the host mount the schema surface (CONTRACT-011)? When not, the console shows no import. */
export function useSchemaOffered() {
  const api = useSchemaApi();
  return useQuery<boolean>({
    queryKey: ["schema-offered", api.schemaBase],
    queryFn: () => api.offered(),
    retry: false,
    staleTime: Infinity,
  });
}
