// SPDX-License-Identifier: MIT OR Apache-2.0
// The registration checks of `arras.view` for the static read-only profile (CONTRACT-010 A): every fault a
// document's view terms can have, each with its document path. A port of `_Checker` and `parse_view` in
// `arras/view.py`; `view_cases.json` holds the two to the same faults.
import { type EntityType, type ModuleModel, type Prop, propertyOf, type Violation } from "./model";
import { defaultFormat, formatSuits, isSearchableType } from "./viewDefaults";
import { placeholders, TemplateError } from "./viewTemplate";
import {
  chars,
  type DeclaredSection,
  FIELD_TERMS,
  type FieldTerms,
  FORMATS,
  FORMATS_SINCE,
  ICONS,
  isObj,
  list,
  MAX_LABEL,
  MAX_MODULE_DESCRIPTION,
  MAX_MODULE_TITLE,
  MAX_SEARCH,
  MAX_SECTION_PROPERTIES,
  MAX_SECTIONS,
  MAX_TEMPLATE,
  MAX_TONES,
  MODULE_TERMS,
  type Obj,
  RECORD_TERMS,
  RELATIONSHIP_ONLY,
  RELATIONSHIP_TERMS,
  type RecordTerms,
  type RelationshipTerms,
  SECTION_TERMS,
  TONES,
  VERSION,
} from "./viewTerms";

// -- the checks at registration ----------------------------------------------------------------

export class Checker {
  readonly out: Violation[] = [];
  constructor(
    readonly mod: ModuleModel,
    readonly version: string = VERSION,
  ) {}

  /** A format of the vocabulary, at the version the document declares. */
  knownFormat(v: string): boolean {
    const since = FORMATS_SINCE[v];
    return (
      (FORMATS as readonly string[]).includes(v) || (since !== undefined && this.version >= since)
    );
  }

  fault(path: string, code: string, message: string): void {
    this.out.push({ path, code, message });
  }

  text(v: unknown, path: string, high: number, low = 1, over = "view_too_large"): string | null {
    if (typeof v !== "string") {
      this.fault(path, "view_bad_template", "a text value is required");
      return null;
    }
    const n = chars(v);
    if (n < low || n > high) {
      this.fault(
        path,
        n > high ? over : "view_bad_template",
        `text of ${low} to ${high} characters is required`,
      );
      return null;
    }
    return v;
  }

  flag(v: unknown, path: string): boolean | null {
    if (typeof v !== "boolean") {
      this.fault(path, "view_bad_template", "true or false is required");
      return null;
    }
    return v;
  }

  named(v: unknown, path: string, allowed: readonly string[], code: string, what: string) {
    if (typeof v === "string" && allowed.includes(v)) return v;
    this.fault(path, code, `${what} is one of ${allowed.join(", ")}`);
    return null;
  }

  terms(ext: unknown, path: string, allowed: string[]): Obj {
    if (!isObj(ext)) {
      this.fault(path, "view_unknown_term", "a view is an object of terms");
      return {};
    }
    const kept: Obj = {};
    for (const [k, v] of Object.entries(ext)) {
      if (allowed.includes(k)) kept[k] = v;
      else if (RELATIONSHIP_ONLY.includes(k))
        this.fault(
          `${path}.${k}`,
          "view_unknown_relationship",
          `'${k}' is a term of a relationship`,
        );
      else this.fault(`${path}.${k}`, "view_unknown_term", `'${k}' is not a term here`);
    }
    return kept;
  }

  template(v: unknown, path: string, t: EntityType): string | null {
    const text = this.text(v, path, MAX_TEMPLATE, 1, "view_bad_template");
    if (text === null) return null;
    let names: string[];
    try {
      names = placeholders(text);
    } catch (e) {
      if (!(e instanceof TemplateError)) throw e;
      this.fault(path, "view_bad_template", e.message);
      return null;
    }
    for (const n of names)
      if (!propertyOf(t, n))
        this.fault(path, "view_unknown_property", `${t.local} has no property '${n}'`);
    return text;
  }

