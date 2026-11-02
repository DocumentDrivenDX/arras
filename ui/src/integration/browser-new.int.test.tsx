// SPDX-License-Identifier: MIT OR Apache-2.0
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { ArrasApp } from "../shell";
import { conn, gql, invoke, type Person, testQueryClient, unique, withDevHost } from "./harness";

// New on a type's list against the real dev host (FR-67): alice creates a solution through the declared
// AddSolution (validate, then invoke) from the form, picking the use case it is for in the picker, and
// the created solution's page opens from the validated key; carol is offered no control.
withDevHost();

afterEach(() => {
  window.location.hash = "";
});

const app = (person: Person, hash: string) => {
  window.history.replaceState(null, "", "/");
  window.location.hash = hash;
  return render(<ArrasApp queryClient={testQueryClient()} {...conn(person)} />);
};

const solutionRead = (key: string) =>
  gql<{ data: { solution: { key: string; name: string } | null } }>(
    "query($key: String!) { solution(key: $key) { key name } }",
    { key },
    "alice",
    "catalog",
  );

describe("FR-67 New through the real server", () => {
  it("alice creates a solution from the Solutions list: the picker names the use case and the new page opens", async () => {
    const user = userEvent.setup();
    const uc = unique("uc");
    const ucName = `Picked ${uc}`;
    expect((await invoke("AddUseCase", { code: uc, name: ucName }, "bob")).status).toBe(200);
    const code = unique("sol");
    app("alice", "#/explore/catalog/Solution");
    await screen.findByRole("heading", { level: 2, name: "Solutions" });
    await user.click(await screen.findByRole("button", { name: "Edit mode" }));
    await user.click(await screen.findByRole("button", { name: "New solution" }));
    const dialog = await screen.findByRole("dialog");
    const creator = within(dialog).queryByRole("combobox", { name: /^Create with/ });
    if (creator) await user.selectOptions(creator, "catalog.AddSolution"); // the module declares more than one creating action
    await user.type(within(dialog).getByRole("textbox", { name: /^code/ }), code);
    await user.type(within(dialog).getByRole("textbox", { name: /^name/ }), "Made from New");
    await user.type(
      within(dialog).getByRole("textbox", { name: /^Filter or search use cases/ }),
      uc,
    );
    const box = await within(dialog).findByRole("combobox", { name: /^useCase/ });
    await within(box).findByRole("option", { name: ucName }, { timeout: 8000 });
    await user.selectOptions(box, ucName);
    await user.click(within(dialog).getByRole("button", { name: "Validate" }));
    await waitFor(() =>
      expect(within(dialog).getByRole("button", { name: "Create" })).toBeEnabled(),
    );
    await user.click(await within(dialog).findByRole("button", { name: "Create" }));
    await waitFor(() => expect(window.location.hash).toBe(`#/explore/catalog/Solution/${code}`), {
      timeout: 10000,
    });
    expect(screen.queryByRole("dialog")).toBeNull();
    await screen.findByRole("heading", { level: 1, name: /Made from New/ });
    expect((await solutionRead(code)).body.data.solution?.name).toBe("Made from New");
  });

  it("shows the server's refusal of a code already taken, in the dialog, and creates nothing", async () => {
    const user = userEvent.setup();
    const code = unique("sol");
    const uc = unique("uc");
    expect((await invoke("AddUseCase", { code: uc, name: `For ${uc}` }, "bob")).status).toBe(200);
    expect(
      (await invoke("AddSolution", { code, name: "First", useCase: uc }, "alice")).status,
    ).toBe(200);
    app("alice", "#/explore/catalog/Solution");
    await user.click(await screen.findByRole("button", { name: "Edit mode" }));
    await user.click(await screen.findByRole("button", { name: "New solution" }));
    const dialog = await screen.findByRole("dialog");
    const creator = within(dialog).queryByRole("combobox", { name: /^Create with/ });
    if (creator) await user.selectOptions(creator, "catalog.AddSolution"); // the module declares more than one creating action
    await user.type(within(dialog).getByRole("textbox", { name: /^code/ }), code);
    await user.type(within(dialog).getByRole("textbox", { name: /^name/ }), "Second");
    await user.type(
      within(dialog).getByRole("textbox", { name: /^Filter or search use cases/ }),
      uc,
    );
    const box = await within(dialog).findByRole("combobox", { name: /^useCase/ });
    await within(box).findByRole("option", { name: `For ${uc}` }, { timeout: 8000 });
    await user.selectOptions(box, `For ${uc}`);
    await user.click(within(dialog).getByRole("button", { name: "Validate" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(/conflict \(exists\)/);
    expect(within(dialog).getByRole("button", { name: "Create" })).toBeDisabled();
    expect(window.location.hash).toBe("#/explore/catalog/Solution");
    expect((await solutionRead(code)).body.data.solution?.name).toBe("First");
  });

  it("carol is offered no edit mode and no New on the list", async () => {
    app("carol", "#/explore/catalog/Solution");
    await screen.findByRole("heading", { level: 2, name: "Solutions" });
    expect(screen.queryByRole("button", { name: "Edit mode" })).toBeNull();
    expect(screen.queryByRole("button", { name: "New solution" })).toBeNull();
  });
});
