// SPDX-License-Identifier: MIT OR Apache-2.0
// The numeric domains of a module's fields in the static read-only profile (CONTRACT-012): the precision and
// scale of a decimal and the width of an integer, read from the document's field facets, and the value a field
// holds, as `arras/fakes_domain.py` gives it (W-011). A decimal is held at its scale (`9` in a scale-2 field is
// `9.00`), a value outside a domain refuses the record that carries it, and a decimal is written as Python's
// `str(Decimal)` writes it. A decimal here is its text: no number ever holds it.

export interface Domain {
  family: "integer" | "decimal";
  precision: number | null;
  scale: number | null;
  bits: number;
  signed: boolean;
}

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj =>
  typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Obj) : {};

const int = (v: unknown): number | null => (Number.isInteger(v) ? (v as number) : null);

function domainOf(el: Obj): Domain | null {
  const facets = obj(el.facets);
  if (el.scalarType === "decimal")
    return {
      family: "decimal",
      precision: int(facets.precision),
      scale: int(facets.scale),
      bits: 64,
      signed: true,
    };
  if (el.scalarType !== "integer") return null;
  const w = obj(facets.integerWidth);
  return {
    family: "integer",
    precision: null,
    scale: null,
    bits: int(w.bits) ?? 64,
    signed: w.signed !== false,
  };
}

/** The domains a registered document declares, by `type\u0000field`; an integer field with no width is signed 64-bit. */
export function readDomains(root: Obj): Map<string, Domain> {
  const out = new Map<string, Domain>();
  const modules = Array.isArray(root.modules) ? root.modules : [];
  for (const el of modules.flatMap((m) =>
    Array.isArray(obj(m).elements) ? (obj(m).elements as unknown[]) : [],
  )) {
    const e = obj(el);
    const id = String(e.id ?? "");
    const dot = id.indexOf(".");
    const domain = e.kind === "field" && dot >= 0 ? domainOf(e) : null;
    if (domain) out.set(`${id.slice(0, dot)}\u0000${id.slice(dot + 1)}`, domain);
  }
  return out;
}

/** A decimal as Python's `Decimal` holds it: sign, coefficient digits (no leading zeros) and exponent. */
export interface Dec {
  neg: boolean;
  coeff: string;
  exp: number;
}

const TEXT = /^([+-]?)(?:(\d+)\.?(\d*)|\.(\d+))(?:[eE]([+-]?\d+))?$/;

export function parseDecimal(text: string): Dec | null {
  const m = TEXT.exec(text);
  if (!m) return null;
  const whole = m[2] ?? "";
  const frac = m[3] ?? m[4] ?? "";
  const exp = Number(m[5] ?? 0) - frac.length;
  return { neg: m[1] === "-", coeff: `${whole}${frac}`.replace(/^0+(?=\d)/, "") || "0", exp };
}

const isZero = (d: Dec) => /^0+$/.test(d.coeff);

/** `Decimal.__str__`: plain notation unless the exponent is positive or the number is below 1e-6. */
export function decimalText(d: Dec): string {
  const left = d.exp + d.coeff.length;
  const dot = d.exp <= 0 && left > -6 ? left : 1;
  let int: string;
  let frac = "";
  if (dot <= 0) {
    int = "0";
    frac = `.${"0".repeat(-dot)}${d.coeff}`;
  } else if (dot >= d.coeff.length) int = d.coeff + "0".repeat(dot - d.coeff.length);
  else {
    int = d.coeff.slice(0, dot);
    frac = `.${d.coeff.slice(dot)}`;
  }
  const e = left === dot ? "" : `E${left - dot >= 0 ? "+" : "-"}${Math.abs(left - dot)}`;
  return `${d.neg ? "-" : ""}${int}${frac}${e}`;
}

/** Digits and exponent with trailing zeros of the coefficient moved into the exponent (`normalize`). */
function normalised(d: Dec): { digits: number; exp: number; zero: boolean } {
  if (isZero(d)) return { digits: 1, exp: 0, zero: true };
  const coeff = d.coeff.replace(/0+$/, "");
  return { digits: coeff.length, exp: d.exp + (d.coeff.length - coeff.length), zero: false };
}

/** Why a decimal falls outside the domain, or `null`. */
export function decimalFault(d: Domain, v: Dec): string | null {
  if (d.precision === null || d.scale === null) return null;
  const n = normalised(v);
  const scale = Math.max(0, -n.exp);
  const whole = n.zero ? 0 : Math.max(0, n.digits + n.exp);
  if (scale > d.scale) return `a decimal with more than ${d.scale} places`;
  if (whole > d.precision - d.scale)
    return `a decimal with more than ${d.precision - d.scale} digits before the point`;
  return null;
}

/** `v` at the domain's scale, as `Decimal.quantize` writes it (the value is within the domain). */
function quantized(v: Dec, scale: number): Dec {
  let { coeff, exp } = v;
  while (exp < -scale && coeff.endsWith("0") && coeff.length > 1) {
    coeff = coeff.slice(0, -1);
    exp += 1;
  }
  while (exp > -scale) {
    coeff += "0";
    exp -= 1;
  }
  return { neg: v.neg, coeff: coeff.replace(/^0+(?=\d)/, "") || "0", exp };
}

/** The integer-width fault of a value, or `null`. */
export function integerFault(d: Domain, v: bigint): string | null {
  const lo = d.signed ? -(2n ** BigInt(d.bits - 1)) : 0n;
  const hi = d.signed ? 2n ** BigInt(d.bits - 1) - 1n : 2n ** BigInt(d.bits) - 1n;
  return v >= lo && v <= hi ? null : `an integer outside ${d.bits}-bit range`;
}

/**
 * The text a decimal field holds for `v` (a decimal string or an integer): at its scale when the domain is
 * complete, else as `Decimal` writes it. Throws an `Error` whose message is the fault.
 */
export function storedDecimal(d: Domain | undefined, v: string | number | bigint): string {
  const dec = parseDecimal(String(v));
  if (!dec) throw new Error("not a decimal");
  if (d?.scale !== null && d?.scale !== undefined) {
    const why = decimalFault(d, dec);
    if (why) throw new Error(why);
    return decimalText(quantized(dec, d.scale));
  }
  return decimalText(dec);
}