  moduleTerms(ext: unknown, path: string): { title?: string; description?: string } {
    const found = this.terms(ext, path, MODULE_TERMS);
    const out: { title?: string; description?: string } = {};
    if ("title" in found) {
      const t = this.text(found.title, `${path}.title`, MAX_MODULE_TITLE);
      if (t !== null) out.title = t;
    }
    if ("description" in found) {
      const d = this.text(found.description, `${path}.description`, MAX_MODULE_DESCRIPTION, 0);
      if (d !== null) out.description = d;
    }
    return out;
  }

  recordTerms(ext: unknown, path: string, t: EntityType): RecordTerms {
    const found = this.terms(ext, path, RECORD_TERMS);
    const out: RecordTerms = {};
    const put = <K extends keyof RecordTerms>(k: K, v: RecordTerms[K] | null) => {
      if (v !== null && v !== undefined) out[k] = v;
    };
    if ("label" in found) put("label", this.text(found.label, `${path}.label`, MAX_LABEL));
    if ("pluralLabel" in found)
      put("pluralLabel", this.text(found.pluralLabel, `${path}.pluralLabel`, MAX_LABEL));
    if ("icon" in found)
      put("icon", this.named(found.icon, `${path}.icon`, ICONS, "view_unknown_icon", "an icon"));
    if ("tone" in found)
      put("tone", this.named(found.tone, `${path}.tone`, TONES, "view_unknown_tone", "a tone"));
    if ("title" in found) put("title", this.template(found.title, `${path}.title`, t));
    if ("summary" in found) put("summary", this.template(found.summary, `${path}.summary`, t));
    if ("sections" in found) put("sections", this.sections(found.sections, `${path}.sections`, t));
    if ("search" in found) put("search", this.search(found.search, `${path}.search`, t));
    return out;
  }

  sections(v: unknown, path: string, t: EntityType): DeclaredSection[] | null {
    if (!Array.isArray(v)) {
      this.fault(path, "view_bad_template", "sections is a list");
      return null;
    }
    if (v.length > MAX_SECTIONS)
      this.fault(path, "view_too_large", `at most ${MAX_SECTIONS} sections`);
    const placed = new Set<string>();
    return v
      .map((s, i) => this.section(s, `${path}[${i}]`, t, placed))
      .filter((s): s is DeclaredSection => s !== null);
  }

  section(v: unknown, path: string, t: EntityType, placed: Set<string>): DeclaredSection | null {
    const found = this.terms(v, path, SECTION_TERMS);
    const label = this.text(found.label, `${path}.label`, MAX_LABEL);
    const props = list(found.properties);
    if (props.length === 0 || props.length > MAX_SECTION_PROPERTIES)
      this.fault(
        `${path}.properties`,
        props.length ? "view_too_large" : "view_bad_template",
        `1 to ${MAX_SECTION_PROPERTIES} properties`,
      );
    const names: string[] = [];
    props.forEach((p, i) => {
      const at = `${path}.properties[${i}]`;
      if (typeof p !== "string" || !propertyOf(t, p))
        this.fault(at, "view_unknown_property", `${t.local} has no property ${pyRepr(p)}`);
      else if (placed.has(p))
        this.fault(at, "view_duplicate", `'${p}' is in more than one section`);
      else {
        placed.add(p);
        names.push(p);
      }
    });
    let collapsed = false;
    if ("collapsed" in found) collapsed = this.flag(found.collapsed, `${path}.collapsed`) === true;
    return label ? { label, properties: names, collapsed } : null;
  }

