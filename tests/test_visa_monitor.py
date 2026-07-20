import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from visa_monitor import FetchResult, assess_change, extract_main_text  # noqa: E402


def make_result(text: str) -> FetchResult:
    import hashlib

    return FetchResult(
        name="Test",
        category="Test",
        url="https://example.com",
        fetched_at="2026-07-21T00:00:00+00:00",
        text=text,
        sha256=hashlib.sha256(text.encode()).hexdigest(),
    )


def test_extracts_main_and_ignores_navigation():
    html = """
    <html><body>
      <nav>Menu Noise</nav>
      <main><h1>Skilled Worker visa</h1><p>The salary is £41,700.</p></main>
      <footer>Footer Noise</footer>
    </body></html>
    """
    text = extract_main_text(html, "https://www.gov.uk/skilled-worker-visa")
    assert "Skilled Worker visa" in text
    assert "£41,700" in text
    assert "Menu Noise" not in text
    assert "Footer Noise" not in text


def test_salary_change_is_meaningful():
    old = make_result("Skilled Worker visa\nThe salary is £40,000.")
    new = make_result("Skilled Worker visa\nThe salary is £41,700.")
    result = assess_change(
        new,
        {"text": old.text, "sha256": old.sha256},
        keywords=["salary"],
        min_changed_lines=8,
        similarity_threshold=0.985,
    )
    assert result.status == "changed"
    assert result.meaningful
    assert "salary" in result.matched_keywords


def test_identical_page_is_unchanged():
    old = make_result("Graduate visa\nThe visa lasts 18 months.")
    new = make_result("Graduate visa\nThe visa lasts 18 months.")
    result = assess_change(
        new,
        {"text": old.text, "sha256": old.sha256},
        keywords=["months"],
        min_changed_lines=8,
        similarity_threshold=0.985,
    )
    assert result.status == "unchanged"
    assert not result.meaningful
