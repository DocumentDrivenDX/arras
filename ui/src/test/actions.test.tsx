// SPDX-License-Identifier: MIT OR Apache-2.0
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createClient } from "../api/client";
import { ActionForm } from "../areas/ActionForm";
import { ActionsArea } from "../areas/ActionsArea";
import { BatchForm } from "../areas/BatchForm";
import { NavProvider } from "../components/NavLink";
import { crossLinks } from "../shell/links";
import { defined } from "./defined";
import {
  catalog,
  err,
  type FakeApi,
  json,
  type Recorded,
  receipt,
  seedCatalog,
  stage,
  validation,
  wire,
} from "./fake";
import { renderConsole, renderPart } from "./render";

let api: FakeApi;
beforeEach(() => {
  window.location.hash = "";
  api = stage();
  seedCatalog(api);
});
afterEach(() => vi.useRealTimers());

const verb = (v: string) => (r: Recorded) => r.method === "POST" && r.path.endsWith(`/${v}`);
const calls = (v: string) => api.log.filter(verb(v));
const form = (action = "catalog.CorrectSolution", prefill?: Record<string, string>) =>
  renderPart(<ActionForm module="catalog" action={action} prefill={prefill} />);

async function fill(user: ReturnType<typeof userEvent.setup>, name: string, value: string) {
  const input = screen.getByLabelText(new RegExp(`^${name}`));
  await user.clear(input);
  await user.type(input, value);
}

