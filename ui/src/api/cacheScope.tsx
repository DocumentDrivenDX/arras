// SPDX-License-Identifier: MIT OR Apache-2.0
import type { QueryClient } from "@tanstack/react-query";
import { type ReactNode, useLayoutEffect, useState } from "react";

// A caller-supplied client is an exclusive Arras cache. Default clients never enter this map.
const owners = new WeakMap<QueryClient, { scope: string; count: number }>();

export function CacheLease({
  client,
  scope,
  children,
}: {
  client: QueryClient;
  scope: string;
  children: ReactNode;
}) {
  const [ready, setReady] = useState<QueryClient | null>(null);
  useLayoutEffect(() => {
    const existing = owners.get(client);
    if (existing && existing.scope !== scope)
      throw new Error("An Arras queryClient must be exclusive to one identity and API scope");
    const owner = existing ?? { scope, count: 0 };
    owner.count += 1;
    owners.set(client, owner);
    setReady(client);
    return () => {
      owner.count -= 1;
      if (owner.count > 0) return;
      void client.cancelQueries();
      client.clear();
      owners.delete(client);
    };
  }, [client, scope]);
  // New children must never render against the preceding identity's external cache.
  return ready === client ? children : null;
}
