// SPDX-License-Identifier: MIT OR Apache-2.0
import { useEffect, useState } from "react";

/** `value`, as it stood `ms` milliseconds ago with no change since. */
export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}
