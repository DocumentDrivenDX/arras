// SPDX-License-Identifier: MIT OR Apache-2.0
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";
import { AuditView } from "../areas/AuditView";
import { defined } from "../test/defined";
import { call, invoke, renderLive, unique, withDevHost } from "./harness";

// Who changed what (US-063), read from the real journal of the dev host.
withDevHost();

let bobCode = "";
let bobGroup = "";
beforeAll(async () => {
  bobCode = unique("audit");
  const r = await invoke<{ group: string }>("AddUseCase", { code: bobCode, name: "By bob" }, "bob");
  expect(r.status).toBe(200);
  bobGroup = r.body.group;
  // Enough changes for more than one page of 50.
  const items = Array.from({ length: 60 }, (_, i) => ({
    code: `${bobCode}-p${i}`,
    name: `Page ${i}`,
  }));
  expect(
    (await call("/api/operate/actions/catalog/AddUseCase/batch", { items, atomic: false })).status,
  ).toBe(200); // one group each
});

const rows = () => screen.getAllByTestId("change-row");
const firstRow = () => defined(rows()[0], "the first change row");

describe("Audit (US-063) on the real journal", () => {
  it("the module's changes, newest first, page with the server's cursor", async () => {
    const user = userEvent.setup();
    renderLive(<AuditView module="catalog" />);
    await waitFor(() => expect(rows()).toHaveLength(50));
    const first = firstRow().textContent;
    expect(first).toContain(`${bobCode}-p59`); // the last item of the batch is the newest
    await user.click(screen.getByRole("button", { name: /Older/ }));
    await waitFor(() => expect(screen.getByText("Page 2")).toBeInTheDocument());
    await waitFor(() => expect(firstRow().textContent).not.toBe(first));
    const second = rows().map((r) => r.textContent);
    expect(second.some((t) => t?.includes(`${bobCode}-p0`) || t?.includes(bobCode))).toBe(true);
    await user.click(screen.getByRole("button", { name: /Newer/ }));
    await waitFor(() => expect(firstRow().textContent).toBe(first));
  });

  it("filters by person and action", async () => {
    const user = userEvent.setup();
    renderLive(<AuditView module="catalog" />);
    await screen.findAllByTestId("change-row");
    await user.type(screen.getByLabelText("Person"), "bob");
    await user.selectOptions(screen.getByLabelText("Action"), "catalog.AddUseCase");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() =>
      expect(
        rows().every(
          (r) =>
            defined(within(r).getAllByRole("cell")[1], "the person cell").textContent === "bob",
        ),
      ).toBe(true),
    );
    expect(rows().some((r) => r.textContent?.includes(bobGroup))).toBe(true);
    await user.clear(screen.getByLabelText("Person"));
    await user.type(screen.getByLabelText("Person"), "carol");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("No changes match")).toBeInTheDocument();
  });

  it("an entity's history by type and key; a key without a type is caught before the request", async () => {
    const user = userEvent.setup();
    renderLive(<AuditView module="catalog" />);
    await screen.findAllByTestId("change-row");
    await user.type(screen.getByLabelText("Key"), bobCode);
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("Choose the key's type too.")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Type"), "catalog.UseCase");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(rows()).toHaveLength(1));
    expect(rows()[0]).toHaveTextContent("bob");
    expect(rows()[0]).toHaveTextContent(`create UseCase ${bobCode}`);
    expect(screen.queryByText("Choose the key's type too.")).toBeNull();
  });

  it("a time range: since in the future matches nothing, since in the past matches the history", async () => {
    const user = userEvent.setup();
    renderLive(<AuditView module="catalog" entity={{ type: "catalog.UseCase", key: bobCode }} />);
    await waitFor(() => expect(rows()).toHaveLength(1));
    fireEvent.change(screen.getByLabelText("Since"), { target: { value: "2999-01-01T00:00" } });
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("No changes match")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Since"), { target: { value: "2000-01-01T00:00" } });
    fireEvent.change(screen.getByLabelText("Until"), { target: { value: "2999-01-01T00:00" } });
    await user.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(rows()).toHaveLength(1));
  });

  it("a receipt's group opens the same change; an unknown group is an empty page", async () => {
    const user = userEvent.setup();
    renderLive(<AuditView module="catalog" />);
    await user.click(await screen.findByRole("tab", { name: "Receipt by group" }));
    expect(screen.getByText("Enter a group id to open a receipt")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Group id"), bobGroup);
    await user.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(rows()).toHaveLength(1));
    expect(rows()[0]).toHaveTextContent(bobGroup);
    expect(rows()[0]).toHaveTextContent("catalog.AddUseCase");
    await user.clear(screen.getByLabelText("Group id"));
    await user.type(screen.getByLabelText("Group id"), "g-999999");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("No changes match")).toBeInTheDocument();
  });

  it("import loads: none recorded for the sandbox module (no import surface reaches the dev host); root has no journal grant", async () => {
    const user = userEvent.setup();
    const asRoot = renderLive(<AuditView module="catalog" />, "root");
    await user.click(await screen.findByRole("tab", { name: "Import loads" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("No access"));
    asRoot.unmount();
    renderLive(<AuditView module="catalog" />, "alice");
    await user.click(await screen.findByRole("tab", { name: "Import loads" }));
    expect(await screen.findByText("No loads recorded for this module")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Older/ })).toBeDisabled();
  });

  it("the trail never shows a validate-only run or a refused attempt", async () => {
    const code = unique("never");
    expect(
      (
        await call("/api/operate/actions/catalog/AddUseCase/validate", {
          inputs: { code, name: "x" },
        })
      ).status,
    ).toBe(200);
    expect((await invoke("AddUseCase", { code, name: "x" }, "carol")).status).toBe(403);
    const r = await call<{ items: unknown[] }>("/api/operate/audit/changes", {
      module: "catalog",
      type: "catalog.UseCase",
      key: code,
    });
    expect(r.body.items).toEqual([]);
  });
});
