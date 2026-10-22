// SPDX-License-Identifier: MIT OR Apache-2.0
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { ArrasConsole } from "../ArrasConsole";
import {
  Button,
  type ButtonProps,
  DesignSystemProvider,
  defaultDesignSystem,
  Mark,
  Notice,
  type NoticeProps,
  ROLE_TOKENS,
  Select,
  TextArea,
  TextField,
  useDesignSystem,
} from "../ds";
import { stageBrowser } from "./browserFake";

// ADR-029: the interface draws through a design-system seam. The built-in implementation renders every
// widget accessibly; a host's own implementation replaces it through the provider; neither touches the
// page the interface sits in.

describe("the built-in design system", () => {
  it("Button: variants, size, a default type of button, and a busy state that is marked and inert", async () => {
    const click = vi.fn();
    const { rerender } = render(
      <Button variant="secondary" size="sm" onClick={click}>
        Save
      </Button>,
    );
    const b = screen.getByRole("button", { name: "Save" });
    expect(b).toHaveAttribute("type", "button");
    expect(b).toHaveClass("arras-btn", "arras-btn--secondary", "arras-btn--sm");
    expect(b).not.toHaveAttribute("aria-busy");
    await userEvent.click(b);
    expect(click).toHaveBeenCalledTimes(1);
    rerender(
      <Button busy onClick={click} type="submit">
        Save
      </Button>,
    );
    const busy = screen.getByRole("button", { name: "Save" });
    expect(busy).toHaveAttribute("aria-busy", "true");
    expect(busy).toHaveAttribute("type", "submit");
    await userEvent.click(busy);
    expect(click).toHaveBeenCalledTimes(1);
  });

  it("Button: disabled, and a ref to the element", () => {
    const ref = createRef<HTMLButtonElement>();
    render(
      <Button ref={ref} disabled>
        Go
      </Button>,
    );
    expect(screen.getByRole("button", { name: "Go" })).toBeDisabled();
    expect(ref.current).toBe(screen.getByRole("button"));
  });

  it("TextField: the label names the input, the hint and the error describe it, and an error makes it invalid", async () => {
    const ref = createRef<HTMLInputElement>();
    const onChange = vi.fn();
    const { rerender } = render(
      <TextField ref={ref} label="Name" hint="As on the record" onChange={onChange} />,
    );
    const input = screen.getByLabelText("Name");
    expect(input).toBe(ref.current);
    expect(input).not.toHaveAttribute("aria-invalid");
    expect(input).toHaveAccessibleDescription("As on the record");
    await userEvent.type(input, "ab");
    expect(onChange).toHaveBeenCalledTimes(2);
    rerender(
      <TextField label="Name" hint="As on the record" error="Required" aria-describedby="extra" />,
    );
    const bad = screen.getByLabelText("Name");
    expect(bad).toHaveAttribute("aria-invalid", "true");
    expect(bad.getAttribute("aria-describedby")?.split(" ")).toHaveLength(3);
    expect(bad.getAttribute("aria-describedby")).toContain("extra");
    expect(screen.getByText("Required")).toBeVisible();
  });

  it("TextField: an explicit id is the label's target, and a field with no label takes an aria-label", () => {
    render(
      <>
        <TextField id="given" label="Key" />
        <TextField aria-label="Bare" />
      </>,
    );
    expect(screen.getByLabelText("Key")).toHaveAttribute("id", "given");
    expect(screen.getByRole("textbox", { name: "Bare" })).toBeInTheDocument();
  });

  it("TextArea: labelled, with rows and an error", () => {
    render(<TextArea label="Notes" rows={4} error="Too long" defaultValue="x" />);
    const area = screen.getByLabelText("Notes");
    expect(area.tagName).toBe("TEXTAREA");
    expect(area).toHaveAttribute("rows", "4");
    expect(area).toHaveAccessibleDescription("Too long");
    expect(area).toHaveAttribute("aria-invalid", "true");
  });

  it("Select: a labelled dropdown with its options, a placeholder, and change events", async () => {
    const onChange = vi.fn();
    render(
      <Select
        label="Module"
        placeholder="Choose…"
        value=""
        onChange={onChange}
        options={[
          { value: "a", label: "Alpha" },
          { value: "b", label: "Beta", disabled: true },
        ]}
      />,
    );
    const select = screen.getByRole("combobox", { name: "Module" });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Choose…",
      "Alpha",
      "Beta",
    ]);
    expect(screen.getByRole("option", { name: "Beta" })).toBeDisabled();
    await userEvent.selectOptions(select, "a");
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("Select: the label may be an element, and no placeholder means no empty entry", () => {
    render(
      <Select
        label={<span className="sr-only">Pick</span>}
        defaultValue="a"
        options={[{ value: "a", label: "Alpha" }]}
      />,
    );
    expect(screen.getByRole("combobox", { name: "Pick" })).toBeInTheDocument();
    expect(screen.getAllByRole("option")).toHaveLength(1);
  });

  it("Notice: a role by tone unless one is given, a title, and a glyph the screen reader skips", () => {
    render(
      <>
        <Notice tone="error">Broken</Notice>
        <Notice tone="warning" title="Careful">
          Be sure
        </Notice>
        <Notice>Plain</Notice>
        <Notice tone="success" role="note">
          Done
        </Notice>
      </>,
    );
    expect(screen.getByText("Broken").closest("[role]")).toHaveAttribute("role", "alert");
    expect(screen.getByText("Careful").closest("[role]")).toHaveAttribute("role", "alert");
    expect(screen.getByText("Plain").closest("[role]")).toHaveAttribute("role", "status");
    expect(screen.getByText("Done").closest("[role]")).toHaveAttribute("role", "note");
    expect(screen.getByText("Careful")).toHaveClass("arras-notice__title");
    for (const g of document.querySelectorAll(".arras-notice__glyph"))
      expect(g).toHaveAttribute("aria-hidden", "true");
  });

  it("Mark: an image with a name when labelled, hidden from assistive technology when not", () => {
    const { container, rerender } = render(<Mark label="Arras" />);
    expect(screen.getByRole("img", { name: "Arras" })).toBeInTheDocument();
    rerender(<Mark />);
    expect(screen.queryByRole("img")).toBeNull();
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });
});

