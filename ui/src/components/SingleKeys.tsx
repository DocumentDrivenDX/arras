// SPDX-License-Identifier: MIT OR Apache-2.0
import { createContext, useContext } from "react";

/**
 * Whether the console's single-key shortcuts (a plain character key: `1`-`6`, `?`, `/`) are on. The
 * switch lives in the shortcuts help and in memory only, for the page's lifetime (the console stores
 * nothing); outside the console they are on.
 */
export const SingleKeysCtx = createContext(true);
export const useSingleKeys = () => useContext(SingleKeysCtx);
