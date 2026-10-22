// SPDX-License-Identifier: MIT OR Apache-2.0
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ArrasProvider } from "../api/context";
import type { ActionInfo, InputSpec } from "../api/types";
import { ActionForm } from "../areas/ActionForm";
import { EntityPanel } from "../areas/EntityPanel";
import type { Entry } from "../areas/entity";
import { requestInputFocus, takeInputFocus } from "../lib/formFocus";
import { catalog, decl, err, type FakeApi, seedCatalog, stage } from "./fake";
import { qc, renderPart } from "./render";

let api: FakeApi;
beforeEach(() => {
  window.location.hash = "";
  api = stage();
  seedCatalog(api);
});

const sol: Entry = { module: "catalog", type: "catalog.Solution", key: "sol-1" };

const refIn = (name: string): InputSpec => ({
  name,
  type: "Solution",
  kind: "ref",
  cardinality: "one",
});
const str = (name: string): InputSpec => ({
  name,
  type: "string",
  kind: "scalar",
  cardinality: "one",
});

const updateSolution = (name: string, props: Record<string, string>): ActionInfo => ({
  name: `catalog.${name}`,
  description: `${name} description`,
  inputSpecs: [refIn("solution"), ...Object.values(props).map(str)],
  preconditions: [],
  effects: [
    decl({
      op: "update",
      ref_type: "Solution",
      key: { name: "solution" },
      properties: Object.fromEntries(Object.entries(props).map(([p, i]) => [p, { name: i }])),
    }),
  ],
});

const linkSolution: ActionInfo = {
  name: "catalog.LinkSolution",
  description: "Link",
  inputSpecs: [refIn("solution"), { ...refIn("useCase"), type: "UseCase" }],
  preconditions: [],
  effects: [
    decl({
      op: "link",
      type: "addresses",
      source: { name: "solution" },
      target: { name: "useCase" },
    }),
  ],
};

interface Spies {
  onAction: ReturnType<typeof vi.fn>;
  onClose: ReturnType<typeof vi.fn>;
}

function panel(over: Partial<Parameters<typeof EntityPanel>[0]> = {}): Spies {
  const spies = { onAction: vi.fn(), onClose: vi.fn() };
  renderPart(
    <EntityPanel
      module="catalog"
      trail={[sol]}
      onTrail={() => undefined}
      onClose={spies.onClose}
      onAction={spies.onAction}
      onHistory={() => undefined}
      onGraph={() => undefined}
      {...over}
    />,
  );
  return spies;
}

const open = async () => within(await screen.findByTestId("entity-panel"));

