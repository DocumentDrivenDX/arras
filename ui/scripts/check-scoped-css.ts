// SPDX-License-Identifier: MIT OR Apache-2.0
// Fails if a built stylesheet has a selector outside `.arras-root` (ADR-027): the library's
// CSS must not reach a host page. Run on a build's output.
//
//   node scripts/check-scoped-css.ts dist-lib/styles.css dist/assets/*.css
import { readFileSync } from "node:fs";
import postcss from "postcss";
import { unscoped } from "./scope-css.ts";

const files = process.argv.slice(2);
if (files.length === 0) throw new Error("name the stylesheets to check");
let failed = false;
for (const file of files) {
  const bad = unscoped(postcss.parse(readFileSync(file, "utf8")));
  if (bad.length) {
    failed = true;
    process.stderr.write(
      `${file}: ${bad.length} rule(s) outside .arras-root: ${bad.slice(0, 8).join(" | ")}\n`,
    );
  }
}
if (failed) process.exit(1);
