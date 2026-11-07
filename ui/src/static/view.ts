// SPDX-License-Identifier: MIT OR Apache-2.0
// `arras.view` for the static read-only profile (CONTRACT-010, CONTRACT-012): terms, templates, defaults and
// resolution, and the registration checks. The barrel; each part is its own module (a port of `arras/view.py`).

export { isSearchableType, pluralize, resolve, splitWords, titleOf } from "./viewDefaults";
export { parseView } from "./viewRead";
export { asText, evaluate, parseTemplate, placeholders, TemplateError } from "./viewTemplate";
export type {
  DeclaredView,
  ResolvedModule,
  ResolvedView,
} from "./viewTerms";
export { VERSION, VOCABULARY } from "./viewTerms";
