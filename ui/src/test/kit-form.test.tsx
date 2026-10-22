// SPDX-License-Identifier: MIT OR Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ArrasClient } from "../api/client";
import { ApiError } from "../api/errors";
import type { ModuleInfo, Receipt } from "../api/types";
import { useAction } from "../browser/useAction";
import { useActionForm } from "../kit";
import { catalog, receipt, validation, wire } from "./fake";

// A fake client in place of the provider's: the kit's model takes it as an input.
const validate = vi.fn();
const invoke = vi.fn();
const client = { validate, invoke } as unknown as ArrasClient;

vi.mock("../api/context", async (orig) => ({
  ...(await orig<typeof import("../api/context")>()),
  useClient: () => client,
}));

const ACTION = "catalog.CorrectSolution";
const module: ModuleInfo = catalog();

const setup = (over: Partial<Parameters<typeof useActionForm>[0]> = {}) => {
  const onApplied = vi.fn<(r: Receipt) => void>();
  const reloadModule = vi.fn(async () => catalog({ revision: { memory: 2 } }));
  const view = renderHook(() =>
    useActionForm({ module, action: ACTION, client, onApplied, reloadModule, ...over }),
  );
  return { ...view, onApplied, reloadModule };
};

const fill = (result: { current: ReturnType<typeof useActionForm> }, level = "partial") => {
  act(() => {
    result.current.onChange("solution", "sol-1");
    result.current.onChange("level", level);
  });
};

beforeEach(() => {
  validate.mockReset().mockResolvedValue(validation());
  invoke.mockReset().mockResolvedValue(receipt());
});

describe("the kit's form model", () => {
  it("validates the built inputs and reports the effects, status and validity", async () => {
    const { result } = setup();
    fill(result);
    await act(() => result.current.validate());
    expect(validate).toHaveBeenCalledWith("catalog", ACTION, {
      inputs: { solution: "sol-1", level: "partial" },
      expected_revision: module.revision,
    });
    expect(result.current.valid).toBe(true);
    expect(result.current.effects).toHaveLength(1);
    expect(result.current.status).toBe("preview");
    expect(result.current.canConfirm).toBe(true);
    // a change to an input makes the review stale
    fill(result, "full");
    expect(result.current.status).toBe("stale");
    expect(result.current.canConfirm).toBe(false);
  });

  it("confirm invokes once with the validated inputs and hands the receipt to onApplied", async () => {
    const { result, onApplied } = setup();
    fill(result);
    await act(() => result.current.validate());
    await act(() => result.current.confirm());
    expect(invoke).toHaveBeenCalledTimes(1);
    expect(invoke.mock.calls[0]?.[2]).toMatchObject({ inputs: { solution: "sol-1" } });
    expect(onApplied).toHaveBeenCalledWith(receipt());
    expect(result.current.receipt).toEqual(receipt());
    expect(result.current.status).toBe("applied");
  });

  it("confirm without a fresh, passing review sends nothing", async () => {
    const { result } = setup();
    fill(result);
    await act(() => result.current.confirm());
    expect(invoke).not.toHaveBeenCalled();
  });

  it("one idempotency key per input signature, and a new one after a conflict", async () => {
    const { result } = setup();
    fill(result);
    await act(() => result.current.validate());
    invoke.mockRejectedValueOnce(new ApiError(503, { type: "Unavailable", message: "later" }));
    await act(() => result.current.confirm());
    await act(() => result.current.confirm());
    const [a, b] = invoke.mock.calls.map((c) => c[2].idempotency_key);
    expect(a).toBeTruthy();
    expect(b).toBe(a); // the retry of the same inputs reuses the key

    act(() => result.current.editAgain());
    await act(() => result.current.validate());
    // a key conflict that is not a revision one clears the key
    invoke
      .mockReset()
      .mockRejectedValueOnce(new ApiError(409, { type: "Conflict", message: "k" }))
      .mockResolvedValue(receipt());
    await act(() => result.current.confirm());
    await act(() => result.current.validate());
    await act(() => result.current.confirm());
    const keys = invoke.mock.calls.map((c) => c[2].idempotency_key);
    expect(keys[0]).not.toBe(a);
    expect(keys[1]).not.toBe(keys[0]);
  });

  it("a different input signature gets a different key", async () => {
    const { result } = setup();
    fill(result);
    await act(() => result.current.validate());
    await act(() => result.current.confirm());
    act(() => result.current.editAgain());
    fill(result, "full");
    await act(() => result.current.validate());
    await act(() => result.current.confirm());
    const [a, b] = invoke.mock.calls.map((c) => c[2].idempotency_key);
    expect(a).not.toBe(b);
  });

  it("a revision conflict reloads the module through reloadModule and rebuilds the form, applying nothing", async () => {
    const { result, reloadModule, onApplied } = setup();
    fill(result);
    await act(() => result.current.validate());
    invoke.mockRejectedValueOnce(new ApiError(409, wire.conflict()));
    await act(() => result.current.confirm());
    expect(reloadModule).toHaveBeenCalledTimes(1);
    expect(result.current.conflict).toBe(true);
    expect(result.current.epoch).toBe(1);
    expect(result.current.checked).toBeNull();
    expect(result.current.revision).toEqual({ memory: 2 });
    expect(result.current.values.solution).toBe("sol-1"); // the typed values stay
    expect(onApplied).not.toHaveBeenCalled();
    // the next review is made under the new revision
    await act(() => result.current.validate());
    expect(validate.mock.calls.at(-1)?.[2].expected_revision).toEqual({ memory: 2 });
  });

  it("returns a refusal without deciding anything: the surface is told and nothing is held for it", async () => {
    const onRefused = vi.fn();
    const { result } = setup({ onRefused });
    fill(result);
    validate.mockRejectedValueOnce(new ApiError(403, wire.refused()));
    await act(() => result.current.validate());
    expect(onRefused).toHaveBeenCalledTimes(1);
    expect(onRefused.mock.calls[0]?.[0].kind).toBe("no_access");
    expect(result.current.locked).toBe(false);
    expect(result.current.error?.kind).toBe("no_access");
    expect(result.current.refusal?.kind).toBe("no_access");
    expect(invoke).not.toHaveBeenCalled();
  });

  it("a refusal the surface holds is returned as given", () => {
    const held = new ApiError(403, wire.notOffered());
    const { result } = setup({ refusal: held });
    expect(result.current.refusal).toBe(held);
    expect(result.current.locked).toBe(true);
  });

  it("a 401 keeps the typed values and the form open", async () => {
    const { result } = setup();
    fill(result);
    validate.mockRejectedValueOnce(new ApiError(401, { type: "Unauthorized", message: "no" }));
    await act(() => result.current.validate());
    expect(result.current.error?.kind).toBe("sign_in");
    expect(result.current.values).toEqual({ solution: "sol-1", level: "partial" });
    expect(result.current.refusal).toBeNull();
    expect(result.current.receipt).toBeNull();
    await act(() => result.current.validate());
    expect(result.current.valid).toBe(true);
  });

  it("an invoke refused as invalid asks for a fresh review and applies nothing", async () => {
    const { result, onApplied } = setup();
    fill(result);
    await act(() => result.current.validate());
    invoke.mockRejectedValueOnce(new ApiError(422, wire.precondition()));
    await act(() => result.current.confirm());
    expect(result.current.failures[0]?.id).toBe("fresh");
    expect(result.current.checked).toBeNull();
    expect(onApplied).not.toHaveBeenCalled();
  });
});

