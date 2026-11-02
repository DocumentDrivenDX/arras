// SPDX-License-Identifier: MIT OR Apache-2.0
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import {
  type ButtonProps,
  DesignSystemProvider,
  type SelectProps,
  type TextAreaProps,
  type TextFieldProps,
} from "../ds";
import { WidgetControls } from "../testkit/host";

// `arras-ui-qualify --host-build` reads a region labelled "Downstream widget controls" with a host's Button,
// TextField, TextArea and Select in that tab order (support/QUALIFICATION.md); WidgetControls renders it from the
// design system in context, so a host marks its widgets and nothing more.

const marked = {
  Button: ({ children }: ButtonProps) => (
    <button type="button" data-theme-button>
      {children}
    </button>
  ),
  TextField: ({ label }: TextFieldProps) => (
    <label>
      {label}
      <input data-theme-text-field />
    </label>
  ),
  TextArea: ({ label }: TextAreaProps) => (
    <label>
      {label}
      <textarea data-theme-text-area />
    </label>
  ),
  Select: ({ label, options }: SelectProps) => (
    <label>
      {label}
      <select data-theme-select>
        {options.map((o) => (
          <option key={o.value}>{o.label}</option>
        ))}
      </select>
    </label>
  ),
  Notice: () => <section data-theme-notice />,
  Mark: () => <span data-theme-mark />,
};

describe("WidgetControls", () => {
  it("renders the labelled region with the host's six widgets, the four controls in tab order", async () => {
    render(
      <DesignSystemProvider designSystem={marked}>
        <WidgetControls />
      </DesignSystemProvider>,
    );
    const region = screen.getByRole("region", { name: "Downstream widget controls" });
    for (const marker of [
      "button[data-theme-button]",
      "input[data-theme-text-field]",
      "textarea[data-theme-text-area]",
      "select[data-theme-select]",
      "[data-theme-notice]",
      "[data-theme-mark]",
    ])
      expect(region.querySelector(marker), marker).not.toBeNull();
    const user = userEvent.setup();
    await user.click(within(region).getByRole("button"));
    const order: string[] = [];
    for (let i = 0; i < 3; i++) {
      await user.tab();
      order.push(document.activeElement?.tagName.toLowerCase() ?? "");
    }
    expect(order).toEqual(["input", "textarea", "select"]);
  });

  it("draws the built-in widgets when the host supplies none", () => {
    render(<WidgetControls />);
    const region = screen.getByRole("region", { name: "Downstream widget controls" });
    expect(within(region).getByRole("button", { name: "Host action" })).toHaveClass("arras-btn");
    expect(within(region).getByLabelText("Host notes")).toBeInTheDocument();
  });
});
