# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""QUERY-010, section C, the pure parts of search: the fold, the words, rank tiers, excerpts."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from arras import Invalid
from arras.fakes_search import text_matches
from arras.searchplan import (
    Ranked,
    Segment,
    TextMatch,
    check_text,
    excerpt,
    fold,
    rank,
    tier,
)

# -- the text ----------------------------------------------------------------------------------


def test_the_text_is_trimmed_collapsed_and_folded() -> None:
    assert fold("  Lumen \t QUERY\n review ") == "lumen query review"
    assert fold("ÄÖ İ") == "äö i̇"  # simple lowercase: no compatibility normalisation
    assert fold("ﬃ") == "ﬃ"  # a ligature is not decomposed


def test_text_is_two_to_two_hundred_characters_and_at_most_six_words() -> None:
    assert check_text(" Lumen  query ") == ("lumen query", ("lumen", "query"))
    assert check_text("ab") == ("ab", ("ab",))
    assert check_text("a b c d e f")[1] == tuple("abcdef")
    assert check_text("x" * 200)[0] == "x" * 200
    for bad in ("", " ", "a", "a  ", "x" * 201, "a b c d e f g"):
        with pytest.raises(Invalid) as e:
            check_text(bad)
        assert [v.path for v in e.value.violations] == ["text"]


def test_a_refusal_never_repeats_the_text() -> None:
    secret = "needle " * 7
    with pytest.raises(Invalid) as e:
        check_text(secret)
    assert "needle" not in str(e.value) and "needle" not in repr(e.value.violations)


@given(st.text(max_size=300))
def test_fold_is_idempotent_and_has_no_outer_or_double_spaces(text: str) -> None:
    once = fold(text)
    assert fold(once) == once
    assert once == once.strip() and "  " not in once


# -- tiers and rank ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,word,expected",
    [
        ("lumen", "lumen", 4),
        ("lumen logs", "lumen", 3),
        ("logs lumen", "lumen", 2),
        ("logs-lumen", "lumen", 2),
        ("sol-lumen-review", "lumen", 2),
        ("logs lumens", "lumen", 2),
        ("logslumen", "lumen", 1),
        ("xlumen", "lumen", 1),
        ("nothing", "lumen", 0),
        ("100% sure", "%", 1),
        ("100% sure", "100%", 3),
        ("a_b", "_", 1),
    ],
)
def test_tiers(value: str, word: str, expected: int) -> None:
    assert tier(value, word) == expected


def ranked(words: tuple[str, ...], props: tuple[str, ...], row: dict) -> Ranked:
    found = rank(words, props, row)
    assert found is not None
    return found


def test_rank_scales_each_word_by_the_position_of_the_property_and_sums_the_words() -> None:
    row = {"name": "Lumen query review", "code": "sol-lumen-review", "summary": "uses Lumen"}
    props = ("name", "code", "summary")  # n = 3: positions weigh 3, 2, 1
    r = rank(("lumen", "query"), props, row)
    # lumen: name starts (3 × 3 = 9); query: a word in name starts (2 × 3 = 6)
    assert r is not None and r.score == 15 and r.matched == ("name", "code", "summary")
    only_late = rank(("uses",), props, row)
    assert only_late is not None and only_late.score == 3 * 1 and only_late.matched == ("summary",)


def test_every_word_must_be_in_some_property_not_necessarily_the_same() -> None:
    row = {"name": "Lumen", "code": "h-1", "summary": "queries"}
    assert rank(("lumen", "queries"), ("name", "code", "summary"), row) is not None
    assert rank(("lumen", "absent"), ("name", "code", "summary"), row) is None
    assert rank(("lumen",), ("code", "summary"), row) is None  # only the named properties


def test_an_earlier_property_outranks_the_same_kind_of_match_in_a_later_one() -> None:
    props = ("name", "summary")
    first = ranked(("logs",), props, {"name": "logs tools", "summary": "x"})
    later = ranked(("logs",), props, {"name": "x", "summary": "logs tools"})
    assert first.score > later.score
    assert ranked(("logs",), props, {"name": "logs", "summary": "x"}).score > first.score


def test_a_property_that_is_not_text_or_absent_is_skipped() -> None:
    assert rank(("a1",), ("n", "m"), {"n": None, "m": 5}) is None
    assert ranked(("a1",), ("n", "m"), {"m": "a1"}).matched == ("m",)


