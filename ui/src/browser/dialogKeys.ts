// SPDX-License-Identifier: MIT OR Apache-2.0
// The keys of a modal dialog: Escape closes it (unless it is busy) and Tab stays inside it.
import { type KeyboardEvent, type RefObject, useCallback } from "react";

const FOCUSABLE =
  'input:not([disabled]), textarea:not([disabled]), select:not([disabled]), button:not([disabled]), [href], [tabindex="0"]';

export function useDialogKeys(
  root: RefObject<HTMLElement | null>,
  onClose: () => void,
  busy: boolean,
) {
  return useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) {
        e.stopPropagation();
        onClose();
      } else if (e.key === "Tab") {
        const items = [...(root.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])];
        const first = items[0];
        const last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    },
    [root, onClose, busy],
  );
}
