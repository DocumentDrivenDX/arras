// SPDX-License-Identifier: MIT OR Apache-2.0
import { basename, resolve } from "node:path";

export function resolveAcceptanceTestDir(here: string, exists: (path: string) => boolean): string {
  const packed = resolve(here, "../support/acceptance/e2e");
  if (exists(packed)) return packed;
  const source = resolve(here, "../../e2e");
  if (basename(resolve(here, "..")) === "src" && exists(source)) return source;
  throw new Error("Arras acceptance specs are missing from this package");
}
