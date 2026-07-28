from __future__ import annotations

from unittest.mock import Mock

import pytest
import requests

from crawler_runtime import (
    CrawlError,
    CrawlPolicy,
    PreviousMetadata,
    build_conditional_headers,
    fetch_with_evidence,
    robots_url,
    validate_text,
)


def response(
    *,
    status: int = 200,
    url: str = "https://example.gov/policy",
    text: str = "policy content " * 30,
    headers: dict[str, str] | None = None,
) -> requests.Response:
    item = requests.Response()
    item.status_code = status
    item.url = url
    item._content = text.encode("utf-8")
    item.encoding = "utf-8"
    item.headers.update(headers or {})
    item.history = []
    return item


def test_build_conditional_headers_uses_previous_validators() -> None:
    headers = build_conditional_headers(
        PreviousMetadata(etag='"abc"', last_modified="Mon, 01 Jun 2026 00:00:00 GMT")
    )

    assert headers["If-None-Match"] == '"abc"'
    assert headers["If-Modified-Since"] == "Mon, 01 Jun 2026 00:00:00 GMT"


def test_robots_url_keeps_origin_only() -> None:
    assert robots_url("https://example.gov/a/b?x=1") == "https://example.gov/robots.txt"


def test_validate_text_detects_challenge_page() -> None:
    findings = validate_text("Access denied. Verify you are human.", min_characters=10)

    assert "BLOCK_OR_CHALLENGE_PAGE_DETECTED" in findings


def test_fetch_with_evidence_records_hashes_and_headers() -> None:
    session = Mock(spec=requests.Session)
    session.get.return_value = response(
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "ETag": '"v2"',
            "Last-Modified": "Tue, 02 Jun 2026 00:00:00 GMT",
        }
    )

    _, evidence = fetch_with_evidence(
        session,
        "https://example.gov/policy",
        policy=CrawlPolicy(obey_robots_txt=False, retries=0),
    )

    assert evidence.status_code == 200
    assert evidence.final_url == "https://example.gov/policy"
    assert evidence.raw_sha256
    assert evidence.text_sha256
    assert evidence.etag == '"v2"'
    assert evidence.findings == []


def test_fetch_with_evidence_supports_304() -> None:
    session = Mock(spec=requests.Session)
    session.get.return_value = response(status=304, text="")

    _, evidence = fetch_with_evidence(
        session,
        "https://example.gov/policy",
        previous=PreviousMetadata(etag='"v1"'),
        policy=CrawlPolicy(obey_robots_txt=False, retries=0),
    )

    assert evidence.not_modified is True
    assert evidence.status_code == 304
    assert evidence.etag == '"v1"'


def test_fetch_with_evidence_rejects_short_content() -> None:
    session = Mock(spec=requests.Session)
    session.get.return_value = response(text="too short")

    with pytest.raises(CrawlError, match="CONTENT_TOO_SHORT"):
        fetch_with_evidence(
            session,
            "https://example.gov/policy",
            policy=CrawlPolicy(
                obey_robots_txt=False,
                retries=0,
                min_text_characters=200,
            ),
        )
