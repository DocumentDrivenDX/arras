// SPDX-License-Identifier: MIT OR Apache-2.0
// Explore's links into Operate (FR-71): drawn only where the shell handed the browser the primitive,
// which it does for an operator. Without it nothing here renders and the page carries no word of Operate.
import { CrossAnchor, entityActions, type LinkArea } from "../kit";
import { useBrowser } from "./context";
import type { TypeEntry } from "./meta";

const LABEL = "Open in Operate";

/** A node page's links into Operate: its Entities row, its History and an action that takes it, prefilled. */
export function OpenInOperate({ entry, keyText }: { entry: TypeEntry; keyText: string }) {
  const { toOperate } = useBrowser();
  if (!toOperate) return null;
  const { module, type } = entry;
  const first = entityActions(module, type.name)[0];
  const entity = {
    module: module.name,
    type: type.name,
    key: keyText,
    ...(first && {
      action: { name: first.action.name, input: { [first.keyInput.name]: keyText } },
    }),
  };
  const items: [string, LinkArea][] = [
    ["Entities", "entities"],
    ["History", "history"],
    ...(first ? ([["Actions", "actions"]] as [string, LinkArea][]) : []),
  ];
  return (
    <nav className="gb-xlinks" aria-label={LABEL} data-testid="gb-open-in-operate">
      <span>{LABEL}</span>
      {items.map(([text, area]) => (
        <CrossAnchor
          key={area}
          link={toOperate({ entity }, area)}
          className="gb-xlink"
          aria-label={`${text} of ${entry.view.label} ${keyText} in Operate`}
        >
          {text}
        </CrossAnchor>
      ))}
    </nav>
  );
}

/** A type list's link to the type's model in Operate. */
export function ModelLink({ entry }: { entry: TypeEntry }) {
  const { toOperate } = useBrowser();
  if (!toOperate) return null;
  return (
    <CrossAnchor
      link={toOperate({ type: { module: entry.module.name, type: entry.type.name } }, "model")}
      className="gb-xlink"
      aria-label={`Model of ${entry.view.label} in Operate`}
    >
      Model
    </CrossAnchor>
  );
}
