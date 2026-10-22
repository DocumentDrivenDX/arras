// SPDX-License-Identifier: MIT OR Apache-2.0
import { useCallback, useEffect, useState } from "react";

/** Which edges of a horizontally scrolling box have more content beyond them. */
export interface ScrollCue {
  start: boolean;
  end: boolean;
}

export interface ScrollMetrics {
  scrollLeft: number;
  clientWidth: number;
  scrollWidth: number;
}

const NONE: ScrollCue = { start: false, end: false };

/** The edges with more to scroll to: within `slack` pixels of an edge counts as at it (sub-pixel scroll positions). */
export function scrollCue(m: ScrollMetrics, slack = 1): ScrollCue {
  const left = Math.abs(m.scrollLeft);
  return {
    start: left > slack,
    end: m.scrollWidth - m.clientWidth - left > slack,
  };
}

/**
 * The scroll cue of an element: `ref` goes on the scrolling box, `cue` is true on an edge only while there is
 * more beyond it. It follows the box's scrolling and resizing, and `deps` re-measures when the content changes.
 */
export function useScrollCue(deps: readonly unknown[] = []) {
  const [el, setEl] = useState<HTMLElement | null>(null);
  const [cue, setCue] = useState<ScrollCue>(NONE);
  const ref = useCallback((node: HTMLElement | null) => setEl(node), []);
  useEffect(() => {
    if (!el) return;
    const measure = () => {
      const next = scrollCue(el);
      setCue((prev) => (prev.start === next.start && prev.end === next.end ? prev : next));
    };
    measure();
    el.addEventListener("scroll", measure, { passive: true });
    const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    ro?.observe(el);
    for (const child of Array.from(el.children)) ro?.observe(child);
    return () => {
      el.removeEventListener("scroll", measure);
      ro?.disconnect();
    };
  }, [el, ...deps]);
  return { ref, cue };
}
