// SPDX-License-Identifier: MIT OR Apache-2.0
import { createContext, type ReactNode, useContext } from "react";

const Inside = createContext(false);

/**
 * The element the library's styles are scoped to (`.arras-root`, scripts/scope-css.ts). Every entry component
 * renders inside one, so the tokens, the reset and the utilities reach nothing of the host's page; one
 * entry nested in another (the shell holds the Graph Browser and the Console) shares the outer element.
 *
 * The root never chooses a colour scheme. It takes the host's: the role tokens (`--arras-*`) a host sets,
 * and where it sets none the `data-appearance="light" | "dark"` on an ancestor, or else
 * `prefers-color-scheme`. No component installs a theme or writes to the host's elements.
 */
export function Scope({ children }: { children: ReactNode }) {
  if (useContext(Inside)) return <>{children}</>;
  return (
    <div className="arras-root">
      <Inside.Provider value>{children}</Inside.Provider>
    </div>
  );
}
