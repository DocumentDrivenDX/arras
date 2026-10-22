// SPDX-License-Identifier: MIT OR Apache-2.0
import { useCallback, useEffect, useRef, useState } from "react";
import { canonicalHash, formatHash, parseHash, type Route, sameRoute } from "../route";

/** How a route change is recorded: a navigation adds a history entry, a replacement does not. */
export interface GoOptions {
  replace?: boolean;
}

export type Go = (r: Route, opts?: GoOptions) => void;

export interface RouteSource {
  /** Keep the route in `location.hash`; otherwise in memory (or the host's, with `route`). */
  hashRouting: boolean;
  /** With `hashRouting`: the first path segment a hosting shell owns. */
  prefix?: string;
  /** A host that owns the route passes it; the console then reads no URL and writes none. */
  route?: Route;
  /** With `route`: called for every change the console asks for. */
  onRoute?: (r: Route, opts: { replace: boolean }) => void;
}

/**
 * The console's route and the one way to change it.
 *
 * - Hash routing: the route is `location.hash`. `go` pushes a history entry (`replace` rewrites the
 *   current one: redirects and normalisation, never a navigation), and Back and Forward arrive as
 *   `popstate` / `hashchange`, which reparse the fragment.
 * - Controlled (`route`): the host owns the location; `go` asks it through `onRoute`.
 * - Otherwise the route is kept in memory.
 */
export function useRoute({
  hashRouting,
  prefix,
  route: controlled,
  onRoute,
}: RouteSource): [Route, Go] {
  const [own, setOwn] = useState<Route>(() =>
    hashRouting ? parseHash(window.location.hash, prefix) : { area: "model" },
  );
  const asked = useRef(onRoute);
  asked.current = onRoute;
  const owned = controlled === undefined;
  useEffect(() => {
    if (!hashRouting || !owned) return;
    // An address naming an area by an alias id (`schema`, `data`, `audit`) is rewritten to its canonical id, in place, once;
    // `replaceState` raises no `hashchange`, so nothing reparses it.
    const rewrite = () => {
      const canonical = canonicalHash(window.location.hash, prefix);
      if (canonical) window.history.replaceState(window.history.state, "", canonical);
    };
    rewrite();
    const on = () => {
      rewrite();
      const next = parseHash(window.location.hash, prefix);
      setOwn((prev) => (sameRoute(prev, next, prefix) ? prev : next));
    };
    window.addEventListener("hashchange", on);
    window.addEventListener("popstate", on);
    return () => {
      window.removeEventListener("hashchange", on);
      window.removeEventListener("popstate", on);
    };
  }, [hashRouting, owned, prefix]);
  const go = useCallback<Go>(
    (r, opts) => {
      const replace = opts?.replace === true;
      if (!owned) {
        asked.current?.(r, { replace });
        return;
      }
      if (!hashRouting) {
        setOwn(r);
        return;
      }
      const hash = formatHash(r, prefix);
      if (!sameRoute(parseHash(window.location.hash, prefix), r, prefix)) {
        const state = window.history.state;
        if (replace) window.history.replaceState(state, "", hash);
        else window.history.pushState(state, "", hash);
      }
      const next = parseHash(hash, prefix);
      setOwn((prev) => (sameRoute(prev, next, prefix) ? prev : next));
    },
    [owned, hashRouting, prefix],
  );
  return [controlled ?? own, go];
}
