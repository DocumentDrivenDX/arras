# SPDX-License-Identifier: MIT OR Apache-2.0
"""The catalog UMF's schema browser is given, built for one viewer (CONTRACT-009).

The console reads it with the viewer's credentials and hands its entries to the browser package:
`{version: 1, entries: [...]}`, each entry a document's text with a little metadata. Here an entry is one module the viewer may read,
and its text is the module's UMF document exactly as it was registered (`Ontology.document`), so
the explorer shows what was declared. Nothing else is put in: no entity data, no action inputs,
no audit rows. A module whose document cannot be read (a replica-only module, or a refusal) is
left out; an outage is raised, so an outage is never shown as an empty catalog.
"""

from __future__ import annotations

import json
from typing import Any

from arras.core import Ontology
from arras.errors import Invalid, Refused, Unsupported
from arras.results import RegisteredDocument
from arras.types import Revision

CATALOG_VERSION = 1
MAX_DOCUMENT = 1024 * 1024  # a larger document is a note entry, not its text
MAX_CATALOG = 8 * MAX_DOCUMENT  # past this, every further document is a note entry


def _revision(r: Revision) -> str:
    parts = [f"{k} {v}" for k, v in r.by_backend.items() if v is not None]
    return ", ".join(parts) or "none"


def _description(doc: RegisteredDocument, record: str, replicas: tuple[str, ...]) -> str:
    return (
        f"Registered at revision {_revision(doc.revision)}; record store {record}; "
        f"replicas {', '.join(replicas) or 'none'}."
    )


def _note(module: str, size: int, limit: int, why: str) -> dict[str, Any]:
    """An entry the explorer can open that says why the document is not shown. It is shaped as a
    JSON Schema so the explorer displays its title and description as declared."""
    text = json.dumps(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": f"{module} (not shown)",
            "description": f"The registered document is {size} bytes, {why} ({limit} bytes).",
        },
        indent=2,
    )
    return {
        "id": f"arras:{module}",
        "title": module,
        "category": "domain",
        "path": f"{module}.not-shown.json",
        "text": text,
        "format": "json",
        "description": f"Not shown: the registered document is larger than {why} allows.",
        "schemaFormat": "json-schema",
    }


def schema_catalog(o: Ontology) -> dict[str, Any]:
    """The viewer's catalog. `Refused` (a token that expired) and `Unavailable` propagate."""
    entries: list[dict[str, Any]] = []
    total = 0
    for mod in o.modules():
        try:
            doc = o.document(mod.name)
        except (Unsupported, Refused, Invalid) as e:
            if isinstance(e, Refused) and e.reason == "token_expired":
                raise  # sign in again is not "no document"
            continue
        size = len(doc.text.encode("utf-8", "surrogatepass"))
        if size > MAX_DOCUMENT:
            entries.append(_note(mod.name, size, MAX_DOCUMENT, "the per-document limit"))
            continue
        if total + size > MAX_CATALOG:
            entries.append(_note(mod.name, size, MAX_CATALOG, "past the catalog's limit"))
            continue
        total += size
        ext = "json" if doc.format == "json" else "yaml"
        entries.append(
            {
                "id": f"arras:{mod.name}",
                "title": mod.name,
                "category": "domain",
                "path": f"{mod.name}.umf.{ext}",
                "text": doc.text,
                "format": doc.format,
                "description": _description(
                    doc, mod.placement.record, tuple(mod.placement.replicas)
                ),
                "schemaFormat": "umf",
            }
        )
    return {"version": CATALOG_VERSION, "entries": entries}