describe("Entity panel: the action bar", () => {
  it("stands above the properties, with the declared update as a primary button, History and Graph", async () => {
    const { onAction } = panel();
    const p = await open();
    await p.findByTestId("prop-name");
    const bar = p.getByRole("toolbar");
    const props = p.getByText("Properties");
    expect(bar.compareDocumentPosition(props) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(p.queryByText("Do")).toBeNull();
    expect(within(bar).getByRole("button", { name: "History" })).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: "Show in graph" })).toBeInTheDocument();
    await userEvent.click(within(bar).getByRole("button", { name: "CorrectSolution…" }));
    expect(onAction).toHaveBeenCalledWith("catalog.CorrectSolution", { solution: "sol-1" });
  });

  it("puts at most three updates in the bar, the others in an Actions menu", async () => {
    api.modules = [
      catalog({
        actions: [
          updateSolution("CorrectSolution", { name: "n", coverageLevel: "l" }),
          updateSolution("RenameSolution", { name: "name" }),
          updateSolution("SetLevel", { coverageLevel: "level" }),
          updateSolution("SetSummary", { summary: "s" }),
          linkSolution,
        ],
      }),
    ];
    const { onAction } = panel();
    const bar = within(await screen.findByRole("toolbar"));
    const labels = bar.getAllByRole("button").map((b) => b.textContent);
    expect(labels.slice(0, 3)).toEqual(["RenameSolution…", "SetLevel…", "SetSummary…"]);
    const menu = bar.getByRole("button", { name: /^Actions/ });
    expect(menu).toHaveAttribute("aria-haspopup", "menu");
    expect(menu).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(menu);
    expect(menu).toHaveAttribute("aria-expanded", "true");
    const items = screen.getAllByRole("menuitem").map((i) => i.textContent);
    expect(items).toEqual(["CorrectSolution…", "LinkSolution…"]);
    await userEvent.click(screen.getByRole("menuitem", { name: "LinkSolution…" }));
    expect(onAction).toHaveBeenCalledWith("catalog.LinkSolution", { solution: "sol-1" });
    expect(screen.queryByRole("menu")).toBeNull();
  });

  describe("the Actions menu's keyboard", () => {
    beforeEach(() => {
      api.modules = [
        catalog({
          actions: [
            updateSolution("RenameSolution", { name: "name" }),
            updateSolution("SetLevel", { coverageLevel: "level" }),
            updateSolution("SetSummary", { summary: "s" }),
            updateSolution("CorrectSolution", { name: "n", coverageLevel: "l" }),
            linkSolution,
          ],
        }),
      ];
    });

    it("opens with ArrowDown on the first item; arrows, Home and End move; Escape closes only the menu", async () => {
      const user = userEvent.setup();
      const { onClose } = panel();
      const trigger = await screen.findByRole("button", { name: /^Actions/ });
      trigger.focus();
      await user.keyboard("{ArrowDown}");
      const [first, second] = screen.getAllByRole("menuitem");
      expect(first).toHaveFocus();
      await user.keyboard("{ArrowDown}");
      expect(second).toHaveFocus();
      await user.keyboard("{ArrowDown}");
      expect(first).toHaveFocus(); // wraps
      await user.keyboard("{End}");
      expect(screen.getAllByRole("menuitem").at(-1)).toHaveFocus();
      await user.keyboard("{Home}");
      expect(first).toHaveFocus();
      await user.keyboard("{ArrowUp}");
      expect(screen.getAllByRole("menuitem").at(-1)).toHaveFocus();
      await user.keyboard("{Escape}");
      expect(screen.queryByRole("menu")).toBeNull();
      expect(trigger).toHaveFocus();
      expect(onClose).not.toHaveBeenCalled();
    });

    it("chooses an item with Enter", async () => {
      const user = userEvent.setup();
      const { onAction } = panel();
      const trigger = await screen.findByRole("button", { name: /^Actions/ });
      trigger.focus();
      await user.keyboard("{Enter}");
      await user.keyboard("{ArrowDown}{Enter}");
      expect(onAction).toHaveBeenCalledWith("catalog.LinkSolution", { solution: "sol-1" });
    });
  });
});

describe("Entity panel: property to action hints", () => {
  it("offers Change beside a property a declared action updates, and none beside others", async () => {
    const { onAction } = panel();
    const p = await open();
    await p.findByTestId("prop-coverageLevel");
    await userEvent.click(p.getByRole("button", { name: "Change coverageLevel" }));
    expect(onAction).toHaveBeenCalledWith("catalog.CorrectSolution", { solution: "sol-1" });
    expect(p.queryByRole("button", { name: "Change name" })).toBeNull();
  });

  it("asks the form to focus the input that carries the property", async () => {
    const { onAction } = panel();
    const p = await open();
    await userEvent.click(await p.findByRole("button", { name: "Change coverageLevel" }));
    expect(onAction).toHaveBeenCalled();
    expect(takeInputFocus("catalog.CorrectSolution")).toBe("level");
  });

  it("the form focuses the requested input when it opens", async () => {
    requestInputFocus("catalog.CorrectSolution", "level");
    renderPart(
      <ActionForm
        module="catalog"
        action="catalog.CorrectSolution"
        prefill={{ solution: "sol-1" }}
      />,
    );
    const input = await screen.findByLabelText(/^level/);
    await waitFor(() => expect(input).toHaveFocus());
  });

  it("shows no Change control without a way to open an action", async () => {
    panel({ onAction: undefined });
    const p = await open();
    await p.findByTestId("prop-name");
    expect(p.queryByRole("button", { name: /^Change / })).toBeNull();
  });
});

