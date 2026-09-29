"""Persist public research with raw evidence in the plugin-owned database."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from .dedupe import program_id as canonical_program_id
from .extraction import ExtractionResult, extract_program
from .schemas import Cost, Institution, ProgramDetails, Requirement, Source, Verification
from .sources import FetchedSource
from .verification import _field_and_value, verify_extractions


def _json(value: object) -> str:
    return json.dumps(asdict(value) if is_dataclass(value) else value, sort_keys=True)


def save_public_research(
    conn,
    institution: Institution,
    program: ProgramDetails,
    results: Sequence[ExtractionResult],
    *,
    program_code: str | None = None,
    verified_at: datetime | None = None,
) -> tuple[str, Verification]:
    """Atomically save one program's public facts, snapshots, and verification."""
    if not results:
        raise ValueError("at least one fetched source is required")
    if len({result.source.source_id for result in results}) != len(results):
        raise ValueError("provide only one current snapshot per source")
    checked_at = verified_at or datetime.now(timezone.utc)
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise ValueError("verified_at must include a timezone")
    identifier = canonical_program_id(institution, program, program_code=program_code)
    with conn.transaction():
        cached = {page.source.source_id: extract_program(page) for page in load_latest_sources(conn, identifier)}
        for result in results:
            previous = cached.get(result.source.source_id)
            if previous and previous.source.url != result.source.url:
                raise ValueError("one source ID cannot identify different URLs")
            if previous and datetime.fromisoformat(result.source.fetched_at.replace("Z", "+00:00")) < datetime.fromisoformat(previous.source.fetched_at.replace("Z", "+00:00")):
                raise ValueError("cannot replace a newer source snapshot with an older one")
            cached[result.source.source_id] = result
        verification = verify_extractions(tuple(cached.values()), now=checked_at)
        field_status = {item.field: item.status for item in verification.fields}
        conn.execute(
            "insert into program_intelligence.program_institutions "
            "(institution_id, name, country, city, official_url) values (%s, %s, %s, %s, %s) "
            "on conflict (institution_id) do update set name=excluded.name, country=excluded.country, "
            "city=excluded.city, official_url=excluded.official_url",
            (institution.institution_id, institution.name, institution.country, institution.city, institution.official_url),
        )
        conn.execute(
            "insert into program_intelligence.program_records "
            "(program_id, institution_id, name, official_url, award, level, fields, mode, campus, "
            "duration_value, duration_unit, credits_value, credits_system) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "on conflict (program_id) do update set institution_id=excluded.institution_id, "
            "name=excluded.name, official_url=excluded.official_url, "
            "award=excluded.award, level=excluded.level, fields=excluded.fields, mode=excluded.mode, "
            "campus=excluded.campus, duration_value=excluded.duration_value, duration_unit=excluded.duration_unit, "
            "credits_value=excluded.credits_value, credits_system=excluded.credits_system, updated_at=now()",
            (
                identifier, institution.institution_id, program.name, program.official_url, program.award,
                program.level, list(program.field), program.mode, program.campus,
                program.duration.value if program.duration else None,
                program.duration.unit if program.duration else None,
                program.credits.value if program.credits else None,
                program.credits.system if program.credits else None,
            ),
        )
        for result in results:
            source = result.source
            conn.execute(
                "insert into program_intelligence.program_sources as current_source "
                "(source_id, url, title, publisher, source_type, fetched_at, status) "
                "values (%s, %s, %s, %s, %s, %s, %s) "
                "on conflict (source_id) do update set title=excluded.title, publisher=excluded.publisher, "
                "source_type=excluded.source_type, fetched_at=excluded.fetched_at, status=excluded.status "
                "where excluded.fetched_at >= current_source.fetched_at",
                (source.source_id, source.url, source.title, source.publisher, source.source_type, source.fetched_at, source.status),
            )
            conn.execute(
                "insert into program_intelligence.program_record_sources (program_id, source_id) "
                "values (%s, %s) on conflict do nothing",
                (identifier, source.source_id),
            )
            conn.execute(
                "delete from program_intelligence.program_requirements where program_id=%s and source_id=%s",
                (identifier, source.source_id),
            )
            conn.execute(
                "delete from program_intelligence.program_costs where program_id=%s and source_id=%s",
                (identifier, source.source_id),
            )
            content_hash = hashlib.sha256(result.raw_text.encode("utf-8")).hexdigest()
            snapshot_id = conn.execute(
                "insert into program_intelligence.program_research_snapshots "
                "(program_id, source_id, fetched_at, raw_text, content_sha256) "
                "values (%s, %s, %s, %s, %s) "
                "on conflict (program_id, source_id, fetched_at, content_sha256) "
                "do update set raw_text=excluded.raw_text returning snapshot_id",
                (identifier, source.source_id, source.fetched_at, result.raw_text, content_hash),
            ).fetchone()[0]
            for claim in result.claims:
                value_json = _json(claim.value) if claim.value is not None else None
                claim_key = hashlib.sha256(
                    f"{claim.field}\0{claim.line_number}\0{claim.raw_text}\0{value_json}".encode("utf-8")
                ).hexdigest()
                conn.execute(
                    "insert into program_intelligence.program_claims "
                    "(snapshot_id, claim_key, field, value_json, raw_text, line_number, status) "
                    "values (%s, %s, %s, %s::jsonb, %s, %s, %s) on conflict do nothing",
                    (snapshot_id, claim_key, claim.field, value_json, claim.raw_text, claim.line_number, claim.status.value),
                )
                verification_field, _ = _field_and_value(claim)
                status = field_status.get(verification_field, claim.status).value
                if isinstance(claim.value, Requirement):
                    requirement = claim.value
                    conn.execute(
                        "insert into program_intelligence.program_requirements "
                        "(program_id, requirement_id, type, raw_text, required, verification_field, "
                        "verification_status, source_id, applies_to, normalized) "
                        "values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb) "
                        "on conflict (program_id, requirement_id) do update set "
                        "verification_field=excluded.verification_field, verification_status=excluded.verification_status, "
                        "applies_to=excluded.applies_to, normalized=excluded.normalized",
                        (
                            identifier, requirement.requirement_id, requirement.type.value, requirement.raw_text,
                            requirement.required, verification_field, status, requirement.source_id,
                            _json(requirement.applies_to), _json(requirement.normalized),
                        ),
                    )
                elif isinstance(claim.value, Cost):
                    cost = claim.value
                    cost_key = hashlib.sha256(
                        f"{identifier}\0{cost.source_id}\0{_json(cost)}".encode("utf-8")
                    ).hexdigest()
                    conn.execute(
                        "insert into program_intelligence.program_costs "
                        "(cost_key, program_id, source_id, type, amount, currency, period, applicant_scope, "
                        "academic_year, verification_field, verification_status) "
                        "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                        "on conflict (cost_key) do update set verification_status=excluded.verification_status",
                        (
                            cost_key, identifier, cost.source_id, cost.type, Decimal(str(cost.amount)),
                            cost.currency, cost.period, cost.applicant_scope, cost.academic_year,
                            verification_field, status,
                        ),
                    )
        for field in verification.fields:
            if field.field.startswith("requirements."):
                conn.execute(
                    "update program_intelligence.program_requirements set verification_status=%s "
                    "where program_id=%s and verification_field=%s",
                    (field.status.value, identifier, field.field),
                )
            elif field.field.startswith("costs."):
                conn.execute(
                    "update program_intelligence.program_costs set verification_status=%s "
                    "where program_id=%s and verification_field=%s",
                    (field.status.value, identifier, field.field),
                )
        verification_id = conn.execute(
            "insert into program_intelligence.program_verification_runs "
            "(program_id, verified_at, overall_status) values (%s, %s, %s) returning verification_id",
            (identifier, checked_at, verification.status.value),
        ).fetchone()[0]
        for field in verification.fields:
            conn.execute(
                "insert into program_intelligence.program_verified_fields "
                "(verification_id, field, status, source_ids) values (%s, %s, %s, %s)",
                (verification_id, field.field, field.status.value, list(field.source_ids)),
            )
    return identifier, verification


def load_latest_sources(conn, program_id: str) -> tuple[FetchedSource, ...]:
    """Return the newest raw page snapshot per source for refresh decisions."""
    rows = conn.execute(
        "select distinct on (snap.source_id) snap.source_id, src.url, src.title, src.publisher, "
        "src.source_type, snap.fetched_at, src.status, snap.raw_text "
        "from program_intelligence.program_research_snapshots snap "
        "join program_intelligence.program_sources src on src.source_id=snap.source_id "
        "where snap.program_id=%s "
        "order by snap.source_id, snap.fetched_at desc, snap.snapshot_id desc",
        (program_id,),
    )
    return tuple(
        FetchedSource(Source(source_id, url, title, publisher, source_type, fetched_at.isoformat(), status), raw_text)
        for source_id, url, title, publisher, source_type, fetched_at, status, raw_text in rows
    )