describe("an Explore apply (useAction)", () => {
  it("invalidates the search read by name beside the gb reads", async () => {
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useAction(module), { wrapper });
    let ok = false;
    await act(async () => {
      ok = await result.current.run(ACTION, { solution: "sol-1", level: "partial" });
    });
    expect(ok).toBe(true);
    const keys = spy.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
    expect(keys).toContain(JSON.stringify(["gb"]));
    expect(keys).toContain(JSON.stringify(["gb", "search"]));
    await waitFor(() => expect(result.current.saving).toBe(false));
  });

  it("does not invalidate when the change was not applied", async () => {
    validate.mockResolvedValueOnce(validation({ ok: false }));
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useAction(module), { wrapper });
    await act(async () => {
      await result.current.run(ACTION, {});
    });
    expect(invoke).not.toHaveBeenCalled();
    expect(spy).not.toHaveBeenCalled();
  });
});

describe("the one-shot core's idempotency key", () => {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
  );
  const inputs = { solution: "sol-1", level: "partial" };
  const keys = () => invoke.mock.calls.map((c) => c[2].idempotency_key);

  it("is reused by a retry after a failure", async () => {
    const { result } = renderHook(() => useAction(module), { wrapper });
    invoke.mockRejectedValueOnce(new ApiError(503, { type: "Unavailable", message: "later" }));
    await act(() => result.current.run(ACTION, inputs));
    await act(() => result.current.run(ACTION, inputs));
    expect(keys()).toHaveLength(2);
    expect(keys()[1]).toBe(keys()[0]);
  });

  it("is new for the same inputs sent again after an apply", async () => {
    const { result } = renderHook(() => useAction(module), { wrapper });
    await act(() => result.current.run(ACTION, inputs));
    await act(() => result.current.run(ACTION, inputs));
    expect(keys()).toHaveLength(2);
    expect(keys()[1]).not.toBe(keys()[0]);
  });
});
