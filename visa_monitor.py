#!/usr/bin/env python3
"""
Visa Policy Monitor

Checks official UK GOV.UK and U.S. USCIS pages, extracts the main content,
compares it with the previous snapshot, and writes Markdown/JSON reports.

First run: creates a baseline and does not alert.
Later runs: flags meaningful policy changes and can optionally send email.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import smtplib
import ssl
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


DEFAULT_KEYWORDS = [
    "salary",
    "going rate",
    "eligible",
    "eligibility",
    "english",
    "fee",
    "cost",
    "duration",
    "months",
    "years",
    "sponsor",
    "certificate of sponsorship",
    "registration",
    "selection",
    "cap",
    "deadline",
    "application",
    "effective",
    "immigration rules",
    "graduate visa",
    "skilled worker",
    "h-1b",
]

USER_AGENT = (
    "VisaPolicyMonitor/1.0 "
    "(personal policy-change monitor; contact: local-user)"
)


@dataclass
class FetchResult:
    name: str
    category: str
    url: str
    fetched_at: str
    text: str
    sha256: str
    etag: str | None = None
    last_modified: str | None = None


@dataclass
class ChangeResult:
    name: str
    category: str
    url: str
    status: str
    meaningful: bool
    similarity: float
    added_lines: list[str]
    removed_lines: list[str]
    matched_keywords: list[str]
    error: str | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
    temp.replace(path)


def normalize_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\r\n?", "\n", text)
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw).strip()
        if not line:
            continue
        if line.lower() in {
            "skip to main content",
            "cookies on gov.uk",
            "accept additional cookies",
            "reject additional cookies",
            "hide this message",
            "menu",
            "search",
            "print this page",
        }:
            continue
        lines.append(line)
    return "\n".join(lines)


def extract_main_text(html: str, url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(
        ["script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form"]
    ):
        tag.decompose()

    host = urlparse(url).netloc.lower()
    selectors: list[str]
    if host.endswith("gov.uk"):
        selectors = [
            "main#content",
            "main",
            ".govuk-main-wrapper",
            "article",
        ]
    elif host.endswith("uscis.gov"):
        selectors = [
            "main",
            "#main-content",
            "article",
            ".field--name-body",
            ".content",
        ]
    else:
        selectors = ["main", "article", "[role='main']", "body"]

    container = None
    for selector in selectors:
        container = soup.select_one(selector)
        if container is not None:
            break
    if container is None:
        container = soup.body or soup

    for selector in [
        ".gem-c-feedback",
        ".govuk-breadcrumbs",
        ".govuk-phase-banner",
        ".share-this-page",
        ".usa-breadcrumb",
        ".usa-footer",
        ".social-share",
        ".pager",
    ]:
        for node in container.select(selector):
            node.decompose()

    return normalize_text(container.get_text("\n", strip=True))


def fetch_source(
    session: requests.Session,
    source: dict[str, Any],
    timeout: int,
    retries: int,
) -> FetchResult:
    url = source["url"]
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            response = session.get(
                url,
                timeout=timeout,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-GB,en;q=0.9",
                    "Cache-Control": "no-cache",
                },
            )
            response.raise_for_status()
            text = extract_main_text(response.text, url)
            if len(text) < 200:
                raise ValueError(
                    f"Extracted content is unexpectedly short ({len(text)} characters)"
                )
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            return FetchResult(
                name=source["name"],
                category=source.get("category", "Other"),
                url=url,
                fetched_at=utc_now(),
                text=text,
                sha256=digest,
                etag=response.headers.get("ETag"),
                last_modified=response.headers.get("Last-Modified"),
            )
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(2**attempt)

    assert last_error is not None
    raise RuntimeError(f"Could not fetch {url}: {last_error}") from last_error


def changed_lines(old_text: str, new_text: str) -> tuple[list[str], list[str]]:
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    diff = difflib.ndiff(old_lines, new_lines)
    added, removed = [], []
    for line in diff:
        if line.startswith("+ "):
            added.append(line[2:])
        elif line.startswith("- "):
            removed.append(line[2:])
    return added, removed


def keyword_matches(lines: Iterable[str], keywords: Iterable[str]) -> list[str]:
    haystack = "\n".join(lines).lower()
    return sorted({keyword for keyword in keywords if keyword.lower() in haystack})


def assess_change(
    current: FetchResult,
    previous: dict[str, Any] | None,
    keywords: list[str],
    min_changed_lines: int,
    similarity_threshold: float,
) -> ChangeResult:
    if previous is None:
        return ChangeResult(
            name=current.name,
            category=current.category,
            url=current.url,
            status="baseline_created",
            meaningful=False,
            similarity=1.0,
            added_lines=[],
            removed_lines=[],
            matched_keywords=[],
        )

    old_text = previous.get("text", "")
    if current.sha256 == previous.get("sha256"):
        return ChangeResult(
            name=current.name,
            category=current.category,
            url=current.url,
            status="unchanged",
            meaningful=False,
            similarity=1.0,
            added_lines=[],
            removed_lines=[],
            matched_keywords=[],
        )

    added, removed = changed_lines(old_text, current.text)
    similarity = difflib.SequenceMatcher(None, old_text, current.text).ratio()
    matches = keyword_matches([*added, *removed], keywords)

    substantial = len(added) + len(removed) >= min_changed_lines
    broad_rewrite = similarity < similarity_threshold
    meaningful = bool(matches) or substantial or broad_rewrite

    return ChangeResult(
        name=current.name,
        category=current.category,
        url=current.url,
        status="changed",
        meaningful=meaningful,
        similarity=round(similarity, 4),
        added_lines=added,
        removed_lines=removed,
        matched_keywords=matches,
    )


def trim_lines(lines: list[str], limit: int = 40) -> list[str]:
    if len(lines) <= limit:
        return lines
    return [*lines[:limit], f"… {len(lines) - limit} more lines omitted"]


def markdown_report(
    results: list[ChangeResult],
    checked_at: str,
    first_run: bool,
) -> str:
    meaningful = [r for r in results if r.meaningful]
    errors = [r for r in results if r.status == "error"]

    if first_run:
        summary = (
            "Baseline created. No alert is sent on the first run; later runs "
            "will compare official pages against this snapshot."
        )
    elif meaningful:
        summary = f"Detected {len(meaningful)} meaningful change(s)."
    elif errors:
        summary = "No confirmed policy change, but one or more pages could not be checked."
    else:
        summary = "No meaningful policy change detected."

    out = [
        "# Visa Policy Monitor",
        "",
        f"- Checked at: `{checked_at}`",
        f"- Result: **{summary}**",
        "",
    ]

    grouped: dict[str, list[ChangeResult]] = {}
    for result in results:
        grouped.setdefault(result.category, []).append(result)

    for category, items in grouped.items():
        out += [f"## {category}", ""]
        for result in items:
            out += [
                f"### {result.name}",
                "",
                f"- URL: {result.url}",
                f"- Status: `{result.status}`",
            ]
            if result.error:
                out.append(f"- Error: `{result.error}`")
            if result.status == "changed":
                out += [
                    f"- Meaningful: **{'yes' if result.meaningful else 'no'}**",
                    f"- Similarity to previous snapshot: `{result.similarity:.2%}`",
                    "- Policy keywords in changed text: "
                    + (
                        ", ".join(f"`{x}`" for x in result.matched_keywords)
                        if result.matched_keywords
                        else "none"
                    ),
                    "",
                    "#### Added",
                    "",
                ]
                added = trim_lines(result.added_lines)
                out.extend([f"- {line}" for line in added] or ["- None"])
                out += ["", "#### Removed", ""]
                removed = trim_lines(result.removed_lines)
                out.extend([f"- {line}" for line in removed] or ["- None"])
            out.append("")

    out += [
        "---",
        "This monitor detects changes to official webpages. It does not provide legal advice, "
        "and an editorial webpage change is not always a legal change. Confirm important updates "
        "in the linked official guidance and rules.",
        "",
    ]
    return "\n".join(out)


def send_email(subject: str, body: str) -> None:
    required = ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "ALERT_TO"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError(
            "Email requested but these environment variables are missing: "
            + ", ".join(missing)
        )

    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "465"))
    username = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    recipient = os.environ["ALERT_TO"]
    sender = os.getenv("ALERT_FROM", username)

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)

    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls(context=context)
            smtp.login(username, password)
            smtp.send_message(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor official visa policy pages.")
    parser.add_argument("--config", type=Path, default=Path("sources.json"))
    parser.add_argument("--state", type=Path, default=Path("data/state.json"))
    parser.add_argument("--report", type=Path, default=Path("reports/latest.md"))
    parser.add_argument(
        "--json-output", type=Path, default=Path("reports/latest.json")
    )
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--min-changed-lines", type=int, default=8)
    parser.add_argument("--similarity-threshold", type=float, default=0.985)
    parser.add_argument(
        "--email",
        action="store_true",
        help="Email the report when meaningful changes are detected.",
    )
    parser.add_argument(
        "--email-on-error",
        action="store_true",
        help="Also email when one or more pages could not be checked.",
    )
    parser.add_argument(
        "--fail-on-change",
        action="store_true",
        help="Exit with code 2 if meaningful changes are detected.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_json(args.config, None)
    if not config or not config.get("sources"):
        print(f"Invalid or empty config: {args.config}", file=sys.stderr)
        return 1

    state = load_json(args.state, {"version": 1, "sources": {}})
    previous_sources: dict[str, Any] = state.get("sources", {})
    first_run = not bool(previous_sources)
    keywords = config.get("meaningful_keywords", DEFAULT_KEYWORDS)

    session = requests.Session()
    results: list[ChangeResult] = []
    new_state_sources = dict(previous_sources)

    for source in config["sources"]:
        name = source["name"]
        try:
            current = fetch_source(
                session=session,
                source=source,
                timeout=args.timeout,
                retries=args.retries,
            )
            previous = previous_sources.get(name)
            result = assess_change(
                current=current,
                previous=previous,
                keywords=keywords,
                min_changed_lines=args.min_changed_lines,
                similarity_threshold=args.similarity_threshold,
            )
            results.append(result)
            new_state_sources[name] = asdict(current)
        except Exception as exc:
            results.append(
                ChangeResult(
                    name=name,
                    category=source.get("category", "Other"),
                    url=source["url"],
                    status="error",
                    meaningful=False,
                    similarity=0.0,
                    added_lines=[],
                    removed_lines=[],
                    matched_keywords=[],
                    error=str(exc),
                )
            )

    checked_at = utc_now()
    report = markdown_report(results, checked_at, first_run)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")

    meaningful = [r for r in results if r.meaningful]
    errors = [r for r in results if r.status == "error"]
    machine_result = {
        "checked_at": checked_at,
        "first_run": first_run,
        "meaningful_change_count": len(meaningful),
        "error_count": len(errors),
        "has_meaningful_changes": bool(meaningful),
        "has_errors": bool(errors),
        "results": [asdict(r) for r in results],
    }
    save_json(args.json_output, machine_result)

    state["version"] = 1
    state["last_checked_at"] = checked_at
    state["sources"] = new_state_sources
    save_json(args.state, state)

    print(report)

    should_email = bool(meaningful) or (args.email_on_error and bool(errors))
    if args.email and should_email:
        subject = (
            f"Visa policy update: {len(meaningful)} meaningful change(s)"
            if meaningful
            else "Visa policy monitor: check error"
        )
        send_email(subject, report)

    if errors and len(errors) == len(config["sources"]):
        return 1
    if args.fail_on_change and meaningful:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
