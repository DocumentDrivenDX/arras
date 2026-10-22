# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
from typing import Any

import pytest

from arras.conformance import (
    KNOWN_TAGS,
    SETUP_OPS,
    STEP_OPS,
    Limit,
    load_corpus,
    run_corpus,
)
from arras.conformance.fakes import MemoryReplicaHarness, MemoryStoreHarness
from arras.fakes import MemoryReplica, MemoryStore


def ids(*tags: str) -> list[str]:
    return [c["id"] for c in load_corpus()["cases"] if set(tags) & set(c["tags"])]


@pytest.mark.parametrize("case", ids("store", "reader"))
def test_memory_store_passes(case: str) -> None:
    [r] = run_corpus(MemoryStoreHarness, only=[case]).results
    assert r.ok, r.message


@pytest.mark.parametrize("case", ids("reader-only", "reader"))
def test_memory_replica_passes(case: str) -> None:
    [r] = run_corpus(MemoryReplicaHarness, only=[case]).results
    assert r.ok, r.message


def test_the_fakes_pass_the_whole_corpus() -> None:
    for harness in (MemoryStoreHarness, MemoryReplicaHarness):
        report = run_corpus(harness)
        assert report.passed and not report.failed and report.skipped


# -- the corpus itself
def test_the_corpus_is_well_formed() -> None:
    corpus = load_corpus()
    seen: set[str] = set()
    for c in corpus["cases"]:
        assert c["id"] not in seen
        seen.add(c["id"])
        assert set(c["tags"]) <= KNOWN_TAGS and c["tags"]
        assert c["fixture"] in corpus["fixtures"]
        for step in c["steps"]:
            assert step["op"] in SETUP_OPS | STEP_OPS, (c["id"], step["op"])
            if step["op"] in STEP_OPS:
                assert "expect" in step, (c["id"], step["op"])


def test_every_listed_area_is_covered_by_some_case() -> None:
    corpus = load_corpus()
    covered = {a for c in corpus["cases"] for a in c["covers"]}
    assert set(corpus["covers"]) <= covered, set(corpus["covers"]) - covered
    for tags in (("store", "reader"), ("reader-only", "reader")):
        assert len(ids(*tags)) >= 15


def test_nothing_in_the_corpus_hard_codes_a_backend_token_format() -> None:
    text = open(__import__("arras.conformance", fromlist=["x"]).__file__).read()
    assert "fake:" not in text
    corpus = load_corpus()
    assert "fake:" not in str(corpus["cases"]) and "fake:" not in str(corpus["fixtures"])


# -- the runner holds an adapter to it: each mutation must fail some case
class _Mutant(MemoryStore):
    pass


def mutant(store_cls: type, **fixes: Any) -> type:
    class H(MemoryStoreHarness):
        def __init__(self) -> None:
            super().__init__()
            self.auth = store_cls(self.access)
            self.root = self.access.grant("root", "catalog", "read", "write", "schema", admin=True)

    for k, v in fixes.items():
        setattr(H, k, v)
    return H


def failing(harness: type) -> list[str]:
    report = run_corpus(harness)
    return [f"{r.case}: {r.message}" for r in report.failed]


def test_import_that_overwrites_a_held_entity_fails() -> None:
    class A(MemoryStore):
        def _import_entity(self, work, mod, r, load_id, by, now):
            for k in [k for k in work.entities if k.key == str(r.get("key"))]:
                del work.entities[k]
            return super()._import_entity(work, mod, r, load_id, by, now)

    assert any(f.startswith("import.identity") for f in failing(mutant(A)))


def test_import_that_resurrects_a_deleted_entity_fails() -> None:
    class A(MemoryStore):
        def _import_entity(self, work, mod, r, load_id, by, now):
            work.tombstones.clear()
            return super()._import_entity(work, mod, r, load_id, by, now)

    assert any(f.startswith("import.deleted") for f in failing(mutant(A)))


def test_extra_columns_and_missing_attribution_fail() -> None:
    class Extra(MemoryStore):
        def query(self, *a, **k):
            ans = super().query(*a, **k)
            from dataclasses import replace

            return replace(ans, rows=tuple({**r, "extra": 1} for r in ans.rows))

    class NoAttribution(MemoryStore):
        def query(self, *a, **k):
            from dataclasses import replace

            ans = super().query(*a, **k)
            return replace(
                ans,
                rows=tuple({k: v for k, v in r.items() if k != "_created_at"} for r in ans.rows),
            )

    assert failing(mutant(Extra))
    # the facts a backend appends to a whole-entity row are every adapter's to carry
    assert any("_created_at" in f for f in failing(mutant(NoAttribution)))


