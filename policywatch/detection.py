from __future__ import annotations

import difflib
from collections.abc import Iterable

from .models import ChangeResult, FetchResult


def changed_lines(old_text: str, new_text: str) -> tuple[list[str], list[str]]:
    added: list[str] = []
    removed: list[str] = []
    for line in difflib.ndiff(old_text.splitlines(), new_text.splitlines()):
        if line.startswith("+ "):
            added.append(line[2:])
        elif line.startswith("- "):
            removed.append(line[2:])
    return added, removed


def keyword_matches(lines: Iterable[str], keywords: Iterable[str]) -> list[str]:
    haystack = "\n".join(lines).casefold()
    return sorted({keyword for keyword in keywords if keyword.casefold() in haystack})


def assess_change(
    current: FetchResult,
    previous: dict[str, object] | None,
    keywords: list[str],
    min_changed_lines: int,
    similarity_threshold: float,
) -> ChangeResult:
    if previous is None:
        return ChangeResult(current.name, current.category, current.url, "baseline_created", False, 1.0)

    previous_sha = str(previous.get("sha256", ""))
    old_text = str(previous.get("text", ""))
    if current.sha256 == previous_sha:
        return ChangeResult(current.name, current.category, current.url, "unchanged", False, 1.0)

    added, removed = changed_lines(old_text, current.text)
    similarity = difflib.SequenceMatcher(None, old_text, current.text, autojunk=False).ratio()
    matches = keyword_matches([*added, *removed], keywords)
    reason_codes: list[str] = []
    if matches:
        reason_codes.append("POLICY_KEYWORD_CHANGED")
    if len(added) + len(removed) >= min_changed_lines:
        reason_codes.append("CHANGE_VOLUME_THRESHOLD")
    if similarity < similarity_threshold:
        reason_codes.append("BROAD_REWRITE")

    return ChangeResult(
        name=current.name,
        category=current.category,
        url=current.url,
        status="changed",
        meaningful=bool(reason_codes),
        similarity=round(similarity, 4),
        added_lines=added,
        removed_lines=removed,
        matched_keywords=matches,
        reason_codes=reason_codes,
    )
