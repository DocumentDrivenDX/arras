// SPDX-License-Identifier: MIT OR Apache-2.0
// The eight tones of CONTRACT-010 (DESIGN-GB, Tokens): a tone is a hue, never a meaning, and it
// always travels with an icon, a label or a position. The colours are CSS variables in styles.css.

export const TONES = ["slate", "blue", "teal", "green", "amber", "red", "violet", "rose"] as const;
export type Tone = (typeof TONES)[number];

const isTone = (t: string | null | undefined): t is Tone => TONES.some((x) => x === t);

/** A name from the server's resolved view, or `slate` for anything this release does not know. */
export const toneOf = (t: string | null | undefined): Tone => (isTone(t) ? t : "slate");

/** The class that sets `--ink`, `--soft` and `--mark` for the tone. */
export const toneClass = (t: string | null | undefined): string => `gb-t-${toneOf(t)}`;
