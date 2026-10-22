// SPDX-License-Identifier: MIT OR Apache-2.0
import { useEffect, useState } from "react";
import type { Brand } from "../lib/brand";
import { ArrasApp, type Mode } from "../shell";
import { SandboxToolbar } from "./SandboxToolbar";
import { type Identity, identityHeaders, identityKey, type People } from "./sandbox";

export interface DevHostProps {
  /** The dev host's origin; empty for the page's own (the standalone build). Tests give an absolute one. */
  apiBase?: string;
  /** Extra headers on every console request (tests give the server's own `Origin`). */
  extraHeaders?: () => Record<string, string>;
  /** The mode to open in (an operator only); the standalone page opens in Explore, the Graph Browser. */
  defaultMode?: Mode;
  /** What the page is called; the standalone page reads it from its own meta tag. */
  brand?: Brand;
}

/**
 * The standalone host's page: the console under the sandbox toolbar (OPR-15). Whoever is viewed is sent as
 * headers only the dev host reads; a new key per identity gives a fresh console and query cache, so nothing
 * one person read is shown to the next. Standalone only: not exported from the library's `index.ts`.
 */
export function DevHost({ apiBase = "", extraHeaders, defaultMode, brand }: DevHostProps) {
  const [people, setPeople] = useState<People | null | undefined>(undefined); // undefined: not asked yet
  const [identity, setIdentity] = useState<Identity | null>(null);
  useEffect(() => {
    let live = true;
    fetch(`${apiBase}/api/people`)
      .then((r) => (r.ok ? (r.json() as Promise<People>) : null))
      .then((p) => {
        if (!live) return;
        setPeople(p);
        if (p) setIdentity({ kind: "fixed", name: p.default });
      })
      .catch(() => live && setPeople(null));
    return () => {
      live = false;
    };
  }, [apiBase]);
  // Nothing is mounted until the sandbox's people are known, so every request carries the chosen person's header.
  if (people === undefined) return null;
  return (
    <ArrasApp
      defaultMode={defaultMode}
      brand={brand}
      key={identityKey(identity)}
      identity={identityKey(identity)}
      operateBase={`${apiBase}/api/operate`}
      consoleBase={`${apiBase}/api/console`}
      schemaBase={`${apiBase}/api/schema`}
      toolbar={
        people &&
        identity && (
          <SandboxToolbar
            people={people}
            identity={identity}
            onIdentity={setIdentity}
            apiBase={apiBase}
          />
        )
      }
      getHeaders={() => ({ ...extraHeaders?.(), ...identityHeaders(identity) })}
      onUnauthorized={() => undefined}
    />
  );
}