def test_stop_on_error_that_keeps_going_fails() -> None:
    class A(MemoryStore):
        def apply_batch(self, *a, **k):
            k["stop_on_error"] = False
            return super().apply_batch(*a, **k)

    assert any("independent-batch" in f for f in failing(mutant(A)))


def test_a_lost_write_is_found_by_the_read_back() -> None:
    class A(MemoryStore):
        def _commit(self, work, action, key, digest, result):
            self._journal[(action, key)] = (digest, result)  # type: ignore  # state not kept

    assert failing(mutant(A))


def test_idempotency_that_never_replays_fails() -> None:
    class A(MemoryStore):
        def _held(self, action, key, digest):
            return None

    assert any("idempotent" in f or "key-reused" in f for f in failing(mutant(A)))


def test_a_shared_identity_for_another_persons_token_fails() -> None:
    class Open(MemoryStoreHarness):
        def borrowed(self, user, token_owner):  # an adapter that trusts the token alone
            from arras.types import Principal

            return Principal(token_owner, self.users[token_owner].token)

    assert any(f.startswith("access.anothers-token") for f in failing(Open))


def test_an_adapter_exception_is_reported_against_its_case_not_the_run() -> None:
    class Boom(MemoryStore):
        def query(self, *a, **k):
            raise ConnectionError("socket closed")

    report = run_corpus(mutant(Boom))
    kinds = ("failed", "harness_error", "fake_only_failed")
    assert report.failed and all(r.status in kinds for r in report.failed)
    assert any(r.status == "failed" for r in report.failed) and not report.passed
    assert any("ConnectionError" in r.message for r in report.failed)
    assert len(report.results) > len(report.failed)  # the run went on


def test_a_replica_without_the_write_operations_is_a_failure_not_a_crash() -> None:
    class Bare(MemoryReplicaHarness):
        def __init__(self) -> None:
            super().__init__()

            class R(MemoryReplica):
                pass

            r = R(self.auth, self.access)
            for name in ("apply", "apply_batch", "import_records", "register"):
                setattr(R, name, property(lambda self: (_ for _ in ()).throw(AttributeError("no"))))
            self.replica = r

    assert any(f.startswith("replica.refuses") for f in failing(Bare))


def test_a_harness_that_cannot_build_the_world_is_a_harness_error() -> None:
    class NoSeed(MemoryStoreHarness):
        def seed(self, user, records):
            raise RuntimeError("cannot load")

    report = run_corpus(NoSeed)
    assert report.results and all(r.status == "harness_error" for r in report.results)
    assert not report.passed


def test_a_replica_that_declares_less_is_held_to_its_descriptor() -> None:
    from arras.fakes_weft import ENTITY, WEFT
    from arras.results import WeftSupport

    class NoCount(MemoryReplicaHarness):
        def __init__(self) -> None:
            super().__init__()
            self.replica.weft = WeftSupport(WEFT.version, (ENTITY,))

    cases = [
        "read.count-group-by",
        "read.relationship-filter-both-directions",
        "read.paging-by-key",
        "read.inner-join-is-a-bag",
        "read.count-over-a-join-by-several-columns",
        "access.no-grant-is-refused-not-empty",  # unknown_type before its profile refusal
    ]
    report = run_corpus(NoCount, only=cases)
    assert report.passed and len(report.results) == 6  # it answers Unsupported, as it declares

    from arras.fakes_weft import GENERAL, RELATED

    for declared in ((ENTITY, RELATED, GENERAL), (GENERAL,)):  # `general` covers every profile

        class General(MemoryReplicaHarness):
            def __init__(self, declared=declared) -> None:
                super().__init__()
                self.replica.weft = WeftSupport(WEFT.version, declared)

        report = run_corpus(General, only=cases)
        assert report.passed and len(report.results) == 6, (declared, report)

    class Lies(MemoryReplicaHarness):  # declares counts but refuses them: held to its declaration
        def __init__(self) -> None:
            super().__init__()
            self.replica.weft = WeftSupport(WEFT.version, (ENTITY,))

        def backend(self) -> Any:
            from dataclasses import replace

            real = self.replica

            class Claims:
                def __getattr__(self, name):
                    return getattr(real, name)

                def describe(self):
                    return replace(real.describe(), weft=WEFT)

            return Claims()

    assert not run_corpus(Lies, only=["read.count-group-by"]).passed
    assert not run_corpus(Lies, only=["read.inner-join-is-a-bag"]).passed  # claims `general`


