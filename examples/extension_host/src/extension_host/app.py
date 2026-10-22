"""Compose one empty in-memory host from this package's explicitly selected resources."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any, cast

from arras.testing import InMemory
from extension_host.configuration import ResourceName, Settings

MODULE_NAME = "notes"
OWNER = "example_owner"


def _resource(name: str) -> bytes:
    return resources.files("extension_host").joinpath("resources", name).read_bytes()


def _records(name: ResourceName) -> list[dict[str, Any]]:
    envelope = json.loads(_resource(name))
    if envelope.get("format") != "extension-host.graph" or envelope.get("module") != MODULE_NAME:
        raise ValueError("example graph resource has an unsupported envelope")
    records: object = envelope.get("records")
    if not isinstance(records, list):
        raise ValueError("example graph resource must contain records")
    rows = cast(list[object], records)
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("example graph resource must contain records")
    return cast(list[dict[str, Any]], rows)


def compose(settings: Settings) -> tuple[InMemory, str, bytes]:
    """Build an isolated host; return it, the chosen resource name, and original module bytes."""
    world = InMemory()
    document = _resource("module.umf.json")
    world.register(document)
    imported = world.import_records(
        MODULE_NAME, _records(settings.resource), load_id=settings.resource
    )
    if imported.rejected:
        raise ValueError(f"example records were refused: {imported.rejected}")
    return world, settings.resource, document


def run(settings: Settings) -> dict[str, object]:
    world, resource, source = compose(settings)
    actor = world.person(OWNER, MODULE_NAME, "read", "write")
    session = world.arras.session(actor)
    rows = session.query(
        MODULE_NAME,
        "SELECT e.* FROM notes.Entry e ORDER BY e.code LIMIT 100",
    ).rows
    added = session.invoke(
        "notes.AddEntry", {"code": "from-action", "title": "Created through a declared action"}
    )
    return {
        "module": MODULE_NAME,
        "selected_resource": resource,
        "registered_source_bytes": len(source),
        "imported": len(rows),
        "imported_by": world.admin.user,
        "created_by_action": added.created,
        "actor": actor.user,
        "brand": settings.distribution.brand.name,
    }
