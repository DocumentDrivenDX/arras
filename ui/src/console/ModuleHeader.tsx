// SPDX-License-Identifier: MIT OR Apache-2.0
import type { ReactNode } from "react";
import { useHideKeyHints } from "../lib/useMediaQuery";
import type { Area } from "../route";
import { AreaTabs } from "./AreaTabs";

/**
 * The module's header: its title, an optional `context` slot under the title (the open entity's
 * context header goes there), the key hint and the area tabs.
 */
export function ModuleHeader({
  module,
  area,
  auditShown,
  context,
  onArea,
}: {
  module: string;
  area: Area;
  auditShown: boolean;
  /** Rendered under the module title; nothing when absent. */
  context?: ReactNode;
  onArea: (area: Area) => void;
}) {
  const hideHints = useHideKeyHints();
  return (
    <div className="flex flex-wrap items-end gap-x-2 gap-y-0 border-b border-line bg-surface px-3 pt-1.5 md:pt-2">
      <h1 className="m-0 mb-1.5 mr-2 text-[14px] font-semibold md:text-[15px]">{module}</h1>
      {context}
      {!hideHints && (
        <span
          className="mb-1.5 hidden text-[11px] text-muted min-[1100px]:inline"
          data-testid="key-hint"
        >
          <kbd>1</kbd>–<kbd>{auditShown ? 6 : 5}</kbd> areas · <kbd>/</kbd> filter · <kbd>←↑↓→</kbd>{" "}
          move in the graph · <kbd>Enter</kbd> open
        </span>
      )}
      <AreaTabs area={area} auditShown={auditShown} onPick={onArea} />
    </div>
  );
}
