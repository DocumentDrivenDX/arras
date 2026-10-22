// SPDX-License-Identifier: MIT OR Apache-2.0
import { createContext, type MouseEvent, type ReactNode, useContext, useMemo } from "react";
import type { LinkTo } from "../kit";
import { formatHash, type Route } from "../route";

/** How a link inside the console navigates: the console's own `go`, and whether Changes is served. */
interface Nav {
  go: (r: Route) => void;
  auditShown: boolean;
  /** The link into Explore, handed in by the shell for an operator (Rule 7); none draws no link. */
  toExplore?: LinkTo;
  /**
   * Set where the fragment is the location (the console's own hash routing), with the prefix its
   * routes carry: links are anchors with that fragment. Unset where the host owns the location or
   * the route is in memory: a link is a button, as the cross-mode link is.
   */
  fragment?: { prefix?: string };
}

const NavContext = createContext<Nav | null>(null);

/** Gives the links below it the console's navigation (one history entry per click). */
export function NavProvider({
  go,
  auditShown,
  toExplore,
  fragment,
  children,
}: Nav & { children: ReactNode }) {
  const prefix = fragment?.prefix;
  const hashed = fragment !== undefined;
  const value = useMemo(
    () => ({ go, auditShown, toExplore, fragment: hashed ? { prefix } : undefined }),
    [go, auditShown, toExplore, hashed, prefix],
  );
  return <NavContext.Provider value={value}>{children}</NavContext.Provider>;
}

/** Whether links to Changes make sense here: true when no console provides the answer. */
export const useAuditShown = (): boolean => useContext(NavContext)?.auditShown ?? true;

/** The link into Explore, or undefined where the shell offers none (no cross-mode link is drawn). */
export const useExploreLink = (): LinkTo | undefined => useContext(NavContext)?.toExplore;

const plain = (e: MouseEvent) =>
  e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey;

type LinkProps = {
  children: ReactNode;
  className?: string;
  "aria-label"?: string;
  "aria-current"?: "page";
  title?: string;
};

/** A link that opens one entity in Entities or Graph, or its History in Changes. */
export function EntityLink({
  module,
  area,
  type,
  entityKey,
  children,
  ...rest
}: LinkProps & {
  module: string;
  area: "entities" | "graph" | "changes";
  type: string;
  entityKey: string;
}) {
  return (
    <NavLink {...rest} to={{ module, area, type, key: entityKey }}>
      {children}
    </NavLink>
  );
}

/** A link that opens the receipt of one change group in Changes. */
export function GroupLink({
  module,
  group,
  children,
  ...rest
}: LinkProps & { module: string; group: string }) {
  return (
    <NavLink {...rest} to={{ module, area: "changes", group }}>
      {children}
    </NavLink>
  );
}

/**
 * A link to a route. Where the fragment is the location it is an anchor to the route's fragment, under
 * the console's own prefix (a plain click navigates through the console, a modified click keeps the
 * browser's own behaviour); where the host owns the location it is a button, as `CrossAnchor` is.
 */
export function NavLink({
  to,
  children,
  className = "text-accent underline-offset-2 hover:underline",
  ...rest
}: LinkProps & { to: Route }) {
  const nav = useContext(NavContext);
  // With no console around the link carries the fragment unprefixed.
  if (nav && !nav.fragment)
    return (
      <button type="button" {...rest} className={className} onClick={() => nav.go(to)}>
        {children}
      </button>
    );
  return (
    <a
      {...rest}
      className={className}
      href={formatHash(to, nav?.fragment?.prefix)}
      onClick={(e) => {
        if (!nav || !plain(e) || e.defaultPrevented) return;
        e.preventDefault();
        nav.go(to);
      }}
    >
      {children}
    </a>
  );
}
