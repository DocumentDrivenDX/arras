// SPDX-License-Identifier: MIT OR Apache-2.0
// The static read-only profile (ADR-031, CONTRACT-012): the Graph Browser's backend as files.
export {
  createStaticClient,
  digestOf,
  loadStore,
  READ_ONLY,
  staticSchemaApi,
} from "./backend";
export { InvalidDocument } from "./model";
export { GraphLoadError } from "./store";
