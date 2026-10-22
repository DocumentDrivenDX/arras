// SPDX-License-Identifier: MIT OR Apache-2.0
// The Explore and Operate switch (DESIGN-GB, Navigation): a two-option segmented control, the chosen
// option `aria-pressed` with a visible check mark. It exists only for an operator; for anyone else
// it is not rendered at all.
import { Glyph } from "../browser/icons";
import type { Mode } from "./modeRoute";

/** The visible cue of the pressed option: a check mark, drawn from the same state as `aria-pressed`. */
const Check = () => <Glyph name="check" size={12} />;

export function ModeSwitch({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  return (
    <fieldset className="gb-seg">
      <legend className="gb-sr">Mode</legend>
      <button type="button" aria-pressed={mode === "user"} onClick={() => onChange("user")}>
        {mode === "user" && <Check />}Explore
      </button>
      <button type="button" aria-pressed={mode === "admin"} onClick={() => onChange("admin")}>
        {mode === "admin" && <Check />}Operate
      </button>
    </fieldset>
  );
}
