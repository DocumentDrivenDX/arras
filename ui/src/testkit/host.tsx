// SPDX-License-Identifier: MIT OR Apache-2.0
import { DevHost } from "../dev/DevHost";
import { Button, Mark, Notice, Select, TextArea, TextField } from "../ds";
import { readBrandMeta } from "../lib/brand";

/** Standard sandbox acceptance host; downstream themes wrap this with their own provider. */
export function AcceptanceHost() {
  return <DevHost brand={readBrandMeta(document)} />;
}

/**
 * The controls region `arras-ui-qualify --host-build` reads (`support/QUALIFICATION.md`, "Host-build fixture
 * contract"): the six widgets of the design system in context, in the tab order the check walks (Button, TextField,
 * TextArea, Select), under the accessible name it looks for. The host's widgets carry the `data-theme-*`
 * markers; render this inside the host's provider and inside an `.arras-root`.
 */
export function WidgetControls() {
  return (
    <section aria-label="Downstream widget controls">
      <h1>Downstream themed controls</h1>
      <Mark label="Host mark" />
      <Button>Host action</Button>
      <TextField label="Host name" name="name" />
      <TextArea label="Host notes" name="notes" />
      <Select
        label="Host mode"
        options={[{ value: "one", label: "One" }]}
        placeholder="Choose mode"
      />
      <Notice title="Host status">Theme fixture is ready.</Notice>
    </section>
  );
}
