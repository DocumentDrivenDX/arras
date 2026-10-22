// SPDX-License-Identifier: MIT OR Apache-2.0
// arras-ui/shell: `ArrasApp`, the Graph Browser and the Operator Console behind one top bar
// (ADR-025). It is the only module that imports both.

export type { ArrasAppProps } from "./ArrasApp";
export { ArrasApp } from "./ArrasApp";
export type { CrossLink, LinkArea, LinkTarget, LinkTo } from "./links";
export type { Mode } from "./modeRoute";
export { effectiveMode, hashKind, operateFor } from "./modeRoute";
