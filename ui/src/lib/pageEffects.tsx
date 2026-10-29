// SPDX-License-Identifier: MIT OR Apache-2.0
import { createContext, useContext } from "react";

/** Page ownership is explicit when components share a host application's document. */
export const PageEffects = createContext(true);
export const usePageEffects = () => useContext(PageEffects);
