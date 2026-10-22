// SPDX-License-Identifier: MIT OR Apache-2.0
import { useEffect, useId, useRef } from "react";
import { shortName } from "../api/gql";
import type { Effect, Receipt } from "../api/types";

export type TouchedRef = Receipt["refs"][number];

/**
 * Where a touched entity opens: an address (an anchor, whose click calls `go` too when both are
 * given), a handler alone for a surface that routes itself (a button), or neither (plain text).
 */
export interface RefLink {
  href?: string;
  go?: () => void;
}

type Group = "created" | "changed" | "deleted";
const GROUPS: { id: Group; title: string }[] = [
  { id: "created", title: "Created" },
  { id: "changed", title: "Changed" },
  { id: "deleted", title: "Deleted" },
];

const same = (a: { type: string; key: string }, b: { type: string; key: string }) =>
  shortName(a.type) === shortName(b.type) && a.key === b.key;

const sameType = (a: { type: string }, b: { type: string }) =>
  shortName(a.type) === shortName(b.type);

/** The group the effect that a ref matches by type and key puts it in, if any effect matches. */
function matchedGroup(r: TouchedRef, effects: readonly Effect[]): Group | undefined {
  const e = effects.find((x) => "ref" in x && same(x.ref, r));
  if (!e) return undefined;
  if (e.kind === "create") return "created";
  return e.kind === "delete" ? "deleted" : "changed";
}

/**
 * Which list each touched entity belongs to: the effects say, and without them it is a change. A
 * ref that matches an effect by type and key follows that effect (create, delete, otherwise
 * changed). A ref that matches none is a change unless, of its type, exactly one `create` is
 * unspent (no ref matches it by key) and exactly one ref is unmatched, and it is that ref (a
 * generated key): then it is the created one. The spent set is computed once for the receipt.
 */
function groupRefs(
  effects: readonly Effect[],
  refs: readonly TouchedRef[],
): Map<TouchedRef, Group> {
  const groups = new Map<TouchedRef, Group>();
  const unmatched: TouchedRef[] = [];
  for (const r of refs) {
    const g = matchedGroup(r, effects);
    if (g) groups.set(r, g);
    else unmatched.push(r);
  }
  const unspent = effects.filter((e) => e.kind === "create" && !refs.some((r) => same(e.ref, r)));
  for (const r of unmatched) {
    const creates = unspent.filter((e) => "ref" in e && sameType(e.ref, r));
    const others = unmatched.filter((x) => sameType(x, r));
    groups.set(r, creates.length === 1 && others.length === 1 ? "created" : "changed");
  }
  return groups;
}

function RefItem({ r, link }: { r: TouchedRef; link: RefLink | undefined }) {
  const text = `${shortName(r.type)} ${r.key}`;
  const go = link?.go;
  let body = <span>{text}</span>;
  if (link?.href) {
    body = (
      <a
        href={link.href}
        className="underline"
        onClick={(e) => {
          if (go) {
            e.preventDefault();
            go();
          }
        }}
      >
        {text}
      </a>
    );
  } else if (go) {
    body = (
      <button
        type="button"
        className="m-0 cursor-pointer border-0 bg-transparent p-0 font-[inherit] text-[inherit] underline"
        onClick={go}
      >
        {text}
      </button>
    );
  }
  return (
    <li data-testid="receipt-ref">
      {body} <span>(version {r.version})</span>
    </li>
  );
}

export function ReceiptSummary({
  receipt,
  linkFor,
  effects = [],
  focusOnMount = false,
}: {
  receipt: Receipt;
  /** Where each touched entity opens; a deleted one is not linked. */
  linkFor: (ref: TouchedRef) => RefLink;
  /** The effects that were validated, to tell the created from the changed. */
  effects?: readonly Effect[];
  focusOnMount?: boolean;
}) {
  const root = useRef<HTMLElement>(null);
  const headingId = useId();
  const groups = groupRefs(effects, receipt.refs);
  useEffect(() => {
    if (focusOnMount) root.current?.focus();
  }, [focusOnMount]);
  return (
    <section ref={root} tabIndex={-1} aria-labelledby={headingId} data-testid="receipt-summary">
      <p id={headingId} className="m-0 mb-1 font-semibold">
        {receipt.replayed ? "Already applied" : "Applied"}: {receipt.action}
      </p>
      {GROUPS.map(({ id, title }) => {
        const refs = receipt.refs.filter((r) => groups.get(r) === id);
        if (refs.length === 0) return null;
        return (
          <div key={id} data-testid={`receipt-${id}`}>
            <p className="m-0 mt-1 font-medium">{title}</p>
            <ul className="m-0 list-none p-0">
              {refs.map((r) => (
                <RefItem
                  key={`${r.type}:${r.key}`}
                  r={r}
                  link={id === "deleted" ? undefined : linkFor(r)}
                />
              ))}
            </ul>
          </div>
        );
      })}
      {receipt.group && (
        <p className="m-0 mt-1">
          Group <code data-testid="receipt-group">{receipt.group}</code>
        </p>
      )}
    </section>
  );
}
