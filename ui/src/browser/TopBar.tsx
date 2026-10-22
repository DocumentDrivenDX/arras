// SPDX-License-Identifier: MIT OR Apache-2.0
// The top bar (the `banner` landmark): the module's name (a menu when the viewer reads more than
// one), the search box, the host's mode switch, and the freshness line of the record store.
import type { ReactNode } from "react";
import type { BackendStatus, ModuleInfo } from "../api/types";
import { Wordmark } from "../lib/brand";
import { lagOf } from "./NodeFooter";
import { SearchBox } from "./SearchBox";

export interface TopBarProps {
  modules: ModuleInfo[];
  module: ModuleInfo | undefined;
  status: BackendStatus[];
  onModule: (name: string) => void;
  search: { value: string; onChange: (v: string) => void } | null;
  /** The host's slot: the shell's Explore and Operate switch. */
  modeSwitch?: ReactNode;
  toolbar?: ReactNode;
  /** `/` focuses the search box (the Single-key shortcuts switch); default on. */
  slashFocus?: boolean;
}

function ModuleName({ p }: { p: TopBarProps }) {
  const m = p.module;
  const title = m?.view?.title ?? m?.name ?? "Graph Browser";
  const sub = m ? `${m.name} · ${m.entityTypes.length} types` : undefined;
  if (p.modules.length > 1)
    return (
      <label className="gb-mod">
        <span className="gb-sr">Module</span>
        <select
          value={m?.name ?? ""}
          onChange={(e) => p.onModule(e.target.value)}
          aria-label="Module"
        >
          {!m && <option value="">Choose a module</option>}
          {p.modules.map((x) => (
            <option key={x.name} value={x.name}>
              {x.view?.title ?? x.name}
            </option>
          ))}
        </select>
        {sub && <small>{sub}</small>}
      </label>
    );
  return (
    <div className="gb-mod">
      <span>{title}</span>
      {sub && <small>{sub}</small>}
    </div>
  );
}

function StatusLine({ module, status }: { module: ModuleInfo; status: BackendStatus[] }) {
  const s = status.find((x) => x.backend === module.record);
  const down = s ? !s.available : false;
  const lag = lagOf(status, module.record);
  const text = down ? "unavailable" : lag > 0 ? `behind by ${lag}` : "current";
  return (
    <div className="gb-fresh" data-testid="gb-status-line">
      <span className={`gb-dot${down || lag > 0 ? " gb-warn" : ""}`} aria-hidden="true" />
      {module.record} · {text}
    </div>
  );
}

export function TopBar(p: TopBarProps) {
  return (
    <header className="gb-top">
      <Wordmark className="gb-brand" />
      <ModuleName p={p} />
      {p.search && (
        <SearchBox
          value={p.search.value}
          onChange={p.search.onChange}
          label={`Search ${p.module?.view?.title ?? p.module?.name ?? ""}`.trim()}
          slashFocus={p.slashFocus}
        />
      )}
      <div className="gb-top-end">
        {p.modeSwitch}
        {p.toolbar}
        {p.module && <StatusLine module={p.module} status={p.status} />}
      </div>
    </header>
  );
}
