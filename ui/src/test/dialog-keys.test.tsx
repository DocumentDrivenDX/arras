// SPDX-License-Identifier: MIT OR Apache-2.0
import { fireEvent, render, screen } from "@testing-library/react";
import { useRef } from "react";
import { describe, expect, it } from "vitest";
import { useDialogKeys } from "../browser/dialogKeys";

function Box({ lastDisabled }: { lastDisabled: boolean }) {
  const root = useRef<HTMLDivElement>(null);
  const onKeyDown = useDialogKeys(root, () => undefined, false);
  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: the dialog's key handler under test
    <div ref={root} onKeyDown={onKeyDown}>
      <input aria-label="first" />
      <input aria-label="last" />
      <input aria-label="gone" disabled={lastDisabled} />
      <textarea aria-label="gone-area" disabled />
      <select aria-label="gone-select" disabled />
    </div>
  );
}

describe("the dialog's Tab trap", () => {
  it("wraps from the last enabled control, skipping disabled inputs, textareas and selects", () => {
    render(<Box lastDisabled />);
    const last = screen.getByLabelText("last");
    last.focus();
    fireEvent.keyDown(last, { key: "Tab" });
    expect(screen.getByLabelText("first")).toHaveFocus();
  });
});
