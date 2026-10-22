// SPDX-License-Identifier: MIT OR Apache-2.0
// The kit's chrome-free pieces (SD-013): fields for every input kind, errors tied to their field,
// the RefInput slot, one sentence per effect, and the receipt's links and focus.

import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Effect, InputSpec } from "../api/types";
import {
  ActionFields,
  EffectsSummary,
  generalViolations,
  KeyRefInput,
  ReceiptSummary,
  type RefInputProps,
  summarizeEffects,
} from "../kit";
import { requestInputFocus } from "../lib/formFocus";
import { receipt } from "./fake";

const spec = (
  name: string,
  type: string,
  kind: InputSpec["kind"] = "scalar",
  cardinality: InputSpec["cardinality"] = "one",
): InputSpec => ({ name, type, kind, cardinality });

const SPECS = [
  spec("title", "string"),
  spec("count", "integer", "scalar", "optional"),
  spec("active", "boolean", "scalar", "optional"),
  spec("owner", "Person", "ref"),
  spec("tags", "string", "scalar", "many"),
  spec("meta", "Meta", "record", "optional"),
];

function fields(over: Partial<Parameters<typeof ActionFields>[0]> = {}) {
  const onChange = vi.fn();
  render(
    <ActionFields
      action="catalog.Do"
      module="catalog"
      specs={SPECS}
      values={{}}
      onChange={onChange}
      {...over}
    />,
  );
  return onChange;
}

