// SPDX-License-Identifier: MIT OR Apache-2.0
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { ArrasApp } from "../shell";
import { conn, gql, invoke, type Person, testQueryClient, unique, withDevHost } from "./harness";

// Entity actions on a node page against the real dev host (FR-70): alice runs the declared AddSolution
// from a use case's page, with the use case prefilled; it validates, applies two effects (a create and a
// link) and the page shows the new solution. carol is offered no menu.
withDevHost();

afterEach(() => {
  window.location.hash = "";
});

const app = (person: Person, hash: string) => {
  window.history.replaceState(null, "", "/");
  window.location.hash = hash;
  return render(<ArrasApp queryClient={testQueryClient()} {...conn(person)} />);
};

async function addUseCase(): Promise<string> {
  const uc = unique("uc");
  expect(
    (await invoke("AddUseCase", { code: uc, name: "Gets a solution", workArea: "finance" }, "bob"))
      .status,
  ).toBe(200);
  return uc;
}

const solutionsOf = (key: string) =>
  gql<{ data: { useCase: { addressedBy: { key: string }[] } | null } }>(
    "query($key: String!) { useCase(key: $key) { addressedBy { key } } }",
    { key },
    "alice",
    "catalog",
  );

describe("FR-70 entity actions through the real server", () => {
  it("alice runs AddSolution from a use case's page: validate, a two-effect apply, a receipt and the page updated", async () => {
    const user = userEvent.setup();
    const uc = await addUseCase();
    const sol = unique("sol");
    app("alice", `#/explore/catalog/UseCase/${uc}`);
    await screen.findByRole("heading", { level: 1, name: /Gets a solution/ });
    await user.click(await screen.findByRole("button", { name: "Edit mode" }));
    await user.click(await screen.findByRole("button", { name: "Entity menu" }));
    const menu = await screen.findByRole("menu");
    expect(
      within(menu)
        .getAllByRole("menuitem")
        .map((i) => i.firstElementChild?.textContent ?? i.textContent),
    ).toEqual(["Retire", "AddSolution"]);
    await user.click(within(menu).getByRole("menuitem", { name: /^AddSolution/ }));
    const dialog = await screen.findByRole("dialog");
    // The use case is the page's: only the solution's own inputs are asked for.
    expect(within(dialog).queryByRole("textbox", { name: /useCase/ })).toBeNull();
    await user.type(within(dialog).getByRole("textbox", { name: /^code/ }), sol);
    await user.type(within(dialog).getByRole("textbox", { name: /^name/ }), "Made from the page");
    await user.click(within(dialog).getByRole("button", { name: "Validate" }));
    const summary = await within(dialog).findByTestId("effects-summary", {}, { timeout: 8000 });
    expect(summary.querySelectorAll("[data-testid=effect-sentence]").length).toBeGreaterThanOrEqual(
      2,
    );
    await user.click(within(dialog).getByRole("button", { name: "Apply" }));
    const receipt = await within(dialog).findByTestId("receipt-summary", {}, { timeout: 8000 });
    await waitFor(() => expect(receipt).toHaveFocus());
    // An entity is named once the normal read says the viewer can read it, so the link follows it.
    expect(
      await within(receipt).findByRole(
        "link",
        { name: new RegExp(`Solution ${sol}`) },
        { timeout: 8000 },
      ),
    ).toHaveAttribute("href", `#/explore/catalog/Solution/${sol}`);
    // The server has the new solution linked, and the page behind the dialog reads it.
    expect((await solutionsOf(uc)).body.data.useCase?.addressedBy.map((s) => s.key)).toEqual([sol]);
    await user.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(
      (await screen.findAllByText(/Made from the page/, {}, { timeout: 8000 })).length,
    ).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Entity menu" })).toHaveFocus();
  });

  it("carol is offered no edit mode and no menu", async () => {
    const uc = await addUseCase();
    app("carol", `#/explore/catalog/UseCase/${uc}`);
    await screen.findByRole("heading", { level: 1, name: /Gets a solution/ });
    expect(screen.queryByRole("button", { name: "Edit mode" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Entity menu" })).toBeNull();
  });
});
