// SPDX-License-Identifier: MIT OR Apache-2.0
import { useSyncExternalStore } from "react";

/** The width below which the console shows one pane at a time and one compact header row (Tailwind `md`). */
export const NARROW = "(max-width: 767.98px)";
/** Touch screens and narrow ones: no keyboard to hint at. */
export const NO_KEYBOARD = `${NARROW}, (pointer: coarse)`;

const hasMatchMedia = () => typeof window !== "undefined" && !!window.matchMedia;

/** Whether a media query matches now and as it changes; `fallback` where there is no `matchMedia` (a test DOM). */
export function useMediaQuery(query: string, fallback = false): boolean {
  return useSyncExternalStore(
    (notify) => {
      if (!hasMatchMedia()) return () => undefined;
      const list = window.matchMedia(query);
      list.addEventListener("change", notify);
      return () => list.removeEventListener("change", notify);
    },
    () => (hasMatchMedia() ? window.matchMedia(query).matches : fallback),
    () => fallback,
  );
}

/** A narrow viewport (below `md`). */
export const useNarrow = () => useMediaQuery(NARROW);

/** Whether keyboard hints are noise: on a narrow viewport or a coarse pointer (touch). */
export const useHideKeyHints = () => useMediaQuery(NO_KEYBOARD);