@given(st.text(min_size=1, max_size=30), st.text(min_size=0, max_size=60))
def test_the_library_recheck_agrees_with_the_backends_substring_match(
    word: str, value: str
) -> None:
    """The in-memory backend and the library's re-check use the same fold, so a candidate the
    backend returns is never dropped, and `%`, `_`, `\\` are only themselves."""
    w = fold(word)
    if not w or " " in w:
        return
    backend = text_matches({"p": value}, TextMatch((w,), ("p",)))
    assert backend == (w in value.lower())
    assert (rank((w,), ("p",), {"p": value}) is not None) == backend


# -- excerpts ----------------------------------------------------------------------------------


def joined(segments: tuple[Segment, ...]) -> str:
    return "".join(s.text for s in segments)


def test_a_short_value_is_one_excerpt_with_its_matches_marked() -> None:
    assert excerpt("Lumen drafts a query for review", ("lumen", "query")) == (
        Segment("Lumen", True),
        Segment(" drafts a ", False),
        Segment("query", True),
        Segment(" for review", False),
    )


def test_marks_keep_the_original_text_not_the_folded_one() -> None:
    assert excerpt("İstanbul LUMEN", ("lumen",)) == (
        Segment("İstanbul ", False),
        Segment("LUMEN", True),
    )


def test_overlapping_and_repeated_words_merge_into_one_mark() -> None:
    assert excerpt("querying", ("query", "tract", "ing")) == (Segment("querying", True),)


def test_a_long_value_is_cut_near_the_match_with_ellipses_at_word_boundaries() -> None:
    value = (
        " ".join(f"word{i}" for i in range(80))
        + " needle "
        + " ".join(f"tail{i}" for i in range(80))
    )
    seg = excerpt(value, ("needle",))
    text = joined(seg)
    assert len(text) <= 162
    assert seg[0].text.startswith("…") and seg[-1].text.endswith("…")
    assert any(s.mark and s.text == "needle" for s in seg)
    body = text.strip("…")
    assert body.split()[0].startswith(("word", "tail")) and not body.startswith(" ")
    assert all(w.startswith(("word", "tail", "needle")) for w in body.split())  # no half words


def test_a_match_at_the_very_start_or_end_gets_a_separate_ellipsis_segment() -> None:
    head = "needle " + "x" * 300
    seg = excerpt(head, ("needle",))
    assert seg[0] == Segment("needle", True) and seg[-1].text.endswith("…")
    tail = "x" * 300 + " needle"
    seg = excerpt(tail, ("needle",))
    assert seg[0] == Segment("…" + seg[0].text[1:], False) and seg[-1] == Segment("needle", True)
    solid = excerpt("needle", ("needle",))
    assert solid == (Segment("needle", True),)
    marked_edge = excerpt("y" * 200 + "needle" + "z" * 200, ("needle",))
    assert any(s.mark for s in marked_edge)


def test_no_match_is_no_excerpt() -> None:
    assert excerpt("nothing", ("lumen",)) == ()


@given(st.text(min_size=1, max_size=400), st.text(alphabet="abc", min_size=1, max_size=3))
def test_segments_are_text_that_reassembles_a_window_of_the_value(value: str, word: str) -> None:
    seg = excerpt(value, (word,))
    if not seg:
        assert word not in value.lower()
        return
    body = joined(seg).strip("…")
    assert body.strip() in value or body in value
    assert any(s.mark for s in seg)
    assert all(word in s.text.lower() for s in seg if s.mark)


# -- the same fold for the query, the ranking and the excerpt -----------------------------------


def test_a_word_final_capital_sigma_folds_alike_in_the_query_the_rank_and_the_excerpt() -> None:
    """`str.lower()` of a whole word turns a final Σ into ς; the fold is per character, so the
    query, the ranking and the excerpt all see σ."""
    assert fold("ΟΔΟΣ") == "οδοσ"
    words = (fold("ΟΔΟΣ"),)
    assert rank(words, ["name"], {"name": "Η ΟΔΟΣ"}) is not None
    assert [(s.text, s.mark) for s in excerpt("Η ΟΔΟΣ", words)] == [("Η ", False), ("ΟΔΟΣ", True)]


@given(st.text(max_size=40), st.text(min_size=1, max_size=6))
def test_a_value_that_ranks_for_a_word_has_an_excerpt_marking_it(value: str, word: str) -> None:
    words = (fold(word),)
    if not words[0]:
        return
    ranked = rank(words, ["p"], {"p": value})
    assert (ranked is not None) == bool(excerpt(value, words))
