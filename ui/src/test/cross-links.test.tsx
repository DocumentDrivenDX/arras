// SPDX-License-Identifier: MIT OR Apache-2.0
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ArrasApp, type ArrasAppProps } from "../shell";
import { crossLinks, exploreLocationFor, operateRouteFor, targetOfLocation } from "../shell/links";
import { type BrowserFake, stageBrowser } from "./browserFake";
import { qc } from "./render";

const sol = { module: "catalog", type: "catalog.Solution", key: "sol-1" };
const SOL1 = "Lumen alert correlation (S-017)";

describe("the link primitive (Rule 7, FR-71)", () => {
  const hash = crossLinks({ hash: true, openOperate: vi.fn(), openExplore: vi.fn() });

  it("in hash mode an entity's History in Operate is the changes address with the qualified type", () => {
    expect(hash.toOperate({ entity: sol }, "history").href).toBe(
      "#/operate/catalog/changes/catalog.Solution/sol-1",
    );
    expect(hash.toOperate({ entity: sol }).href).toBe(
      "#/operate/catalog/entities/catalog.Solution/sol-1",
    );
    expect(hash.toOperate({ entity: sol }, "model").href).toBe(
      "#/operate/catalog/model/catalog.Solution",
    );
  });

  it("Actions carries the action and the entity's key as its prefill", () => {
    const entity = {
      ...sol,
      action: { name: "catalog.CorrectSolution", input: { solution: "sol-1" } },
    };
    expect(hash.toOperate({ entity }, "actions").href).toBe(
      "#/operate/catalog/actions/catalog.CorrectSolution?in.solution=sol-1",
    );
  });

  it("types, modules and change groups open their Operate places", () => {
    expect(hash.toOperate({ type: { module: "catalog", type: "catalog.UseCase" } }).href).toBe(
      "#/operate/catalog/entities/catalog.UseCase",
    );
    expect(
      hash.toOperate({ type: { module: "catalog", type: "catalog.UseCase" } }, "model").href,
    ).toBe("#/operate/catalog/model/catalog.UseCase");
    expect(hash.toOperate({ module: "catalog" }).href).toBe("#/operate/catalog/model");
    expect(hash.toOperate({ group: { module: "catalog", id: "g-4" } }).href).toBe(
      "#/operate/catalog/changes?group=g-4",
    );
  });

  it("converts the other way with the short type name; a group opens its module", () => {
    expect(hash.toExplore({ entity: sol }).href).toBe("#/explore/catalog/Solution/sol-1");
    expect(hash.toExplore({ entity: sol }, "history").href).toBe(
      "#/explore/catalog/Solution/sol-1/history",
    );
    expect(hash.toExplore({ type: { module: "catalog", type: "catalog.Solution" } }).href).toBe(
      "#/explore/catalog/Solution",
    );
    expect(hash.toExplore({ module: "catalog" }).href).toBe("#/explore/catalog");
    expect(hash.toExplore({ group: { module: "catalog", id: "g-4" } }).href).toBe(
      "#/explore/catalog",
    );
  });

  it("where the host owns the location there is no href, and go hands the host the other mode's route", () => {
    const openOperate = vi.fn();
    const openExplore = vi.fn();
    const own = crossLinks({ hash: false, openOperate, openExplore });
    const operate = own.toOperate({ entity: sol }, "history");
    expect(operate.href).toBeUndefined();
    operate.go();
    expect(openOperate).toHaveBeenCalledWith({
      module: "catalog",
      area: "changes",
      type: "catalog.Solution",
      key: "sol-1",
    });
    const explore = own.toExplore({ entity: sol });
    expect(explore.href).toBeUndefined();
    explore.go();
    expect(openExplore).toHaveBeenCalledWith({ module: "catalog", type: "Solution", key: "sol-1" });
  });

  it("routes and locations round-trip through one pair of conversions", () => {
    const at = targetOfLocation({
      module: "catalog",
      type: "Solution",
      key: "sol-1",
      history: true,
    });
    expect(at).toBeDefined();
    if (!at) return;
    expect(operateRouteFor(at.target, at.area).area).toBe("changes");
    expect(exploreLocationFor(at.target, at.area)).toEqual({
      module: "catalog",
      type: "Solution",
      key: "sol-1",
      history: true,
    });
    expect(targetOfLocation({})).toBeUndefined();
    expect(targetOfLocation({ module: "catalog", type: "UseCase", after: "uc-1" })).toEqual({
      target: { type: { module: "catalog", type: "catalog.UseCase", after: "uc-1" } },
    });
  });
});

