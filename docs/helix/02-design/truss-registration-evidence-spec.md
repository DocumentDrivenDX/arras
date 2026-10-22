---
ddx:
  id: truss-registration-evidence-spec
  type: design-note
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-20
  authoring:
    home: repo
  links:
    - id: truss-requirements
      kind: informed_by
    - id: truss-catalog-mapping
      kind: informed_by
---

# Registration evidence

Written to be handed to the Truss project as-is. It records what `truss-toolkit` 0.0.45 (native runtime 0.72, layout 1.0, preparation `truss-registration-preparation/2.0`, registration report `truss-catalog-registration-report/0.6`) produces when an embedding Python host prepares UMF 0.10.0 documents, and what is left. It names no host-specific concept.

## Summary

Preparation runs the bundled UMF producer in an embedded V8 (no subprocess, no executable on `PATH`) and keeps the validation results, not per-operation inspection transcripts. The evidence is on the order of the document's own size or smaller, so no limit on it (an owner-observation cap, a bridge output cap, a decode bound) is reached by any document the host has. `prepare_acceptance` and `prepare_catalog` take the same time. The only accepted source is UMF 0.10.0: a document that says another version is refused `unsupported_profile`.

## Measurements

macOS arm64, load average near 9, `prepare_acceptance` and `prepare_catalog` three runs each (the times agree to 0.02 s):

| Document | UMF bytes | Evidence bytes | `prepare_acceptance` | `prepare_catalog` |
|----------|----------:|---------------:|---------------------:|------------------:|
| conformance module | 12,827 | 706 | 0.36 s | 0.36 s |
| sample "pizza" | 37,289 | 1,356 | 0.39 s | 0.39 s |
| sample "northwind" | 74,603 | 2,016 | 0.40 s | 0.41 s |
| sample "catalog" (37 elements, 30 actions) | 88,530 | 2,341 | 0.42 s | 0.42 s |

All four register on a real Truss through the host's adapter and take writes.

## Asks

### E1. Evidence linear in the document (met)

The three samples and the control module prepare with evidence under 2.4 KB each. Not run: a 500 KB document.

### E2. A typed refusal, before the database

No document the host has is refused for its evidence. The reasons of a refusal in preparation 2.0 are `resource`, `invalid_input`, `invalid_document`, `unsupported_profile` and `producer_unavailable`.

### E3. No bare `ValueError` mapped to `invalid_transaction` (open, in part)

A record or field element with no `name` is refused at registration: `prepare_group_in_transaction` answers `PreparationRejected(reason='invalid_document')` whose diagnostics carry one `TRUSS-NAME-MISSING` for each element (module, element id, kind, JSON pointer), measured on 0.0.45 with a pizza document with every `name` removed (R16.4 of `truss-requirements.md`). A decimal other than precision 18 and scale 4 and structured values were not re-run on 0.0.41.

### E5. Registration time

0.36 to 0.42 s a document, about 0.2 s of a registration of an unchanged document over TCP (the reader catalog read dominates).

## Reproduction

```python
import json
from hashlib import sha256
from pathlib import Path
from truss import CatalogDocument
from truss.catalog_runtime import _configuration
from truss.catalog_preparation import prepare_catalog
from truss.preparation import PreparationRejected, prepare_acceptance
from truss._catalog_report_semantics import canonical_numeric_free

for path in ("pizza.umf.json", "northwind.umf.json", "catalog.umf.json"):
    raw = Path(path).read_bytes()
    doc = json.loads(raw)
    carrier = (CatalogDocument(doc["id"], sha256(raw).hexdigest(), raw),)
    prepared = prepare_acceptance(carrier, canonical_numeric_free(_configuration()))
    print(path, len(raw), len(prepared.report_evidence_bytes))
    prepare_catalog(carrier)
```

The documents are in the host repository at `examples/pizza/pizza.umf.json`, `examples/northwind/northwind.umf.json` and `examples/catalog/catalog.umf.json`; they are plain UMF 0.10.0 with one module each.