describe("a host's own design system", () => {
  const HostButton = ({ children, variant }: ButtonProps) => (
    <button type="button" data-host-button={variant ?? "primary"}>
      {children}
    </button>
  );
  const HostNotice = ({ children }: NoticeProps) => <aside data-host-notice>{children}</aside>;

  it("is used by every widget it supplies, and the built-in completes the rest", () => {
    render(
      <DesignSystemProvider designSystem={{ Button: HostButton, Notice: HostNotice }}>
        <Button variant="secondary">Mine</Button>
        <Notice>Heads up</Notice>
        <TextField label="Built in" />
      </DesignSystemProvider>,
    );
    expect(screen.getByRole("button", { name: "Mine" })).toHaveAttribute(
      "data-host-button",
      "secondary",
    );
    expect(screen.getByText("Heads up").closest("[data-host-notice]")).not.toBeNull();
    expect(screen.getByLabelText("Built in")).toHaveClass("arras-field__input");
    expect(document.querySelector(".arras-btn")).toBeNull();
  });

  it("is used by the interface's own surfaces, not only by direct calls", async () => {
    const fake = stageBrowser();
    fake.mods = fake.mods.slice(0, 1);
    window.location.hash = "";
    render(
      <DesignSystemProvider designSystem={{ Button: HostButton }}>
        <ArrasConsole />
      </DesignSystemProvider>,
    );
    await screen.findByRole("navigation", {}, { timeout: 3000 });
    expect(document.querySelectorAll("[data-host-button]").length).toBeGreaterThan(0);
    expect(document.querySelector(".arras-btn")).toBeNull();
    window.location.hash = "";
  });

  it("an inner provider overrides an outer one, and a provider with none leaves the outer in place", () => {
    const Inner = ({ children }: ButtonProps) => (
      <button type="button" data-inner>
        {children}
      </button>
    );
    render(
      <DesignSystemProvider designSystem={{ Button: HostButton }}>
        <DesignSystemProvider>
          <Button>Outer</Button>
        </DesignSystemProvider>
        <DesignSystemProvider designSystem={{ Button: Inner }}>
          <Button>Inner</Button>
        </DesignSystemProvider>
      </DesignSystemProvider>,
    );
    expect(screen.getByRole("button", { name: "Outer" })).toHaveAttribute("data-host-button");
    expect(screen.getByRole("button", { name: "Inner" })).toHaveAttribute("data-inner");
  });

  it("useDesignSystem returns the built-in one with no provider", () => {
    let seen: unknown;
    function Probe() {
      seen = useDesignSystem();
      return null;
    }
    render(<Probe />);
    expect(seen).toBe(defaultDesignSystem);
  });
});

