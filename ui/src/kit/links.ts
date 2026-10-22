// SPDX-License-Identifier: MIT OR Apache-2.0
// The cross-mode link primitive's vocabulary (SD-013, Rule 7): what a mode asks the shell to link to,
// and what the shell hands back. Type names are qualified (`catalog.Solution`), as the API gives
// them; the shell is the only place that converts them to either mode's address grammar.

/** The place in the other mode a link opens, when the target alone does not say. */
export type LinkArea = "entities" | "history" | "actions" | "model" | "changes";

export type LinkTarget =
  | {
      entity: {
        module: string;
        type: string;
        key: string;
        /** With the `actions` area: the action to open, and the entity keys to prefill by input name. */
        action?: { name: string; input: Record<string, string> };
      };
    }
  | {
      type: {
        module: string;
        type: string;
        /** A list's position: the key its page starts after. */
        after?: string;
      };
    }
  | { module: string }
  | { group: { module: string; id: string } };

/** An anchor's address where the host's location is the fragment; `go` acts wherever the host owns it. */
export interface CrossLink {
  href?: string;
  go(): void;
}

/** What the shell gives a mode: a function from a target to the link into the other mode. */
export type LinkTo = (target: LinkTarget, area?: LinkArea) => CrossLink;
