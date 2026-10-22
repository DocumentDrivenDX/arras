# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""Reading a module's registered UMF document back, verbatim (CONTRACT-001, 002, 004; concern
`umf-fidelity`)."""

import json
import logging

import pytest

from arras import (
    Arras,
    Invalid,
    Placement,
    Refused,
    RegisteredDocument,
    Unavailable,
    Unsupported,
)
from arras.sandbox import Sandbox, catalog_document


@pytest.fixture
def box() -> Sandbox:
    return Sandbox().seed()


def as_(box: Sandbox, who: str):
    return box.arras.session(box.people[who])


def odd(text: str) -> str:
    """The catalog document as a person might have written it: tabs, a trailing space after
    a comma, an escaped character, the keys of the root out of order and no final newline."""
    d = json.loads(text)
    root = {"modules": d.pop("modules"), **d}
    out = json.dumps(root, indent="\t", ensure_ascii=True, separators=(", ", " :  "))
    return out.replace('"catalog"', '"cat\\u0061log"', 1).rstrip("\n")


def test_a_reader_gets_the_registered_document_verbatim(box: Sandbox) -> None:
    doc = as_(box, "carol").document("catalog")
    assert isinstance(doc, RegisteredDocument)
    assert doc.module == "catalog" and doc.format == "json"
    assert doc.text == catalog_document()  # the original text, not a re-serialization
    assert doc.revision == as_(box, "carol").describe("catalog")[0].revision


def test_odd_whitespace_escapes_and_key_order_survive_byte_for_byte() -> None:
    text = odd(catalog_document())
    assert json.loads(text) == json.loads(catalog_document())  # the same module, other bytes
    box = Sandbox().load(text)
    got = box.arras.session(box.people["alice"]).document("catalog")
    assert got.text == text and got.text.encode() == text.encode()


def test_bytes_are_kept_as_registered_including_non_ascii() -> None:
    d = json.loads(catalog_document())
    d["modules"][0]["elements"][0]["description"] = "Cas d’usage — résumé"
    raw = json.dumps(d, ensure_ascii=False, indent=1).encode("utf-8")
    box = Sandbox()
    box.arras.session(box.people["root"]).registry().register(raw)
    box.access.grant("alice", "catalog", "read")
    got = box.arras.session(box.people["alice"]).document("catalog")
    assert got.text.encode("utf-8") == raw


def test_the_same_module_keeps_its_revision_and_text_and_a_change_replaces_both(
    box: Sandbox,
) -> None:
    root = box.arras.session(box.people["root"]).registry()
    before = as_(box, "alice").document("catalog")
    assert root.register(catalog_document()).changed is False  # the same bytes: nothing changes
    assert as_(box, "alice").document("catalog") == before
    # The same meaning in other bytes is no new revision (as Truss accepts none when the derived
    # rows are equal), so the revision keeps the one text registered at it.
    assert root.register(odd(catalog_document())).changed is False
    assert as_(box, "alice").document("catalog") == before
    d = json.loads(catalog_document())
    d["modules"][0]["elements"][0]["description"] = "changed"  # a description is the document's
    changed = json.dumps(d, indent=3)
    r = root.register(changed)
    assert r.changed and r.revision != before.revision
    got = as_(box, "alice").document("catalog")
    assert got.text == changed and got.revision == r.revision


def test_an_unknown_and_an_unreadable_module_are_the_same_invalid(box: Sandbox) -> None:
    with pytest.raises(Invalid) as unknown:
        as_(box, "alice").document("nosuch")
    with pytest.raises(Invalid) as unreadable:
        as_(box, "dave").document("catalog")  # dave holds no grant on catalog
    assert [v.code for v in unknown.value.violations] == ["unknown_type"]
    assert [v.code for v in unreadable.value.violations] == ["unknown_type"]


def test_no_token_and_the_administrator_are_refused(box: Sandbox) -> None:
    with pytest.raises(Refused) as e:
        box.arras.session(box.principal("(no token)")).document("catalog")
    assert e.value.reason == "token_expired"
    with pytest.raises(Refused):
        as_(box, "root").document("catalog")  # a read is a person's (CONTRACT-005)


def test_a_replica_only_module_is_unsupported() -> None:
    box = Sandbox()
    d = json.loads(catalog_document().replace('"catalog"', '"shelf"'))
    d["modules"][0]["actions"] = []
    box.arras = Arras.start(  # the host places `shelf` on the replica alone: read-only there
        box.backends,
        admin=box.people["root"],
        placement={"shelf": Placement(box.replica.name)},
        default_placement=Placement(box.store.name, (box.replica.name,)),
    )
    box.access.grant("root", "shelf", "read", "write", "schema", admin=True)
    box.arras.session(box.people["root"]).registry().attach(json.dumps(d))
    alice = box.access.grant("alice", "shelf", "read")
    with pytest.raises(Unsupported):
        box.arras.session(alice).document("shelf")


def test_the_library_never_asks_a_replica_for_a_document(monkeypatch) -> None:
    """Even a replica that answered would not be asked: the registered document is the
    record store's, and an attached module has none."""
    from arras.fakes import MemoryReplica

    asked: list[str] = []
    monkeypatch.setattr(
        MemoryReplica, "document", lambda self, p, m: asked.append(m), raising=False
    )
    test_a_replica_only_module_is_unsupported()
    assert asked == []


def test_an_outage_is_unavailable_never_absent(box: Sandbox) -> None:
    box.store.available = False
    box.replica.available = False
    with pytest.raises(Unavailable):
        as_(box, "alice").document("catalog")


def test_the_record_store_itself_gates_the_document(box: Sandbox) -> None:
    dave = box.people["dave"]
    with pytest.raises(Refused) as e:
        box.store.document(dave, "catalog")
    assert e.value.reason == "no_access"
    box.access.grant("alice", "nosuch", "read")
    with pytest.raises(Invalid):
        box.store.document(box.people["alice"], "nosuch")
    with pytest.raises(Unsupported):
        box.replica.document(box.people["alice"], "catalog")  # pyright: ignore[reportAttributeAccessIssue]


def test_reading_the_document_is_one_event_with_the_resolved_module(
    box: Sandbox, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="arras.telemetry")
    as_(box, "alice").document("catalog")
    with pytest.raises(Invalid):
        as_(box, "alice").document("secret-module-name")
    events = [r for r in caplog.records if getattr(r, "arras_event", "") == "arras.document"]
    attrs = [e.__dict__["arras_attrs"] for e in events]
    assert [a.get("outcome") for a in attrs] == ["ok", "error"]
    assert attrs[0]["module"] == "catalog" and attrs[0]["backend"] == "memory"
    assert "module" not in attrs[1]  # never what the caller typed
