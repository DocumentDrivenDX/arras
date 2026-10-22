// SPDX-License-Identifier: MIT OR Apache-2.0
// The write half of every in-place change (ADR-015): the host offers it (`canEdit`, an operator's
// mode, CONTRACT-010 E), and a change is the module's declared action, checked with `validate` and
// applied with `invoke` by the kit's core, never a write of the browser's own. A property edit
// (`useEdit`) and a link change (`useLink`) are both this, with the inputs they build.
import { useQueryClient } from "@tanstack/react-query";
import type { ModuleInfo } from "../api/types";
import { type ActionState, invalidateAfterApply, useActionCore } from "../kit";

export type { ActionState };

export function useAction(module: ModuleInfo): ActionState {
  const qc = useQueryClient();
  // The page, its neighbours' labels and every search show the new state, not the old: the shared
  // invalidation (kit/invalidate) runs once the change is applied.
  return useActionCore(module, () => invalidateAfterApply(qc));
}
