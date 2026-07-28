"""Reusable, audit-ready HTTP crawler primitives for VisaPolicyWatch.

The runtime is intentionally conservative: it obeys robots.txt by default,
uses conditional requests when previous metadata exists, validates fetched
content before it is trusted, and returns evidence suitable for JSON reports.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

DEFAULT_USER_AGENT = (
    "VisaPolicyWatch/2.0 "
    "(audit-ready policy monitor; low-frequency official-source retrieval)"
)

BLOCK_PAGE_MARKERS = (
    "access denied",
    "verify you are human",
    "captcha",
    "temporarily unavailable",
    "service unavailable",
    "request blocked",
)


@dataclass(frozen=True)
class CrawlPolicy:
    timeout_seconds: int = 30
    retries: int = 2
    backoff_seconds: float = 1.0
    min_text_characters: int = 200
    max_redirects: int = 5
    obey_robots_txt: bool = True
    user_agent: str = DEFAULT_USER_AGENT


@dataclass(frozen=True)
class PreviousMetadata:
    etag: str | None = None
    last_modified: str | None = None


@dataclass
class CrawlEvidence:
    requested_url: str
    final_url: str
    fetched_at: str
    status_code: int
    content_type: str
    elapsed_ms: int
    redirect_chain: list[str]
    raw_sha256: str
    text_sha256: str
    etag: str | None
    last_modified: str | None
    not_modified: bool = False
    findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CrawlError(RuntimeError):
    """Raised when a source cannot be safely fetched or validated."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_conditional_headers(
    previous: PreviousMetadata | None,
    *,
    user_agent: str = DEFAULT_USER_AGENT,
) -> dict[str, str]:
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.1",
        "Accept-Language": "en-GB,en;q=0.9",
    }
    if previous and previous.etag:
        headers["If-None-Match"] = previous.etag
    if previous and previous.last_modified:
        headers["If-Modified-Since"] = previous.last_modified
    return headers


def robots_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


def is_allowed_by_robots(
    session: requests.Session,
    url: str,
    user_agent: str,
    timeout_seconds: int,
) -> bool:
    parser = RobotFileParser()
    parser.set_url(robots_url(url))
    try:
        response = session.get(
            parser.url,
            headers={"User-Agent": user_agent},
            timeout=timeout_seconds,
        )
        if response.status_code >= 400:
            # A missing/unavailable robots file is not interpreted as a ban.
            return True
        parser.parse(response.text.splitlines())
        return parser.can_fetch(user_agent, url)
    except requests.RequestException:
        # Fail open for robots transport errors while preserving conservative
        # request rates at the scheduler level.
        return True


def validate_text(text: str, min_characters: int = 200) -> list[str]:
    findings: list[str] = []
    normalized = text.strip()
    lowered = normalized.lower()

    if len(normalized) < min_characters:
        findings.append("CONTENT_TOO_SHORT")
    if any(marker in lowered for marker in BLOCK_PAGE_MARKERS):
        findings.append("BLOCK_OR_CHALLENGE_PAGE_DETECTED")
    if not normalized:
        findings.append("EMPTY_CONTENT")
    if normalized and len(set(normalized)) < 20:
        findings.append("LOW_CONTENT_DIVERSITY")

    return findings


def _redirect_chain(response: requests.Response) -> list[str]:
    return [item.url for item in response.history] + [response.url]


def fetch_with_evidence(
    session: requests.Session,
    url: str,
    *,
    extracted_text: str | None = None,
    previous: PreviousMetadata | None = None,
    policy: CrawlPolicy | None = None,
) -> tuple[requests.Response, CrawlEvidence]:
    """Fetch one URL and return the response plus immutable crawl evidence.

    ``extracted_text`` may be supplied by a domain-specific extractor. When it
    is omitted, response text is used for validation and hashing.
    """
    policy = policy or CrawlPolicy()

    if policy.obey_robots_txt and not is_allowed_by_robots(
        session, url, policy.user_agent, policy.timeout_seconds
    ):
        raise CrawlError(f"robots.txt disallows retrieval: {url}")

    headers = build_conditional_headers(previous, user_agent=policy.user_agent)
    last_error: Exception | None = None

    for attempt in range(policy.retries + 1):
        started = time.perf_counter()
        try:
            response = session.get(
                url,
                headers=headers,
                timeout=policy.timeout_seconds,
                allow_redirects=True,
            )
            elapsed_ms = round((time.perf_counter() - started) * 1000)

            if len(response.history) > policy.max_redirects:
                raise CrawlError(
                    f"redirect limit exceeded: {len(response.history)} > "
                    f"{policy.max_redirects}"
                )

            if response.status_code == 304:
                evidence = CrawlEvidence(
                    requested_url=url,
                    final_url=response.url,
                    fetched_at=utc_now(),
                    status_code=304,
                    content_type=response.headers.get("Content-Type", ""),
                    elapsed_ms=elapsed_ms,
                    redirect_chain=_redirect_chain(response),
                    raw_sha256="",
                    text_sha256="",
                    etag=response.headers.get("ETag") or (previous.etag if previous else None),
                    last_modified=response.headers.get("Last-Modified")
                    or (previous.last_modified if previous else None),
                    not_modified=True,
                )
                return response, evidence

            response.raise_for_status()
            raw_bytes = response.content
            text = extracted_text if extracted_text is not None else response.text
            findings = validate_text(text, policy.min_text_characters)

            evidence = CrawlEvidence(
                requested_url=url,
                final_url=response.url,
                fetched_at=utc_now(),
                status_code=response.status_code,
                content_type=response.headers.get("Content-Type", ""),
                elapsed_ms=elapsed_ms,
                redirect_chain=_redirect_chain(response),
                raw_sha256=hashlib.sha256(raw_bytes).hexdigest(),
                text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                etag=response.headers.get("ETag"),
                last_modified=response.headers.get("Last-Modified"),
                findings=findings,
            )

            if findings:
                raise CrawlError(
                    "content validation failed: " + ", ".join(findings)
                )
            return response, evidence
        except (requests.RequestException, CrawlError) as exc:
            last_error = exc
            if attempt < policy.retries:
                time.sleep(policy.backoff_seconds * (2**attempt))

    raise CrawlError(f"could not fetch {url}: {last_error}") from last_error
