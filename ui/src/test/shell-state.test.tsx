// SPDX-License-Identifier: MIT OR Apache-2.0
import { act, render, renderHook, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { createQueryClient } from "../api/context";
import { ArrasApp } from "../shell";
import { useShellState } from "../shell/ShellState";
import { stageBrowser } from "./browserFake";

describe("the shell's state (SD-013 D6)", () => {
  it("starts with the lock off, the single-key switch on, and the help and palette closed", () => {
    const { result } = renderHook(() => useShellState());
    expect(result.current).toMatchObject({
      editing: false,
      singleKeys: true,
      helpOpen: false,
      paletteOpen: false,
    });
  });

  it("holds each piece apart from the others", () => {
    const { result } = renderHook(() => useShellState());
    act(() => result.current.setEditing(true));
    expect(result.current.editing).toBe(true);
    expect(result.current.singleKeys).toBe(true);
    act(() => result.current.setSingleKeys(false));
    act(() => result.current.openHelp());
    act(() => result.current.openPalette());
    expect(result.current).toMatchObject({
      editing: true,
      singleKeys: false,
      helpOpen: true,
      paletteOpen: true,
    });
    act(() => result.current.closeHelp());
    act(() => result.current.closePalette());
    expect(result.current).toMatchObject({ helpOpen: false, paletteOpen: false, editing: true });
  });

  it("keeps the same callbacks from one render to the next, so a listener is not rebound for nothing", () => {
    const { result, rerender } = renderHook(() => useShellState());
    const first = result.current;
    act(() => result.current.openHelp());
    rerender();
    for (const k of ["setEditing", "setSingleKeys", "openHelp", "closeHelp"] as const)
      expect(result.current[k]).toBe(first[k]);
    expect(result.current.openPalette).toBe(first.openPalette);
    expect(result.current.closePalette).toBe(first.closePalette);
  });

  it("keeps nothing in the browser's storage", () => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    const { result } = renderHook(() => useShellState());
    act(() => {
      result.current.setEditing(true);
      result.current.setSingleKeys(false);
    });
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });
});

describe("the fragment's mode, read before its query (CONTRACT-010 D)", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
    window.location.hash = "";
    const fake = stageBrowser();
    fake.mods = fake.mods.slice(0, 1);
  });
  afterEach(() => {
    window.location.hash = "";
  });

  it("an operator at a list position (#/explore/<module>/<type>?after=<key>) stays in Explore and the fragment is left as it is", async () => {
    window.location.hash = "#/explore/catalog/UseCase?after=a-1";
    render(<ArrasApp queryClient={createQueryClient()} />);
    await screen.findByRole("group", { name: "Mode" });
    await act(async () => undefined);
    expect(window.location.hash).toBe("#/explore/catalog/UseCase?after=a-1");
    expect(screen.queryByTestId("console-header")).toBeNull();
    expect(screen.getByRole("button", { name: "Explore" })).toHaveAttribute("aria-pressed", "true");
  });

  it("a query on a bare #/explore is Explore's too, not the console's alias form", async () => {
    window.location.hash = "#/explore?after=x";
    render(<ArrasApp queryClient={createQueryClient()} />);
    await screen.findByRole("group", { name: "Mode" });
    await act(async () => undefined);
    expect(window.location.hash).toBe("#/explore?after=x");
    expect(screen.queryByTestId("console-header")).toBeNull();
  });
});