  search(v: unknown, path: string, t: EntityType): string[] | null {
    if (!Array.isArray(v)) {
      this.fault(path, "view_bad_template", "search is a list of property names");
      return null;
    }
    if (v.length > MAX_SEARCH)
      this.fault(path, "view_too_large", `at most ${MAX_SEARCH} search properties`);
    const chosen: string[] = [];
    v.forEach((name, i) => {
      const p = typeof name === "string" ? propertyOf(t, name) : undefined;
      const at = `${path}[${i}]`;
      if (!p) this.fault(at, "view_unknown_property", `no property ${pyRepr(name)}`);
      else if (!isSearchableType(p))
        this.fault(at, "view_bad_template", `'${name}' is not a string`);
      else if (chosen.includes(name as string))
        this.fault(at, "view_duplicate", `'${name}' is listed twice`);
      else chosen.push(name as string);
    });
    return chosen;
  }

  fieldTerms(ext: unknown, path: string, p: Prop): FieldTerms {
    const found = this.terms(ext, path, FIELD_TERMS);
    const out: FieldTerms = {};
    if ("label" in found) {
      const l = this.text(found.label, `${path}.label`, MAX_LABEL);
      if (l !== null) out.label = l;
    }
    if ("format" in found) {
      const f = this.format(found.format, `${path}.format`, p);
      if (f !== null) out.format = f;
    }
    if ("hideWhenEmpty" in found) {
      const h = this.flag(found.hideWhenEmpty, `${path}.hideWhenEmpty`);
      if (h !== null) out.hideWhenEmpty = h;
    }
    if ("tones" in found) {
      const t = this.tones(found.tones, `${path}.tones`, out.format ?? defaultFormat(p));
      if (t !== null) out.tones = t;
    }
    return out;
  }

  format(v: unknown, path: string, p: Prop): string | null {
    if (typeof v !== "string" || !this.knownFormat(v) || !formatSuits(p, v)) {
      this.fault(
        path,
        "view_format_mismatch",
        `${p.name} (${p.type}) cannot be shown as ${pyRepr(v)}`,
      );
      return null;
    }
    return v;
  }

  tones(v: unknown, path: string, fmt: string): Record<string, string> | null {
    if (fmt !== "badge") {
      this.fault(path, "view_format_mismatch", "tones belong to the badge format");
      return null;
    }
    if (!isObj(v)) {
      this.fault(path, "view_bad_template", "tones is an object of value to tone");
      return null;
    }
    const items = Object.entries(v);
    if (items.length > MAX_TONES) this.fault(path, "view_too_large", `at most ${MAX_TONES} tones`);
    const out: Record<string, string> = {};
    for (const [k, tone] of items) {
      const c = this.named(tone, `${path}.${k}`, TONES, "view_unknown_tone", "a tone");
      if (c !== null) out[k] = c;
    }
    return out;
  }

  relationshipTerms(ext: unknown, path: string, hasInverse: boolean): RelationshipTerms {
    const found = this.terms(ext, path, RELATIONSHIP_TERMS);
    const out: RelationshipTerms = {};
    if ("label" in found) {
      const l = this.text(found.label, `${path}.label`, MAX_LABEL);
      if (l !== null) out.label = l;
    }
    if ("inverseLabel" in found) {
      if (hasInverse) {
        const l = this.text(found.inverseLabel, `${path}.inverseLabel`, MAX_LABEL);
        if (l !== null) out.inverseLabel = l;
      } else this.fault(`${path}.inverseLabel`, "view_unknown_relationship", "no inverse");
    }
    if ("hideWhenEmpty" in found) {
      const h = this.flag(found.hideWhenEmpty, `${path}.hideWhenEmpty`);
      if (h !== null) out.hideWhenEmpty = h;
    }
    if ("order" in found) this.order(found.order, `${path}.order`, out);
    return out;
  }

  order(n: unknown, path: string, out: RelationshipTerms): void {
    if (typeof n === "number" && Number.isInteger(n) && n >= 0 && n <= 99) out.order = n;
    else this.fault(path, "view_bad_template", "order is an integer 0 to 99");
  }
}

/** A value as Python's `repr` writes the few kinds a message names (a string, else its JSON). */
function pyRepr(v: unknown): string {
  if (typeof v === "string") return `'${v}'`;
  if (v === null || v === undefined) return "None";
  if (typeof v === "boolean") return v ? "True" : "False";
  return JSON.stringify(v);
}
