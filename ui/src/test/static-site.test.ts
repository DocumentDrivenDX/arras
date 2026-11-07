// SPDX-License-Identifier: MIT OR Apache-2.0
// @vitest-environment node
// Check a module and graph pair before it is staged (`npm run check:static`): load it with the code the static
// host runs. Set STATIC_MODULE and STATIC_GRAPH; with neither set there is nothing to check and it is skipped.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { loadStore } from "../static/backend";

const moduleFile = process.env.STATIC_MODULE;
const graphFile = process.env.STATIC_GRAPH;

describe.skipIf(!moduleFile || !graphFile)(
  "the module and graph named by STATIC_MODULE and STATIC_GRAPH",
  () => {
    it("load, with every record accepted", async () => {
      const store = await loadStore(
        readFileSync(moduleFile as string, "utf8"),
        readFileSync(graphFile as string, "utf8"),
      );
      const entities = [...store.entities.values()].reduce((n, l) => n + l.length, 0);
      expect(entities).toBeGreaterThan(0);
      process.stdout.write(
        `${store.module.name}: ${entities} entities, ${store.records.length} records\n`,
      );
    });
  },
);
