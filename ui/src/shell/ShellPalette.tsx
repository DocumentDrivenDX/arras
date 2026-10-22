// SPDX-License-Identifier: MIT OR Apache-2.0
// The command palette at the shell: one component for both modes, drawn by each mode where its own
// would be (the shell owns the keys and whether it is open). In Explore an entity result opens its page,
// the commands are the module's types and, for an operator, Open in Operate; in Operate they are the
// console's areas, types and actions.
import { useEffect, useMemo } from "react";
import type { ModuleInfo } from "../api/types";
import { CommandPalette } from "../console/CommandPalette";
import type { Place } from "../lib/paletteCommands";
import type { Route } from "../route";

interface Common {
  module: ModuleInfo | undefined;
  open: boolean;
  onClose: () => void;
}

/** A palette asked for where there is no module to search is closed again, not left to appear later. */
function useCloseWithoutModule({ module, open, onClose }: Common) {
  useEffect(() => {
    if (open && !module) onClose();
  }, [open, module, onClose]);
}

export function ExplorePalette(
  p: Common & {
    go: (place: Place) => void;
    /** Present for an operator: Open in Operate is offered. */
    toOperate: (() => void) | undefined;
  },
) {
  useCloseWithoutModule(p);
  const { go, toOperate } = p;
  const targets = useMemo(() => ({ open: go, toOperate }), [go, toOperate]);
  return (
    <CommandPalette
      mode="explore"
      module={p.module}
      auditShown={false}
      targets={targets}
      controlled={{ open: p.open, onClose: p.onClose }}
    />
  );
}

export function OperatePalette(
  p: Common & { auditShown: boolean; go: (route: Route, opts?: { replace?: boolean }) => void },
) {
  useCloseWithoutModule(p);
  return (
    <CommandPalette
      mode="operate"
      module={p.module}
      auditShown={p.auditShown}
      go={p.go}
      controlled={{ open: p.open, onClose: p.onClose }}
    />
  );
}