describe("ActionFields", () => {
  it("renders a control for every input kind", () => {
    fields();
    expect(screen.getByLabelText(/title/)).toHaveProperty("tagName", "INPUT");
    expect(screen.getByLabelText(/count/)).toHaveProperty("inputMode", "numeric");
    expect(screen.getByLabelText(/active/)).toHaveProperty("tagName", "SELECT");
    expect(screen.getByLabelText(/owner/)).toHaveProperty("tagName", "INPUT");
    expect(screen.getByLabelText(/tags/)).toHaveProperty("tagName", "TEXTAREA");
    expect(screen.getByLabelText(/meta/)).toHaveProperty("tagName", "TEXTAREA");
    expect(screen.getByText("one value per line")).toBeTruthy();
  });

  it("marks required inputs and only those", () => {
    fields();
    expect(screen.getByLabelText(/title/).getAttribute("aria-required")).toBe("true");
    expect(screen.getByLabelText(/owner/).getAttribute("aria-required")).toBe("true");
    expect(screen.getByLabelText(/count/).getAttribute("aria-required")).toBeNull();
  });

  it("reports edits by input name, a list as the text of its lines", () => {
    const onChange = fields({ values: { tags: ["a", "b"] } });
    expect((screen.getByLabelText(/tags/) as HTMLTextAreaElement).value).toBe("a\nb");
    fireEvent.change(screen.getByLabelText(/title/), { target: { value: "x" } });
    fireEvent.change(screen.getByLabelText(/active/), { target: { value: "true" } });
    expect(onChange).toHaveBeenCalledWith("title", "x");
    expect(onChange).toHaveBeenCalledWith("active", "true");
  });

  it("a boolean offers true and false and an unset choice", () => {
    fields();
    const options = [...screen.getByLabelText(/active/).querySelectorAll("option")].map(
      (o) => o.textContent,
    );
    expect(options).toEqual(expect.arrayContaining(["true", "false", "(unset)"]));
  });

  it("shows the client's error at its field, tied by aria-describedby", () => {
    fields({ errors: { count: "an integer", title: "required" } });
    const count = screen.getByLabelText(/count/);
    expect(count.getAttribute("aria-invalid")).toBe("true");
    const described = count.getAttribute("aria-describedby") ?? "";
    const text = described
      .split(" ")
      .map((id) => document.getElementById(id)?.textContent)
      .join(" ");
    expect(text).toContain("Expected an integer");
    expect(screen.getByText(/Expected a value \(required\)/)).toBeTruthy();
  });

  it("shows server violations at the field their path names, and by index path", () => {
    fields({
      violations: [
        { path: "inputs.title", code: "too_long", message: "too long" },
        { path: "inputs.tags[2]", code: "bad_tag", message: "bad tag" },
        { path: "items[3].inputs.count", code: "range", message: "out of range" },
        { path: "effects[0]", code: "other", message: "elsewhere" },
      ],
    });
    const described = (label: RegExp) =>
      (screen.getByLabelText(label).getAttribute("aria-describedby") ?? "")
        .split(" ")
        .map((id) => document.getElementById(id)?.textContent ?? "")
        .join(" ");
    expect(described(/title/)).toContain("too long (too_long)");
    expect(described(/tags/)).toContain("bad tag (bad_tag)");
    expect(described(/count/)).toContain("out of range (range)");
    expect(described(/owner/)).not.toContain("elsewhere");
    expect(screen.queryByText(/elsewhere/)).toBeNull();
  });

  it("leaves the violations with no field path to the caller, which reads them", () => {
    const violations = [
      { path: "inputs.title", code: "too_long", message: "too long" },
      { path: "effects[0]", code: "other", message: "elsewhere" },
      { path: "", code: "bare", message: "no path" },
    ];
    expect(generalViolations(violations)).toEqual([
      "effects[0]: elsewhere (other)",
      "no path (bare)",
    ]);
  });

  it("shows the JSON.parse error of a record at its field", () => {
    fields({ values: { meta: "{ nope" } });
    const meta = screen.getByLabelText(/meta/);
    expect(meta.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByText(/Not valid JSON/)).toBeTruthy();
  });

  it("accepts a record that parses", () => {
    fields({ values: { meta: '{"a": 1}' } });
    expect(screen.getByLabelText(/meta/).getAttribute("aria-invalid")).not.toBe("true");
  });

  it("asks for a reference through the slot it is given", () => {
    const Picker = ({ spec: s, module, type, value, onChange }: RefInputProps) => (
      <button type="button" data-testid={`pick-${s.name}`} onClick={() => onChange("p-1")}>
        pick {type} in {module} ({value || "none"})
      </button>
    );
    const onChange = fields({ RefInput: Picker });
    fireEvent.click(screen.getByTestId("pick-owner"));
    expect(onChange).toHaveBeenCalledWith("owner", "p-1");
    expect(screen.getByText("pick Person in catalog (none)")).toBeTruthy();
    expect(screen.queryByLabelText(/owner/)).toBeNull();
  });

  it("the default slot is the key field", () => {
    const onChange = vi.fn();
    render(
      <KeyRefInput
        spec={spec("owner", "catalog.Person", "ref")}
        value=""
        onChange={onChange}
        module="catalog"
        type="catalog.Person"
      />,
    );
    fireEvent.change(screen.getByLabelText(/owner/), { target: { value: "p-9" } });
    expect(onChange).toHaveBeenCalledWith("p-9");
    expect(screen.getByText("the key of a Person")).toBeTruthy();
  });

  it("focuses the input a pending request names, once", () => {
    requestInputFocus("catalog.Do", "count");
    fields();
    expect(document.activeElement).toBe(screen.getByLabelText(/count/));
  });
});

const sol = { type: "catalog.Solution", key: "sol-1" };
const uc = { type: "catalog.UseCase", key: "uc-2" };
const EFFECTS: Effect[] = [
  { kind: "create", ref: sol, properties: { name: "Alpha", rank: 2 } },
  { kind: "create", ref: { ...sol, key: "", generated: true }, properties: {} },
  { kind: "update", ref: sol, set: { name: "Beta" }, unset: ["summary"] },
  { kind: "update", ref: sol, set: {}, unset: ["a", "b"] },
  { kind: "update", ref: sol, set: { rank: 3 }, unset: [] },
  { kind: "update", ref: sol, set: {}, unset: [] },
  { kind: "link", relationship: "addresses", source: sol, target: uc },
  { kind: "unlink", relationship: "addresses", source: sol, target: uc },
  { kind: "delete", ref: uc },
];

describe("summarizeEffects", () => {
  it("is one sentence per effect, naming the type and the key", () => {
    expect(summarizeEffects(EFFECTS)).toEqual([
      'Create Solution sol-1 with name "Alpha", rank 2.',
      "Create a new Solution.",
      'Update Solution sol-1: set name to "Beta"; unset summary.',
      "Update Solution sol-1: unset a, b.",
      "Update Solution sol-1: set rank to 3.",
      "Update Solution sol-1: no property changes.",
      "Link addresses from Solution sol-1 to UseCase uc-2.",
      "Unlink addresses from Solution sol-1 to UseCase uc-2.",
      "Delete UseCase uc-2.",
    ]);
  });

  it("is empty for no effects", () => {
    expect(summarizeEffects([])).toEqual([]);
  });
});

