from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

NOISE_LINES = {
    "skip to main content",
    "cookies on gov.uk",
    "accept additional cookies",
    "reject additional cookies",
    "hide this message",
    "menu",
    "search",
    "print this page",
}


def normalize_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\r\n?", "\n", text)
    lines: list[str] = []
    for raw in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw).strip()
        if line and line.lower() not in NOISE_LINES:
            lines.append(line)
    return "\n".join(lines)


def extract_main_text(html: str, url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    host = urlparse(url).netloc.lower()
    if host.endswith("gov.uk"):
        selectors = ["main#content", "main", ".govuk-main-wrapper", "article"]
    elif host.endswith("uscis.gov"):
        selectors = ["main", "#main-content", "article", ".field--name-body", ".content"]
    else:
        selectors = ["main", "article", "[role='main']", "body"]

    container = next((node for selector in selectors if (node := soup.select_one(selector)) is not None), None)
    container = container or soup.body or soup

    for selector in [".gem-c-feedback", ".govuk-breadcrumbs", ".govuk-phase-banner", ".share-this-page", ".usa-breadcrumb", ".usa-footer", ".social-share", ".pager"]:
        for node in container.select(selector):
            node.decompose()

    return normalize_text(container.get_text("\n", strip=True))