describe("Actions (US-062)", () => {
  it("US-062-AC1: the form has one field per input, by type, with a list and a reference offered as such", async () => {
    form("catalog.Typed");
    await screen.findByTestId("action-form");
    expect(screen.getAllByTestId(/^field-/)).toHaveLength(7);
    // by type
    expect(screen.getByLabelText(/^active/).tagName).toBe("SELECT"); // boolean
    expect(screen.getByLabelText(/^count/).tagName).toBe("INPUT");
    expect(screen.getByTestId("field-count")).toHaveTextContent("integer");
    expect(within(screen.getByTestId("field-count")).getByText("required")).toBeInTheDocument();
    expect(within(screen.getByTestId("field-amount")).queryByText("required")).toBeNull();
    expect(screen.getByTestId("field-amount")).toHaveTextContent("decimal");
    expect(screen.getByTestId("field-when")).toHaveTextContent("RFC 3339");
    // a list: one value per line
    expect(screen.getByLabelText(/^tags/).tagName).toBe("TEXTAREA");
    expect(screen.getByTestId("field-tags")).toHaveTextContent("many");
    expect(screen.getByTestId("field-tags")).toHaveTextContent("one value per line");
    // a reference, and a list of references
    expect(screen.getByTestId("field-useCases")).toHaveTextContent("ref UseCase");
    expect(screen.getByTestId("field-useCases")).toHaveTextContent("many");
    // a record has no generated form: a raw JSON textarea
    expect(screen.getByLabelText(/^terms/).tagName).toBe("TEXTAREA");
    expect(screen.getByTestId("field-terms")).toHaveTextContent("JSON object");
  });

  it("US-062 typing: validate runs when a field loses focus, never per keystroke", async () => {
    const user = userEvent.setup();
    api.on((r) => (verb("validate")(r) ? json(200, validation()) : undefined));
    form();
    const level = await screen.findByLabelText(/^level/);
    await user.type(screen.getByLabelText(/^solution/), "sol-1");
    await user.click(level);
    expect(calls("validate")).toHaveLength(0); // blur of `solution` with an incomplete form: no request
    await user.type(level, "partial");
    expect(calls("validate")).toHaveLength(0); // seven keystrokes, still none
    await user.tab();
    await waitFor(() => expect(calls("validate")).toHaveLength(1));
    expect(defined(calls("validate")[0], 'calls("validate")[0]').body.inputs).toEqual({
      solution: "sol-1",
      level: "partial",
    });
  });

  it("US-062 typing: types are checked in the browser while editing, before any request", async () => {
    const user = userEvent.setup();
    form("catalog.Typed");
    const count = await screen.findByLabelText(/^count/);
    await user.type(count, "12x");
    await user.tab();
    expect(await screen.findByTestId("err-count")).toHaveTextContent("an integer");
    await user.type(screen.getByLabelText(/^when/), "yesterday");
    await user.tab();
    expect(await screen.findByTestId("err-when")).toHaveTextContent("RFC 3339");
    await user.type(screen.getByLabelText(/^terms/), "{{not json");
    await user.tab();
    expect(await screen.findByTestId("err-terms")).toHaveTextContent("valid JSON");
    expect(calls("validate")).toHaveLength(0);
    expect(screen.getByTestId("confirm")).toBeDisabled();
  });

  it("US-062 wire encoding: decimals, timestamps and large integers as text, lists as arrays, records as objects", async () => {
    const user = userEvent.setup();
    api.on((r) => (verb("validate")(r) ? json(200, validation({ effects: [] })) : undefined));
    form("catalog.Typed");
    await screen.findByTestId("action-form");
    await fill(user, "count", "9007199254740993");
    await fill(user, "amount", "12.50");
    await user.selectOptions(screen.getByLabelText(/^active/), "true");
    await fill(user, "when", "2026-10-09T14:02:11Z");
    await user.type(screen.getByLabelText(/^tags/), "a{Enter}b");
    await user.type(screen.getByLabelText(/^useCases/), "uc-1{Enter}uc-2");
    fireEvent.change(screen.getByLabelText(/^terms/), { target: { value: '{"months": 12}' } });
    await user.click(screen.getByTestId("validate"));
    await waitFor(() => expect(calls("validate").length).toBeGreaterThan(0));
    expect(defined(calls("validate").at(-1), 'calls("validate").at(-1)').body.inputs).toEqual({
      count: "9007199254740993",
      amount: "12.50",
      active: true,
      when: "2026-10-09T14:02:11Z",
      tags: ["a", "b"],
      useCases: ["uc-1", "uc-2"],
      terms: { months: 12 },
    });
  });

  it("US-062-AC2: invalid inputs show every violation at its field and offer no invoke", async () => {
    const user = userEvent.setup();
    api.on((r) =>
      verb("validate")(r)
        ? json(
            200,
            validation({
              ok: false,
              effects: [],
              violations: [
                { path: "inputs.level", code: "type", message: "expected a string" },
                { path: "inputs.solution", code: "required", message: "a value is required" },
              ],
            }),
          )
        : undefined,
    );
    form();
    await user.type(await screen.findByLabelText(/^solution/), "x");
    await user.type(screen.getByLabelText(/^level/), "y");
    await user.tab();
    await waitFor(() =>
      expect(screen.getByTestId("violation-level")).toHaveTextContent("expected a string"),
    );
    expect(screen.getByTestId("violation-solution")).toHaveTextContent("a value is required");
    expect(screen.getByTestId("not-valid")).toBeInTheDocument();
    expect(screen.getByTestId("confirm")).toBeDisabled();
    expect(calls("invoke")).toHaveLength(0);
  });

  it("US-062-AC2: a failed precondition is shown with its reason", async () => {
    const user = userEvent.setup();
    api.on((r) =>
      verb("validate")(r)
        ? json(
            200,
            validation({
              ok: false,
              effects: [],
              failures: [{ id: "exists", reason: "no such solution" }],
            }),
          )
        : undefined,
    );
    form("catalog.CorrectSolution", { solution: "nope" });
    await user.type(await screen.findByLabelText(/^level/), "x");
    await user.tab();
    expect(await screen.findByTestId("precondition-exists")).toHaveTextContent("no such solution");
    expect(screen.getByTestId("confirm")).toBeDisabled();
  });

  it("US-062-AC3: valid inputs show the effects the invoke would apply, and nothing has changed", async () => {
    const user = userEvent.setup();
    api.on((r) => (verb("validate")(r) ? json(200, validation()) : undefined));
    form("catalog.CorrectSolution", { solution: "sol-1" });
    await user.type(await screen.findByLabelText(/^level/), "partial");
    await user.tab();
    const effects = await screen.findByTestId("effects");
    expect(within(effects).getByTestId("effect")).toHaveTextContent("update");
    expect(effects).toHaveTextContent("Solution sol-1");
    expect(effects).toHaveTextContent('set coverageLevel="partial"');
    expect(calls("invoke")).toHaveLength(0); // validating applies nothing
    expect(screen.getByTestId("confirm")).toBeEnabled();
    expect(screen.queryByTestId("receipt")).toBeNull();
  });

  it("US-062-AC3: effects of every kind are shown, and a delete warns that it cannot be undone", async () => {
    const user = userEvent.setup();
    const ref = { type: "catalog.Solution", key: "sol-1", generated: false };
    api.on((r) =>
      verb("validate")(r)
        ? json(
            200,
            validation({
              effects: [
                {
                  kind: "create",
                  ref: { type: "catalog.UseCase", key: "x", generated: true },
                  properties: { name: "N" },
                },
                { kind: "update", ref, set: { coverageLevel: "full" }, unset: ["name"] },
                { kind: "delete", ref },
                {
                  kind: "link",
                  relationship: "addresses",
                  source: ref,
                  target: { type: "catalog.UseCase", key: "uc-1" },
                },
                {
                  kind: "unlink",
                  relationship: "addresses",
                  source: ref,
                  target: { type: "catalog.UseCase", key: "uc-2" },
                },
              ],
            }),
          )
        : undefined,
    );
    form("catalog.CorrectSolution", { solution: "sol-1", level: "x" });
    await user.click(await screen.findByTestId("validate"));
    const effects = await screen.findByTestId("effects");
    expect(within(effects).getAllByTestId("effect")).toHaveLength(5);
    expect(effects).toHaveTextContent("(new key)");
    expect(effects).toHaveTextContent("unset name");
    expect(effects).toHaveTextContent("addresses");
    expect(effects).toHaveTextContent("A delete cannot be undone from the console");
  });

  it("US-062-AC4: a confirmed invoke sends a generated idempotency key and the module revision, and shows the receipt", async () => {
    const user = userEvent.setup();
    api.on((r) => (verb("validate")(r) ? json(200, validation()) : undefined));
    api.on((r) => (verb("invoke")(r) ? json(200, receipt()) : undefined));
    form("catalog.CorrectSolution", { solution: "sol-1" });
    await user.type(await screen.findByLabelText(/^level/), "partial");
    await user.tab();
    await screen.findByTestId("effects");
    expect(calls("invoke")).toHaveLength(0); // an explicit confirmation is required
    await user.click(screen.getByTestId("confirm"));
    const r = await screen.findByTestId("receipt");
    expect(r).toHaveTextContent("catalog.Solution");
    expect(r).toHaveTextContent("sol-1");
    expect(r).toHaveTextContent("updated 1");
    expect(r).toHaveTextContent("group g-4");
    expect(r).toHaveTextContent("token fake:4");
    const sent = defined(calls("invoke")[0], 'calls("invoke")[0]').body;
    expect(defined(calls("invoke")[0], 'calls("invoke")[0]').path).toBe(
      "/api/operate/actions/catalog/CorrectSolution/invoke",
    );
    expect(sent.idempotency_key).toMatch(/^[0-9a-f-]{36}$/);
    expect(sent.expected_revision).toEqual({ memory: 1 });
    expect(sent.inputs).toEqual({ solution: "sol-1", level: "partial" });
    // The validate before it carried the same revision.
    expect(defined(calls("validate")[0], 'calls("validate")[0]').body.expected_revision).toEqual({
      memory: 1,
    });
  });

  it("US-062-AC4: the same key sent again shows a replay", async () => {
    const user = userEvent.setup();
    api.on((r) => (verb("validate")(r) ? json(200, validation()) : undefined));
    api.on((r) => (verb("invoke")(r) ? json(200, receipt({ replayed: true })) : undefined));
    form("catalog.CorrectSolution", { solution: "sol-1", level: "partial" });
    await user.click(await screen.findByTestId("validate"));
    await user.click(await screen.findByTestId("confirm"));
    const r = await screen.findByTestId("receipt");
    expect(r).toHaveTextContent("Already applied");
    expect(r).toHaveTextContent("replay");
  });

  it("US-062 edge: a double click is one change", async () => {
    const user = userEvent.setup();
    api.on((r) => (verb("validate")(r) ? json(200, validation()) : undefined));
    let release: () => void = () => undefined;
    const gate = new Promise<void>((res) => (release = res));
    api.on(async (r) => {
      if (!verb("invoke")(r)) return undefined;
      await gate;
      return json(200, receipt());
    });
    form("catalog.CorrectSolution", { solution: "sol-1", level: "partial" });
    await user.click(await screen.findByTestId("validate"));
    const confirm = await screen.findByTestId("confirm");
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    release();
    await screen.findByTestId("receipt");
    expect(calls("invoke")).toHaveLength(1);
  });

  it("US-062-AC5: a revision that changed shows the conflict, rebuilds the form and applies nothing", async () => {
    const user = userEvent.setup();
    api.on((r) => (verb("validate")(r) ? json(200, validation()) : undefined));
    let conflict = true;
    api.on((r) => {
      if (!verb("invoke")(r)) return undefined;
      if (conflict) {
        conflict = false;
        api.modules = [catalog({ revision: { memory: 2 } })]; // the registry moved on
        return err(409, wire.conflict());
      }
      return json(200, receipt());
    });
    form("catalog.CorrectSolution", { solution: "sol-1", level: "partial" });
    await user.click(await screen.findByTestId("validate"));
    await user.click(await screen.findByTestId("confirm"));
    const banner = await screen.findByText(/The module changed while this form was open/);
    expect(banner.closest("[role=alert]")).toHaveTextContent('"memory":2');
    expect(screen.queryByTestId("receipt")).toBeNull();
    // The form is rebuilt: values kept, the effects must be reviewed again, confirmation is not offered.
    expect(screen.getByLabelText(/^level/)).toHaveValue("partial");
    expect(screen.getByTestId("confirm")).toBeDisabled();
    // The next validate and invoke carry the new revision.
    await user.click(screen.getByTestId("validate"));
    await user.click(
      await waitFor(() => {
        const b = screen.getByTestId("confirm");
        expect(b).toBeEnabled();
        return b;
      }),
    );
    await screen.findByTestId("receipt");
    expect(
      defined(calls("validate").at(-1), 'calls("validate").at(-1)').body.expected_revision,
    ).toEqual({ memory: 2 });
    expect(
      defined(calls("invoke").at(-1), 'calls("invoke").at(-1)').body.expected_revision,
    ).toEqual({ memory: 2 });
  });

  it("US-062-AC6: a batch of 20 applied independently shows 19 receipts and one refusal with its index", async () => {
    const user = userEvent.setup();
    api.on((r) => {
      if (!verb("batch")(r)) return undefined;
      const items = Array.from({ length: 20 }, (_, i) =>
        i === 7
          ? {
              index: i,
              refusal: {
                ...wire.precondition(),
                failures: [{ id: "exists", reason: "no such solution" }],
              },
            }
          : {
              index: i,
              receipt: receipt({
                refs: [{ type: "catalog.Solution", key: `s-${i}`, version: 2 }],
                group: `g-${i}`,
              }),
            },
      );
      return json(200, {
        action: "catalog.CorrectSolution",
        atomic: false,
        items,
        succeeded: 19,
        failed: 1,
        token: "fake:9",
      });
    });
    renderPart(<BatchForm module="catalog" action="catalog.CorrectSolution" />);
    const items = Array.from({ length: 20 }, (_, i) => ({ solution: `s-${i}`, level: "x" }));
    fireEvent.change(await screen.findByLabelText("Items"), {
      target: { value: JSON.stringify(items) },
    });
    expect(screen.getByText("20 items")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Review batch/ }));
    expect(calls("batch")).toHaveLength(0); // explicit confirmation first
    await user.click(screen.getByRole("button", { name: /Confirm and apply batch/ }));
    const result = await screen.findByTestId("batch-result");
    expect(result).toHaveTextContent("19 applied");
    expect(result).toHaveTextContent("1 refused");
    expect(within(result).getAllByTestId("receipt")).toHaveLength(19);
    expect(screen.getByTestId("batch-refusal-7")).toHaveTextContent("exists: no such solution");
    expect(screen.getByTestId("batch-item-7")).toHaveTextContent("#7");
    const sent = defined(calls("batch")[0], 'calls("batch")[0]').body;
    expect(sent.atomic).toBe(false);
    expect(sent.items).toHaveLength(20);
    expect(sent.idempotency_key).toBeTruthy();
    expect(sent.expected_revision).toEqual({ memory: 1 });
  });

  it("US-062 batch: more than 100 items is refused in the browser", async () => {
    renderPart(<BatchForm module="catalog" action="catalog.CorrectSolution" />);
    fireEvent.change(await screen.findByLabelText("Items"), {
      target: { value: JSON.stringify(Array.from({ length: 101 }, () => ({}))) },
    });
    expect(screen.getByRole("alert")).toHaveTextContent("1 to 100");
    expect(screen.getByRole("button", { name: /Review batch/ })).toBeDisabled();
  });

  it("US-062 edge: a viewer without write access sees the refusal and its reason, and no invoke is offered", async () => {
    const user = userEvent.setup();
    api.on((r) => (verb("validate")(r) ? err(403, wire.refused()) : undefined));
    form("catalog.CorrectSolution", { solution: "sol-1", level: "partial" });
    await user.click(await screen.findByTestId("validate"));
    const alert = await screen.findByText(/The provider refused you/);
    expect(alert).toHaveTextContent("no_access");
    expect(screen.queryByTestId("confirm")).toBeNull();
    expect(screen.getByLabelText(/^level/)).toBeDisabled();
    expect(screen.getByTestId("validate")).toBeDisabled();
  });

  it("US-062: an action is prefilled from an entity row, and the list marks a refused action", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/catalog/entities/catalog.Solution";
    api.on((r) => (verb("validate")(r) ? err(403, wire.refused()) : undefined));
    renderConsole({ hashRouting: true });
    await user.click(await screen.findByText("sol-1"));
    await user.click(await screen.findByRole("button", { name: /CorrectSolution/ }));
    const solution = await screen.findByLabelText(/^solution/);
    expect(solution).toHaveValue("sol-1");
    await user.type(screen.getByLabelText(/^level/), "x");
    await user.tab();
    await screen.findByText(/The provider refused you/);
    expect(screen.getByRole("navigation", { name: "Actions" })).toHaveTextContent("no access");
  });
});

