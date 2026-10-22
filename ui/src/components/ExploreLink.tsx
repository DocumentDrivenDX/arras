// SPDX-License-Identifier: MIT OR Apache-2.0
import { CrossAnchor, type LinkArea, type LinkTarget } from "../kit";
import { useExploreLink } from "./NavLink";

const CLASS = "text-accent underline-offset-2 hover:underline";

/**
 * **View in Explore**: the shell's link into the other mode (Rule 7). Nothing renders where the shell
 * handed the console none, which is every viewer who is not an operator.
 */
export function ViewInExplore({
  target,
  area,
  label,
  className = CLASS,
}: {
  target: LinkTarget;
  area?: LinkArea;
  /** What it opens, for the accessible name: "View in Explore: <label>". */
  label: string;
  className?: string;
}) {
  const toExplore = useExploreLink();
  if (!toExplore) return null;
  return (
    <CrossAnchor
      link={toExplore(target, area)}
      className={className}
      aria-label={`View in Explore: ${label}`}
    >
      View in Explore
    </CrossAnchor>
  );
}
