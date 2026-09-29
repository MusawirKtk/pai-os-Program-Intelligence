"""Cross-check source-linked claims without treating a single page as proof."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Mapping, Sequence

from .extraction import ExtractedClaim, ExtractionResult
from .freshness import DEFAULT_MAX_AGE_DAYS, is_stale
from .schemas import Cost, Credits, Duration, FieldEvidence, Requirement, RequirementType, Verification, VerificationStatus


def _requirement_key(value: Requirement) -> tuple[str, object]:
    normalized = json.dumps(value.normalized, sort_keys=True)
    scope = value.applies_to.applicant_type or "all"
    if value.type == RequirementType.LANGUAGE_TEST and {"test", "minimum_overall"} <= value.normalized.keys():
        return f"requirements.language_test:{value.normalized['test']}:{scope}", (
            value.normalized["minimum_overall"], value.required
        )
    if value.type == RequirementType.MINIMUM_GRADE and {"minimum", "scale"} <= value.normalized.keys():
        return f"requirements.minimum_grade:{value.normalized['scale']}:{scope}", (
            value.normalized["minimum"], value.required
        )
    # Other requirements are additive; exact wording may corroborate, but
    # different subjects or pathways must not be called contradictions.
    raw = " ".join(value.raw_text.casefold().split())
    digest = hashlib.sha256(f"{value.type}:{raw}:{normalized}:{scope}".encode("utf-8")).hexdigest()[:12]
    return f"requirements.{value.type}:{digest}", value.required


def _field_and_value(claim: ExtractedClaim) -> tuple[str, object | None]:
    value = claim.value
    if value is None:
        return claim.field, None
    if isinstance(value, Requirement):
        return _requirement_key(value)
    if isinstance(value, Cost):
        scope = value.applicant_scope or "all"
        year = value.academic_year or "unspecified"
        field = f"{claim.field}:{value.currency}:{value.period}:{scope}:{year}"
        return field, value.amount
    if isinstance(value, Duration):
        return claim.field, (value.value, value.unit)
    if isinstance(value, Credits):
        return claim.field, (value.value, value.system)
    if isinstance(value, str):
        return claim.field, " ".join(value.casefold().split())
    return claim.field, value


def verify_extractions(
    results: Sequence[ExtractionResult],
    *,
    now: datetime | None = None,
    max_age_days: Mapping[str, int] = DEFAULT_MAX_AGE_DAYS,
) -> Verification:
    """Verify claims for one resolved program from distinct, current official pages."""
    current = now or datetime.now(timezone.utc)
    latest: dict[str, ExtractionResult] = {}
    for result in results:
        previous = latest.get(result.source.source_id)
        if previous and previous.source.url != result.source.url:
            raise ValueError("one source ID cannot identify different URLs")
        fetched_at = datetime.fromisoformat(result.source.fetched_at.replace("Z", "+00:00"))
        previous_at = datetime.fromisoformat(previous.source.fetched_at.replace("Z", "+00:00")) if previous else None
        if previous_at is None or fetched_at > previous_at:
            latest[result.source.source_id] = result

    groups: dict[str, list[tuple[ExtractedClaim, object | None, ExtractionResult]]] = {}
    observed: set[str] = set()
    missing = set.intersection(*(set(result.not_observed_fields) for result in latest.values())) if latest else set()
    for result in latest.values():
        for claim in result.claims:
            observed.add(claim.field)
            field, value = _field_and_value(claim)
            groups.setdefault(field, []).append((claim, value, result))

    fields: list[FieldEvidence] = []
    for field, entries in sorted(groups.items()):
        usable = [
            (claim, value, result)
            for claim, value, result in entries
            if value is not None
            and claim.status != VerificationStatus.NEEDS_REVIEW
            and result.source.source_type.startswith("official_")
            and result.source.status == "accessible"
            and not is_stale(result.source, field, now=current, max_age_days=max_age_days)
        ]
        by_source: dict[str, set[object]] = {}
        distinct_pages: set[str] = set()
        for claim, value, result in usable:
            by_source.setdefault(claim.source_id, set()).add(value)
            distinct_pages.add(hashlib.sha256(result.raw_text.encode("utf-8")).hexdigest())
        if any(len(values) > 1 for values in by_source.values()):
            status = VerificationStatus.NEEDS_REVIEW
        elif len({value for values in by_source.values() for value in values}) > 1:
            status = VerificationStatus.CONFLICTING
        elif len(by_source) >= 2 and len(distinct_pages) >= 2:
            status = VerificationStatus.VERIFIED
        elif by_source:
            status = VerificationStatus.UNVERIFIED
        elif any(value is not None and is_stale(result.source, field, now=current, max_age_days=max_age_days) for _, value, result in entries):
            status = VerificationStatus.STALE
        else:
            status = VerificationStatus.NEEDS_REVIEW
        cited = usable if status in {
            VerificationStatus.VERIFIED,
            VerificationStatus.CONFLICTING,
            VerificationStatus.UNVERIFIED,
        } else entries
        source_ids = tuple(sorted({claim.source_id for claim, _, _ in cited}))
        fields.append(FieldEvidence(field, status, source_ids))

    for field in sorted(missing - observed):
        fields.append(FieldEvidence(field, VerificationStatus.NOT_FOUND))
    statuses = {field.status for field in fields}
    overall = next(
        (status for status in (VerificationStatus.CONFLICTING, VerificationStatus.NEEDS_REVIEW, VerificationStatus.STALE)
         if status in statuses),
        VerificationStatus.VERIFIED if statuses == {VerificationStatus.VERIFIED} else VerificationStatus.UNVERIFIED,
    )
    return Verification(overall, tuple(fields))
