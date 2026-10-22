// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Effect } from "../api/types";
import { ActionsArea } from "../areas/ActionsArea";
import { ImpactPanel, type ImpactState } from "../areas/ImpactPanel";
import { buildImpact, nextSteps, summarize } from "../lib/impact";
import { defined } from "./defined";
import {
  catalog,
  type FakeApi,
  json,
  type Recorded,
  receipt,
  seedCatalog,
  stage,
  validation,
} from "./fake";
import { renderPart } from "./render";

let api: FakeApi;
beforeEach(() => {
  window.location.hash = "";
  api = stage();
  seedCatalog(api);
  defined(
    defined(api.rows["catalog.Solution"], "api.rows[catalog.Solution]")[0],
    "defined(api.rows[catalog.Solution], api.",
  ).coverageLevel = "full";
  api.targets["catalog.Solution:sol-1"] = defined(
    defined(api.rows["catalog.Solution"], "api.rows[catalog.Solution]")[0],
    "defined(api.rows[catalog.Solution], api.",
  );
});

const ref = (type: string, key: string, generated = false) => ({
  type: `catalog.${type}`,
  key,
  generated,
});
const state = (
  effects: Effect[],
  status: ImpactState["status"] = "preview",
  r = null as ImpactState["receipt"],
): ImpactState => ({
  action: "catalog.CorrectSolution",
  effects,
  status,
  valid: true,
  receipt: r,
});
const node = (id: string) =>
  defined(
    within(screen.getByTestId("impact-graph"))
      .getAllByTestId("node")
      .find((n) => n.getAttribute("data-node-id") === id),
    `node ${id}`,
  );
const edgesOf = (status: string) =>
  within(screen.getByTestId("impact-graph"))
    .queryAllByTestId("edge")
    .filter((e) => e.getAttribute("data-status") === status);

describe("Impact preview", () => {
  it("is empty until a change has been reviewed", async () => {
    renderPart(<ImpactPanel module="catalog" state={null} />);
    expect(await screen.findByTestId("impact-empty")).toHaveTextContent("Review changes");
  });

  it("draws a create with its link: green dashed node, dashed added edge, neighbours kept", async () => {
    const fx: Effect[] = [
      { kind: "create", ref: ref("Solution", "sol-new"), properties: { name: "Fresh one" } },
      {
        kind: "link",
        relationship: "addresses",
        source: ref("Solution", "sol-new"),
        target: ref("UseCase", "uc-2"),
      },
    ];
    renderPart(<ImpactPanel module="catalog" state={state(fx)} />);
    await waitFor(() => expect(screen.getByTestId("impact-graph")).toBeInTheDocument());
    const created = await waitFor(() => node("catalog.Solution:sol-new"));
    expect(created).toHaveAttribute("data-status", "created");
    expect(created).toHaveTextContent("Fresh one");
    expect(created.querySelector("rect.arras-node-box")).toHaveAttribute("stroke-dasharray", "4 3");
    expect(edgesOf("added")).toHaveLength(1);
    expect(node("catalog.UseCase:uc-2")).toHaveAttribute("data-status", "touched");
    // uc-2's existing neighbour sol-1 is drawn as a plain neighbour
    expect(node("catalog.Solution:sol-1")).toHaveAttribute("data-status", "plain");
    expect(screen.getByTestId("impact-summary")).toHaveTextContent(
      "Creates 1 Solution; links 1 relationship; updates nothing.",
    );
    expect(screen.getByTestId("impact")).toHaveAttribute("data-state", "preview");
    expect(screen.getByText(/preview: nothing applied/)).toBeInTheDocument();
  });

  it("shows an update as amber with before and after of the changed property", async () => {
    const fx: Effect[] = [
      {
        kind: "update",
        ref: ref("Solution", "sol-1"),
        set: { coverageLevel: "partial" },
        unset: [],
      },
    ];
    renderPart(<ImpactPanel module="catalog" state={state(fx)} />);
    const n = await waitFor(() => node("catalog.Solution:sol-1"));
    expect(n).toHaveAttribute("data-status", "updated");
    const changes = await screen.findByTestId("impact-changes");
    await waitFor(() => expect(changes).toHaveTextContent('"full"'));
    expect(changes).toHaveTextContent("coverageLevel");
    expect(changes).toHaveTextContent('"partial"');
  });

  it("shows a delete as red and struck through, and the links that go with it as dashed red", async () => {
    const fx: Effect[] = [{ kind: "delete", ref: ref("UseCase", "uc-1") }];
    renderPart(<ImpactPanel module="catalog" state={state(fx)} />);
    const n = await waitFor(() => node("catalog.UseCase:uc-1"));
    expect(n).toHaveAttribute("data-status", "deleted");
    expect(n.querySelector("text[text-decoration='line-through']")).not.toBeNull();
    expect(edgesOf("removed")).toHaveLength(1);
    expect(screen.getByTestId("impact-summary")).toHaveTextContent("Deletes 1 UseCase");
    expect(screen.getByTestId("impact-summary")).toHaveTextContent(
      "1 link to other entities would go with it",
    );
  });

  it("shows an unlink as a removed edge between two entities that stay", async () => {
    const fx: Effect[] = [
      {
        kind: "unlink",
        relationship: "addresses",
        source: ref("Solution", "sol-1"),
        target: ref("UseCase", "uc-1"),
      },
    ];
    renderPart(<ImpactPanel module="catalog" state={state(fx)} />);
    await waitFor(() => expect(edgesOf("removed")).toHaveLength(1));
    expect(node("catalog.UseCase:uc-1")).toHaveAttribute("data-status", "touched");
    expect(screen.getByTestId("impact-summary")).toHaveTextContent("Unlinks 1 relationship");
  });

  it("marks stale inputs and keeps the last picture dimmed", async () => {
    const fx: Effect[] = [{ kind: "delete", ref: ref("UseCase", "uc-1") }];
    renderPart(<ImpactPanel module="catalog" state={state(fx, "stale")} />);
    await waitFor(() => node("catalog.UseCase:uc-1"));
    expect(screen.getByText(/inputs changed; review again/)).toBeInTheDocument();
  });

  it("applied keeps the same view in solid colours and offers only declared reversing actions", async () => {
    const user = userEvent.setup();
    const onNext = vi.fn();
    const base = catalog();
    api.modules = [
      {
        ...base,
        actions: [
          ...base.actions,
          {
            name: "catalog.AddUseCase",
            description: "Add a use case",
            inputSpecs: [],
            preconditions: [],
            effects: [{ op: "create", type: "UseCase", alias: null }],
          },
        ],
      },
    ];
    const fx: Effect[] = [{ kind: "delete", ref: ref("UseCase", "uc-1") }];
    renderPart(
      <ImpactPanel
        module="catalog"
        state={state(fx, "applied", receipt({ deleted: 1, updated: 0, refs: [] }))}
        onNextAction={onNext}
      />,
    );
    await waitFor(() => node("catalog.UseCase:uc-1"));
    expect(screen.getByTestId("impact")).toHaveAttribute("data-state", "applied");
    expect(screen.getByTestId("impact-summary")).toHaveTextContent("Deleted 1 UseCase");
    // the module declares AddUseCase, which creates a use case again; nothing else reverses a delete
    const next = screen.getByTestId("next-steps");
    expect(within(next).getAllByRole("button")).toHaveLength(1);
    await user.click(within(next).getByRole("button", { name: /AddUseCase/ }));
    expect(onNext).toHaveBeenCalledWith("catalog.AddUseCase", {});
  });

  it("offers no undo when no declared action reverses the change", () => {
    const m = catalog();
    const fx: Effect[] = [{ kind: "create", ref: ref("Solution", "s"), properties: {} }];
    expect(nextSteps(m, fx)).toEqual([]);
    const del: Effect[] = [{ kind: "create", ref: ref("UseCase", "u"), properties: {} }];
    // there is no declared delete in the test module, so a created use case has no reversing step either
    expect(nextSteps(m, del)).toEqual([]);
  });
});

