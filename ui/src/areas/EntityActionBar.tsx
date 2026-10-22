// SPDX-License-Identifier: MIT OR Apache-2.0
import { shortName } from "../api/gql";
import type { ModuleInfo } from "../api/types";
import { Button } from "../components/ui";
import { entityActions, splitActions } from "../kit";
import { ActionMenu } from "./ActionMenu";
import type { Entry } from "./entity";

export interface EntityActionBarProps {
  module: ModuleInfo;
  entry: Entry;
  onAction?: (action: string, prefill: Record<string, string>) => void;
  onHistory?: (type: string, key: string) => void;
  onGraph?: (type: string, key: string) => void;
}

/**
 * The actions for this entity at the top of its panel: the few declared updates of its type that
 * change the fewest properties as buttons, the rest of the actions that take it in a menu, with
 * History and Graph beside them. Each action opens its form prefilled with this entity's key.
 */
export function EntityActionBar({
  module: m,
  entry,
  onAction,
  onHistory,
  onGraph,
}: EntityActionBarProps) {
  const { primary, rest } = splitActions(entityActions(m, entry.type));
  const run = (x: (typeof primary)[number]) =>
    onAction?.(x.action.name, { [x.keyInput.name]: entry.key });
  if (primary.length === 0 && rest.length === 0 && !onHistory && !onGraph) return null;
  return (
    <div
      role="toolbar"
      aria-label={`Actions for ${shortName(entry.type)} ${entry.key}`}
      data-testid="entity-actions"
      className="flex flex-wrap items-center gap-1 border-b border-line bg-surface px-3 py-1.5"
    >
      {onAction &&
        primary.map((x, i) => (
          <Button
            key={x.action.name}
            variant={i === 0 ? "primary" : "default"}
            title={x.action.description}
            onClick={() => run(x)}
          >
            {shortName(x.action.name)}…
          </Button>
        ))}
      {onAction && (
        <ActionMenu
          label="Actions"
          items={rest.map((x) => ({
            id: x.action.name,
            label: `${shortName(x.action.name)}…`,
            title: x.action.description,
            onSelect: () => run(x),
          }))}
        />
      )}
      {onHistory && <Button onClick={() => onHistory(entry.type, entry.key)}>History</Button>}
      {onGraph && (
        <Button aria-label="Show in graph" onClick={() => onGraph(entry.type, entry.key)}>
          Graph
        </Button>
      )}
    </div>
  );
}
