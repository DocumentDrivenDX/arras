// SPDX-License-Identifier: MIT OR Apache-2.0
// Stage a static read-only site (ADR-031, CONTRACT-012): copy the built host (dist-static) to OUT and put a UMF
// module document and an `arras.graph` file beside it, named in `arras-static.json`.
//
//   node scripts/stage-static.ts OUT MODULE.umf.json GRAPH.graph.json [--title TEXT] [--name NAME]
//
// Check the pair first with `STATIC_MODULE=MODULE STATIC_GRAPH=GRAPH npm run check:static`, which loads it with
// the code the page runs, so a pair the page would refuse is refused before anything is published.
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { basename, resolve } from "node:path";

const args = process.argv.slice(2);
const flag = (name: string): string | undefined => {
  const i = args.indexOf(name);
  if (i < 0) return undefined;
  const v = args[i + 1];
  args.splice(i, 2);
  return v;
};
const title = flag("--title");
const name = flag("--name");
const [out, moduleFile, graphFile] = args;
if (!out || !moduleFile || !graphFile) {
  process.stderr.write(
    "usage: stage-static.ts OUT MODULE.umf.json GRAPH.graph.json [--title T] [--name N]\n",
  );
  process.exit(2);
}
const dist = resolve(import.meta.dirname, "../dist-static");
if (!existsSync(`${dist}/static.html`)) {
  process.stderr.write("dist-static is not built: run `npm run build:static` first\n");
  process.exit(2);
}
const moduleText = readFileSync(moduleFile, "utf8");
const graphText = readFileSync(graphFile, "utf8");
rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });
cpSync(dist, out, { recursive: true });
renameSync(`${out}/static.html`, `${out}/index.html`);
writeFileSync(`${out}/${basename(moduleFile)}`, moduleText);
writeFileSync(`${out}/${basename(graphFile)}`, graphText);
const config: Record<string, unknown> = {
  module: basename(moduleFile),
  graph: basename(graphFile),
};
if (title || name) config.brand = { name: name ?? title, ...(title ? { title } : {}) };
writeFileSync(`${out}/arras-static.json`, `${JSON.stringify(config, null, 2)}\n`);
process.stdout.write(`staged ${out}\n`);