describe("Client limits (CONTRACT-009)", () => {
  it("never has more than four requests in flight", async () => {
    let live = 0;
    let peak = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        live++;
        peak = Math.max(peak, live);
        await new Promise((r) => setTimeout(r, 5));
        live--;
        return new Response(JSON.stringify(validation()), { status: 200 });
      }),
    );
    const c = createClient({ operateBase: "/api/operate", consoleBase: "/api/console" });
    await Promise.all(
      Array.from({ length: 12 }, () => c.validate("catalog", "catalog.A", { inputs: {} })),
    );
    expect(peak).toBe(4);
  });

  it("a 429 backs off for Retry-After and tries again", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ error: { type: "TooManyRequests", message: "too many requests" } }),
          { status: 429, headers: { "retry-after": "2" } },
        ),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify(validation()), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const c = createClient({ operateBase: "/api/operate", consoleBase: "/api/console" });
    const p = c.validate("catalog", "catalog.A", { inputs: {} });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1900);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });
    await expect(p).resolves.toMatchObject({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("Actions area", () => {
  it("lists the declared actions and builds the form for the chosen one", async () => {
    const user = userEvent.setup();
    let chosen: string | undefined;
    renderPart(<ActionsArea module="catalog" onAction={(a) => (chosen = a)} />);
    const nav = await screen.findByRole("navigation", { name: "Actions" });
    expect(within(nav).getAllByRole("button")).toHaveLength(2);
    await user.click(within(nav).getByRole("button", { name: /CorrectSolution/ }));
    expect(chosen).toBe("catalog.CorrectSolution");
  });
});

describe("View in Explore on a receipt (FR-71)", () => {
  const toExplore = crossLinks({
    hash: true,
    openOperate: () => {},
    openExplore: () => {},
  }).toExplore;

  const apply = async (ui: ReactElement) => {
    const user = userEvent.setup();
    api.on((r) => (verb("validate")(r) ? json(200, validation()) : undefined));
    api.on((r) => (verb("invoke")(r) ? json(200, receipt()) : undefined));
    renderPart(ui);
    await user.type(await screen.findByLabelText(/^level/), "partial");
    await user.tab();
    await screen.findByTestId("effects");
    await user.click(screen.getByTestId("confirm"));
    return await screen.findByRole("region", { name: "Receipt" });
  };

  it("opens the changed entity in Explore for an operator", async () => {
    const section = await apply(
      <NavProvider go={() => {}} auditShown toExplore={toExplore}>
        <ActionForm
          module="catalog"
          action="catalog.CorrectSolution"
          prefill={{ solution: "sol-1" }}
        />
      </NavProvider>,
    );
    const section2 = section.parentElement as HTMLElement;
    expect(within(section2).getByRole("link", { name: /View in Explore/ })).toHaveAttribute(
      "href",
      "#/explore/catalog/Solution/sol-1",
    );
  });

  it("draws none without the shell's primitive", async () => {
    const section = await apply(
      <ActionForm
        module="catalog"
        action="catalog.CorrectSolution"
        prefill={{ solution: "sol-1" }}
      />,
    );
    expect(within(section.parentElement as HTMLElement).queryByText(/Explore/)).toBeNull();
  });
});
