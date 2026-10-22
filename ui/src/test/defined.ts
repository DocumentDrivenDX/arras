// SPDX-License-Identifier: MIT OR Apache-2.0
/** A value a test knows is there: narrows it, or fails the test naming what was missing. */
export function defined<T>(value: T | null | undefined, what = "value"): T {
  if (value === null || value === undefined) throw new Error(`expected ${what} to be defined`);
  return value;
}