describe("Entity panel: relationship chips", () => {
  const chip = async () => {
    const p = await open();
    return within(await p.findByTestId("rels-addresses"));
  };

  it("shows the key alone while the name is loading", async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((r) => {
      release = r;
    });
    api.on(async (r) => {
      if (/t0:/.test(r.body?.query ?? "")) await gate;
      return undefined;
    });
    panel();
    const rels = await chip();
    expect(await rels.findByRole("button", { name: "uc-1" })).toBeInTheDocument();
    release();
    expect(await rels.findByRole("button", { name: /Use case 1/ })).toBeInTheDocument();
  });

  it("shows the target's name with its key beside it, from one bounded read that selects no target", async () => {
    panel();
    const rels = await chip();
    const b = await rels.findByRole("button", { name: /Use case 1/ });
    expect(b).toHaveTextContent("Use case 1");
    expect(b).toHaveTextContent("uc-1");
    const reads = api.log.filter((r) => /t0:/.test(r.body?.query ?? ""));
    expect(reads).toHaveLength(1);
    expect(reads[0]?.body.query).toContain("useCase(key: $k0) { name }");
    expect(reads[0]?.body.query).not.toMatch(/target \{/);
  });

  it("falls back to the key when the read fails, with no error shown", async () => {
    api.on((r) =>
      /t0:/.test(r.body?.query ?? "") ? err(500, { type: "Error", message: "boom" }) : undefined,
    );
    panel();
    const rels = await chip();
    await waitFor(() => expect(api.log.some((r) => /t0:/.test(r.body?.query ?? ""))).toBe(true));
    expect(await rels.findByRole("button", { name: "uc-1" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("falls back to the key for a target that has no name", async () => {
    api.rows["catalog.UseCase"] = [];
    panel();
    const rels = await chip();
    await waitFor(() => expect(api.log.some((r) => /t0:/.test(r.body?.query ?? ""))).toBe(true));
    expect(await rels.findByRole("button", { name: "uc-1" })).toBeInTheDocument();
  });
});

function Harness({ onClosed }: { onClosed: () => void }) {
  const [shown, setShown] = useState(true);
  return (
    <ArrasProvider queryClient={qc()}>
      <button type="button" data-testid="row">
        row
      </button>
      {shown && (
        <EntityPanel
          module="catalog"
          trail={[sol]}
          onTrail={() => undefined}
          onClose={() => {
            setShown(false);
            onClosed();
          }}
        />
      )}
    </ArrasProvider>
  );
}

describe("Entity panel: keyboard and focus", () => {
  it("takes the focus in its heading and gives it back on Escape", async () => {
    const user = userEvent.setup();
    const onClosed = vi.fn();
    // The row has the focus first, as when Enter opens it.
    const row = document.createElement("button");
    document.body.appendChild(row);
    row.focus();
    render(<Harness onClosed={onClosed} />);
    const heading = await screen.findByRole("heading", { name: "sol-1" });
    await waitFor(() => expect(heading).toHaveFocus());
    expect(heading).toHaveAttribute("tabindex", "-1");
    await user.keyboard("{Escape}");
    expect(onClosed).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("entity-panel")).toBeNull();
    expect(row).toHaveFocus();
    row.remove();
  });

  it("does not trap the focus: Tab leaves the heading for the controls", async () => {
    const user = userEvent.setup();
    panel();
    const heading = await screen.findByRole("heading", { name: "sol-1" });
    await waitFor(() => expect(heading).toHaveFocus());
    await user.tab();
    expect(heading).not.toHaveFocus();
    expect(screen.getByTestId("entity-panel")).toContainElement(
      document.activeElement as HTMLElement,
    );
  });
});
