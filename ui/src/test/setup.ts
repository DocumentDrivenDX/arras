// SPDX-License-Identifier: MIT OR Apache-2.0
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

// React reports invalid markup (`<div>` in `<p>`, `<button>` in `<button>`) only through console.error.
// Fail the test that renders it instead of leaving a warning in the log.
const nesting: string[] = [];
beforeEach(() => {
  nesting.length = 0;
  // biome-ignore lint/suspicious/noConsole: the spy forwards to the real console.error
  const log = console.error.bind(console);
  vi.spyOn(console, "error").mockImplementation((...args: unknown[]) => {
    const text = args.map(String).join(" ");
    if (
      text.includes("validateDOMNesting") ||
      /cannot (contain a nested|be a descendant of)/.test(text)
    )
      nesting.push(text);
    log(...args);
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  if (nesting.length) throw new Error(`Invalid DOM nesting:\n${nesting.join("\n")}`);
});
