// SPDX-License-Identifier: MIT OR Apache-2.0
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ApiError } from "../api/errors";
import type { MetaData } from "../api/types";
import { ActionForm } from "../areas/ActionForm";
import { ActionsArea } from "../areas/ActionsArea";
import { AuditView } from "../areas/AuditView";
import { BatchForm } from "../areas/BatchForm";
import { EntityPanel } from "../areas/EntityPanel";
import { EntityTable } from "../areas/EntityTable";
import { GraphArea } from "../areas/GraphArea";
import { defined } from "../test/defined";
import {
  call,
  client,
  gql,
  invoke,
  renderLive,
  testQueryClient,
  unique,
  withDevHost,
} from "./harness";

// Changing data only through declared actions (US-062), against the real dev host.
withDevHost();

const enabled = (id: string) =>
  waitFor(() => {
    const b = screen.getByTestId(id);
    expect(b).toBeEnabled();
    return b;
  });
const useCase = async (code: string) =>
  (
    await gql<{ data: { useCase: Record<string, unknown> | null } }>(
      "query($key: String!) { useCase(key: $key) { key name version updatedBy } }",
      { key: code },
      "alice",
      "catalog",
    )
  ).body.data.useCase;

describe("validate and invoke (US-062)", () => {
  it("validates on blur and shows the server's violations at their fields, offering no invoke", async () => {
    const user = userEvent.setup();
    renderLive(<ActionForm module="catalog" action="catalog.AddUseCase" />);
    const code = await screen.findByLabelText(/^code/);
    await user.type(code, unique("uc"));
    await user.tab(); // name is required: the browser holds the request back
    await user.type(screen.getByLabelText(/^workArea/), "finance");
    await user.tab();
    expect(await screen.findByTestId("err-name")).toHaveTextContent("Expected a value (required)");
    expect(screen.getByTestId("confirm")).toBeDisabled();
  });

  it("a failed precondition on validate (a duplicate code) shows the module's reason", async () => {
    const user = userEvent.setup();
    renderLive(
      <ActionForm
        module="catalog"
        action="catalog.AddUseCase"
        prefill={{ code: "uc-pipeline", name: "Dup" }}
      />,
    );
    await user.click(await screen.findByTestId("validate"));
    // The declared precondition is listed from the start; wait for the server's answer to mark it failed.
    await waitFor(() =>
      expect(screen.getByTestId("precondition-fresh")).toHaveTextContent(
        "✗ fresh: a use case with that code exists",
      ),
    );
    expect(screen.getByTestId("not-valid")).toBeInTheDocument();
    expect(screen.getByTestId("confirm")).toBeDisabled();
  });

  it("shows the effects, invokes once with a key, and the receipt's group finds the change in the audit", async () => {
    const user = userEvent.setup();
    const code = unique("uc");
    renderLive(
      <ActionForm
        module="catalog"
        action="catalog.AddUseCase"
        prefill={{ code, name: "Invoked", workArea: "finance" }}
      />,
    );
    await user.click(await screen.findByTestId("validate"));
    const effects = await screen.findByTestId("effects");
    expect(within(effects).getByTestId("effect")).toHaveTextContent(
      new RegExp(`create\\s*UseCase\\s*${code}`),
    );
    expect(await useCase(code)).toBeNull(); // validating applied nothing
    await user.click(await enabled("confirm"));
    const receipt = await screen.findByTestId("receipt");
    expect(receipt).toHaveTextContent("Applied");
    expect(receipt).toHaveTextContent("created 1");
    const group = defined(/group (g-\d+)/.exec(receipt.textContent ?? "")?.[1], "the group id");
    expect(await useCase(code)).toMatchObject({ key: code, name: "Invoked", updatedBy: "alice" });

    renderLive(<AuditView module="catalog" />);
    await user.click(screen.getByRole("tab", { name: "Receipt by group" }));
    await user.type(screen.getByLabelText("Group id"), group);
    await user.click(screen.getByRole("button", { name: "Search" }));
    const row = await screen.findByTestId("change-row");
    expect(row).toHaveTextContent(group);
    expect(row).toHaveTextContent("alice");
    expect(row).toHaveTextContent(`create UseCase ${code}`);
  });

  it("the same key sent again is a replay: nothing is applied twice", async () => {
    const c = client("alice");
    const code = unique("uc");
    const key = unique("key");
    const a = await c.invoke("catalog", "catalog.AddUseCase", {
      inputs: { code, name: "Once" },
      idempotency_key: key,
    });
    const b = await c.invoke("catalog", "catalog.AddUseCase", {
      inputs: { code, name: "Once" },
      idempotency_key: key,
    });
    expect(a.replayed).toBe(false);
    expect(b).toEqual({ ...a, replayed: true });
    const hist = await c.changes({ module: "catalog", type: "catalog.UseCase", key: code });
    expect(hist.items).toHaveLength(1);
  });

  it("a form built from an older revision gets the real 409, rebuilds from the server and then applies", async () => {
    const user = userEvent.setup();
    // The form was built when the module was at an older revision: its cached schema says memory 0.
    const qc = testQueryClient(Infinity);
    const meta = await client("alice").meta();
    const stale: MetaData = {
      ...meta,
      modules: meta.modules.map((m) => ({ ...m, revision: { ...m.revision, memory: 0 } })),
    };
    qc.setQueryData(["meta"], stale);
    const code = unique("uc");
    renderLive(
      <ActionForm
        module="catalog"
        action="catalog.AddUseCase"
        prefill={{ code, name: "After conflict" }}
      />,
      "alice",
      { queryClient: qc },
    );
    await user.click(await screen.findByTestId("validate"));
    const banner = await screen.findByText(/The module changed while this form was open/);
    expect(banner.closest("[role=alert]")).toHaveTextContent('"memory":1');
    expect(await useCase(code)).toBeNull();
    expect(screen.getByTestId("confirm")).toBeDisabled();
    await user.click(screen.getByTestId("validate"));
    await user.click(await enabled("confirm"));
    expect(await screen.findByTestId("receipt")).toHaveTextContent("Applied");
    expect(await useCase(code)).toMatchObject({ name: "After conflict" });
  });

  it("a stale expected_revision on invoke answers 409 revision through the client", async () => {
    const c = client("alice");
    const e = await c
      .invoke("catalog", "catalog.AddUseCase", {
        inputs: { code: unique("uc"), name: "x" },
        expected_revision: { memory: 0 },
      })
      .catch((x: unknown) => x as ApiError);
    expect(e).toMatchObject({ status: 409, kind: "revision_conflict", reason: "revision" });
  });

  it("a precondition that fails between validate and invoke (422) is shown and nothing is applied", async () => {
    const user = userEvent.setup();
    const code = unique("uc");
    renderLive(
      <ActionForm module="catalog" action="catalog.AddUseCase" prefill={{ code, name: "Mine" }} />,
    );
    await user.click(await screen.findByTestId("validate"));
    const confirm = await enabled("confirm");
    // Someone else takes the code first.
    expect((await invoke("AddUseCase", { code, name: "Theirs" }, "bob")).status).toBe(200);
    await user.click(confirm);
    await waitFor(() =>
      expect(screen.getByTestId("precondition-fresh")).toHaveTextContent(
        "✗ fresh: a use case with that code exists",
      ),
    );
    expect(screen.queryByTestId("receipt")).toBeNull();
    expect(screen.getByTestId("confirm")).toBeDisabled();
    expect(await useCase(code)).toMatchObject({ name: "Theirs", updatedBy: "bob" });
  });

  it("invalid inputs on invoke answer 400 with the violation at its path", async () => {
    const e = await client("alice")
      .invoke("catalog", "catalog.CorrectSolution", { inputs: { solution: "sol-1", level: 5 } })
      .catch((x: unknown) => x as ApiError);
    expect(e).toMatchObject({ status: 400, kind: "invalid" });
    expect((e as ApiError).violations).toEqual([
      { path: "inputs.level", code: "type", message: "expected a string" },
    ]);
  });
});

