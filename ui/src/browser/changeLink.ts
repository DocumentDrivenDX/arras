// SPDX-License-Identifier: MIT OR Apache-2.0
// The cross-mode link slot for a change's group (SD-013, D7): the receipt view in Operate, through
// the context's `toOperate` where the shell handed it over, nothing where it did not. A URL is never
// built here.
import type { CrossLink } from "../kit";
import type { BrowserContext } from "./context";

export function changeLinkFor(
  ctx: Pick<BrowserContext, "toOperate">,
  module: string,
  group: string,
): CrossLink | undefined {
  return ctx.toOperate?.({ group: { module, id: group } }, "changes");
}
