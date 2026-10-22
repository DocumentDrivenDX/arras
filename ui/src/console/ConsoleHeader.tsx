// SPDX-License-Identifier: MIT OR Apache-2.0
import type { ReactNode } from "react";
import { Chip } from "../components/ui";
import { Wordmark } from "../lib/brand";
import { OPERATE } from "../lib/vocabulary";

/**
 * The console's top bar: its name, the operate contract version, the host's toolbar and, on a narrow screen,
 * the module picker that stands in for the rail. One wrapping row, so a phone spends one or two lines on it.
 */
export function ConsoleHeader({
  operateVersion,
  toolbar,
  modulePicker,
}: {
  operateVersion?: number;
  toolbar?: ReactNode;
  modulePicker?: ReactNode;
}) {
  return (
    <header
      data-testid="console-header"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line bg-surface px-3 py-1.5"
    >
      <Wordmark className="truncate font-semibold" />
      <span className="truncate text-muted">{OPERATE}</span>
      {operateVersion !== undefined && (
        <span className="hidden md:inline-flex">
          <Chip title="contract versions">operate v{operateVersion}</Chip>
        </span>
      )}
      {modulePicker}
      <div className="ml-auto flex flex-wrap items-center gap-2">{toolbar}</div>
    </header>
  );
}
