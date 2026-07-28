# Audit-ready crawler runtime

`crawler_runtime.py` adds reusable retrieval controls without changing the existing monitor's deterministic comparison logic.

## Added capabilities

- `robots.txt` evaluation, enabled by default
- conditional HTTP headers using `ETag` and `Last-Modified`
- explicit handling of `304 Not Modified`
- exponential retry backoff
- redirect-chain and final-URL evidence
- raw-response and extracted-text SHA-256 hashes
- content-type, latency, HTTP status, and retrieval timestamps
- challenge/block-page detection
- minimum-content and low-diversity quality gates
- serializable crawl evidence for audit reports

## Example

```python
import requests

from crawler_runtime import (
    CrawlPolicy,
    PreviousMetadata,
    fetch_with_evidence,
)

session = requests.Session()
response, evidence = fetch_with_evidence(
    session,
    "https://www.gov.uk/skilled-worker-visa",
    previous=PreviousMetadata(
        etag='"previous-etag"',
        last_modified="Mon, 01 Jun 2026 00:00:00 GMT",
    ),
    policy=CrawlPolicy(
        retries=2,
        timeout_seconds=30,
        obey_robots_txt=True,
    ),
)

print(evidence.to_dict())
```

Domain-specific extraction should occur before policy comparison. Pass the normalized extractor output as `extracted_text` when available so the evidence contains separate hashes for the raw response and trusted extracted text.

## Trust boundary

A successful HTTP response is not automatically trusted. The runtime rejects content when quality findings are present, including short responses and common CAPTCHA/access-denied pages. These failures should be routed to the existing error report or a future human-review queue.

## Recommended integration path

1. Load the prior source's `etag` and `last_modified` values from `data/state.json`.
2. Call `fetch_with_evidence` before extraction, or pass extractor output as `extracted_text`.
3. For `304`, reuse the previous normalized text and avoid recomputing a diff.
4. Store `evidence.to_dict()` beside the source snapshot.
5. Surface `findings`, redirect changes, and content-type changes in JSON and Markdown reports.

The crawler remains intentionally bounded and low-frequency. It is not designed for unrestricted site-wide scraping.
