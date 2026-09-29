"""Run V1 program research and matching without the PAI host."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
import re
from typing import Any

from .cache import load_latest_sources, save_public_research
from .comparison import compare_programs
from .eligibility import evaluate_eligibility
from .extraction import ExtractionResult, extract_program
from .schemas import (
    ApplicationWindow, Cost, Credits, Duration, Institution, Offering, ProgramDetails,
    ProgramRecord, Requirement, VerificationStatus,
)
from .sources import (
    ResearchClient, SourceCandidate, SourceLayerError, classify_official_url,
    discover_official_sources, fetch_official_source,
)
from .verification import _field_and_value, verify_extractions


def _expected_name(actual: str, expected: str) -> bool:
    actual_words = " ".join(re.findall(r"[a-z0-9]+", actual.casefold()))
    expected_words = " ".join(re.findall(r"[a-z0-9]+", expected.casefold()))
    return bool(expected_words) and actual_words == expected_words


def _record(institution: Institution, official_url: str, results: Sequence[ExtractionResult], verification) -> ProgramRecord:
    sources = tuple(result.source for result in results)
    evidence = {item.field: item for item in verification.fields}
    claims = [claim for result in results for claim in result.claims]

    def claim_value(field: str, kind: type):
        status = evidence.get(field)
        if status is None or status.status in {VerificationStatus.CONFLICTING, VerificationStatus.NEEDS_REVIEW, VerificationStatus.STALE}:
            return None
        return next((claim.value for claim in claims if claim.field == field and isinstance(claim.value, kind)), None)

    name = claim_value("program.name", str)
    if not name:
        raise ValueError("Official pages did not establish a program name")
    requirements: dict[tuple[str, str], Requirement] = {}
    costs: dict[tuple[str, object], Cost] = {}
    deadlines: dict[str, Offering] = {}
    for claim in claims:
        field, value = _field_and_value(claim)
        status = evidence.get(field)
        if isinstance(claim.value, Requirement):
            rule = claim.value
            requirements.setdefault((field, json.dumps(value, sort_keys=True)), replace(rule, verification_status=status.status if status else VerificationStatus.UNVERIFIED))
        elif isinstance(claim.value, Cost):
            cost = claim.value
            costs.setdefault((field, value), replace(cost, verification_status=status.status if status else VerificationStatus.UNVERIFIED))
        elif claim.field == "offerings.application_window.closes" and isinstance(claim.value, str):
            deadlines[claim.value] = Offering(
                intake_id=f"unspecified-{claim.value}", application_window=ApplicationWindow(closes=claim.value),
                deadline_type="unknown", status="intake_unknown", source_id=claim.source_id,
            )
    from .dedupe import program_id

    details = ProgramDetails(
        name, official_url, award=claim_value("program.award", str), level=claim_value("program.level", str),
        duration=claim_value("program.duration", Duration), credits=claim_value("program.credits", Credits),
    )
    return ProgramRecord(
        program_id(institution, details), institution, details, sources, verification,
        offerings=tuple(deadlines.values()), requirements=tuple(requirements.values()), costs=tuple(costs.values()),
    )


async def run_standalone(
    client: ResearchClient,
    targets: Sequence[Mapping[str, Any]],
    context: Mapping[str, object],
    *,
    conn=None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Research named programs; only public pages reach the provider/cache."""
    if not isinstance(context, Mapping) or not isinstance(targets, Sequence) or not targets:
        raise ValueError("context must be an object and programs must be a non-empty list")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must include a timezone")
    records = []
    matches = {}
    searches = []
    errors = []
    for index, target in enumerate(targets):
        try:
            if not isinstance(target, Mapping):
                raise ValueError("program target must be an object")
            institution = Institution(**target["institution"])
            domains = target["official_domains"]
            expected = target["expected_name"]
            urls = list(dict.fromkeys(([target["official_url"]] if target.get("official_url") else []) + target.get("source_urls", [])))
            query = target.get("query")
            leads = []
            search_error = None
            if query:
                try:
                    leads = await discover_official_sources(client, query, official_domains=domains, limit=5)
                except SourceLayerError as exc:
                    search_error = exc.code.value
            urls.extend(candidate.url for candidate in leads if candidate.url not in urls)
            searches.append({"target": expected, "official_leads": [candidate.url for candidate in leads], "search_error": search_error})
            if not urls:
                raise ValueError(search_error or "No official URL or search leads found")
            extracted = []
            rejected = []
            for url in urls:
                try:
                    fetched = await fetch_official_source(
                        client, SourceCandidate(url, classify_official_url(url), 1),
                        official_domains=domains, publisher=institution.name,
                    )
                    page = extract_program(fetched)
                    names = [claim.value for claim in page.claims if claim.field == "program.name"]
                    if not any(isinstance(name, str) and _expected_name(name, expected) for name in names):
                        rejected.append({"url": url, "reason": "program identity not established"})
                        continue
                    extracted.append(page)
                except SourceLayerError as exc:
                    rejected.append({"url": url, "reason": exc.code.value})
            if not extracted:
                raise ValueError("No fetched official page established the expected program identity")
            official_url = target.get("official_url") or extracted[0].source.url
            if official_url not in {page.source.url for page in extracted}:
                official_url = extracted[0].source.url
            if conn is not None:
                preliminary = _record(institution, official_url, extracted, verify_extractions(extracted, now=current))
                identifier, verification = save_public_research(conn, institution, preliminary.program, extracted, verified_at=current)
                extracted = [extract_program(page) for page in load_latest_sources(conn, identifier)]
            else:
                verification = verify_extractions(extracted, now=current)
            record = _record(institution, official_url, extracted, verification)
            if record.program_id in matches:
                raise ValueError("Duplicate program target")
            match = evaluate_eligibility(record.program_id, record.requirements, context)
            records.append(record)
            matches[record.program_id] = match
            searches[-1]["validated_program_id"] = record.program_id
            searches[-1]["rejected_sources"] = rejected
        except (KeyError, TypeError, ValueError, SourceLayerError) as exc:
            errors.append({"target_index": index, "reason": str(exc)})
    comparison = compare_programs(records, matches, now=current) if len(records) >= 2 else None
    return {
        "search": searches,
        "research": [asdict(record) for record in records],
        "eligibility": [asdict(matches[record.program_id]) for record in records],
        "comparison": asdict(comparison) if comparison else None,
        "errors": errors,
    }
