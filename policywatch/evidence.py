from __future__ import annotations

from dataclasses import asdict

from .models import ChangeResult, EvidenceRecord, FetchResult


def build_evidence(
    current: FetchResult,
    previous: dict[str, object] | None,
    change: ChangeResult,
) -> EvidenceRecord:
    return EvidenceRecord(
        source_name=current.name,
        source_url=current.url,
        observed_at=current.fetched_at,
        previous_sha256=str(previous.get("sha256")) if previous and previous.get("sha256") else None,
        current_sha256=current.sha256,
        extractor_version=current.extractor_version,
        decision="meaningful_change" if change.meaningful else change.status,
        reason_codes=list(change.reason_codes),
        matched_keywords=list(change.matched_keywords),
        added_lines=list(change.added_lines),
        removed_lines=list(change.removed_lines),
    )


def evidence_to_dict(record: EvidenceRecord) -> dict[str, object]:
    return asdict(record)
