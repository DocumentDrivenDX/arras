// SPDX-License-Identifier: MIT OR Apache-2.0
// arras-ui: the Operator Console as components (FEAT-010, ADR-021). Import "arras-ui/styles.css"
// once in the host for the console's tokens and Tailwind utilities.

export type { Area, ArrasConsoleProps, Route } from "./ArrasConsole";
export { ArrasConsole, formatHash, parseHash } from "./ArrasConsole";
export type { ArrasClient, ClientConfig, SchemaApi } from "./api/client";
export { createClient, createSchemaApi, DEFAULT_SCHEMA_BASE } from "./api/client";
export type { ProviderProps } from "./api/context";
export { ArrasProvider } from "./api/context";
export { ApiError } from "./api/errors";
export * from "./api/types";
export type { ActionFormProps } from "./areas/ActionForm";
export { ActionForm } from "./areas/ActionForm";
export type { AuditViewProps } from "./areas/AuditView";
export { AuditView } from "./areas/AuditView";
export type { EntityTableProps } from "./areas/EntityTable";
export { EntityTable } from "./areas/EntityTable";
export type { QueryAreaProps } from "./areas/QueryArea";
export { QueryArea } from "./areas/QueryArea";
export { SchemaBrowser } from "./areas/SchemaBrowser";
export { SchemaExport } from "./areas/SchemaExport";
export { SchemaImport } from "./areas/SchemaImport";
export { DEFAULT_EXPLORER_BASE, UmfSource, type UmfSourceProps } from "./areas/UmfSource";
export { annotationsFor, entryId, toEntries, typeForSelection } from "./areas/umfBrowser";
export type { Brand } from "./lib/brand";
export { DEFAULT_BRAND, readBrandMeta } from "./lib/brand";