describe("EffectsSummary", () => {
  it("states its status and lists a sentence per effect", () => {
    const { rerender } = render(<EffectsSummary effects={EFFECTS.slice(0, 2)} status="preview" />);
    expect(screen.getByTestId("effects-status").textContent).toMatch(/Preview/);
    expect(screen.getAllByTestId("effect-sentence")).toHaveLength(2);
    rerender(<EffectsSummary effects={EFFECTS.slice(0, 2)} status="stale" />);
    expect(screen.getByTestId("effects-status").textContent).toMatch(/Out of date/);
    rerender(<EffectsSummary effects={EFFECTS.slice(0, 2)} status="applied" />);
    expect(screen.getByTestId("effects-status").textContent).toMatch(/Applied/);
  });

  it("warns before a delete and says when nothing would change", () => {
    const { rerender } = render(
      <EffectsSummary effects={[EFFECTS[8] as Effect]} status="preview" />,
    );
    expect(screen.getByText(/cannot be undone/)).toBeTruthy();
    rerender(<EffectsSummary effects={[]} status="preview" />);
    expect(screen.getByText(/nothing would change/)).toBeTruthy();
  });
});

describe("ReceiptSummary", () => {
  const r = receipt({
    action: "catalog.Do",
    refs: [
      { type: "catalog.Solution", key: "sol-1", version: 1 },
      { type: "catalog.UseCase", key: "uc-2", version: 4 },
      { type: "catalog.Person", key: "p-3", version: 2 },
    ],
    group: "g-77",
  });
  const effects: Effect[] = [
    { kind: "create", ref: sol, properties: {} },
    { kind: "delete", ref: uc },
  ];

  it("lists created, changed and deleted refs with links from the slot", () => {
    const go = vi.fn();
    const linkFor = vi.fn((x: { type: string; key: string }) =>
      x.key === "sol-1" ? { href: "#/solutions/sol-1" } : { go },
    );
    render(<ReceiptSummary receipt={r} effects={effects} linkFor={linkFor} />);
    expect(screen.getByTestId("receipt-created").textContent).toContain("Solution sol-1");
    expect(screen.getByTestId("receipt-changed").textContent).toContain("Person p-3");
    expect(screen.getByTestId("receipt-deleted").textContent).toContain("UseCase uc-2");
    expect(screen.getByRole("link", { name: "Solution sol-1" }).getAttribute("href")).toBe(
      "#/solutions/sol-1",
    );
    const button = screen.getByRole("button", { name: "Person p-3" });
    expect(button.hasAttribute("href")).toBe(false);
    fireEvent.click(button);
    expect(go).toHaveBeenCalledTimes(1);
    // a deleted entity is not offered as a link
    expect(screen.queryByRole("link", { name: "UseCase uc-2" })).toBeNull();
    expect(linkFor).not.toHaveBeenCalledWith(expect.objectContaining({ key: "uc-2" }));
    expect(screen.getByTestId("receipt-group").textContent).toBe("g-77");
  });

  it("files a ref with a generated key under Created when it is the type's one create", () => {
    const generated = receipt({
      refs: [
        { type: "catalog.Solution", key: "sol-new", version: 1 },
        { type: "catalog.UseCase", key: "uc-2", version: 4 },
      ],
    });
    const fx: Effect[] = [
      { kind: "create", ref: { ...sol, key: "", generated: true }, properties: {} },
      { kind: "update", ref: uc, set: {}, unset: [] },
    ];
    render(<ReceiptSummary receipt={generated} effects={fx} linkFor={() => ({})} />);
    expect(screen.getByTestId("receipt-created").textContent).toContain("Solution sol-new");
    expect(screen.getByTestId("receipt-changed").textContent).toContain("UseCase uc-2");
  });

  it("keeps a same-type update Changed beside a generated create", () => {
    const mixed = receipt({
      refs: [
        { type: "catalog.Solution", key: "sol-old", version: 3 },
        { type: "catalog.Solution", key: "sol-new", version: 1 },
      ],
    });
    const fx: Effect[] = [
      { kind: "create", ref: { ...sol, key: "", generated: true }, properties: {} },
      { kind: "update", ref: { ...sol, key: "sol-old" }, set: {}, unset: [] },
    ];
    render(<ReceiptSummary receipt={mixed} effects={fx} linkFor={() => ({})} />);
    expect(screen.getByTestId("receipt-created").textContent).toContain("Solution sol-new");
    expect(screen.getByTestId("receipt-created").textContent).not.toContain("sol-old");
    expect(screen.getByTestId("receipt-changed").textContent).toContain("Solution sol-old");
  });

  it("files an unmatched ref as Changed when its type has two creates or none", () => {
    const two: Effect[] = [
      { kind: "create", ref: { ...sol, key: "a" }, properties: {} },
      { kind: "create", ref: { ...sol, key: "b" }, properties: {} },
    ];
    const { unmount } = render(
      <ReceiptSummary receipt={receipt()} effects={two} linkFor={() => ({})} />,
    );
    expect(screen.queryByTestId("receipt-created")).toBeNull();
    expect(screen.getByTestId("receipt-changed").textContent).toContain("Solution sol-1");
    unmount();
    render(<ReceiptSummary receipt={receipt()} effects={[]} linkFor={() => ({})} />);
    expect(screen.getByTestId("receipt-changed")).toBeTruthy();
  });

  it("files a keyed create matched by one ref Created and an unmatched same-type ref Changed", () => {
    const keyed = receipt({
      refs: [
        { type: "catalog.Solution", key: "sol-a", version: 1 },
        { type: "catalog.Solution", key: "sol-b", version: 5 },
      ],
    });
    const fx: Effect[] = [{ kind: "create", ref: { ...sol, key: "sol-a" }, properties: {} }];
    render(<ReceiptSummary receipt={keyed} effects={fx} linkFor={() => ({})} />);
    expect(screen.getByTestId("receipt-created").textContent).toContain("Solution sol-a");
    expect(screen.getByTestId("receipt-created").textContent).not.toContain("sol-b");
    expect(screen.getByTestId("receipt-changed").textContent).toContain("Solution sol-b");
  });

  it("spends a create at most once: two unmatched same-type refs and one unspent create are both Changed", () => {
    const two = receipt({
      refs: [
        { type: "catalog.Solution", key: "sol-x", version: 1 },
        { type: "catalog.Solution", key: "sol-y", version: 1 },
      ],
    });
    const fx: Effect[] = [
      { kind: "create", ref: { ...sol, key: "", generated: true }, properties: {} },
    ];
    render(<ReceiptSummary receipt={two} effects={fx} linkFor={() => ({})} />);
    // Which of the two the create made is unknowable, so neither is filed Created.
    expect(screen.queryByTestId("receipt-created")).toBeNull();
    const changed = screen.getByTestId("receipt-changed").textContent ?? "";
    expect(changed).toContain("Solution sol-x");
    expect(changed).toContain("Solution sol-y");
    expect(screen.getAllByTestId("receipt-ref")).toHaveLength(2);
  });

  it("files an unmatched ref Changed when two creates of its type are unspent", () => {
    const fx: Effect[] = [
      { kind: "create", ref: { ...sol, key: "", generated: true }, properties: {} },
      { kind: "create", ref: { ...sol, key: "", generated: true }, properties: {} },
    ];
    render(<ReceiptSummary receipt={receipt()} effects={fx} linkFor={() => ({})} />);
    expect(screen.queryByTestId("receipt-created")).toBeNull();
    expect(screen.getByTestId("receipt-changed").textContent).toContain("Solution sol-1");
  });

  it("files an update ref with no effects as Changed", () => {
    const upd = receipt({ refs: [{ type: "catalog.Solution", key: "sol-1", version: 2 }] });
    render(<ReceiptSummary receipt={upd} linkFor={() => ({})} />);
    expect(screen.queryByTestId("receipt-created")).toBeNull();
    expect(screen.getByTestId("receipt-changed").textContent).toContain("Solution sol-1");
  });

  it("renders an href link as an anchor whose plain click calls go", () => {
    const go = vi.fn();
    render(
      <ReceiptSummary receipt={receipt()} linkFor={() => ({ href: "#/solutions/sol-1", go })} />,
    );
    const link = screen.getByRole("link", { name: "Solution sol-1" });
    expect(link.getAttribute("href")).toBe("#/solutions/sol-1");
    fireEvent.click(link);
    expect(go).toHaveBeenCalledTimes(1);
  });

  it("renders a go-only link as a button, never an href-less anchor or href=#", () => {
    const go = vi.fn();
    const { container } = render(<ReceiptSummary receipt={r} linkFor={() => ({ go })} />);
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(screen.getAllByRole("button")).toHaveLength(3);
    expect(container.querySelector('[href="#"]')).toBeNull();
    for (const b of screen.getAllByRole("button")) expect(b.getAttribute("type")).toBe("button");
  });

  it("shows a ref the slot has no link for as text", () => {
    render(<ReceiptSummary receipt={r} linkFor={() => ({})} />);
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(screen.getAllByTestId("receipt-ref")).toHaveLength(3);
  });

  it("is focusable, and takes focus when asked", () => {
    render(<ReceiptSummary receipt={r} linkFor={() => ({})} focusOnMount />);
    const box = screen.getByTestId("receipt-summary");
    expect(box.getAttribute("tabindex")).toBe("-1");
    expect(document.activeElement).toBe(box);
    expect(box.getAttribute("aria-labelledby")).toBeTruthy();
    expect(box.className).not.toContain("outline-none");
  });
});