def test_whole_entity_rows_carry_their_facts_and_relationships_their_keys() -> None:
    """No case is outside the pass rule: the facts a backend appends and the keys `RELATED_KEYS`
    returns are held of every adapter."""
    corpus = load_corpus()
    assert all("fake-only" not in c["tags"] for c in corpus["cases"])
    for c in corpus["cases"]:
        for step in c["steps"]:
            text = str(step.get("expect", {}))
            if step["op"] == "query" and ("addresses" in text or "addressedBy" in text):
                assert "RELATED_KEYS" in step["sql"] or "HAS_RELATED" in step["sql"], c["id"]
            assert "fake_only" not in step, c["id"]
            assert step["op"] != "query" or "after" not in step, c["id"]
    store = {r.case: r.status for r in run_corpus(MemoryStoreHarness).results}
    assert set(store.values()) == {"passed"}


def test_a_counted_read_back_fails_an_adapter_that_breaks_the_rule() -> None:
    from dataclasses import replace

    class NoVersion(MemoryStore):  # whole-entity rows without `_version`
        def query(self, *a, **k):
            ans = super().query(*a, **k)
            return replace(
                ans, rows=tuple({k: v for k, v in r.items() if k != "_version"} for r in ans.rows)
            )

    report = run_corpus(mutant(NoVersion), only=["action.update-bumps-the-version-once"])
    assert [r.status for r in report.results] == ["failed"] and not report.passed

    class NoLink(MemoryStore):  # an action that loses its link fails the counted read-back
        def _effects(self, work, principal, effects, mod, now, counts, touched):
            from arras.actions import Link

            kept = [e for e in effects if not isinstance(e, Link)]
            return super()._effects(work, principal, kept, mod, now, counts, touched)

    report = run_corpus(mutant(NoLink), only=["action.applies-atomically-and-reads-back"])
    assert [r.status for r in report.results] == ["failed"] and not report.passed


def test_the_runner_parses_no_statement() -> None:
    import arras.conformance as c

    text = open(c.__file__).read()
    assert "dialect" not in text and "resolve_query" not in text and "fakes_weft" not in text


def test_strictness_unknown_keys_and_missing_values_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    import arras.conformance as c

    base = c.load_corpus()

    def with_step(step: dict) -> dict:
        corpus = {
            **base,
            "cases": [
                {
                    "id": "x",
                    "tags": ["store"],
                    "covers": [],
                    "description": "",
                    "fixture": "basic",
                    "steps": [step],
                }
            ],
        }
        return corpus

    q = {
        "op": "query",
        "as": "carol",
        "sql": "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100",
    }
    for step, needle in (
        ({**q, "expect": {"row_count": 2, "bogus": 1}}, "unknown expectation"),
        ({**q, "expect": {"row_count": 2}, "save": {"cursor": "c"}}, "nothing to save"),
        ({**q, "as": "anon", "expect": {"error": "Refused", "bogus": 1}}, "unknown"),
        ({**q}, "states what it expects"),
        ({**q, "expect": {"rows": [{"nope": 1}, {"nope": 2}]}}, "has no 'nope'"),
        (
            {"op": "reached", "as": "carol", "token": "$never", "expect": {"value": True}},
            "never saved",
        ),
        ({"op": "teleport", "expect": {}}, "unknown op"),
        (
            {
                "op": "apply",
                "as": "alice",
                "action": "catalog.AddUseCase",
                "inputs": {"code": "x", "name": "x"},
                "expect": {"receipt": {"bogus": 1}},
            },
            "unknown receipt",
        ),
    ):
        corpus = with_step(step)
        monkeypatch.setattr(c, "load_corpus", lambda corpus=corpus: corpus)
        [r] = c.run_corpus(MemoryStoreHarness).results
        assert r.status == "failed" and needle in r.message, (step, r)


def test_a_newer_corpus_than_the_adapter_claims_is_reported_not_passed() -> None:
    class Old(MemoryStoreHarness):
        corpus_version = 0

    report = run_corpus(Old)
    assert report.newer_corpus and not report.passed and not report.results


