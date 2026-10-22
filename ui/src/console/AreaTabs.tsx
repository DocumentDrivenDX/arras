// SPDX-License-Identifier: MIT OR Apache-2.0
import { CueScroll } from "../components/CueScroll";
import { TabList } from "../components/Tabs";
import { AREA_LABELS } from "../lib/vocabulary";
import { AREAS, type Area } from "../route";

/** The areas a module offers: Changes only when the journal is served. */
export const shownAreas = (auditShown: boolean): Area[] =>
  AREAS.filter((a) => a !== "changes" || auditShown);

/**
 * The area tablist of a module's header (arrow keys, Home and End move between areas). A tab never shrinks below
 * its label: on a narrow screen the list scrolls sideways, with an edge fade where there is more.
 */
export function AreaTabs({
  area,
  auditShown,
  onPick,
}: {
  area: Area;
  auditShown: boolean;
  onPick: (area: Area) => void;
}) {
  return (
    <CueScroll
      className="max-w-full min-w-0 max-md:w-full md:ml-auto"
      scrollerClass="overflow-x-auto"
      deps={[auditShown]}
    >
      <TabList
        label="Areas"
        className="flex w-max gap-1"
        items={shownAreas(auditShown).map((a) => ({ id: a, label: AREA_LABELS[a] }))}
        selected={area}
        onSelect={(a) => onPick(a as Area)}
        tabClass={(on) =>
          `shrink-0 whitespace-nowrap rounded-t border border-b-0 px-3 py-1.5 text-[12px] ${on ? "border-line bg-bg font-semibold" : "border-transparent text-muted hover:text-fg"}`
        }
      />
    </CueScroll>
  );
}
