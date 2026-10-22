// SPDX-License-Identifier: MIT OR Apache-2.0
// The real dev host for the integration tier: `uv run --extra devhost python -m arras.devhost`, one
// per test file on a free loopback port, killed when the file ends. No fetch double anywhere: the
// components and the client talk HTTP to it.
import { type ChildProcess, spawn } from "node:child_process";
import { createServer } from "node:net";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// ARRAS_REPO_ROOT lets a copy of ui/ (a mutation run) start the repository's dev host.
export const REPO_ROOT =
  process.env.ARRAS_REPO_ROOT ?? resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const READY_TIMEOUT = 90_000;

export interface DevHost {
  base: string;
  port: number;
  /** stdout and stderr so far, for a failure message. */
  log: () => string;
  stop: () => Promise<void>;
}

export function freePort(): Promise<number> {
  return new Promise((res, rej) => {
    const s = createServer();
    s.unref();
    s.on("error", rej);
    s.listen(0, "127.0.0.1", () => {
      const addr = s.address();
      s.close(() =>
        typeof addr === "object" && addr ? res(addr.port) : rej(new Error("no port")),
      );
    });
  });
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function kill(child: ChildProcess, signal: NodeJS.Signals) {
  try {
    // The group: `uv` and the Python it started.
    if (child.pid) process.kill(-child.pid, signal);
  } catch {
    child.kill(signal);
  }
}

export async function startDevHost(opts: { demo?: boolean } = {}): Promise<DevHost> {
  let lastError = "";
  for (let attempt = 0; attempt < 3; attempt++) {
    const port = await freePort();
    const args = [
      "run",
      "--extra",
      "devhost",
      "python",
      "-m",
      "arras.devhost",
      "--port",
      String(port),
    ];
    if (opts.demo === false) args.push("--no-demo");
    const child = spawn("uv", args, {
      cwd: REPO_ROOT,
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });
    let out = "";
    child.stdout?.on("data", (d: Buffer) => (out += d.toString()));
    child.stderr?.on("data", (d: Buffer) => (out += d.toString()));
    let exited: number | null | undefined;
    child.on("exit", (code) => (exited = code));
    const onExit = () => kill(child, "SIGKILL");
    process.once("exit", onExit);
    const base = `http://127.0.0.1:${port}`;
    const host: DevHost = {
      base,
      port,
      log: () => out,
      stop: async () => {
        process.removeListener("exit", onExit);
        if (exited !== undefined) return;
        kill(child, "SIGTERM");
        for (let i = 0; i < 50 && exited === undefined; i++) await sleep(100);
        if (exited === undefined) kill(child, "SIGKILL");
      },
    };
    const deadline = Date.now() + READY_TIMEOUT;
    while (Date.now() < deadline && exited === undefined) {
      try {
        const r = await fetch(`${base}/api/operate/version`);
        if (r.ok) return host;
      } catch {
        /* not listening yet */
      }
      await sleep(150);
    }
    await host.stop();
    lastError = `the dev host did not start on port ${port} (exit ${String(exited)}):\n${out}`;
    if (!/address already in use|Errno 48|Errno 98/i.test(out)) break; // retry only a lost port race
  }
  throw new Error(lastError);
}
