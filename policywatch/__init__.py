"""Core library for VisaPolicyWatch."""

from .detection import assess_change, changed_lines, keyword_matches
from .evidence import build_evidence, evidence_to_dict
from .models import ChangeResult, EvidenceRecord, FetchResult
from .normalization import extract_main_text, normalize_text

__all__ = [
    "ChangeResult",
    "EvidenceRecord",
    "FetchResult",
    "assess_change",
    "build_evidence",
    "changed_lines",
    "evidence_to_dict",
    "extract_main_text",
    "keyword_matches",
    "normalize_text",
]
