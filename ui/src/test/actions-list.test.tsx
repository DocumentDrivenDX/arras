// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ActionInfo } from "../api/types";
import { ActionsArea } from "../areas/ActionsArea";
import { catalog, decl, type FakeApi, seedCatalog, stage } from "./fake";
import { renderPart } from "./render";

let api: FakeApi;
beforeEach(() => {
  window.location.hash = "";
  api = stage();
  seedCatalog(api);
  const ref = (name: string, type: string) =>
    ({ name, type, kind: "ref", cardinality: "one" }) as const;
  const text = (name: string) =>
    ({ name, type: "string", kind: "scalar", cardinality: "one" }) as const;
  const upd = (name: string, type: string, prop: string): ActionInfo => ({
    name: `catalog.${name}`,
    description: `Change the ${prop} of a ${type}`,
    inputSpecs: [ref("target", type), text("value")],
    preconditions: [],
    effects: [
      decl({
        op: "update",
        ref_type: type,
        key: { name: "target" },
        properties: { [prop]: { name: "value" } },
      }),
    ],
  });
  api.modules = [
    catalog({
      actions: [
        {
          name: "catalog.AddUseCase",
          description: "Add a use case",
          inputSpecs: [text("name")],
          preconditions: [],
          effects: [
            decl({ op: "create", type: "UseCase", properties: { name: { name: "name" } } }),
          ],
        },
        upd("RenameUseCase", "UseCase", "name"),
        upd("RenameSolution", "Solution", "name"),
        upd("SetLevel", "Solution", "coverageLevel"),
        {
          name: "catalog.Ping",
          description: "Send a ping",
          inputSpecs: [],
          preconditions: [],
          effects: [],
        },
      ],
    }),
  ];
});

function area(props: Partial<Parameters<typeof ActionsArea>[0]> = {}) {
  const onAction = vi.fn();
  renderPart(<ActionsArea module="catalog" onAction={onAction} {...props} />);
  return onAction;
}

const list = async () => within(await screen.findByRole("navigation", { name: "Actions" }));

describe("Actions area: the list", () => {
  it("groups the actions by the type they act on, the rest under Other", async () => {
    area();
    const nav = await list();
    const titles = nav.getAllByRole("heading").map((h) => h.textContent);
    expect(titles).toEqual(["UseCase", "Solution", "Other"]);
    const solution = within(nav.getByRole("list", { name: "Solution" }));
    expect(solution.getAllByRole("button").map((b) => b.getAttribute("data-action"))).toEqual([
      "catalog.RenameSolution",
      "catalog.SetLevel",
    ]);
  });

  it("opens on the first declared action when none is asked for and no entity is in context", async () => {
    area();
    const nav = await list();
    expect(nav.getByRole("button", { name: /AddUseCase/ })).toHaveAttribute("aria-current", "true");
  });

  it("filters on name and description with a count in a live region, and clears", async () => {
    const user = userEvent.setup();
    area();
    const nav = await list();
    expect(nav.getByRole("status")).toHaveTextContent("5 actions");
    await user.type(nav.getByRole("searchbox", { name: "Filter actions" }), "COVERAGE");
    expect(nav.getByRole("status")).toHaveAttribute("aria-live", "polite");
    expect(nav.getByRole("status")).toHaveTextContent("1 of 5 actions");
    expect(nav.getAllByRole("button").filter((b) => b.dataset.action)).toHaveLength(1);
    expect(nav.getByRole("button", { name: /SetLevel/ })).toBeInTheDocument();
    await user.click(nav.getByRole("button", { name: "Clear filter" }));
    expect(nav.getByRole("status")).toHaveTextContent("5 actions");
    await user.type(nav.getByRole("searchbox"), "zzz");
    expect(nav.getByText("No action matches.")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(nav.getByRole("searchbox")).toHaveValue("");
  });

  it("sets the actions relevant to the entity in context first, and opens on the one asked for", async () => {
    area({ action: "catalog.SetLevel", prefill: { target: "sol-1" } });
    const nav = await list();
    const titles = nav.getAllByRole("heading").map((h) => h.textContent);
    expect(titles[0]).toBe("For Solution sol-1");
    const relevant = within(nav.getByRole("list", { name: "For Solution sol-1" }));
    expect(relevant.getAllByRole("button").map((b) => b.getAttribute("data-action"))).toEqual([
      "catalog.RenameSolution",
      "catalog.SetLevel",
    ]);
    expect(relevant.getByRole("button", { name: /SetLevel/ })).toHaveAttribute(
      "aria-current",
      "true",
    );
    // each action appears once
    expect(nav.getAllByRole("button", { name: /SetLevel/ })).toHaveLength(1);
  });

  it("opens on the first relevant action when the one asked for does not exist", async () => {
    area({ action: "catalog.Gone", prefill: { target: "sol-1" } });
    // no context can be read from an unknown action: the first declared opens
    const nav = await list();
    expect(nav.getByRole("button", { name: /AddUseCase/ })).toHaveAttribute("aria-current", "true");
  });

  it("moves between actions with the arrow keys and chooses with Enter", async () => {
    const user = userEvent.setup();
    const onAction = area();
    const nav = await list();
    const first = nav.getByRole("button", { name: /AddUseCase/ });
    first.focus();
    await user.keyboard("{ArrowDown}");
    expect(nav.getByRole("button", { name: /RenameUseCase/ })).toHaveFocus();
    await user.keyboard("{End}");
    expect(nav.getByRole("button", { name: /Ping/ })).toHaveFocus();
    await user.keyboard("{ArrowUp}");
    expect(nav.getByRole("button", { name: /SetLevel/ })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onAction).toHaveBeenCalledWith("catalog.SetLevel");
  });

  it("moves from the filter into the list with ArrowDown", async () => {
    const user = userEvent.setup();
    area();
    const nav = await list();
    nav.getByRole("searchbox").focus();
    await user.keyboard("{ArrowDown}");
    expect(nav.getByRole("button", { name: /AddUseCase/ })).toHaveFocus();
  });
});
