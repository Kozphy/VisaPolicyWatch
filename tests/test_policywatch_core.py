import hashlib

from policywatch import FetchResult, assess_change, build_evidence, extract_main_text


def make_result(text: str) -> FetchResult:
    return FetchResult(
        name="Skilled Worker",
        category="UK",
        url="https://www.gov.uk/skilled-worker-visa",
        fetched_at="2026-08-01T00:00:00+00:00",
        text=text,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def test_extraction_removes_navigation_and_footer():
    html = "<html><body><nav>noise</nav><main><h1>Visa</h1><p>Salary £41,700</p></main><footer>noise</footer></body></html>"
    assert extract_main_text(html, "https://www.gov.uk/example") == "Visa\nSalary £41,700"


def test_change_exposes_reason_codes():
    old = make_result("Salary is £40,000")
    new = make_result("Salary is £41,700")
    result = assess_change(
        new,
        {"text": old.text, "sha256": old.sha256},
        keywords=["salary"],
        min_changed_lines=8,
        similarity_threshold=0.5,
    )
    assert result.meaningful is True
    assert result.reason_codes == ["POLICY_KEYWORD_CHANGED"]


def test_non_policy_editorial_change_can_be_non_meaningful():
    old = make_result("Guidance page\nContact the department.")
    new = make_result("Guidance page\nContact the department online.")
    result = assess_change(
        new,
        {"text": old.text, "sha256": old.sha256},
        keywords=["salary", "eligibility"],
        min_changed_lines=8,
        similarity_threshold=0.5,
    )
    assert result.status == "changed"
    assert result.meaningful is False
    assert result.reason_codes == []


def test_evidence_contains_hashes_and_extractor_version():
    old = make_result("Salary is £40,000")
    new = make_result("Salary is £41,700")
    change = assess_change(
        new,
        {"text": old.text, "sha256": old.sha256},
        keywords=["salary"],
        min_changed_lines=8,
        similarity_threshold=0.5,
    )
    evidence = build_evidence(new, {"sha256": old.sha256}, change)
    assert evidence.previous_sha256 == old.sha256
    assert evidence.current_sha256 == new.sha256
    assert evidence.extractor_version == "2"
    assert evidence.decision == "meaningful_change"
