// SPDX-License-Identifier: MIT OR Apache-2.0
import { DevHost } from "../dev/DevHost";
import { readBrandMeta } from "../lib/brand";

/** Standard sandbox acceptance host; downstream themes wrap this with their own provider. */
export function AcceptanceHost() {
  return <DevHost brand={readBrandMeta(document)} />;
}
