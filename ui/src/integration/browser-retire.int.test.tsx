// SPDX-License-Identifier: MIT OR Apache-2.0
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { ArrasApp } from "../shell";
import { conn, gql, invoke, type Person, testQueryClient, unique, withDevHost } from "./harness";

// Retire on an entity page against the real dev host (FR-68): alice retires a solution through its
// declared action and the page after is not available; carol is offered no control.
withDevHost();

afterEach(() => {
  window.location.hash = "";
});

const app = (person: Person, hash: string) => {
  window.history.replaceState(null, "", "/");
  window.location.hash = hash;
  return render(<ArrasApp queryClient={testQueryClient()} {...conn(person)} />);
};

/** A use case with one solution addressing it, so its page has a group that goes with it. */
async function addUseCase(): Promise<string> {
  const uc = unique("uc");
  expect(
    (await invoke("AddUseCase", { code: uc, name: "To be retired", workArea: "finance" }, "bob"))
      .status,
  ).toBe(200);
  expect(
    (
      await invoke(
        "AddSolution",
        { code: unique("sol"), name: "Addresses it", useCase: uc },
        "alice",
      )
    ).status,
  ).toBe(200);
  return uc;
}

const useCaseRead = (key: string, person: Person) =>
  gql<{ data: { useCase: { key: string } | null } }>(
    "query($key: String!) { useCase(key: $key) { key } }",
    { key },
    person,
    "catalog",
  );

describe("FR-68 Retire through the real server", () => {
  it("alice retires a use case from its page (the dev host declares RetireUseCase): the list replaces the page and the page after is not available", async () => {
    const user = userEvent.setup();
    const code = await addUseCase();
    app("alice", `#/explore/catalog/UseCase/${code}`);
    await screen.findByRole("heading", { level: 1, name: /To be retired/ });
    await user.click(await screen.findByRole("button", { name: "Edit mode" }));
    await user.click(await screen.findByRole("button", { name: "Entity menu" }));
    await user.click(await screen.findByRole("menuitem", { name: "Retire" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByTestId("retire-groups")).toHaveTextContent(/\(1\)/);
    expect(dialog).toHaveTextContent("cannot be used again");
    await user.click(within(dialog).getByRole("button", { name: "Retire" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull(), { timeout: 8000 });
    expect(window.location.hash).toBe("#/explore/catalog/UseCase");
    // The server no longer has it, and the page after is not available.
    expect((await useCaseRead(code, "alice")).body.data.useCase).toBeNull();
    window.location.hash = `#/explore/catalog/UseCase/${code}`;
    expect(await screen.findByTestId("gb-state")).toHaveTextContent(/not available/i);
  });

  it("carol is offered no edit mode and no menu on a use case's page", async () => {
    const code = await addUseCase();
    app("carol", `#/explore/catalog/UseCase/${code}`);
    await screen.findByRole("heading", { level: 1, name: /To be retired/ });
    expect(screen.queryByRole("button", { name: "Edit mode" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Entity menu" })).toBeNull();
  });
});