describe("Impact helpers", () => {
  it("summarizes in plain words, in the past tense once applied", () => {
    const m = catalog();
    const fx: Effect[] = [
      { kind: "create", ref: ref("Solution", "n"), properties: {} },
      {
        kind: "link",
        relationship: "addresses",
        source: ref("Solution", "n"),
        target: ref("UseCase", "uc-1"),
      },
    ];
    const model = buildImpact(m, null, fx, new Map());
    expect(summarize(model, false)).toBe(
      "Creates 1 Solution; links 1 relationship; updates nothing.",
    );
    expect(summarize(model, true)).toBe(
      "Created 1 Solution; linked 1 relationship; updated nothing.",
    );
    expect(summarize(buildImpact(m, null, [], new Map()), false)).toBe("Changes nothing.");
  });
});

describe("Actions area with the impact view", () => {
  const verb = (v: string) => (r: Recorded) => r.method === "POST" && r.path.endsWith(`/${v}`);

  it("opens the first action when none is chosen, and shows the impact after review and after apply", async () => {
    const user = userEvent.setup();
    api.on((r) => (verb("validate")(r) ? json(200, validation()) : undefined));
    api.on((r) => (verb("invoke")(r) ? json(200, receipt()) : undefined));
    const onView = vi.fn();
    renderPart(<ActionsArea module="catalog" onAction={() => undefined} onViewInGraph={onView} />);
    // never a blank page: the first declared action's form is open
    expect(
      await screen.findByRole("form", { name: /AddUseCase|CorrectSolution/ }),
    ).toBeInTheDocument();
    await user.click(
      within(screen.getByRole("navigation", { name: "Actions" })).getByRole("button", {
        name: /CorrectSolution/,
      }),
    );
    await screen.findByRole("form", { name: "Action catalog.CorrectSolution" });
    expect(screen.getByTestId("impact-empty")).toBeInTheDocument();
    await user.type(screen.getByLabelText(/^solution/), "sol-1");
    await user.type(screen.getByLabelText(/^level/), "partial");
    await user.tab();
    await waitFor(() =>
      expect(screen.getByTestId("impact")).toHaveAttribute("data-state", "preview"),
    );
    await waitFor(() =>
      expect(node("catalog.Solution:sol-1")).toHaveAttribute("data-status", "updated"),
    );
    expect(api.posts(/\/invoke$/)).toHaveLength(0); // drawing the impact applies nothing
    await user.click(screen.getByTestId("confirm"));
    await screen.findByTestId("receipt");
    await waitFor(() =>
      expect(screen.getByTestId("impact")).toHaveAttribute("data-state", "applied"),
    );
    expect(node("catalog.Solution:sol-1")).toHaveAttribute("data-status", "updated");
    // focus moves to the receipt
    expect(document.activeElement).toBe(screen.getByLabelText("Receipt"));
    await user.click(screen.getByRole("button", { name: "View in graph" }));
    expect(onView).toHaveBeenCalledWith({ label: "group g-4", ids: ["catalog.Solution:sol-1"] });
  });
});
