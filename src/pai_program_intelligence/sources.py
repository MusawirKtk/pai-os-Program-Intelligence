"""Official-source discovery and fetching over an injected research client.

Search results are leads. Only a fetched page on a trusted official domain can
become a Source; the client must enforce the approved network egress policy.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from dataclasses import dataclass
from typing import Protocol, Sequence
from urllib.parse import urlsplit, urlunsplit

from .schemas import ErrorCode, Source


@dataclass(frozen=True, slots=True)
class SearchHit:
    url: str
    title: str = ""
    snippet: str = ""


@dataclass(frozen=True, slots=True)
class FetchedPage:
    reported_url: str
    title: str
    text: str
    fetched_at: str
    status_code: int = 200


class ResearchClient(Protocol):
    async def search(
        self, query: str, *, limit: int = 10, domains: Sequence[str] = ()
    ) -> Sequence[SearchHit]: ...

    async def fetch(self, url: str) -> FetchedPage: ...


@dataclass(frozen=True, slots=True)
class SourceCandidate:
    url: str
    source_type: str
    priority: int


@dataclass(frozen=True, slots=True)
class FetchedSource:
    source: Source
    raw_text: str


class SourceLayerError(Exception):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


_PRIORITY = {
    "official_program_page": 1,
    "official_admissions_page": 2,
    "official_faculty_page": 3,
    "official_catalog": 4,
    "official_tuition_page": 5,
    "official_funding_page": 6,
    "official_accreditation_page": 7,
    "official_other": 8,
}


def _domain(value: str) -> str:
    if not isinstance(value, str) or not value or any(char.isspace() for char in value):
        raise ValueError("official domains must be public DNS names")
    name = value.rstrip(".").lower()
    if name.startswith("www."):
        name = name[4:]
    try:
        name = name.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("official domains must be public DNS names") from exc
    try:
        ipaddress.ip_address(name)
    except ValueError:
        pass
    else:
        raise ValueError("IP addresses cannot be official domains")
    labels = name.split(".")
    if len(labels) < 2 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) for part in labels):
        raise ValueError("official domains must be public DNS names")
    if name.endswith((".local", ".localhost", ".internal", ".test", ".invalid")):
        raise ValueError("local domains cannot be official domains")
    return name


def _official_domains(domains: Sequence[str]) -> tuple[str, ...]:
    if not domains:
        raise ValueError("at least one trusted official domain is required")
    return tuple(_domain(domain) for domain in domains)


def _canonical_url(url: str) -> str | None:
    if not isinstance(url, str) or not url or any(char.isspace() for char in url):
        return None
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        expected_port = 443 if parsed.scheme == "https" else 80
        if parsed.port not in (None, expected_port):
            return None
        _domain(parsed.hostname)
    except ValueError:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def _is_official(url: str, domains: tuple[str, ...]) -> bool:
    canonical = _canonical_url(url)
    if canonical is None:
        return False
    host = _domain(urlsplit(canonical).hostname or "")
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def classify_official_url(url: str) -> str:
    """Classify a candidate by URL path, never by an unverified search snippet."""
    path_terms = set(re.findall(r"[a-z]+", urlsplit(url).path.lower()))
    if path_terms & {"program", "programs", "programme", "programmes", "course", "courses", "degree", "degrees"}:
        return "official_program_page"
    if path_terms & {"admission", "admissions", "apply", "application", "applications"}:
        return "official_admissions_page"
    if path_terms & {"faculty", "faculties", "school", "schools", "department", "departments"}:
        return "official_faculty_page"
    if path_terms & {"catalog", "catalogue", "handbook"}:
        return "official_catalog"
    if path_terms & {"tuition", "fees", "fee", "costs"}:
        return "official_tuition_page"
    if path_terms & {"scholarship", "scholarships", "funding", "financialaid"}:
        return "official_funding_page"
    if path_terms & {"accreditation", "accredited", "recognition"}:
        return "official_accreditation_page"
    return "official_other"


async def discover_official_sources(
    client: ResearchClient,
    query: str,
    *,
    official_domains: Sequence[str],
    limit: int = 10,
) -> list[SourceCandidate]:
    """Find official URL leads; this function does not verify page facts."""
    domains = _official_domains(official_domains)
    if not isinstance(query, str) or not query.strip() or type(limit) is not int or not 1 <= limit <= 20:
        raise SourceLayerError(ErrorCode.INVALID_REQUEST, "A query and a limit from 1 to 20 are required")
    try:
        hits = await client.search(query, limit=limit, domains=domains)
    except SourceLayerError:
        raise
    except Exception:
        raise SourceLayerError(ErrorCode.PROVIDER_ERROR, "Source search failed") from None
    candidates: dict[str, SourceCandidate] = {}
    for hit in hits[:limit]:
        url = _canonical_url(hit.url)
        if url is None or not _is_official(url, domains):
            continue
        source_type = classify_official_url(url)
        candidates.setdefault(url, SourceCandidate(url, source_type, _PRIORITY[source_type]))
    return sorted(candidates.values(), key=lambda candidate: (candidate.priority, candidate.url))


async def fetch_official_source(
    client: ResearchClient,
    candidate: SourceCandidate,
    *,
    official_domains: Sequence[str],
    publisher: str,
) -> FetchedSource:
    """Fetch a lead and check its final URL before creating source evidence."""
    domains = _official_domains(official_domains)
    if not _is_official(candidate.url, domains):
        raise SourceLayerError(ErrorCode.UNSUPPORTED_SOURCE, "URL is outside trusted official domains")
    if not isinstance(publisher, str) or not publisher.strip():
        raise SourceLayerError(ErrorCode.INVALID_REQUEST, "A publisher is required")
    try:
        page = await client.fetch(candidate.url)
    except SourceLayerError:
        raise
    except Exception:
        raise SourceLayerError(ErrorCode.SOURCE_UNAVAILABLE, "Official page fetch failed") from None
    reported_url = _canonical_url(page.reported_url)
    if reported_url is None or not _is_official(reported_url, domains):
        raise SourceLayerError(ErrorCode.UNSUPPORTED_SOURCE, "Fetched page URL is outside trusted official domains")
    if page.status_code != 200 or not isinstance(page.text, str) or not page.text.strip():
        raise SourceLayerError(ErrorCode.SOURCE_UNAVAILABLE, "Official page has no readable content")
    source_type = classify_official_url(reported_url)
    try:
        source = Source(
            source_id="source-" + hashlib.sha256(reported_url.encode("utf-8")).hexdigest()[:16],
            url=reported_url,
            title=page.title.strip() or reported_url,
            publisher=publisher,
            source_type=source_type,
            fetched_at=page.fetched_at,
        )
    except (AttributeError, ValueError):
        raise SourceLayerError(ErrorCode.PROVIDER_ERROR, "Fetched page metadata is invalid") from None
    return FetchedSource(source, page.text)
