// SPDX-License-Identifier: MIT OR Apache-2.0
import { SUPPORTED_OPERATE_VERSION } from "../api/types";
import { NavLink } from "../components/NavLink";
import { Notice } from "../components/ui";
import { AREA_LABELS } from "../lib/vocabulary";
import type { Route } from "../route";

/**
 * The one page for an address that names nothing the viewer can open: an unknown module, a type the
 * module does not declare, an entity that cannot be read, an action it does not declare, a group with
 * no changes. It is the same for every cause, so it never says which, or whether the thing exists.
 * With `module` it links to that module's entry, its Model.
 */
export function NotFound({ module }: { module?: string }) {
  const entry: Route | undefined = module ? { module, area: "model" } : undefined;
  return (
    <div className="p-4" data-testid="not-found">
      <Notice tone="bad" role="alert">
        <strong>Not found.</strong> There is nothing at this address, or you cannot read it.{" "}
        {module && entry && (
          <NavLink to={entry} className="text-accent underline underline-offset-2">
            Go to {AREA_LABELS.model} of {module}
          </NavLink>
        )}
      </Notice>
    </div>
  );
}

export function VersionMismatch({ reported }: { reported: unknown }) {
  return (
    <div className="p-4">
      <Notice tone="bad" role="alert">
        <strong>This console cannot talk to this server.</strong> It supports operate contract
        version <span className="arras-mono">{SUPPORTED_OPERATE_VERSION}</span>, and the server
        reports <span className="arras-mono">{String(reported)}</span>. Update{" "}
        <span className="arras-mono">arras-ui</span> or the server so the versions match.
      </Notice>
    </div>
  );
}