def test_unknown_tags_are_a_failure_not_a_silent_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    import arras.conformance as c

    corpus = {
        **c.load_corpus(),
        "cases": [
            {
                "id": "x",
                "tags": ["authorty"],
                "covers": [],
                "description": "",
                "fixture": "basic",
                "steps": [],
            }
        ],
    }
    monkeypatch.setattr(c, "load_corpus", lambda: corpus)
    [r] = c.run_corpus(MemoryStoreHarness).results
    assert r.status == "failed" and "unknown tags" in r.message


# -- text search
def test_a_backend_that_treats_percent_and_underscore_as_wildcards_fails() -> None:
    """@covers US-065-AC1: `%` and `_` in the text match literally (CONTRACT-010)."""
    import re
    from dataclasses import replace

    class Wild(MemoryStore):
        def query(self, principal, module, statement, *, limit, text=None):
            if text is None:
                return super().query(principal, module, statement, limit=limit)
            ans = super().query(principal, module, statement, limit=100)
            pats = [
                re.compile(re.escape(w).replace("%", ".*").replace("_", "."), re.I)
                for w in text.words
            ]
            rows = tuple(
                r
                for r in ans.rows
                if all(
                    any(isinstance(r.get(p), str) and pat.search(r[p]) for p in text.properties)
                    for pat in pats
                )
            )
            return replace(ans, rows=rows[:limit])

    assert any("percent-underscore-backslash" in f for f in failing(mutant(Wild)))


def test_a_backend_that_ignores_the_text_fails() -> None:

    class Ignores(MemoryStore):
        def query(self, principal, module, statement, *, limit, text=None):
            return super().query(principal, module, statement, limit=limit)

    found = failing(mutant(Ignores))
    assert any(f.startswith("text.every-word") for f in found)
    assert any(f.startswith("text.only-the-named") for f in found)


def test_a_backend_that_declares_no_search_is_held_to_unsupported() -> None:
    """@covers US-065-AC6: a type whose backend declares `none` answers `Unsupported`."""
    from arras.fakes_search import with_search

    class NoSearch(MemoryStore):
        def caps(self, t):
            return with_search(super().caps(t), t, "none")

    assert failing(mutant(NoSearch)) == []
    cases = [c["id"] for c in load_corpus()["cases"] if c["id"].startswith("text.")]
    assert len(cases) >= 9


def test_corpus_9_names_a_person_on_every_reached_step() -> None:
    import arras.conformance as c

    corpus = c.load_corpus()
    assert corpus["version"] == 13
    assert MemoryStoreHarness.corpus_version == MemoryReplicaHarness.corpus_version == 13
    steps = [s for case in corpus["cases"] for s in case["steps"] if s["op"] == "reached"]
    assert steps and all(s.get("as") for s in steps)
    assert not run_corpus(MemoryStoreHarness).newer_corpus


def test_a_reached_step_without_a_person_fails_and_a_non_member_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import arras.conformance as c

    base = c.load_corpus()
    case = next(x for x in base["cases"] if x["id"] == "freshness.store-has-reached-its-own-tokens")
    for step, ok in (
        ({"op": "reached", "token": "fake:0", "expect": {"value": True}}, False),
        ({"op": "reached", "as": "dave", "token": "fake:0", "expect": {"error": "Refused"}}, True),
    ):
        one = {**case, "steps": [step]}
        monkeypatch.setattr(c, "load_corpus", lambda one=one: {**base, "cases": [one]})
        [r] = c.run_corpus(MemoryStoreHarness).results
        assert (r.status == "passed") is ok, r
        if not ok:
            assert "names a person" in r.message


# -- corpus 9: the cases the Truss adapter needs
NEW_CASES = [
    "access.non-member-write-is-refused",
    "freshness.non-member-reached-is-refused",
    "registry.rewritten-equal-document-registers-unchanged",
    "action.retry-with-generated-keys-matches",
]


def test_corpus_9_holds_the_cases_the_truss_adapter_needs() -> None:
    corpus = load_corpus()
    assert corpus["version"] == 13
    assert MemoryStoreHarness.corpus_version == MemoryReplicaHarness.corpus_version == 13
    held = {c["id"] for c in corpus["cases"]}
    assert set(NEW_CASES) <= held
    assert "freshness.undeterminable-token-is-unavailable-not-false" in held  # not duplicated
    assert not run_corpus(MemoryStoreHarness).newer_corpus


