// SPDX-License-Identifier: MIT OR Apache-2.0
// Bind the temporary neutral-theme fixture to the exact UI package carried by a selected wheel.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const arrasPackageName = "@documentdrivendx/arras-ui";
const themePackageName = "@arras-fixtures/neutral-theme";
const expectedPeerNames = [arrasPackageName, "react"].sort();

export function bindNeutralThemePeer(manifest, selectedVersion) {
  assert.equal(manifest.name, themePackageName, "unexpected downstream theme fixture");
  assert.ok(
    manifest.peerDependencies && typeof manifest.peerDependencies === "object",
    "neutral theme must declare peer dependencies",
  );
  assert.deepEqual(Object.keys(manifest.peerDependencies).sort(), expectedPeerNames);
  assert.match(selectedVersion, /^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$/);

  return {
    ...manifest,
    peerDependencies: {
      ...manifest.peerDependencies,
      [arrasPackageName]: selectedVersion,
    },
  };
}

export function selfTest() {
  const source = {
    name: themePackageName,
    version: "1.0.0",
    private: true,
    peerDependencies: { [arrasPackageName]: "0.6.1", react: "^19.3.0" },
    futureMetadata: { retain: true },
  };
  const before = structuredClone(source);
  const bound = bindNeutralThemePeer(source, "9.8.7");
  assert.deepEqual(source, before, "binding must not mutate the source fixture");
  assert.equal(bound.name, source.name);
  assert.deepEqual(Object.keys(bound.peerDependencies).sort(), expectedPeerNames);
  assert.equal(bound.peerDependencies[arrasPackageName], "9.8.7");
  assert.equal(bound.peerDependencies.react, "^19.3.0");
  assert.deepEqual(bound.futureMetadata, source.futureMetadata);
  process.stdout.write("neutral-theme selected-wheel peer binding checks passed\n");
}

function argument(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

if (process.argv.includes("--self-test")) {
  selfTest();
  const driverDir = argument("--driver-dir");
  if (driverDir) {
    const root = resolve(driverDir);
    const expectedDriverSha = argument("--expected-driver-sha");
    const payloadSourceSha = argument("--payload-source-sha");
    const receiptPath = argument("--receipt");
    assert.ok(
      expectedDriverSha && payloadSourceSha && receiptPath,
      "driver receipt arguments are required",
    );
    const driverSha = execFileSync("git", ["-C", root, "rev-parse", "HEAD"], {
      encoding: "utf8",
    }).trim();
    assert.equal(driverSha, expectedDriverSha, "driver checkout must match the workflow SHA");
    const runner = join(root, "ui/scripts/run-downstream-qualification.mjs");
    const helper = join(root, "ui/scripts/bind-downstream-theme.mjs");
    const digest = (path) => createHash("sha256").update(readFileSync(path)).digest("hex");
    const receipt = {
      schema: "arras.ui-qualification-driver/1",
      driver_sha: driverSha,
      payload_source_sha: payloadSourceSha,
      scripts: {
        run_downstream_qualification: digest(runner),
        bind_downstream_theme: digest(helper),
      },
      theme_peer_binding_self_test: "passed",
    };
    const output = resolve(receiptPath);
    mkdirSync(dirname(output), { recursive: true });
    writeFileSync(output, `${JSON.stringify(receipt, null, 2)}\n`);
  }
}
