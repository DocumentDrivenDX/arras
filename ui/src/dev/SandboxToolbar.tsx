// SPDX-License-Identifier: MIT OR Apache-2.0
import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useRef, useState } from "react";
import { useStatus } from "../api/queries";
import { Button, Chip } from "../components/ui";
import { type Control, DEFAULT_BACKENDS, type Identity, nameProblem, type People } from "./sandbox";

const CUSTOM = "\u0000custom";

export interface SandboxToolbarProps {
  people: People;
  identity: Identity;
  onIdentity: (who: Identity) => void;
  /** The dev host's origin (empty for the page's own); `POST {apiBase}/api/dev/control`. */
  apiBase?: string;
}

/**
 * The standalone host's sandbox toolbar (OPR-15): pick one of the sandbox's people, or a made-up name with a
 * role, and break and mend the sandbox's backends. Only the development host has this; the library does not
 * export it. It must render inside the console (it reads the registry's status and refreshes its queries).
 * The identity is sent as headers only the dev host reads; nothing is stored and no name goes in a URL.
 */
export function SandboxToolbar({
  people,
  identity,
  onIdentity,
  apiBase = "",
}: SandboxToolbarProps) {
  const qc = useQueryClient();
  const status = useStatus();
  // The registry names its backends; when it cannot be read (a person it refuses) the last names seen,
  // else the sandbox's documented two, are used.
  const seen = useRef<string[]>(DEFAULT_BACKENDS);
  if (status.data?.length) seen.current = status.data.map((s) => s.backend);
  const backends = seen.current;
  const state = (b: string) => status.data?.find((s) => s.backend === b);

  const fixedNames = people.people;
  const [custom, setCustom] = useState(identity.kind === "custom");
  const [name, setName] = useState(identity.kind === "custom" ? identity.name : "");
  const [role, setRole] = useState(
    identity.kind === "custom"
      ? identity.role
      : people.roles.includes("viewer")
        ? "viewer"
        : (people.roles[0] ?? ""),
  );
  const [problem, setProblem] = useState<string | null>(null);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  function pick(value: string) {
    setProblem(null);
    if (value === CUSTOM) return setCustom(true);
    setCustom(false);
    onIdentity({ kind: "fixed", name: value });
  }

  function useCustom(e: FormEvent) {
    e.preventDefault();
    const bad = nameProblem(name, fixedNames);
    setProblem(bad);
    if (!bad) onIdentity({ kind: "custom", name, role });
  }

  async function control(body: Control, done: string) {
    try {
      const r = await fetch(`${apiBase}/api/dev/control`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      setNote(
        r.ok
          ? { ok: true, text: done }
          : { ok: false, text: `The dev host refused it (${r.status}).` },
      );
    } catch (e) {
      setNote({
        ok: false,
        text: `The dev host could not be reached (${e instanceof Error ? e.message : String(e)}).`,
      });
      return;
    }
    // The console shows the new state: every active read is made again.
    await qc.invalidateQueries();
  }

  const viewed = identity.name;
  return (
    <div className="flex flex-wrap items-center gap-2 text-[12px]" data-testid="sandbox-toolbar">
      <label className="flex items-center gap-1.5">
        <span className="text-muted">Viewing as</span>
        <select
          aria-label="Person"
          className="rounded border border-strong bg-surface px-1.5 py-0.5 text-fg"
          value={custom ? CUSTOM : identity.name}
          onChange={(e) => pick(e.target.value)}
        >
          {people.people.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
          <option value={CUSTOM}>Custom name and role…</option>
        </select>
      </label>
      {custom && (
        <form
          noValidate
          onSubmit={useCustom}
          className="flex flex-wrap items-center gap-1.5"
          aria-label="Custom person"
        >
          <input
            aria-label="Name"
            aria-invalid={problem ? true : undefined}
            aria-describedby={problem ? "sandbox-name-problem" : undefined}
            autoComplete="off"
            spellCheck={false}
            maxLength={64}
            placeholder="ana"
            className="w-28 rounded border border-strong bg-surface px-1.5 py-0.5 text-fg"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setProblem(null);
            }}
          />
          <select
            aria-label="Role"
            className="rounded border border-strong bg-surface px-1.5 py-0.5 text-fg"
            value={role}
            onChange={(e) => setRole(e.target.value)}
          >
            {people.roles.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
          <Button type="submit">Use</Button>
          {problem && (
            <span id="sandbox-name-problem" role="alert" className="text-bad">
              {problem}
            </span>
          )}
        </form>
      )}
      {identity.kind === "custom" && (
        <Chip tone="accent" title="A made-up person: the role's grants on every module">
          {identity.name} · {identity.role}
        </Chip>
      )}
      <span className="rounded border border-warn/40 bg-warnsoft px-1.5 text-[11px] text-warn">
        dev host: no sign-in
      </span>
      <details className="relative" data-testid="sandbox-controls">
        <summary className="cursor-pointer rounded border border-strong bg-surface px-2 py-0.5 hover:bg-surface2">
          Sandbox
        </summary>
        <div className="absolute right-0 z-20 mt-1 w-[min(92vw,22rem)] space-y-2 rounded border border-line bg-surface p-3 shadow-lg">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">
            Backends
          </div>
          {backends.map((b) => {
            const s = state(b);
            return (
              <div key={b} className="flex flex-wrap items-center gap-1.5">
                <span className="arras-mono min-w-[7.5rem]">{b}</span>
                {s && (
                  <Chip tone={s.available ? "ok" : "bad"}>
                    {s.available ? "available" : `unavailable${s.reason ? ` (${s.reason})` : ""}`}
                  </Chip>
                )}
                <Button
                  className="ml-auto"
                  aria-label={`Outage ${b}`}
                  onClick={() =>
                    void control(
                      { op: "outage", backend: b, reason: "unreachable" },
                      `${b} is unreachable.`,
                    )
                  }
                >
                  Outage
                </Button>
                <Button
                  aria-label={`Mend ${b}`}
                  onClick={() =>
                    void control({ op: "outage", backend: b, reason: null }, `${b} is mended.`)
                  }
                >
                  Mend
                </Button>
              </div>
            );
          })}
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">
            Token of {viewed}
          </div>
          <div className="flex flex-wrap gap-1.5">
            <Button
              onClick={() =>
                void control({ op: "expire", user: viewed }, `${viewed}'s token is expired.`)
              }
            >
              Expire token
            </Button>
            <Button
              onClick={() =>
                void control({ op: "restore", user: viewed }, `${viewed}'s token is restored.`)
              }
            >
              Restore token
            </Button>
          </div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">
            Replica
          </div>
          <Button onClick={() => void control({ op: "feed" }, "The replica's feed ran.")}>
            Run the replica&apos;s feed
          </Button>
          <div
            role="status"
            aria-live="polite"
            className={`min-h-4 ${note && !note.ok ? "text-bad" : "text-muted"}`}
            data-testid="sandbox-note"
          >
            {note?.text}
          </div>
        </div>
      </details>
    </div>
  );
}