def test_a_store_that_lets_a_non_member_write_fails_the_corpus() -> None:
    class A(MemoryStore):
        def gate(self, principal, module, mode, op):
            if mode == "write" and not self.access.grants.get(principal.user):
                return  # leaks only for a person who holds nothing here
            super().gate(principal, module, mode, op)

    failed = {f.split(":", 1)[0] for f in failing(mutant(A))}
    assert failed == {"access.non-member-write-is-refused"}


def test_a_store_that_answers_reached_for_a_non_member_fails_the_corpus() -> None:
    class A(MemoryStore):
        def reached(self, principal, token):
            if not self.access.grants.get(principal.user):
                return True  # leaks only for a non-member; members are answered as before
            return super().reached(principal, token)

    failed = {f.split(":", 1)[0] for f in failing(mutant(A))}
    assert failed == {"freshness.non-member-reached-is-refused"}


def test_a_store_that_compares_bytes_for_an_equal_registration_fails_the_corpus() -> None:
    class A(MemoryStore):
        def _unchanged(self, module, document):
            return self.documents.get(module.name) == document

    assert any(f.startswith("registry.rewritten-equal") for f in failing(mutant(A)))


def test_a_store_that_keys_a_retry_on_the_plan_effects_fails_the_corpus() -> None:
    class A(MemoryStore):
        @staticmethod
        def _digest(plans):
            return repr([(p.action, p.effects) for p in plans])

    assert any(f.startswith("action.retry-with-generated-keys") for f in failing(mutant(A)))


# -- a backend that declares no journal answers Unsupported to the audit reads (TR-11)
JOURNAL_CASES = ["journal.changes-are-committed-groups-newest-first", "journal.loads-newest-first"]


def _audit_harness(*, declares: bool, raises: bool) -> type:
    from dataclasses import replace

    from arras.errors import Unsupported

    class H(MemoryStoreHarness):
        def backend(self) -> Any:
            real = self.auth

            class Wrapped:
                def __getattr__(self, name: str) -> Any:
                    return getattr(real, name)

                def describe(self) -> Any:
                    return replace(real.describe(), audit=declares)

                def changes(self, *a: Any, **k: Any) -> Any:
                    if raises:
                        raise Unsupported("changes", [])
                    return real.changes(*a, **k)

                def loads(self, *a: Any, **k: Any) -> Any:
                    if raises:
                        raise Unsupported("loads", [])
                    return real.loads(*a, **k)

            return Wrapped()

    return H


def test_a_backend_declaring_no_audit_is_held_to_unsupported_and_a_false_claim_fails() -> None:
    ok = run_corpus(_audit_harness(declares=False, raises=True), only=JOURNAL_CASES)
    assert ok.passed and len(ok.results) == 2, ok
    # the other steps still run: a backend that declares none but serves the reads fails
    serving = run_corpus(_audit_harness(declares=False, raises=False), only=JOURNAL_CASES)
    assert len(serving.failed) == 2
    # negative control: a claim of a journal that answers Unsupported fails
    lying = run_corpus(_audit_harness(declares=True, raises=True), only=JOURNAL_CASES)
    assert len(lying.failed) == 2


# -- a backend's documented limits: a case ends at a declared step, or it fails


def _limit_corpus(monkeypatch: pytest.MonkeyPatch, step: dict[str, Any]) -> None:
    import arras.conformance as c

    corpus = {
        **c.load_corpus(),
        "cases": [
            {
                "id": "x",
                "tags": ["store"],
                "covers": [],
                "description": "",
                "fixture": "basic",
                "steps": [step],
            }
        ],
    }
    monkeypatch.setattr(c, "load_corpus", lambda: corpus)


_Q = {
    "op": "query",
    "as": "carol",
    "sql": "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100",
}


def _limited(limits: dict[str, Limit]) -> type:
    class H(MemoryStoreHarness):
        pass

    H.limits = limits  # type: ignore[attr-defined]
    return H


# a value expected of a step that anon is refused: the case ends at step 0 in Refused(token_expired)
_REFUSED = {**_Q, "as": "anon", "expect": {"row_count": 2}}
_AT_0 = "step 0 (query)"


