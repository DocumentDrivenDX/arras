// SPDX-License-Identifier: MIT OR Apache-2.0
import { describe, expect, it } from "vitest";
import { parityErrors } from "../../scripts/check-public-manifest";

const baseline = {
  subpaths: [".", "./browser", "./shell"],
  runtime: {
    ".": ["ArrasConsole", "createClient"],
    "./browser": ["GraphBrowser"],
    "./shell": ["ArrasApp"],
  },
  types: {
    ".": ["ArrasConsoleProps"],
    "./browser": ["GraphBrowserProps"],
    "./shell": ["ArrasAppProps"],
  },
  peers: {
    react: { version: "^19.3.0", optional: false },
    "react-dom": { version: "^19.3.0", optional: false },
  },
  tokens: ["--arras-color-accent", "--arras-color-text"],
};

function errorsFor(actual: typeof baseline) {
  return parityErrors(baseline, actual);
}

describe("public API manifest parity comparator", () => {
  it.each([
    [
      "removed runtime symbol",
      { ...baseline, runtime: { ...baseline.runtime, ".": ["ArrasConsole"] } },
    ],
    [
      "extra runtime symbol",
      {
        ...baseline,
        runtime: { ...baseline.runtime, ".": [...baseline.runtime["."], "InternalHelper"] },
      },
    ],
    ["removed type symbol", { ...baseline, types: { ...baseline.types, ".": [] } }],
    [
      "extra type symbol",
      {
        ...baseline,
        types: { ...baseline.types, ".": [...baseline.types["."], "PrivateOptions"] },
      },
    ],
    ["removed subpath", { ...baseline, subpaths: [".", "./browser"] }],
    ["extra subpath", { ...baseline, subpaths: [...baseline.subpaths, "./internal"] }],
    ["removed peer", { ...baseline, peers: { react: baseline.peers.react } }],
    [
      "extra peer",
      { ...baseline, peers: { ...baseline.peers, lodash: { version: "*", optional: false } } },
    ],
    ["removed role token", { ...baseline, tokens: ["--arras-color-accent"] }],
    ["extra role token", { ...baseline, tokens: [...baseline.tokens, "--arras-color-internal"] }],
  ])("rejects %s", (_name, actual) => {
    expect(errorsFor(actual as typeof baseline)).not.toEqual([]);
  });
});
