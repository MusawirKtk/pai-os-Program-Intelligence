"""One-source live smoke test using this repository's own .env file."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from pai_program_intelligence.extraction import extract_program  # noqa: E402
from pai_program_intelligence.sources import (  # noqa: E402
    SourceCandidate,
    classify_official_url,
    discover_official_sources,
    fetch_official_source,
)
from pai_program_intelligence.tavily import TavilyResearchClient  # noqa: E402


def _local_key() -> str | None:
    key = os.environ.get("TAVILY_API_KEY") or os.environ.get("WEB_SEARCH_API_KEY")
    if key:
        return key
    env_file = REPO_ROOT / ".env"
    if not env_file.is_file():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("TAVILY_API_KEY=") or line.startswith("WEB_SEARCH_API_KEY="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if value:
                return value
    return None


def _name_matches(actual: str, expected: str) -> bool:
    actual_words = " ".join(re.findall(r"[a-z0-9]+", actual.casefold()))
    expected_words = " ".join(re.findall(r"[a-z0-9]+", expected.casefold()))
    return bool(expected_words) and f" {expected_words} " in f" {actual_words} "


async def _run(domain: str, query: str | None, url: str | None, publisher: str, expected_name: str | None, key: str) -> None:
    client = TavilyResearchClient(api_key=key)
    if url:
        candidate = SourceCandidate(url, classify_official_url(url), 1)
    else:
        leads = await discover_official_sources(client, query or "", official_domains=(domain,), limit=5)
        print("official_leads:", len(leads))
        if not leads:
            return
        candidate = leads[0]
    fetched = await fetch_official_source(client, candidate, official_domains=(domain,), publisher=publisher)
    extracted = extract_program(fetched)
    print("source_domain:", urlsplit(extracted.source.url).hostname)
    if expected_name:
        names = [claim.value for claim in extracted.claims if claim.field == "program.name"]
        matches = any(isinstance(name, str) and _name_matches(name, expected_name) for name in names)
        print("expected_program_name_match:", matches)
        if not matches:
            raise SystemExit("Fetched page does not establish the expected program name")
    print("raw_text_characters:", len(extracted.raw_text))
    print("claims:", len(extracted.claims))
    print("claim_fields:", ", ".join(sorted({claim.field for claim in extracted.claims})) or "none")
    print("needs_review:", sum(claim.value is None or claim.status == "needs_review" for claim in extracted.claims))
    print("not_observed_fields:", ", ".join(extracted.not_observed_fields) or "none")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True, help="Trusted official institution domain")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--query", help="Program search query, without student personal data")
    target.add_argument("--url", help="Known official program URL")
    parser.add_argument("--publisher", required=True, help="Institution name for source metadata")
    parser.add_argument("--expected-name", help="Reject a page whose extracted heading names a different program")
    args = parser.parse_args()
    key = _local_key()
    if not key:
        raise SystemExit("Missing TAVILY_API_KEY in the plugin repo .env or process environment")
    asyncio.run(_run(args.domain, args.query, args.url, args.publisher, args.expected_name, key))


if __name__ == "__main__":
    main()
