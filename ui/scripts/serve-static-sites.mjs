// SPDX-License-Identifier: MIT OR Apache-2.0
// The static host's whole-stack test server (ADR-031): stage the example modules and a synthetic thousand-node
// graph as three static sites under .static-sites/, then serve that directory with nothing but file reads, as any
// static file host would (GET and HEAD only; no API, no state). `node scripts/serve-static-sites.mjs [port]`.
import { execFileSync } from "node:child_process";
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize, resolve, sep } from "node:path";

const ui = resolve(import.meta.dirname, "..");
const root = join(ui, ".static-sites");
const run = (cmd, args, cwd) => execFileSync(cmd, args, { cwd, stdio: "inherit" });
const stage = (name, dir, module, graph, title) =>
  run(
    "node",
    [
      "scripts/stage-static.ts",
      join(root, name),
      join(dir, module),
      join(dir, graph),
      "--title",
      title,
    ],
    ui,
  );

stage("catalog", "../examples/catalog", "catalog.umf.json", "catalog.graph.json", "Catalog");
stage("pizza", "../examples/pizza", "pizza.umf.json", "pizza.graph.json", "Pizza");
run("uv", ["run", "python", "tools/gen_synthetic_graph.py", join(root, "_src")], resolve(ui, ".."));
stage("synthetic", join(root, "_src"), "synthetic.umf.json", "synthetic.graph.json", "Synthetic");

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
};
const port = Number(process.argv[2] ?? 8130);
createServer((req, res) => {
  if (req.method !== "GET" && req.method !== "HEAD") {
    res.writeHead(405).end();
    return;
  }
  const path = normalize(decodeURIComponent((req.url ?? "/").split(/[?#]/)[0])).replace(
    /^(\.\.[/\\])+/,
    "",
  );
  let file = join(root, path);
  if (existsSync(file) && statSync(file).isDirectory()) file = join(file, "index.html");
  if (!file.startsWith(root + sep) || !existsSync(file) || path.includes("_src")) {
    res.writeHead(404).end("not found");
    return;
  }
  res.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" });
  if (req.method === "HEAD") res.end();
  else createReadStream(file).pipe(res);
}).listen(port, "127.0.0.1", () => process.stdout.write(`serving ${root} on ${port}\n`));
