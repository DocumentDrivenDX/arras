// SPDX-License-Identifier: MIT OR Apache-2.0
// `#/explore` with more than one readable module: choose one.
import type { ModuleInfo } from "../api/types";
import { linkProps, useBrowser } from "./context";

export function ModuleChooser({ modules }: { modules: ModuleInfo[] }) {
  const { go } = useBrowser();
  return (
    <>
      <div className="gb-entry-h">
        <h1>Choose a module</h1>
      </div>
      <ul className="gb-hits">
        {modules.map((m) => (
          <li key={m.name}>
            <a className="gb-hit gb-t-slate" {...linkProps(go, { module: m.name })}>
              <span />
              <span className="gb-hit-body">
                <span className="gb-t">{m.view?.title ?? m.name}</span>
                {m.view?.description && <span className="gb-ex">{m.view.description}</span>}
              </span>
              <span />
            </a>
          </li>
        ))}
      </ul>
    </>
  );
}