describe("batch (US-062-AC6)", () => {
  async function run(items: unknown[], atomic: boolean) {
    const user = userEvent.setup();
    renderLive(<BatchForm module="catalog" action="catalog.AddUseCase" />);
    fireEvent.change(await screen.findByLabelText("Items"), {
      target: { value: JSON.stringify(items) },
    });
    if (atomic) await user.click(screen.getByLabelText(/Atomic/));
    await user.click(screen.getByRole("button", { name: /Review batch/ }));
    await user.click(screen.getByRole("button", { name: /Confirm and apply batch/ }));
  }

  it("atomic with one failing item applies nothing and says which precondition failed", async () => {
    const a = unique("ba");
    const b = unique("bb");
    await run(
      [
        { code: a, name: "A" },
        { code: "uc-pipeline", name: "dup" },
        { code: b, name: "B" },
      ],
      true,
    );
    const alert = await screen.findByText("A precondition failed");
    expect(alert.closest("[role=alert]")).toHaveTextContent(
      "fresh: a use case with that code exists",
    );
    expect(screen.queryByTestId("batch-result")).toBeNull();
    expect(await useCase(a)).toBeNull();
    expect(await useCase(b)).toBeNull();
  });

  it("independent shows a receipt per applied item and the refusal at its index", async () => {
    const a = unique("ba");
    const b = unique("bb");
    await run(
      [
        { code: a, name: "A" },
        { code: "uc-pipeline", name: "dup" },
        { code: b, name: "B" },
      ],
      false,
    );
    const result = await screen.findByTestId("batch-result");
    expect(result).toHaveTextContent("2 applied");
    expect(result).toHaveTextContent("1 refused");
    expect(result).toHaveTextContent("independent");
    expect(within(screen.getByTestId("batch-item-0")).getByTestId("receipt")).toHaveTextContent(a);
    expect(screen.getByTestId("batch-refusal-1")).toHaveTextContent(
      "Refused: a precondition failed",
    );
    expect(screen.getByTestId("batch-refusal-1")).toHaveTextContent(
      "fresh: a use case with that code exists",
    );
    expect(within(screen.getByTestId("batch-item-2")).getByTestId("receipt")).toHaveTextContent(b);
    expect(await useCase(b)).toMatchObject({ name: "B" });
  });

  it("an item with a missing input refuses the batch with the item's path", async () => {
    await run([{ code: unique("bc"), name: "ok" }, { code: unique("bd") }], false);
    expect(
      await screen.findByText(/items\[1\]\.inputs\.name: a value is required/),
    ).toBeInTheDocument();
  });
});

