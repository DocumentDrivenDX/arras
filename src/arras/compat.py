# SPDX-License-Identifier: MIT OR Apache-2.0
"""Compatibility rules applied when a module registers a new revision (CONTRACT-002).

They are stricter than a backend's, so no accepted change rewrites records. Retiring a name and
reserving its identifier is the backend's; the rule here is only that removal is refused while
records exist.
"""

from __future__ import annotations

from typing import Any, Protocol

from arras.errors import Invalid, Violation
from arras.model import ModuleInfo, PropertyInfo


class RecordStats(Protocol):
    """What the authority can say about the records of a module's types."""

    def count(self, type_name: str) -> int: ...

    def missing(self, type_name: str, prop: str) -> list[str]:
        """Keys of the entities of the type that hold no value for the property."""
        ...


def _bad(path: str, message: str) -> Violation:
    return Violation(path, "incompatible_change", message)


def _action_types(action: Any) -> set[str]:
    """The entity types (local names) an action's inputs, effects and preconditions name."""
    names = {s.type for s in action.inputs if s.kind == "ref"}

    def walk(effects: Any) -> None:
        for e in effects:
            names.update(x for x in (e.type, e.ref_type) if x)
            walk(e.body)

    walk(action.effects)
    names.update(
        p.args["type"] for p in action.preconditions if p.op == "absent" and "type" in p.args
    )
    return {n for n in names if isinstance(n, str)}


def check(old: ModuleInfo | None, new: ModuleInfo, stats: RecordStats) -> None:
    """Raise `Invalid` (`incompatible_change`) naming every rule the change breaks."""
    if old is None:
        return
    out: list[Violation] = []
    if new.name != old.name:
        out.append(_bad("module", "a module's name cannot change"))
    if new.metadata_profile != old.metadata_profile:
        out.append(_bad("metadata_profile", "a module's metadata profile cannot change"))
    new_types = {t.name: t for t in new.entity_types}
    named = {e for r in new.relationships for e in (*r.source, *r.target)}
    for ot in old.entity_types:
        path = f"types.{ot.name}"
        nt = new_types.get(ot.name)
        n = stats.count(ot.name)
        if nt is None:
            if n:
                out.append(_bad(path, f"cannot remove a type while {n} records exist"))
            if ot.name in named:
                out.append(_bad(path, "cannot remove a type a relationship names"))
            if ot.local_name in {t for a in old.actions for t in _action_types(a)}:
                out.append(_bad(path, "cannot remove a type an action names"))
            continue
        if nt.key != ot.key:
            out.append(_bad(path, "the key of a type cannot change"))
        old_props = {p.name: p for p in ot.properties}
        for np_ in nt.properties:
            op = old_props.get(np_.name)
            if op is None:
                if np_.required and n:
                    out.append(
                        _bad(
                            f"{path}.{np_.name}",
                            f"cannot add a required property while {n} records exist",
                        )
                    )
            else:
                _changed(op, np_, ot.name, stats, out)
        new_props = {p.name for p in nt.properties}
        for name in old_props.keys() - new_props:
            if n:
                out.append(
                    _bad(f"{path}.{name}", f"cannot remove a property while {n} records exist")
                )
    _relationships(old, new, stats, out)
    if out:
        raise Invalid(out)


def _changed(
    old: PropertyInfo,
    new: PropertyInfo,
    tname: str,
    stats: RecordStats,
    out: list[Violation],
) -> None:
    path = f"types.{tname}.{old.name}"
    same = (old.type, old.scalar, old.cardinality) == (new.type, new.scalar, new.cardinality)
    if same:
        return
    if (old.type, old.scalar) == (new.type, new.scalar) and (
        old.cardinality == "optional" and new.cardinality == "one"
    ):
        offenders = stats.missing(tname, old.name)
        if offenders:
            out.append(
                _bad(
                    path,
                    f"{len(offenders)} records lack it, so it cannot be required: {offenders[:10]}",
                )
            )
        return
    out.append(_bad(path, "a property's type or cardinality cannot change"))


def _relationships(
    old: ModuleInfo, new: ModuleInfo, stats: RecordStats, out: list[Violation]
) -> None:
    new_rels = {r.name: r for r in new.relationships}
    for orl in old.relationships:
        nr = new_rels.get(orl.name)
        if nr is None:
            continue  # removal of a relationship is the backend's to retire
        for side, o, n in (("source", orl.source, nr.source), ("target", orl.target, nr.target)):
            # The count of the removed endpoint's records stands in for its instances, which the
            # authority does not yet report (CONTRACT-004).
            for t in sorted(set(o) - set(n)):
                if c := stats.count(t):
                    out.append(
                        _bad(
                            f"relationships.{orl.name}.{side}",
                            f"cannot drop {t} from the endpoints while {c} records exist",
                        )
                    )
