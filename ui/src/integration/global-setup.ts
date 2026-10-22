// SPDX-License-Identifier: MIT OR Apache-2.0
// Fails the run at once, with the reason, when the dev host cannot be started at all (no `uv`, or the
// Python environment does not resolve), instead of every file timing out on its own server.
import { spawnSync } from "node:child_process";
import { REPO_ROOT } from "./server";

export default function setup() {
  const r = spawnSync(
    "uv",
    ["run", "--extra", "devhost", "python", "-c", "import uvicorn, arras.devhost"],
    {
      cwd: REPO_ROOT,
      encoding: "utf8",
      timeout: 300_000,
    },
  );
  if (r.error || r.status !== 0) {
    throw new Error(
      `The integration tier needs the real dev host: \`uv run --extra devhost python -m arras.devhost\` from ${REPO_ROOT}.\n` +
        `Install uv and run \`uv sync --locked\` there.\n${r.error?.message ?? ""}${r.stdout ?? ""}${r.stderr ?? ""}`,
    );
  }
}