def test_a_case_that_ends_at_its_declared_limit_is_recorded_and_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _limit_corpus(monkeypatch, _REFUSED)
    report = run_corpus(_limited({"x": Limit(_AT_0, "Refused", "token_expired")}))
    [r] = report.results
    assert r.status == "limit" and r.ok and report.passed
    assert _AT_0 in r.message and "Refused(token_expired)" in r.message
    assert not run_corpus(MemoryStoreHarness).passed  # without the declaration it fails
    # a limit with no detail is held to the class alone
    assert run_corpus(_limited({"x": Limit(_AT_0, "Refused")})).passed


def test_a_case_that_ends_at_another_step_than_its_limit_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _limit_corpus(monkeypatch, _REFUSED)
    report = run_corpus(_limited({"x": Limit("step 1 (query)", "Refused", "token_expired")}))
    [r] = report.results
    assert r.status == "failed" and "documented limit ends it at step 1" in r.message
    assert not report.passed


def test_a_case_that_ends_in_another_class_than_its_limit_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _limit_corpus(monkeypatch, _REFUSED)
    report = run_corpus(_limited({"x": Limit(_AT_0, "Invalid", "token_expired")}))
    [r] = report.results
    assert r.status == "failed" and not report.passed
    assert (
        "step 0 (query): expected Invalid(token_expired), got Refused(token_expired)" in r.message
    )


def test_a_case_that_ends_in_another_detail_than_its_limit_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _limit_corpus(monkeypatch, _REFUSED)
    report = run_corpus(_limited({"x": Limit(_AT_0, "Refused", "no_access")}))
    [r] = report.results
    assert r.status == "failed" and not report.passed
    assert "expected Refused(no_access), got Refused(token_expired)" in r.message


def test_an_unsupported_limit_matches_on_its_construct_not_on_its_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from arras.errors import Unsupported

    class H(_limited({})):  # type: ignore[misc]
        def backend(self) -> Any:
            real = self.auth

            class Wrapped:
                def __getattr__(self, name: str) -> Any:
                    return getattr(real, name)

                def query(self, *a: Any, **k: Any) -> Any:
                    raise Unsupported("a window function", ["select"])

            return Wrapped()

    _limit_corpus(monkeypatch, _REFUSED)
    H.limits = {"x": Limit(_AT_0, "Unsupported", "window function")}  # type: ignore[attr-defined]
    [r] = run_corpus(H).results
    assert r.status == "limit" and "Unsupported(window function)" in r.message
    # a fragment found only in str(e), the message's own prefix, is no match
    H.limits = {"x": Limit(_AT_0, "Unsupported", "unsupported:")}  # type: ignore[attr-defined]
    [r] = run_corpus(H).results
    assert r.status == "failed"
    assert "expected Unsupported(unsupported:), got Unsupported(a window function)" in r.message


def test_a_failure_that_is_no_refusal_does_not_meet_a_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # the step fails on a wrong value, not on an error the backend raised
    _limit_corpus(monkeypatch, {**_Q, "expect": {"row_count": 2, "bogus": 1}})
    report = run_corpus(_limited({"x": Limit(_AT_0, "Refused")}))
    [r] = report.results
    assert r.status == "failed" and "got no refusal" in r.message


def test_a_value_expected_and_an_error_met_reports_the_error_not_an_unknown_expectation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _limit_corpus(monkeypatch, _REFUSED)
    [r] = run_corpus(MemoryStoreHarness).results
    assert r.status == "failed"
    assert "expected ['row_count'], got Refused(token_expired)" in r.message
    assert "unknown error expectation" not in r.message


def test_a_case_that_passes_despite_its_limit_fails_so_a_fixed_limit_shows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _limit_corpus(monkeypatch, {**_Q, "as": "anon", "expect": {"error": "Refused"}})
    assert run_corpus(MemoryStoreHarness).passed
    report = run_corpus(_limited({"x": Limit(_AT_0, "Refused")}))
    [r] = report.results
    assert r.status == "failed" and "limit" in r.message and "gone" in r.message
    assert not report.passed


def test_a_limit_that_names_no_case_fails_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    _limit_corpus(monkeypatch, {**_Q, "as": "anon", "expect": {"error": "Refused"}})
    report = run_corpus(_limited({"nope": Limit(_AT_0, "Refused")}))
    assert not report.passed
    assert [(r.case, r.status) for r in report.results] == [("x", "passed"), ("nope", "failed")]
    # a run of chosen cases is not held to the limits of the others
    assert run_corpus(_limited({"nope": Limit(_AT_0, "Refused")}), only=["x"]).passed
