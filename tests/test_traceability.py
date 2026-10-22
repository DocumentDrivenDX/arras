# SPDX-License-Identifier: MIT OR Apache-2.0
"""The traceability summary tables are recomputed from the criterion rows, so they cannot drift."""

import re
from collections import Counter, defaultdict
from pathlib import Path

MATRIX = Path(__file__).resolve().parents[1] / "docs/helix/03-test/traceability.md"
STATUSES = ("covered", "partial", "blocked", "gap")
CRITERION = re.compile(r"^\| \*\*(US-\d+)-AC(\d+)\*\*.*?\| `(\w+)` \|")
COUNTS = r"((?: \d+ \|){5})$"


def _counts(text: str) -> list[int]:
    return [int(x) for x in text.split("|")[:-1]]


def _row(counter: Counter[str]) -> list[int]:
    return [*(counter[s] for s in STATUSES), sum(counter[s] for s in STATUSES)]


def _summarised() -> set[str]:
    """Stories in the summary table; the Graph Browser stories (US-065 to US-072) are not in it."""
    return set(re.findall(r"^\| (US-\d+) \|", MATRIX.read_text(), re.MULTILINE))


def _recount() -> tuple[dict[str, Counter[str]], dict[str, Counter[str]]]:
    stories: dict[str, Counter[str]] = defaultdict(Counter)
    features: dict[str, Counter[str]] = defaultdict(Counter)
    feature: str | None = None
    summarised = _summarised()
    for line in MATRIX.read_text().splitlines():
        if line.startswith("## "):
            heading = re.match(r"## (FEAT-\d+):", line)
            feature = heading.group(1) if heading else feature
        found = CRITERION.match(line)
        if found and feature and found.group(1) in summarised:
            stories[found.group(1)][found.group(3)] += 1
            features[feature][found.group(3)] += 1
    return stories, features


def test_the_summary_tables_equal_the_recount_of_the_criterion_rows() -> None:
    stories, features = _recount()
    lines = MATRIX.read_text().splitlines()
    drift: list[str] = []
    seen_stories: set[str] = set()
    seen_features: set[str] = set()
    for line in lines:
        story = re.match(rf"\| (US-\d+) \|.*?\|{COUNTS}", line)
        if story:
            seen_stories.add(story.group(1))
            want = _row(stories[story.group(1)])
            if _counts(story.group(2)) != want:
                drift.append(f"{story.group(1)}: {_counts(story.group(2))} != {want}")
        feat = re.match(rf"\| (FEAT-\d+) [^|]*\|{COUNTS}", line)
        if feat:
            seen_features.add(feat.group(1))
            want = _row(features[feat.group(1)])
            if _counts(feat.group(2)) != want:
                drift.append(f"{feat.group(1)}: {_counts(feat.group(2))} != {want}")
        total = re.match(r"\| \*\*All\*\* \| \|((?: \*\*\d+\*\* \|){5})$", line)
        if total:
            total_row = _counts(total.group(1).replace("*", ""))
            want = _row(sum(stories.values(), Counter[str]()))
            if total_row != want:
                drift.append(f"All: {total_row} != {want}")
            if total_row != [sum(_row(c)[i] for c in stories.values()) for i in range(5)]:
                drift.append("All is not the sum of the story rows")
    assert drift == []
    assert seen_stories == set(stories)
    assert seen_features == set(features)