describe("cross-mode links in the shell", () => {
  let fake: BrowserFake;
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
    window.location.hash = "";
    fake = stageBrowser();
    fake.mods = fake.mods.slice(0, 1);
  });
  afterEach(() => {
    window.location.hash = "";
  });
  const app = (props: ArrasAppProps = {}) => render(<ArrasApp queryClient={qc()} {...props} />);
  const footer = async () => within(await screen.findByTestId("gb-open-in-operate"));

  it("hash mode: Open in Operate on a node page is anchors to Entities, History and Actions", async () => {
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    app();
    const nav = await footer();
    expect(nav.getByRole("link", { name: /Entities of/ })).toHaveAttribute(
      "href",
      "#/operate/catalog/entities/catalog.Solution/sol-1",
    );
    expect(nav.getByRole("link", { name: /History of/ })).toHaveAttribute(
      "href",
      "#/operate/catalog/changes/catalog.Solution/sol-1",
    );
    expect(nav.getByRole("link", { name: /Actions of/ })).toHaveAttribute(
      "href",
      "#/operate/catalog/actions/catalog.ChangeSolutionDelivery?in.solution=sol-1",
    );
  });

  it("hash mode: following one opens Operate there, and View in Explore on its context bar comes back", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    app();
    await user.click((await footer()).getByRole("link", { name: /History of/ }));
    await screen.findByTestId("console-header");
    expect(window.location.hash).toBe("#/operate/catalog/changes/catalog.Solution/sol-1");
    const bar = await screen.findByRole("navigation", { name: "Entity context" });
    const back = within(bar).getByRole("link", { name: /View in Explore/ });
    expect(back).toHaveAttribute("href", "#/explore/catalog/Solution/sol-1/history");
    await user.click(back);
    expect(await screen.findByRole("heading", { level: 1, name: SOL1 })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/explore/catalog/Solution/sol-1/history");
  });

  it("hash mode: a type's list has a Model link", async () => {
    window.location.hash = "#/explore/catalog/Solution";
    app();
    const link = await screen.findByRole("link", { name: /Model of/ });
    expect(link).toHaveAttribute("href", "#/operate/catalog/model/catalog.Solution");
    expect(link).toHaveTextContent("Model");
  });

  it("a host that owns the location: the link has no href, switches mode and sets the route", async () => {
    const user = userEvent.setup();
    const seen: unknown[] = [];
    app({
      location: { module: "catalog", type: "Solution", key: "sol-1" },
      onLocation: (l) => seen.push(l),
    });
    const link = (await footer()).getByRole("button", { name: /History of/ });
    expect(link.tagName).toBe("BUTTON");
    await user.click(link);
    await screen.findByTestId("console-header");
    expect(window.location.hash).toBe("");
    await waitFor(() =>
      expect(screen.getAllByRole("tab", { name: "Changes", selected: true })).not.toHaveLength(0),
    );
    const bar = await screen.findByRole("navigation", { name: "Entity context" });
    await user.click(within(bar).getByRole("button", { name: /View in Explore/ }));
    expect(await screen.findByRole("heading", { level: 1, name: SOL1 })).toBeInTheDocument();
    expect(seen).toContainEqual({
      module: "catalog",
      type: "Solution",
      key: "sol-1",
      history: true,
    });
  });

  it("a host that owns the location: history.state is left as the host set it", async () => {
    const mine = { host: "owns-this" };
    window.history.replaceState(mine, "", "/");
    app({ location: { module: "catalog", type: "Solution", key: "sol-1" }, onLocation: () => {} });
    await footer();
    expect(window.history.state).toMatchObject(mine);
    expect(window.history.state).not.toHaveProperty("gbMode");
  });

  it("no cross-mode link for a viewer who is not an operator, and no word of Operate", async () => {
    fake.viewerModes = ["user"];
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    const { container } = app();
    await screen.findByRole("heading", { level: 1, name: SOL1 });
    await waitFor(() => expect(fake.requests.some((r) => r.path.endsWith("/viewer"))).toBe(true));
    await act(async () => undefined);
    expect(screen.queryByTestId("gb-open-in-operate")).toBeNull();
    expect(container.innerHTML).not.toMatch(/operate/i);
  });

  it("the palette's Open in Operate goes through the primitive and keeps the page that is open", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    app();
    await screen.findByRole("heading", { level: 1, name: SOL1 });
    await footer();
    await user.keyboard("{Control>}k{/Control}");
    await user.click(await screen.findByRole("option", { name: /Open in Operate/ }));
    await screen.findByTestId("console-header");
    expect(window.location.hash).toBe("#/operate/catalog/entities/catalog.Solution/sol-1");
  });
});
