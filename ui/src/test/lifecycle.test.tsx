// SPDX-License-Identifier: MIT OR Apache-2.0
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { ActionForm } from "../areas/ActionForm";
import { BatchForm } from "../areas/BatchForm";
import { defined } from "./defined";
import {
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
import { renderPart } from "./render";

// The idempotency key's life (CONTRACT-009): one key per change the operator confirms. A retry of the
// same change (after a 503 or a dropped connection) sends the same key so the server applies it at
// most once; a conflict or a different change gets a new key.

let api: FakeApi;
beforeEach(() => {
  api = stage();
  seedCatalog(api);
});
const verb = (v: string) => (r: Recorded) => r.method === "POST" && r.path.endsWith(`/${v}`);
const calls = (v: string) => api.log.filter(verb(v));
const keys = (v: string) => calls(v).map((r) => r.body.idempotency_key as string);
const enabled = (id: string) =>
  waitFor(() => {
    const b = screen.getByTestId(id);
    expect(b).toBeEnabled();
    return b;
  });
const single = (prefill = { solution: "sol-1", level: "partial" }) =>
  renderPart(<ActionForm module="catalog" action="catalog.CorrectSolution" prefill={prefill} />);

/** Answer invokes from a queue of replies; a function reply may throw (a dropped connection). */
function invokes(...replies: (ReturnType<typeof json> | (() => never))[]) {
  api.on((r) => {
    if (!verb("invoke")(r)) return undefined;
    const next = replies.shift() ?? json(200, receipt());
    return typeof next === "function" ? next() : next;
  });
}

describe("ActionForm: the idempotency key", () => {
  beforeEach(() => {
    api.on((r) => (verb("validate")(r) ? json(200, validation()) : undefined));
  });

  it("a retry after a 503 sends the same key, and the change applies once", async () => {
    const user = userEvent.setup();
    invokes(err(503, wire.unavailable()));
    single();
    await user.click(await screen.findByTestId("validate"));
    await user.click(await enabled("confirm"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Backend unavailable");
    expect(screen.queryByTestId("receipt")).toBeNull();
    await user.click(await enabled("confirm"));
    await screen.findByTestId("receipt");
    expect(keys("invoke")).toHaveLength(2);
    expect(keys("invoke")[1]).toBe(keys("invoke")[0]);
  });

  it("a retry after a dropped connection sends the same key", async () => {
    const user = userEvent.setup();
    invokes(() => {
      throw new TypeError("fetch failed");
    });
    single();
    await user.click(await screen.findByTestId("validate"));
    await user.click(await enabled("confirm"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Network error");
    await user.click(await enabled("confirm"));
    await screen.findByTestId("receipt");
    expect(new Set(keys("invoke")).size).toBe(1);
    expect(keys("invoke")).toHaveLength(2);
  });

  it("a 409 conflict mints a new key for the next confirmation", async () => {
    const user = userEvent.setup();
    invokes(err(409, { type: "Conflict", message: "conflict (version)", reason: "version" }));
    single();
    await user.click(await screen.findByTestId("validate"));
    await user.click(await enabled("confirm"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Conflict");
    await user.click(await enabled("confirm"));
    await screen.findByTestId("receipt");
    const [a, b] = keys("invoke");
    expect(a).toBeTruthy();
    expect(b).toBeTruthy();
    expect(b).not.toBe(a);
  });

  it("a revision conflict rebuilds the form and the next confirmation carries a new key", async () => {
    const user = userEvent.setup();
    invokes(err(409, wire.conflict()));
    single();
    await user.click(await screen.findByTestId("validate"));
    await user.click(await enabled("confirm"));
    await screen.findByText(/The module changed while this form was open/);
    await user.click(screen.getByTestId("validate"));
    await user.click(await enabled("confirm"));
    await screen.findByTestId("receipt");
    const [a, b] = keys("invoke");
    expect(b).not.toBe(a);
  });

  it("after a receipt, Run again with changed inputs sends a new key", async () => {
    const user = userEvent.setup();
    invokes();
    single();
    await user.click(await screen.findByTestId("validate"));
    await user.click(await enabled("confirm"));
    await screen.findByTestId("receipt");
    await user.click(screen.getByRole("button", { name: "Run again" }));
    expect(screen.queryByTestId("receipt")).toBeNull();
    expect(screen.getByLabelText(/^level/)).toHaveValue("partial"); // the prefill again
    expect(screen.getByTestId("confirm")).toBeDisabled(); // a fresh review is needed
    const level = screen.getByLabelText(/^level/);
    await user.clear(level);
    await user.type(level, "full");
    await user.tab();
    await user.click(await enabled("confirm"));
    await waitFor(() => expect(keys("invoke")).toHaveLength(2));
    expect(defined(calls("invoke")[1], "calls(invoke)[1]").body.inputs.level).toBe("full");
    expect(keys("invoke")[1]).not.toBe(keys("invoke")[0]);
  });

  it("after a receipt, Run again with the same inputs still sends a new key (a new change, not a retry)", async () => {
    const user = userEvent.setup();
    invokes();
    single();
    await user.click(await screen.findByTestId("validate"));
    await user.click(await enabled("confirm"));
    await screen.findByTestId("receipt");
    await user.click(screen.getByRole("button", { name: "Run again" }));
    await user.click(screen.getByTestId("validate"));
    await user.click(await enabled("confirm"));
    await waitFor(() => expect(keys("invoke")).toHaveLength(2));
    expect(keys("invoke")[1]).not.toBe(keys("invoke")[0]);
  });
});

describe("ActionForm: a refusal at invoke after a passing validate", () => {
  beforeEach(() => {
    api.on((r) => (verb("validate")(r) ? json(200, validation()) : undefined));
  });

  it("400: the violations are shown at their fields and confirmation waits for a new review", async () => {
    const user = userEvent.setup();
    invokes(err(400, wire.invalid()));
    single();
    await user.click(await screen.findByTestId("validate"));
    await user.click(await enabled("confirm"));
    expect(await screen.findByTestId("violation-level")).toHaveTextContent(
      "a value is required (required)",
    );
    expect(screen.getByTestId("confirm")).toBeDisabled();
    expect(screen.queryByTestId("receipt")).toBeNull();
    // Editing the field clears the server's word on it.
    await user.type(screen.getByLabelText(/^level/), "!");
    expect(screen.queryByTestId("violation-level")).toBeNull();
  });

  it("400 without violations shows the error itself", async () => {
    const user = userEvent.setup();
    invokes(err(400, wire.badRequest("send application/json")));
    single();
    await user.click(await screen.findByTestId("validate"));
    await user.click(await enabled("confirm"));
    expect(await screen.findByRole("alert")).toHaveTextContent("send application/json");
  });

  it("422: the failed precondition is shown with its reason and nothing is applied", async () => {
    const user = userEvent.setup();
    invokes(
      err(422, {
        ...wire.precondition(),
        failures: [{ id: "exists", reason: "no such solution" }],
      }),
    );
    single();
    await user.click(await screen.findByTestId("validate"));
    await user.click(await enabled("confirm"));
    expect(await screen.findByTestId("precondition-exists")).toHaveTextContent(
      "✗ exists: no such solution",
    );
    expect(screen.getByTestId("confirm")).toBeDisabled();
    expect(screen.queryByTestId("receipt")).toBeNull();
    // A fresh review offers confirmation again.
    await user.click(screen.getByTestId("validate"));
    await enabled("confirm");
  });

  it("422 for a precondition the action does not declare is still listed", async () => {
    const user = userEvent.setup();
    invokes(
      err(422, {
        ...wire.precondition(),
        failures: [{ id: "conflict:version", reason: "conflict (version)" }],
      }),
    );
    single();
    await user.click(await screen.findByTestId("validate"));
    await user.click(await enabled("confirm"));
    expect(await screen.findByTestId("precondition-conflict:version")).toHaveTextContent(
      "conflict (version)",
    );
  });
});

describe("ActionForm: validate answers in order", () => {
  it("a slow first validate that returns after a newer one is dropped", async () => {
    const user = userEvent.setup();
    let release: () => void = () => undefined;
    const gate = new Promise<void>((r) => (release = r));
    let n = 0;
    api.on(async (r) => {
      if (!verb("validate")(r)) return undefined;
      const level = r.body.inputs.level as string;
      if (++n === 1) await gate; // the first validate is held
      return json(
        200,
        validation({
          effects: [
            {
              kind: "update",
              ref: { type: "catalog.Solution", key: "sol-1", generated: false },
              set: { coverageLevel: level },
              unset: [],
            },
          ],
        }),
      );
    });
    single({ solution: "sol-1", level: "" } as never);
    const level = await screen.findByLabelText(/^level/);
    await user.type(level, "first");
    await user.tab(); // validate #1, held
    await waitFor(() => expect(calls("validate")).toHaveLength(1));
    await user.clear(level);
    await user.type(level, "second");
    await user.tab(); // validate #2 answers at once
    await waitFor(() =>
      expect(screen.getByTestId("effects")).toHaveTextContent('set coverageLevel="second"'),
    );
    release();
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByTestId("effects")).toHaveTextContent('set coverageLevel="second"');
    expect(screen.getByTestId("effects")).not.toHaveTextContent("first");
    expect(screen.getByTestId("confirm")).toBeEnabled();
  });
});

describe("BatchForm: the request and its key", () => {
  const items = [
    { code: "b-1", name: "B1" },
    { code: "uc-1", name: "dup" },
  ];
  async function paste(user: ReturnType<typeof userEvent.setup>, value: unknown = items) {
    fireEvent.change(await screen.findByLabelText("Items"), {
      target: { value: JSON.stringify(value) },
    });
    await user.click(screen.getByRole("button", { name: /Review batch/ }));
  }
  const apply = (user: ReturnType<typeof userEvent.setup>) =>
    user.click(screen.getByRole("button", { name: /Confirm and apply batch/ }));
  const batches = (...replies: ReturnType<typeof json>[]) =>
    api.on((r) => (verb("batch")(r) ? (replies.shift() ?? json(200, wire.batch())) : undefined));
  const form = () => renderPart(<BatchForm module="catalog" action="catalog.AddUseCase" />);

  it("sends atomic and stop_on_error as chosen; atomic disables stop-on-error", async () => {
    const user = userEvent.setup();
    batches(json(200, wire.batch()), json(200, wire.batch({ atomic: true })));
    form();
    await screen.findByLabelText("Items");
    await user.click(screen.getByLabelText(/Stop on first error/));
    await paste(user);
    await apply(user);
    await screen.findByTestId("batch-result");
    expect(defined(calls("batch")[0], "calls(batch)[0]").body).toMatchObject({
      atomic: false,
      stop_on_error: true,
      items,
    });
    await user.click(screen.getByLabelText(/Atomic/));
    expect(screen.getByLabelText(/Stop on first error/)).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /Review batch/ }));
    expect(screen.getByRole("alert")).toHaveTextContent("atomically: if one fails none apply");
    await apply(user);
    await waitFor(() => expect(calls("batch")).toHaveLength(2));
    expect(defined(calls("batch")[1], "calls(batch)[1]").body).toMatchObject({ atomic: true });
    expect(screen.getByTestId("batch-result")).toHaveTextContent("atomic");
  });

  it("an atomic batch refused as a whole (422) applies nothing and lists the failed precondition", async () => {
    const user = userEvent.setup();
    batches(err(422, wire.precondition()));
    form();
    await screen.findByLabelText("Items");
    await user.click(screen.getByLabelText(/Atomic/));
    await paste(user);
    await apply(user);
    const alert = await screen.findByText("A precondition failed");
    expect(alert.closest("[role=alert]")).toHaveTextContent(
      "Nothing was applied. fresh: a use case with that code exists",
    );
    expect(screen.queryByTestId("batch-result")).toBeNull();
  });

  it("a 400 for one item names the item's path", async () => {
    const user = userEvent.setup();
    batches(
      err(400, {
        ...wire.invalid(),
        violations: [
          { path: "items[1].inputs.name", code: "required", message: "a value is required" },
        ],
      }),
    );
    form();
    await paste(user);
    await apply(user);
    expect(
      await screen.findByText(/items\[1\]\.inputs\.name: a value is required/),
    ).toBeInTheDocument();
  });

  it("an independent batch shows each refusal at its index", async () => {
    const user = userEvent.setup();
    batches(json(200, wire.batch()));
    form();
    await paste(user);
    await apply(user);
    const result = await screen.findByTestId("batch-result");
    expect(result).toHaveTextContent("1 applied");
    expect(result).toHaveTextContent("1 refused");
    expect(within(screen.getByTestId("batch-item-0")).getByTestId("receipt")).toHaveTextContent(
      "b-1",
    );
    expect(screen.getByTestId("batch-refusal-1")).toHaveTextContent(
      "Refused: a precondition failed",
    );
    expect(screen.getByTestId("batch-refusal-1")).toHaveTextContent(
      "fresh: a use case with that code exists",
    );
  });

  it("a retry after a 503 sends the same key; a 409 mints a new one; changed items a new one", async () => {
    const user = userEvent.setup();
    batches(
      err(503, wire.unavailable()),
      json(200, wire.batch()),
      err(409, wire.conflict()),
      json(200, wire.batch()),
      json(200, wire.batch()),
    );
    form();
    await paste(user);
    await apply(user); // 503
    expect(await screen.findByText("Backend unavailable")).toBeInTheDocument();
    await apply(user); // the same change again: 200
    await screen.findByTestId("batch-result");
    expect(keys("batch")[1]).toBe(keys("batch")[0]);

    await user.click(screen.getByRole("button", { name: /Review batch/ }));
    await apply(user); // 409 revision (the same items again: a replay would have kept the key)
    await waitFor(() => expect(calls("batch")).toHaveLength(3));
    await screen.findByText("Conflict");
    await user.click(screen.getByRole("button", { name: /Review batch/ }));
    await apply(user); // after the conflict: a new key
    await waitFor(() => expect(calls("batch")).toHaveLength(4));
    expect(keys("batch")[3]).not.toBe(keys("batch")[2]);

    await paste(user, [{ code: "b-9", name: "B9" }]);
    await apply(user); // different items: a new key
    await waitFor(() => expect(calls("batch")).toHaveLength(5));
    const k = keys("batch");
    // The same items confirmed again after a success replay under the same key (applied at most once);
    // the conflict's retry and the different items each got a key of their own.
    expect(k[2]).toBe(k[1]);
    expect(new Set(k).size).toBe(3);
    expect(k[4]).not.toBe(k[3]);
  });

  it("a refused viewer cannot run a batch; not offered is worded as such", async () => {
    const user = userEvent.setup();
    batches(err(403, wire.notOffered()));
    form();
    await paste(user);
    await apply(user);
    expect(
      await screen.findByText(/Not offered: this host does not offer that action to you/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Items")).toBeDisabled();
    expect(screen.queryByText(/Request failed/)).toBeNull();
  });

  it("a non-array or empty paste is refused in the browser", async () => {
    form();
    const box = await screen.findByLabelText("Items");
    fireEvent.change(box, { target: { value: "{" } });
    expect(screen.getByRole("alert")).toHaveTextContent("not valid JSON");
    fireEvent.change(box, { target: { value: '{"a":1}' } });
    expect(screen.getByRole("alert")).toHaveTextContent("Paste a JSON array");
    fireEvent.change(box, { target: { value: "[1]" } });
    expect(screen.getByRole("alert")).toHaveTextContent("Paste a JSON array");
    fireEvent.change(box, { target: { value: "[]" } });
    expect(screen.getByRole("alert")).toHaveTextContent("this has 0");
  });
});
