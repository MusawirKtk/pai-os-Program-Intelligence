"""Evidence-preserving comparison of researched programs, without ranking them."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Sequence

from .eligibility import EligibilityResult, MatchStatus
from .freshness import is_stale
from .schemas import ProgramRecord, RequirementType, VerificationStatus
from .verification import _requirement_key


DIMENSIONS = (
    "academic_match", "prerequisites", "language", "tuition", "duration",
    "location", "mode", "intake", "deadline", "curriculum_focus",
    "application_materials", "funding",
)


@dataclass(frozen=True, slots=True)
class ComparisonCell:
    value: object | None
    verification_status: VerificationStatus
    source_ids: tuple[str, ...] = ()
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ComparedProgram:
    program_id: str
    program_name: str
    institution_name: str
    official_url: str
    values: Mapping[str, ComparisonCell]


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    dimensions: tuple[str, ...]
    programs: tuple[ComparedProgram, ...]


def _evidence(record: ProgramRecord, field: str, now: datetime) -> ComparisonCell:
    evidence = next((item for item in record.verification.fields if item.field == field), None)
    if evidence is None:
        return ComparisonCell(None, VerificationStatus.NOT_FOUND)
    sources = {source.source_id: source for source in record.sources}
    status = evidence.status
    if status == VerificationStatus.VERIFIED and any(
        is_stale(sources[source_id], field, now=now) for source_id in evidence.source_ids
    ):
        status = VerificationStatus.STALE
    return ComparisonCell(None, status, evidence.source_ids)


def _fact(record: ProgramRecord, field: str, value: object | None, now: datetime) -> ComparisonCell:
    cell = _evidence(record, field, now)
    return ComparisonCell(value, cell.verification_status, cell.source_ids) if value is not None else ComparisonCell(None, VerificationStatus.NOT_FOUND)


def _matches(record: ProgramRecord, eligibility: EligibilityResult | None, kinds: set[RequirementType], now: datetime) -> ComparisonCell:
    rules = [rule for rule in record.requirements if rule.type in kinds]
    if not rules:
        return ComparisonCell(None, VerificationStatus.NOT_FOUND)
    matched = {item.requirement_id: item for item in eligibility.requirements} if eligibility else {}
    rows = []
    states = []
    sources = set()
    for rule in rules:
        evidence = _evidence(record, _requirement_key(rule)[0], now)
        status = evidence.verification_status if evidence.verification_status != VerificationStatus.NOT_FOUND else VerificationStatus.UNVERIFIED
        if status == VerificationStatus.VERIFIED and is_stale(next(source for source in record.sources if source.source_id == rule.source_id), "requirements", now=now):
            status = VerificationStatus.STALE
        match = matched.get(rule.requirement_id)
        row_sources = evidence.source_ids if status != VerificationStatus.CONFLICTING and evidence.source_ids else (rule.source_id,)
        rows.append({
            "requirement_id": rule.requirement_id,
            "text": rule.raw_text,
            "required": rule.required,
            "match": (match.status if status == VerificationStatus.VERIFIED else MatchStatus.NEEDS_REVIEW) if match else None,
            "verification_status": status,
            "source_ids": row_sources,
        })
        states.append(status)
        sources.update(evidence.source_ids or (rule.source_id,))
    overall = (
        VerificationStatus.CONFLICTING if VerificationStatus.CONFLICTING in states else
        VerificationStatus.STALE if VerificationStatus.STALE in states else
        VerificationStatus.VERIFIED if all(state == VerificationStatus.VERIFIED for state in states) else
        VerificationStatus.NEEDS_REVIEW
    )
    return ComparisonCell(rows, overall, tuple(sorted(sources)))


def _costs(record: ProgramRecord, now: datetime) -> ComparisonCell:
    costs = [cost for cost in record.costs if cost.type == "tuition"]
    if not costs:
        return ComparisonCell(None, VerificationStatus.NOT_FOUND)
    rows = []
    statuses = []
    for cost in costs:
        field = f"costs.tuition:{cost.currency}:{cost.period}:{cost.applicant_scope or 'all'}:{cost.academic_year or 'unspecified'}"
        evidence = _evidence(record, field, now)
        status = evidence.verification_status if evidence.verification_status != VerificationStatus.NOT_FOUND else VerificationStatus.UNVERIFIED
        if status == VerificationStatus.VERIFIED and is_stale(next(source for source in record.sources if source.source_id == cost.source_id), field, now=now):
            status = VerificationStatus.STALE
        row_sources = evidence.source_ids if status != VerificationStatus.CONFLICTING and evidence.source_ids else (cost.source_id,)
        rows.append({
            "amount": cost.amount, "currency": cost.currency, "period": cost.period,
            "applicant_scope": cost.applicant_scope, "academic_year": cost.academic_year,
            "verification_status": status, "source_ids": row_sources,
        })
        statuses.append(status)
    overall = (
        VerificationStatus.CONFLICTING if VerificationStatus.CONFLICTING in statuses else
        VerificationStatus.STALE if VerificationStatus.STALE in statuses else
        VerificationStatus.VERIFIED if all(status == VerificationStatus.VERIFIED for status in statuses) else
        VerificationStatus.NEEDS_REVIEW
    )
    return ComparisonCell(rows, overall, tuple(sorted({source_id for row in rows for source_id in row["source_ids"]})))


def compare_programs(
    programs: Sequence[ProgramRecord],
    eligibility: Mapping[str, EligibilityResult] | None = None,
    *,
    now: datetime | None = None,
) -> ComparisonResult:
    """Return comparable, cited cells; never score or recommend a program."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must include a timezone")
    if len(programs) < 2 or len({record.program_id for record in programs}) != len(programs):
        raise ValueError("comparison requires at least two distinct programs")
    matches = eligibility or {}
    program_ids = {record.program_id for record in programs}
    if any(program_id not in program_ids for program_id in matches):
        raise ValueError("eligibility result does not belong to a compared program")
    rows = []
    for record in programs:
        result = matches.get(record.program_id)
        if result is not None and result.program_id != record.program_id:
            raise ValueError("eligibility result program_id mismatch")
        values = {
            "academic_match": _matches(record, result, {RequirementType.ACADEMIC_DEGREE, RequirementType.MINIMUM_GRADE}, current),
            "prerequisites": _matches(record, result, {RequirementType.COURSE_PREREQUISITE, RequirementType.SUBJECT_PREREQUISITE}, current),
            "language": _matches(record, result, {RequirementType.LANGUAGE_TEST, RequirementType.STANDARDIZED_TEST}, current),
            "tuition": _costs(record, current),
            "duration": _fact(record, "program.duration", record.program.duration, current),
            "location": ComparisonCell(
                {"country": record.institution.country, "city": record.institution.city},
                VerificationStatus.UNVERIFIED, note="Institution location is supplied metadata, not source-verified",
            ),
            "mode": _fact(record, "program.mode", record.program.mode, current),
            "intake": ComparisonCell(
                [{"intake_id": item.intake_id, "term": item.term, "academic_year": item.academic_year,
                  "start_date": item.start_date, "source_id": item.source_id} for item in record.offerings] or None,
                VerificationStatus.UNVERIFIED if record.offerings else VerificationStatus.NOT_FOUND,
                tuple(sorted({item.source_id for item in record.offerings if item.source_id})),
            ),
            "deadline": _fact(
                record, "offerings.application_window.closes",
                [{"intake_id": item.intake_id, "closes": item.application_window.closes,
                  "source_id": item.source_id} for item in record.offerings
                 if item.application_window and item.application_window.closes] or None,
                current,
            ),
            "curriculum_focus": _fact(record, "curriculum", record.curriculum or None, current),
            "application_materials": _matches(record, result, {RequirementType.PORTFOLIO, RequirementType.REFERENCE, RequirementType.STATEMENT, RequirementType.RESEARCH_PROPOSAL}, current),
            "funding": ComparisonCell(
                [{"title": link.title, "url": link.url, "source_id": link.source_id} for link in record.funding] or None,
                VerificationStatus.UNVERIFIED if record.funding else VerificationStatus.NOT_FOUND,
                tuple(sorted({link.source_id for link in record.funding})),
            ),
        }
        rows.append(ComparedProgram(record.program_id, record.program.name, record.institution.name, record.program.official_url, values))
    return ComparisonResult(DIMENSIONS, tuple(rows))
