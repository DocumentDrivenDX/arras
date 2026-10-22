// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/errors";
import { ErrorPanel } from "../components/ui";
import { renderPart } from "./render";

// A 401 (kind sign_in): "Sign in again" when the host supplied onUnauthorized (FEAT-010).
const expired = () => new ApiError(401, { type: "Unauthorized", reason: "token_expired" });

describe("the sign-in panel", () => {
  it("offers Sign in again, once per click, beside Retry, when the host supplied onUnauthorized", async () => {
    const user = userEvent.setup();
    const onUnauthorized = vi.fn();
    const retry = vi.fn();
    renderPart(<ErrorPanel error={expired()} onRetry={retry} inputsKept />, { onUnauthorized });
    expect(screen.getByRole("alert")).toHaveTextContent("What you typed is kept.");
    await user.click(screen.getByRole("button", { name: "Sign in again" }));
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    expect(retry).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledTimes(1);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("keeps Retry and the guidance, with no sign-in button, when the host gave none", () => {
    renderPart(<ErrorPanel error={expired()} onRetry={() => {}} />);
    expect(screen.queryByRole("button", { name: "Sign in again" })).toBeNull();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Sign in, then retry.");
  });

  it("says inputs are kept only where they are, and only for a sign-in", () => {
    const { unmount } = renderPart(<ErrorPanel error={expired()} />);
    expect(screen.getByRole("alert")).not.toHaveTextContent("What you typed is kept");
    unmount();
    renderPart(<ErrorPanel error={new ApiError(503, {})} inputsKept />, {
      onUnauthorized: vi.fn(),
    });
    expect(screen.getByRole("alert")).not.toHaveTextContent("What you typed is kept");
    expect(screen.queryByRole("button", { name: "Sign in again" })).toBeNull();
  });
});
