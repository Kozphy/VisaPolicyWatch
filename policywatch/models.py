from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FetchResult:
    name: str
    category: str
    url: str
    fetched_at: str
    text: str
    sha256: str
    etag: str | None = None
    last_modified: str | None = None
    extractor_version: str = "2"


@dataclass(frozen=True)
class ChangeResult:
    name: str
    category: str
    url: str
    status: str
    meaningful: bool
    similarity: float
    added_lines: list[str] = field(default_factory=list)
    removed_lines: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class EvidenceRecord:
    source_name: str
    source_url: str
    observed_at: str
    previous_sha256: str | None
    current_sha256: str
    extractor_version: str
    decision: str
    reason_codes: list[str]
    matched_keywords: list[str]
    added_lines: list[str]
    removed_lines: list[str]