describe("the seam has no side effects on the host document", () => {
  it("rendering every widget changes no attribute of html or body, adds nothing to head, stores nothing", () => {
    const html = document.documentElement.outerHTML.replace(/<body[\s\S]*<\/body>/, "");
    const seen: MutationRecord[] = [];
    const watch = new MutationObserver((r) => seen.push(...r));
    watch.observe(document.documentElement, { attributes: true });
    watch.observe(document.head, { childList: true, subtree: true });
    watch.observe(document.body, { attributes: true });
    const { unmount } = render(
      <DesignSystemProvider>
        <Button busy>Go</Button>
        <TextField label="a" error="e" />
        <TextArea label="b" />
        <Select label="c" options={[]} />
        <Notice tone="error">n</Notice>
        <Mark label="m" />
      </DesignSystemProvider>,
    );
    unmount();
    watch.takeRecords();
    watch.disconnect();
    expect(seen).toEqual([]);
    expect(document.documentElement.outerHTML.replace(/<body[\s\S]*<\/body>/, "")).toBe(html);
    expect(document.documentElement.style.colorScheme).toBe("");
    expect(window.localStorage.length + window.sessionStorage.length).toBe(0);
  });
});

describe("the role tokens", () => {
  const SRC = join(import.meta.dirname, "..");
  const css = (dir: string): string[] =>
    readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
      const p = join(dir, e.name);
      if (e.isDirectory()) return e.name === "test" ? [] : css(p);
      return e.name.endsWith(".css") ? [readFileSync(p, "utf8")] : [];
    });
  const all = css(SRC).join("\n");
  const styles = readFileSync(join(SRC, "styles.css"), "utf8");

  it("the stylesheet reads exactly the contract's tokens, each with a built-in value", () => {
    const used = new Set([...all.matchAll(/var\(\s*(--arras-[\w-]+)/g)].map((m) => m[1]));
    expect([...used].sort()).toEqual([...ROLE_TOKENS].sort());
    for (const token of ROLE_TOKENS)
      expect(styles, token).toMatch(new RegExp(`var\\(\\s*${token},\\s*[^)\\s]`));
  });

  it("the colour tokens have a light and a dark built-in value", () => {
    const colours = ROLE_TOKENS.filter((t) => t.startsWith("--arras-color-"));
    expect(colours).toHaveLength(8);
    for (const token of colours) {
      const values = [...styles.matchAll(new RegExp(`var\\(\\s*${token},\\s*([^)]+)\\)`, "g"))].map(
        (m) => m[1],
      );
      expect(new Set(values).size, `${token}: ${values}`).toBeGreaterThanOrEqual(2);
    }
  });

  it("the built-in widgets' stylesheet defines no colour of its own", () => {
    const widgets = readFileSync(join(SRC, "ds/default.css"), "utf8");
    expect(widgets).not.toMatch(/#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(/i);
  });
});