describe("safety: a name is text, never markup (XSS)", () => {
  const evil = `<img src=x onerror="window.__xss=1">`;

  it("a use case named with markup, created through the real action, renders as text everywhere", async () => {
    const user = userEvent.setup();
    const w = window as unknown as { __xss?: number };
    delete w.__xss;
    const code = unique("xss");
    // Created through the form, as an operator would.
    const form = renderLive(<ActionForm module="catalog" action="catalog.AddUseCase" />);
    await user.type(await screen.findByLabelText(/^code/), code);
    fireEvent.change(screen.getByLabelText(/^name/), { target: { value: evil } });
    await user.click(screen.getByTestId("validate"));
    expect(await screen.findByTestId("effects")).toHaveTextContent(`name=${JSON.stringify(evil)}`);
    await user.click(await enabled("confirm"));
    await screen.findByTestId("receipt");
    form.unmount();
    expect((await useCase(code))?.name).toBe(evil);

    const noMarkup = (el: HTMLElement) => {
      expect(el.querySelector("img")).toBeNull();
      expect(el.querySelector("[onerror]")).toBeNull();
    };

    // The table
    const t = renderLive(<EntityTable module="catalog" type="catalog.UseCase" />);
    await user.type(await screen.findByLabelText("Filter code"), `${code}{Enter}`);
    expect(await screen.findByText(evil)).toBeInTheDocument();
    noMarkup(t.container);
    t.unmount();

    // The entity panel
    const p = renderLive(
      <EntityPanel
        module="catalog"
        trail={[{ module: "catalog", type: "catalog.UseCase", key: code }]}
        onTrail={() => undefined}
        onClose={() => undefined}
      />,
    );
    expect(await screen.findByTestId("prop-name")).toHaveTextContent(evil);
    noMarkup(p.container);
    p.unmount();

    // The graph (node label and accessible name)
    const g = renderLive(<GraphArea module="catalog" />);
    const area = await screen.findByTestId("graph-area");
    await user.type(within(area).getByLabelText("Filter entities"), code);
    await waitFor(() =>
      expect(
        area.querySelector(`[data-testid="node"][data-node-id="catalog.UseCase:${code}"]`),
      ).not.toBeNull(),
    );
    expect(
      defined(
        area.querySelector(`[data-testid="node"][data-node-id="catalog.UseCase:${code}"]`),
        "the use case node",
      ).textContent,
    ).toContain("<img");
    noMarkup(g.container);
    g.unmount();

    // The impact view of retiring it (validate only; nothing is applied)
    const i = renderLive(
      <ActionsArea
        module="catalog"
        action="catalog.RetireUseCase"
        prefill={{ useCase: code }}
        onAction={() => undefined}
      />,
    );
    await user.click(await screen.findByTestId("validate"));
    const impact = await screen.findByTestId("impact");
    await waitFor(() =>
      expect(
        within(impact).getByTestId("impact-graph").querySelector("[data-status=deleted]"),
      ).not.toBeNull(),
    );
    expect(
      defined(
        within(impact).getByTestId("impact-graph").querySelector("[data-status=deleted]"),
        "the deleted node",
      ).textContent,
    ).toContain("<img");
    noMarkup(i.container);
    i.unmount();

    expect(w.__xss).toBeUndefined();
    expect(await useCase(code)).not.toBeNull();
    // and the read surface never echoed it as anything but a JSON string
    const raw = await call<{ data: { useCase: { name: string } } }>(
      `/api/console/graphql/catalog`,
      {
        query: `{ useCase(key: "${code}") { name } }`,
      },
    );
    expect(raw.body.data.useCase.name).toBe(evil);
  });
});