// Tailwind palette classes (`text-red-600`, `bg-[#fff]`) bypass the library's colour variables. The
// exceptions are listed by file and exact class; there are none.
const PALETTE_EXCEPTIONS: Record<string, string[]> = {};
const HUES =
  "slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose";
const PALETTE = new RegExp(
  `(?<![\\w-])(?:bg|text|border|ring|fill|stroke|outline|divide|from|via|to)-(?:(?:${HUES})-\\d{2,3}|\\[(?:#|rgb|hsl)[^\\]]*\\])`,
  "g",
);
const paletteClasses = (text: string): string[] => text.match(PALETTE) ?? [];

describe("the pieces' markup", () => {
  it("no piece sets a colour inline", () => {
    const dir = join(import.meta.dirname, "..", "kit");
    const sources = readdirSync(dir).filter((f) => /\.tsx$/.test(f));
    expect(sources.length).toBeGreaterThanOrEqual(4);
    for (const f of sources) {
      const text = readFileSync(join(dir, f), "utf8");
      expect(text, f).not.toMatch(/style=\{\{/);
      expect(text, f).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/);
    }
  });

  it("no class names a palette hue and shade or an arbitrary colour in kit/ or browser/", () => {
    for (const area of ["kit", "browser"]) {
      const dir = join(import.meta.dirname, "..", area);
      for (const f of readdirSync(dir).filter((n) => /\.tsx$/.test(n))) {
        const text = readFileSync(join(dir, f), "utf8");
        const allowed = PALETTE_EXCEPTIONS[`${area}/${f}`] ?? [];
        const found = paletteClasses(text).filter((c) => !allowed.includes(c));
        expect(found, `${area}/${f}`).toEqual([]);
      }
    }
  });

  it("negative control: the palette check finds each form it is meant to catch", () => {
    const planted =
      '<p className="text-red-600 bg-[#fff] border-slate-200 hover:bg-blue-50/50 ring-1">';
    expect(paletteClasses(planted)).toEqual([
      "text-red-600",
      "bg-[#fff]",
      "border-slate-200",
      "bg-blue-50",
    ]);
    const fine = '<p className="text-sm bg-transparent border-0 text-[inherit]">';
    expect(paletteClasses(fine)).toEqual([]);
  });

  it("rendered output carries no inline colour", () => {
    const { container } = render(
      <div>
        <ActionFields
          action="a"
          module="m"
          specs={SPECS}
          values={{}}
          errors={{ title: "required" }}
          onChange={() => {}}
        />
        <EffectsSummary effects={EFFECTS} status="preview" />
        <ReceiptSummary receipt={receipt()} linkFor={() => ({ href: "#" })} />
      </div>,
    );
    for (const el of container.querySelectorAll("[style]")) {
      expect(el.getAttribute("style") ?? "", el.outerHTML).not.toMatch(/color|background|border/i);
    }
  });
});
