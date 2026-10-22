// SPDX-License-Identifier: MIT OR Apache-2.0
import type { ReactNode } from "react";
import { useScrollCue } from "../lib/scrollCue";

/**
 * A horizontally scrolling box that shows an edge fade where more lies beyond (`.arras-cue`, styles.css). The
 * wrapper carries `data-cue-start` / `data-cue-end`, which drive a mask on the scroller inside (its first child, `scrollerClass`), so no layer sits over the text; `scrollerClass` must make it scroll (`overflow-x-auto` or `overflow-auto`).
 */
export function CueScroll({
  className = "",
  scrollerClass = "",
  scrollerTestId,
  deps,
  children,
}: {
  className?: string;
  scrollerClass?: string;
  scrollerTestId?: string;
  deps?: readonly unknown[];
  children: ReactNode;
}) {
  const { ref, cue } = useScrollCue(deps);
  return (
    <div
      className={`arras-cue ${className}`}
      data-cue-start={cue.start ? "true" : undefined}
      data-cue-end={cue.end ? "true" : undefined}
    >
      <div ref={ref} className={scrollerClass} data-testid={scrollerTestId}>
        {children}
      </div>
    </div>
  );
}
