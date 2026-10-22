// SPDX-License-Identifier: MIT OR Apache-2.0
import { useState } from "react";
import { useClient } from "../api/context";
import { ApiError } from "../api/errors";
import { buildFollowQuery, byKeyField, relationFields, shortName } from "../api/gql";
import type { ModuleInfo, Ref } from "../api/types";
import { Button, Chip, ErrorPanel, Section } from "../components/ui";
import { refId } from "../lib/relLabels";
import { type EntityData, type Entry, toEntity } from "./entity";
import { useRefLabels } from "./useRefLabels";

type Field = ReturnType<typeof relationFields>[number];

/** A relationship chip: the target's name when one was read, its key beside it (alone until then). */
function RefChip({
  r,
  module,
  label,
  busy,
  disabled,
  onOpen,
}: {
  r: Ref;
  module: string;
  label: string | undefined;
  busy: boolean;
  disabled: boolean;
  onOpen: () => void;
}) {
  const foreign = r.module !== module;
  return (
    <Button
      disabled={disabled}
      onClick={onOpen}
      title={`Open ${r.type} ${r.key}${foreign ? ` (module ${r.module})` : ""}`}
    >
      {busy ? (
        "…"
      ) : (
        <>
          {label && <span>{label}</span>}
          <span className={label ? "arras-mono text-[11px] text-muted" : "arras-mono"}>
            {r.key}
          </span>
        </>
      )}
      {foreign && <span className="text-muted"> ↗ {r.module}</span>}
    </Button>
  );
}

function FieldRefs({
  f,
  refs,
  module,
  labels,
  busy,
  onOpen,
}: {
  f: Field;
  refs: Ref[];
  module: string;
  labels: Record<string, string>;
  busy: string | null;
  onOpen: (field: string, r: Ref) => void;
}) {
  return (
    <div data-testid={`rels-${f.field}`}>
      <div className="flex items-center gap-1.5">
        <span className="arras-mono font-medium">{f.field}</span>
        <span className="text-muted">→ {f.targets.map(shortName).join(", ")}</span>
        <Chip>{f.multiplicity}</Chip>
        {refs.length >= 100 && <Chip tone="warn">truncated at 100</Chip>}
      </div>
      {refs.length === 0 ? (
        <div className="text-muted">none</div>
      ) : (
        <ul className="m-0 mt-0.5 flex list-none flex-wrap gap-1 p-0">
          {refs.map((r) => (
            <li key={refId(r)}>
              <RefChip
                r={r}
                module={module}
                label={labels[refId(r)]}
                busy={busy === `${f.field}:${r.key}`}
                disabled={busy !== null}
                onOpen={() => onOpen(f.field, r)}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function Relationships({
  m,
  entry,
  data,
  onFollowed,
}: {
  m: ModuleInfo;
  entry: Entry;
  data: EntityData;
  onFollowed: (e: Entry) => void;
}) {
  const client = useClient();
  const t = m.entityTypes.find((x) => x.name === entry.type);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const fields = relationFields(m, entry.type);
  const all = fields.flatMap((f) => data.rels[f.field] ?? []);
  const labels = useRefLabels(m, all);
  if (!t || fields.length === 0) return null;

  // Opening a ref selects `target` (one by-key read per target) and nothing selects it before.
  const open = async (field: string, ref: Ref) => {
    setBusy(`${field}:${ref.key}`);
    setErr(null);
    try {
      const r = await client.moduleQuery<Record<string, Record<string, Ref[]> | null>>(
        m.name,
        buildFollowQuery(m, t, field),
        { key: entry.key },
      );
      const refs = r.data?.[byKeyField(t.name)]?.[field] ?? [];
      const hit = refs.find((x) => x.key === ref.key && x.type === ref.type);
      const err0 = r.errors.find((e) => e.code === "COST_EXCEEDED" || e.code === "DEPTH_EXCEEDED");
      if (err0) throw new ApiError(200, { message: err0.message, code: err0.code });
      const target = hit?.target;
      if (!target) {
        onFollowed({ module: ref.module, type: ref.type, key: ref.key, seed: undefined });
        setErr(new ApiError(404, { message: "That entity is absent or you cannot read it." }));
        return;
      }
      const foreign = ref.module !== m.name;
      onFollowed({
        module: ref.module,
        type: ref.type,
        key: ref.key,
        seed: toEntity(foreign ? undefined : m, target as Record<string, unknown>, foreign),
      });
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Section title="Relationships">
      <div className="space-y-2">
        {fields.map((f) => (
          <FieldRefs
            key={f.field}
            f={f}
            refs={data.rels[f.field] ?? []}
            module={m.name}
            labels={labels}
            busy={busy}
            onOpen={(field, r) => void open(field, r)}
          />
        ))}
      </div>
      {err !== null && <ErrorPanel error={err} />}
    </Section>
  );
}
